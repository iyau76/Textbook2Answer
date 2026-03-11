# -*- coding: utf-8 -*-
"""
项目工作区管理：
- 项目元数据（projects.json）
- 运行历史（runs.json）
- 章节页码解析
- 输出统计、版本快照、运行报告
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from ..constants import (
    EXTRACTED_TASKS_FILE,
    FINAL_SOLUTION_FILE,
    SOLVE_FAILURES_FILE,
    SOLVED_ANSWERS_FILE,
)
from ..pdf_processor import sanitize_book_title

WORKSPACE_DIR = ".t2a_workspace"
PROJECTS_FILE = "projects.json"
RUNS_FILE = "runs.json"
REPORTS_DIR = "reports"


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure_workspace(root: Path) -> Path:
    ws = root / WORKSPACE_DIR
    ws.mkdir(parents=True, exist_ok=True)
    (ws / REPORTS_DIR).mkdir(parents=True, exist_ok=True)
    return ws


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_projects(root: Path) -> list[dict]:
    ws = _ensure_workspace(root)
    projects = _read_json(ws / PROJECTS_FILE, [])
    if isinstance(projects, list):
        return projects
    return []


def get_project(root: Path, project_id: str) -> dict | None:
    for p in list_projects(root):
        if p.get("project_id") == project_id:
            return p
    return None


def upsert_project(root: Path, project: dict) -> dict:
    ws = _ensure_workspace(root)
    projects = list_projects(root)
    replaced = False
    for idx, old in enumerate(projects):
        if old.get("project_id") == project.get("project_id"):
            projects[idx] = project
            replaced = True
            break
    if not replaced:
        projects.append(project)
    _write_json(ws / PROJECTS_FILE, projects)
    return project


def patch_project(root: Path, project_id: str, **patches: Any) -> dict | None:
    projects = list_projects(root)
    for idx, p in enumerate(projects):
        if p.get("project_id") == project_id:
            p.update(patches)
            projects[idx] = p
            _write_json(_ensure_workspace(root) / PROJECTS_FILE, projects)
            return p
    return None


def parse_pages_expr(expr: str) -> list[int]:
    """
    解析页码表达式，例如: "15-18, 20, 24-25" -> [15,16,17,18,20,24,25]
    """
    if not expr or not str(expr).strip():
        return []
    pages: set[int] = set()
    for token in str(expr).replace("，", ",").split(","):
        t = token.strip()
        if not t:
            continue
        if "-" in t:
            a, b = t.split("-", 1)
            a_i = int(a.strip())
            b_i = int(b.strip())
            if a_i > b_i:
                a_i, b_i = b_i, a_i
            for p in range(a_i, b_i + 1):
                if p > 0:
                    pages.add(p)
        else:
            p = int(t)
            if p > 0:
                pages.add(p)
    return sorted(pages)


def create_project(
    root: Path,
    book_title: str,
    author_model: str,
    pdf_path: str,
    chapters: list[dict],
    extract_provider: str,
    solve_provider: str,
    extract_model: str | None,
    solve_model: str | None,
    quality_profile: str,
) -> dict:
    """
    创建或更新一个项目，同时写入独立 chapter_config。
    """
    safe_name = sanitize_book_title(book_title)
    project_id = safe_name

    cfg_dir = root / "input" / "projects" / safe_name
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = cfg_dir / "chapter_config.json"

    chapter_config = {
        "book_title": book_title,
        "author_model": author_model,
        "pdf_path": pdf_path,
        "chapters": chapters,
    }
    _write_json(cfg_path, chapter_config)

    output_base = root / "output" / safe_name
    now = _now_str()
    existing = get_project(root, project_id)
    created_at = existing.get("created_at") if existing else now

    project = {
        "project_id": project_id,
        "book_title": book_title,
        "config_path": str(cfg_path),
        "pdf_path": pdf_path,
        "output_base": str(output_base),
        "extract_provider": extract_provider,
        "solve_provider": solve_provider,
        "extract_model": extract_model,
        "solve_model": solve_model,
        "quality_profile": quality_profile,
        "status": "idle",
        "created_at": created_at,
        "updated_at": now,
        "last_run_at": existing.get("last_run_at") if existing else "",
    }
    return upsert_project(root, project)


def collect_output_stats(output_base: Path) -> dict:
    """采集项目输出统计。"""
    images_dir = output_base / "images"
    extracted_path = output_base / EXTRACTED_TASKS_FILE
    solved_path = output_base / SOLVED_ANSWERS_FILE
    fail_path = output_base / SOLVE_FAILURES_FILE
    tex_path = output_base / FINAL_SOLUTION_FILE

    extracted = _read_json(extracted_path, [])
    solved = _read_json(solved_path, [])
    failed = _read_json(fail_path, [])

    return {
        "images": len(list(images_dir.glob("*.png"))) if images_dir.exists() else 0,
        "tasks": len(extracted) if isinstance(extracted, list) else 0,
        "answers": len(solved) if isinstance(solved, list) else 0,
        "failed": len(failed) if isinstance(failed, list) else 0,
        "has_tex": tex_path.exists(),
        "paths": {
            "images_dir": str(images_dir),
            "extracted": str(extracted_path),
            "solved": str(solved_path),
            "failed": str(fail_path),
            "tex": str(tex_path),
            "log": str(output_base / "run.log"),
        },
    }


def append_run_record(
    root: Path,
    project_id: str,
    action: str,
    status: str,
    elapsed_seconds: float,
    message: str = "",
    details: dict | None = None,
) -> dict:
    ws = _ensure_workspace(root)
    runs = _read_json(ws / RUNS_FILE, [])
    rec = {
        "time": _now_str(),
        "project_id": project_id,
        "action": action,
        "status": status,
        "elapsed_seconds": round(float(elapsed_seconds), 2),
        "message": message,
        "details": details or {},
    }
    runs.append(rec)
    _write_json(ws / RUNS_FILE, runs)
    return rec


def list_run_records(root: Path, project_id: str | None = None) -> list[dict]:
    ws = _ensure_workspace(root)
    runs = _read_json(ws / RUNS_FILE, [])
    if not isinstance(runs, list):
        return []
    if not project_id:
        return list(reversed(runs))
    return [r for r in reversed(runs) if r.get("project_id") == project_id]


def create_output_snapshot(output_base: Path) -> Path:
    """
    创建输出快照目录，保留当前 JSON/TEX 结果。
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap_dir = output_base / "versions" / ts
    snap_dir.mkdir(parents=True, exist_ok=True)

    for filename in [EXTRACTED_TASKS_FILE, SOLVED_ANSWERS_FILE, SOLVE_FAILURES_FILE, FINAL_SOLUTION_FILE, "run.log"]:
        src = output_base / filename
        if src.exists():
            shutil.copy2(src, snap_dir / src.name)

    return snap_dir


def write_run_report(
    root: Path,
    project: dict,
    stats: dict,
    summary: str,
) -> Path:
    """写出一份 Markdown 运行报告。"""
    ws = _ensure_workspace(root)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = ws / REPORTS_DIR / f"report_{project.get('project_id', 'unknown')}_{ts}.md"

    text = f"""# Textbook2Answer 运行报告

- 项目: {project.get('book_title', '')}
- 生成时间: {_now_str()}
- 配置文件: {project.get('config_path', '')}
- PDF 路径: {project.get('pdf_path', '')}
- 提取节点: {project.get('extract_provider', '')}
- 解答节点: {project.get('solve_provider', '')}

## 输出统计

- 切片图片: {stats.get('images', 0)}
- 提取题目: {stats.get('tasks', 0)}
- 已解答题目: {stats.get('answers', 0)}
- 失败题目: {stats.get('failed', 0)}
- 已生成 LaTeX: {'是' if stats.get('has_tex') else '否'}

## 说明

{summary}
"""
    path.write_text(text, encoding="utf-8")
    return path
