# -*- coding: utf-8 -*-
"""
Textbook2Answer Pro GUI

Phase 1 已实现：
- 新建项目向导（不再手改 JSON）
- 质量档位（极速/均衡/高质量/自定义）
- 任务中心（全流程/局部运行）
- 失败题一键补跑

Phase 2 已实现：
- 章节页码可视化预览（基于 PDF 渲染缩略图）
- 题目与答案审阅/修订
- 导出报告与版本快照

启动：
    streamlit run gui/streamlit_app.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.app.workspace_manager import (  # noqa: E402
    append_run_record,
    collect_output_stats,
    create_output_snapshot,
    create_project,
    get_project,
    list_projects,
    list_run_records,
    parse_pages_expr,
    patch_project,
    write_run_report,
)
from src.config_schema import validate_api_config_file, validate_chapter_config_file  # noqa: E402
from src.constants import EXTRACTED_TASKS_FILE, FINAL_SOLUTION_FILE, SOLVE_FAILURES_FILE, SOLVED_ANSWERS_FILE  # noqa: E402
from src.latex_builder import run as run_latex  # noqa: E402
from src.logger import add_ui_handler, remove_ui_handlers  # noqa: E402
from src.pdf_processor import render_pdf_pages, sanitize_book_title  # noqa: E402
from src.pipeline import Pipeline, PipelineConfig  # noqa: E402
from src.reasoning_solver import run as run_solver  # noqa: E402
from src.gui_utils import (  # noqa: E402
    init_gui_state,
    render_language_settings,
    render_api_config_section,
    render_concurrency_settings,
    render_task_queue_section,
)


st.set_page_config(page_title="Textbook2Answer Pro", page_icon="📚", layout="wide")

# 初始化 GUI 状态（多语言、API 配置、任务队列）
init_gui_state()


def _safe_load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_api_config() -> tuple[dict, Path | None]:
    for p in [ROOT / "config" / "api_config.json", ROOT / "api_config.json"]:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8")), p
            except Exception:
                continue
    return {}, None


def _available_pdfs() -> list[str]:
    candidates = []
    for folder in [ROOT / "input", ROOT]:
        if folder.exists():
            candidates.extend(str(p) for p in folder.glob("*.pdf"))
    return sorted(set(candidates))


def _quality_defaults(profile: str, providers: list[str]) -> tuple[str, str, str | None, str | None]:
    fallback = providers[0] if providers else "gemini"
    gemini = "gemini" if "gemini" in providers else fallback
    deepseek = "deepseek" if "deepseek" in providers else gemini

    if profile == "极速":
        return gemini, gemini, None, None
    if profile == "均衡":
        return gemini, deepseek, None, None
    if profile == "高质量":
        return gemini, deepseek, None, None
    return gemini, deepseek, None, None


def _retry_failed(project: dict) -> None:
    output_base = Path(project["output_base"])
    fail_path = output_base / SOLVE_FAILURES_FILE
    solved_path = output_base / SOLVED_ANSWERS_FILE

    failed = _safe_load_json(fail_path, [])
    if not isinstance(failed, list) or not failed:
        raise ValueError("当前项目没有失败题可重跑")

    failed_ids = {str(x.get("question_id", "")) for x in failed if x.get("question_id")}
    if not failed_ids:
        raise ValueError("失败题列表中没有有效 question_id")

    solved = _safe_load_json(solved_path, [])
    if isinstance(solved, list):
        solved = [x for x in solved if str(x.get("question_id", "")) not in failed_ids]
        _save_json(solved_path, solved)

    run_solver(
        output_base=output_base,
        config_path=project["config_path"],
        provider=project.get("solve_provider", "gemini"),
        model=project.get("solve_model") or None,
        max_workers=st.session_state.get("concurrency", 1),
    )
    run_latex(output_base=output_base, config_path=project["config_path"])


def _run_action(project: dict, action: str, flow_box, log_box) -> tuple[bool, str, float, dict]:
    start = time.monotonic()
    st.session_state["live_logs"] = []

    remove_ui_handlers()

    def _on_log(level: str, msg: str) -> None:
        line = f"[{level}] {msg}"
        st.session_state["live_logs"].append(line)
        log_box.code("\n".join(st.session_state["live_logs"][-400:]))

    add_ui_handler(_on_log)

    def _run_stage(label: str, fn) -> None:
        with flow_box:
            with st.status(f"{label}...", expanded=False) as status:
                fn()
                status.update(label=f"{label} ✅", state="complete")

    try:
        cfg = PipelineConfig(
            config_path=project["config_path"],
            pdf_path=project.get("pdf_path") or None,
            extract_provider=project.get("extract_provider", "gemini"),
            solve_provider=project.get("solve_provider", "gemini"),
            extract_model=project.get("extract_model") or None,
            solve_model=project.get("solve_model") or None,
            max_workers=st.session_state.get("concurrency", 1),
        )
        pipeline = Pipeline(cfg)

        if action == "full":
            _run_stage("📄 PDF 切片", pipeline.run_pdf)
            _run_stage("🔍 VLM 提取", pipeline.run_extract)
            _run_stage("🧠 推理求解", pipeline.run_solve)
            _run_stage("📝 LaTeX 组装", pipeline.run_latex)
        elif action == "extract":
            _run_stage("🔍 VLM 提取", pipeline.run_extract)
        elif action == "solve":
            _run_stage("🧠 推理求解", pipeline.run_solve)
        elif action == "latex":
            _run_stage("📝 LaTeX 组装", pipeline.run_latex)
        elif action == "retry_failed":
            _run_stage("♻️ 失败题重跑", lambda: _retry_failed(project))
        else:
            raise ValueError(f"未知任务动作: {action}")

        elapsed = time.monotonic() - start
        return True, "执行完成", elapsed, {"log_lines": len(st.session_state["live_logs"])}
    except Exception as exc:
        elapsed = time.monotonic() - start
        return False, f"执行失败: {exc}", elapsed, {"error": str(exc)}
    finally:
        remove_ui_handlers()


def _render_pdf_preview(pdf_path: Path, pages: list[int], book_title: str) -> list[Path]:
    preview_dir = ROOT / ".t2a_workspace" / "previews" / sanitize_book_title(book_title)
    preview_dir.mkdir(parents=True, exist_ok=True)
    page_subset = pages[:8]
    rendered = render_pdf_pages(pdf_path, page_subset, preview_dir, dpi=90)
    return [p for _, p in rendered]


for k, v in {
    "active_project_id": "",
    "live_logs": [],
}.items():
    st.session_state.setdefault(k, v)

api_cfg, api_cfg_path = _load_api_config()
provider_options = [k for k in api_cfg.keys() if not k.startswith("_")] or ["gemini"]

projects = list_projects(ROOT)
if not st.session_state["active_project_id"] and projects:
    st.session_state["active_project_id"] = projects[0]["project_id"]
# 侧边栏：多语言、API 配置、并发、任务队列
is_zh = st.session_state.language == "zh"
with st.sidebar:
    st.markdown("## ⚙️ " + ("系统设置" if is_zh else "Settings"))
    render_language_settings()
    st.divider()
    render_api_config_section()
    st.divider()
    render_concurrency_settings()
    st.divider()
    render_task_queue_section()
st.title("📚 Textbook2Answer Pro" + (" 工作台" if is_zh else " Workspace"))
st.caption(
    "从手工配置工具升级为项目向导 + 任务中心 + 审阅交付"
    if is_zh else
    "Upgraded from manual config tool to project wizard + task center + review & delivery"
)

_tab_labels = (
    ["🧭 新建项目向导", "📁 项目中心", "🚀 任务中心", "🧪 审阅与修订", "📦 导出与报告"]
    if is_zh else
    ["🧭 New Project", "📁 Projects", "🚀 Tasks", "🧪 Review", "📦 Export"]
)
wizard_tab, center_tab, task_tab, review_tab, export_tab = st.tabs(_tab_labels)

with wizard_tab:
    st.subheader("Step 1 · 基本信息")

    default_title = "新教材项目"
    book_title = st.text_input("项目/书名", value=default_title)

    pdf_candidates = _available_pdfs()
    selected_pdf = st.selectbox("快速选择本地 PDF", ["(手动输入)"] + pdf_candidates, index=0)
    pdf_path = st.text_input(
        "PDF 路径",
        value=(selected_pdf if selected_pdf != "(手动输入)" else ""),
        placeholder="例如 D:/Books/量子力学.pdf",
    )

    st.subheader("Step 2 · 质量档位")
    quality_profile = st.radio(
        "运行档位",
        ["极速", "均衡", "高质量", "自定义"],
        horizontal=True,
        help="极速=快，均衡=默认推荐，高质量=更强调答案质量",
    )

    default_extract, default_solve, default_extract_model, default_solve_model = _quality_defaults(
        quality_profile, provider_options
    )

    if quality_profile == "自定义":
        c1, c2 = st.columns(2)
        with c1:
            extract_provider = st.selectbox("提取节点", provider_options, index=provider_options.index(default_extract) if default_extract in provider_options else 0)
            extract_model = st.text_input("提取模型（可选）", value="")
        with c2:
            solve_provider = st.selectbox("求解节点", provider_options, index=provider_options.index(default_solve) if default_solve in provider_options else 0)
            solve_model = st.text_input("求解模型（可选）", value="")
    else:
        extract_provider = default_extract
        solve_provider = default_solve
        extract_model = default_extract_model or ""
        solve_model = default_solve_model or ""
        st.info(f"当前档位策略：提取节点={extract_provider}，求解节点={solve_provider}")

    author_model = st.text_input(
        "作者展示字段（写入 LaTeX 标题）",
        value=(solve_model or solve_provider),
    )

    st.subheader("Step 3 · 章节与页码")
    chapter_count = int(st.number_input("章节数量", min_value=1, max_value=50, value=3, step=1))

    chapter_rows: list[dict] = []
    parse_error = False
    for i in range(chapter_count):
        col1, col2 = st.columns([2, 3])
        with col1:
            ch_name = st.text_input(f"章节 {i+1} 名称", key=f"wizard_ch_name_{i}")
        with col2:
            pages_expr = st.text_input(
                f"章节 {i+1} 页码（支持 15-18,20）",
                key=f"wizard_ch_pages_{i}",
                placeholder="例如 45-50, 52",
            )

        pages: list[int] = []
        if pages_expr.strip():
            try:
                pages = parse_pages_expr(pages_expr)
                st.caption(f"章节 {i+1} 解析页码：{pages[:8]}{' ...' if len(pages) > 8 else ''}")
            except Exception as exc:
                parse_error = True
                st.error(f"章节 {i+1} 页码格式错误: {exc}")

        chapter_rows.append({"chapter_name": ch_name.strip(), "pages": pages})

    st.subheader("Step 4 · 章节页码可视化预览")
    preview_chapters = [r for r in chapter_rows if r["chapter_name"] and r["pages"]]
    if preview_chapters:
        preview_idx = st.selectbox(
            "选择要预览的章节",
            options=list(range(len(preview_chapters))),
            format_func=lambda x: f"{preview_chapters[x]['chapter_name']}（{len(preview_chapters[x]['pages'])}页）",
        )
        if st.button("生成缩略图预览", key="btn_preview_pages"):
            pdf_obj = Path(pdf_path) if pdf_path else None
            if not pdf_obj or not pdf_obj.exists():
                st.warning("请先填写有效的 PDF 路径")
            else:
                try:
                    img_paths = _render_pdf_preview(pdf_obj, preview_chapters[preview_idx]["pages"], book_title)
                    st.success(f"已生成 {len(img_paths)} 张预览图")
                    st.image([str(p) for p in img_paths], caption=[p.name for p in img_paths], width=220)
                except Exception as exc:
                    st.error(f"预览生成失败: {exc}")
    else:
        st.caption("请先至少填写一个完整章节（名称+页码）后再预览")

    st.subheader("Step 5 · 创建项目")
    if st.button("✅ 保存项目并设为当前项目", type="primary"):
        valid_chapters = [r for r in chapter_rows if r["chapter_name"] and r["pages"]]
        if not book_title.strip():
            st.error("书名不能为空")
        elif parse_error:
            st.error("请先修复页码格式错误")
        elif not valid_chapters:
            st.error("至少需要一个有效章节")
        elif not pdf_path or not Path(pdf_path).exists():
            st.error("PDF 路径无效，请检查文件是否存在")
        else:
            project = create_project(
                root=ROOT,
                book_title=book_title.strip(),
                author_model=author_model.strip() or solve_provider,
                pdf_path=pdf_path,
                chapters=valid_chapters,
                extract_provider=extract_provider,
                solve_provider=solve_provider,
                extract_model=extract_model or None,
                solve_model=solve_model or None,
                quality_profile=quality_profile,
            )
            st.session_state["active_project_id"] = project["project_id"]
            st.success(f"项目创建成功：{project['book_title']}")
            st.rerun()

with center_tab:
    st.subheader("项目列表")
    projects = list_projects(ROOT)
    if not projects:
        st.info("暂无项目，请先在“新建项目向导”创建")
    else:
        labels = [f"{p['book_title']}（{p['project_id']}）" for p in projects]
        idx_default = 0
        for i, p in enumerate(projects):
            if p["project_id"] == st.session_state["active_project_id"]:
                idx_default = i
                break
        selected_label = st.selectbox("选择项目", labels, index=idx_default)
        selected_project = projects[labels.index(selected_label)]

        col_a, col_b = st.columns([1, 1])
        with col_a:
            if st.button("设为当前项目"):
                st.session_state["active_project_id"] = selected_project["project_id"]
                st.success("已切换当前项目")
                st.rerun()
        with col_b:
            if st.button("校验当前项目配置"):
                api_errors = validate_api_config_file(api_cfg_path) if api_cfg_path else ["未找到 api_config.json"]
                chapter_errors = validate_chapter_config_file(selected_project["config_path"])
                if api_errors:
                    for e in api_errors:
                        st.error(f"API 配置: {e}")
                else:
                    st.success("API 配置校验通过")
                if chapter_errors:
                    for e in chapter_errors:
                        st.error(f"章节配置: {e}")
                else:
                    st.success("章节配置校验通过")

        stats = collect_output_stats(Path(selected_project["output_base"]))
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("图片", stats["images"])
        m2.metric("题目", stats["tasks"])
        m3.metric("答案", stats["answers"])
        m4.metric("失败", stats["failed"])
        m5.metric("LaTeX", "✅" if stats["has_tex"] else "—")

        with st.expander("项目配置预览", expanded=False):
            cfg = _safe_load_json(Path(selected_project["config_path"]), {})
            st.json(cfg)

        st.caption(
            f"当前项目输出目录：{selected_project['output_base']}  |  最近运行：{selected_project.get('last_run_at') or '尚未运行'}"
        )

with task_tab:
    st.subheader("任务中心")
    active_id = st.session_state.get("active_project_id", "")
    project = get_project(ROOT, active_id) if active_id else None
    if not project:
        st.info("请先在项目中心选择一个项目")
    else:
        st.caption(f"当前项目：{project['book_title']}（{project['project_id']}）")

        action_label = st.radio(
            "执行动作",
            [
                "全流程运行",
                "仅执行提取",
                "仅执行求解",
                "仅组装 LaTeX",
                "失败题一键重跑",
            ],
            horizontal=True,
        )
        action_map = {
            "全流程运行": "full",
            "仅执行提取": "extract",
            "仅执行求解": "solve",
            "仅组装 LaTeX": "latex",
            "失败题一键重跑": "retry_failed",
        }

        col1, col2 = st.columns([2, 3])
        with col1:
            flow_box = st.container()
        with col2:
            st.markdown("##### 📋 实时日志")
            log_box = st.empty()
            if st.session_state.get("live_logs"):
                log_box.code("\n".join(st.session_state["live_logs"][-400:]))

        if st.button("🚀 开始执行", type="primary"):
            action = action_map[action_label]
            patch_project(ROOT, project["project_id"], status="running", updated_at=time.strftime("%Y-%m-%d %H:%M:%S"))
            ok, msg, elapsed, details = _run_action(project, action, flow_box, log_box)
            stats = collect_output_stats(Path(project["output_base"]))

            patch_project(
                ROOT,
                project["project_id"],
                status=("completed" if ok else "failed"),
                last_run_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                updated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            )
            append_run_record(
                ROOT,
                project_id=project["project_id"],
                action=action,
                status=("completed" if ok else "failed"),
                elapsed_seconds=elapsed,
                message=msg,
                details={**details, **stats},
            )

            if ok:
                st.success(f"{msg}（耗时 {elapsed:.1f}s）")
                st.balloons()
            else:
                st.error(f"{msg}（耗时 {elapsed:.1f}s）")

        st.markdown("##### 🕒 最近任务记录")
        runs = list_run_records(ROOT, project["project_id"])[:12]
        if runs:
            st.dataframe(runs, use_container_width=True, hide_index=True)
        else:
            st.info("暂无任务记录")

with review_tab:
    st.subheader("审阅与修订")
    active_id = st.session_state.get("active_project_id", "")
    project = get_project(ROOT, active_id) if active_id else None
    if not project:
        st.info("请先在项目中心选择一个项目")
    else:
        output_base = Path(project["output_base"])
        extracted_path = output_base / EXTRACTED_TASKS_FILE
        solved_path = output_base / SOLVED_ANSWERS_FILE
        fail_path = output_base / SOLVE_FAILURES_FILE

        task_list = _safe_load_json(extracted_path, [])
        answer_list = _safe_load_json(solved_path, [])
        fail_list = _safe_load_json(fail_path, [])

        t1, t2, t3 = st.tabs(["📋 题目修订", "📝 答案修订", "⚠️ 失败题管理"])

        with t1:
            if not isinstance(task_list, list) or not task_list:
                st.info("暂无 extracted_tasks.json")
            else:
                qids = [str(t.get("question_id", "")) for t in task_list]
                selected_qid = st.selectbox("选择题号", qids)
                idx = next(i for i, t in enumerate(task_list) if str(t.get("question_id", "")) == selected_qid)
                task = task_list[idx]

                with st.form("task_edit_form"):
                    new_ch = st.text_input("章节", value=str(task.get("chapter_name", "")))
                    new_content = st.text_area("题目内容", value=str(task.get("content", "")), height=220)
                    new_has_image = st.checkbox("是否依赖图片", value=bool(task.get("has_image", False)))
                    new_page = int(st.number_input("页码", min_value=1, value=int(task.get("page_num", 1))))
                    submitted = st.form_submit_button("保存题目修改")

                if submitted:
                    task_list[idx].update(
                        {
                            "chapter_name": new_ch,
                            "content": new_content,
                            "has_image": new_has_image,
                            "page_num": new_page,
                        }
                    )
                    _save_json(extracted_path, task_list)
                    st.success("题目修改已保存")

                if st.button("删除该题已解答结果（用于强制重跑）"):
                    if isinstance(answer_list, list):
                        answer_list = [a for a in answer_list if str(a.get("question_id", "")) != selected_qid]
                        _save_json(solved_path, answer_list)
                        st.success("已删除该题答案，下次执行“仅求解”会自动重跑")

        with t2:
            if not isinstance(answer_list, list) or not answer_list:
                st.info("暂无 solved_answers.json")
            else:
                aqids = [str(a.get("question_id", "")) for a in answer_list]
                selected_qid = st.selectbox("选择题号", aqids, key="ans_qid")
                idx = next(i for i, a in enumerate(answer_list) if str(a.get("question_id", "")) == selected_qid)
                ans = answer_list[idx]

                with st.form("answer_edit_form"):
                    new_sol = st.text_area("解答过程 (LaTeX)", value=str(ans.get("solution_process", "")), height=260)
                    new_kp = st.text_area("知识点", value=str(ans.get("knowledge_points", "")), height=120)
                    new_alt = st.text_area("一题多解", value=str(ans.get("alternative_methods", "")), height=120)
                    new_ext = st.text_area("高阶拓展", value=str(ans.get("extensions", "")), height=120)
                    submitted = st.form_submit_button("保存答案修改")

                if submitted:
                    answer_list[idx].update(
                        {
                            "solution_process": new_sol,
                            "knowledge_points": new_kp,
                            "alternative_methods": new_alt,
                            "extensions": new_ext,
                        }
                    )
                    _save_json(solved_path, answer_list)
                    st.success("答案修改已保存")

        with t3:
            if isinstance(fail_list, list) and fail_list:
                st.warning(f"当前共有 {len(fail_list)} 道失败题")
                st.dataframe(fail_list, use_container_width=True, hide_index=True)

                colx, coly = st.columns(2)
                with colx:
                    if st.button("♻️ 一键重跑失败题", key="retry_failed_in_review"):
                        flow_box = st.container()
                        log_box = st.empty()
                        ok, msg, elapsed, details = _run_action(project, "retry_failed", flow_box, log_box)
                        append_run_record(
                            ROOT,
                            project_id=project["project_id"],
                            action="retry_failed",
                            status=("completed" if ok else "failed"),
                            elapsed_seconds=elapsed,
                            message=msg,
                            details=details,
                        )
                        if ok:
                            st.success(msg)
                        else:
                            st.error(msg)
                with coly:
                    if st.button("清空失败记录文件"):
                        _save_json(fail_path, [])
                        st.success("已清空 solve_failures.json")
            else:
                st.success("当前没有失败题")

with export_tab:
    st.subheader("导出与报告")
    active_id = st.session_state.get("active_project_id", "")
    project = get_project(ROOT, active_id) if active_id else None
    if not project:
        st.info("请先在项目中心选择一个项目")
    else:
        output_base = Path(project["output_base"])
        tex_path = output_base / FINAL_SOLUTION_FILE

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("🛠️ 重新组装 LaTeX"):
                try:
                    path = run_latex(output_base=output_base, config_path=project["config_path"])
                    st.success(f"LaTeX 已生成: {path}")
                except Exception as exc:
                    st.error(f"组装失败: {exc}")
        with c2:
            if st.button("📸 创建版本快照"):
                snap = create_output_snapshot(output_base)
                st.success(f"快照已创建: {snap}")
        with c3:
            if st.button("🧾 生成运行报告"):
                stats = collect_output_stats(output_base)
                report = write_run_report(
                    ROOT,
                    project,
                    stats,
                    summary="该报告由 GUI 自动生成，用于记录当前输出状态与节点配置。",
                )
                st.success(f"报告已生成: {report}")

        if tex_path.exists():
            st.download_button(
                "⬇️ 下载 final_solution.tex",
                data=tex_path.read_bytes(),
                file_name=tex_path.name,
                mime="application/x-tex",
            )
        else:
            st.caption("当前还没有 final_solution.tex，请先执行任务。" if is_zh else "No final_solution.tex yet. Run a task first.")

        st.markdown("##### 🔗 " + ("在线预览工具" if is_zh else "Online Preview Tools"))
        lc1, lc2 = st.columns(2)
        with lc1:
            st.link_button(
                "📄 Overleaf — LaTeX 在线编辑",
                "https://www.overleaf.com/project",
                help="上传 .tex 文件到 Overleaf 即可在线编译预览 PDF" if is_zh else "Upload .tex to Overleaf for online PDF compilation",
            )
        with lc2:
            st.link_button(
                "🔬 Prism (OpenAI) — LaTeX 渲染",
                "https://chatgpt.com",
                help="将 LaTeX 代码粘贴到 ChatGPT 可快速预览公式渲染效果" if is_zh else "Paste LaTeX into ChatGPT to preview formula rendering",
            )

        st.markdown("##### 📜 " + ("项目历史记录" if is_zh else "Run History"))
        runs = list_run_records(ROOT, project["project_id"])
        if runs:
            st.dataframe(runs, use_container_width=True, hide_index=True)
        else:
            st.info("暂无历史记录")

st.divider()
st.caption("Textbook2Answer Pro · 项目工作台模式（Phase1+2）")
