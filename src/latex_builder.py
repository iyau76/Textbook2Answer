# -*- coding: utf-8 -*-
"""
将 extracted_tasks.json 与 solved_answers.json 按 question_id 合并，
注入 Jinja2 模板，生成 output/final_solution.tex。
"""
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .pdf_processor import get_output_base


def load_config(config_path: str | Path) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_chapters(
    extracted_path: str | Path,
    solved_path: str | Path,
    config_path: str | Path,
) -> list[dict]:
    """
    合并提取结果与解答结果，按章节组织。
    返回: [{"chapter_name": "...", "tasks": [task_dict, ...]}, ...]
    """
    with open(extracted_path, "r", encoding="utf-8") as f:
        tasks = json.load(f)
    with open(solved_path, "r", encoding="utf-8") as f:
        answers = json.load(f)
    config = load_config(config_path)
    book_title = config.get("book_title", "教材")
    author_model = config.get("author_model", "")

    # 以 question_id 为键的解答
    ans_map = {a["question_id"]: a for a in answers}

    # 按章节名分组，保持原始顺序
    chapter_order = []
    seen_chapters = set()
    for ch in config.get("chapters", []):
        name = ch.get("chapter_name", "")
        if name and name not in seen_chapters:
            seen_chapters.add(name)
            chapter_order.append(name)

    def _norm(s: str) -> str:
        """规范化：strip；空或仅空白视为空字符串。不替换 \\n/\\r，否则会破坏 LaTeX 中的 \\nabla、\\ref、\\neq 等。"""
        if not s:
            return ""
        return s.strip()

    # 每个章节下的题目列表（保持 extracted 顺序）
    chapter_tasks = {c: [] for c in chapter_order}
    for t in tasks:
        ch_name = t.get("chapter_name", "")
        qid = t.get("question_id", "")
        ans = ans_map.get(qid, {})
        task = {
            "question_id": qid,
            "content": _norm(t.get("content", "")),
            "solution_process": _norm(ans.get("solution_process", "")),
            "knowledge_points": _norm(ans.get("knowledge_points", "")),
            "alternative_methods": _norm(ans.get("alternative_methods", "")),
            "extensions": _norm(ans.get("extensions", "")),
        }
        if ch_name in chapter_tasks:
            chapter_tasks[ch_name].append(task)
        else:
            chapter_tasks.setdefault(ch_name, []).append(task)
            if ch_name not in seen_chapters:
                seen_chapters.add(ch_name)
                chapter_order.append(ch_name)

    chapters = []
    for ch_name in chapter_order:
        if chapter_tasks.get(ch_name):
            chapters.append({"chapter_name": ch_name, "tasks": chapter_tasks[ch_name]})

    return chapters, book_title, author_model


def run(
    extracted_path: str | Path | None = None,
    solved_path: str | Path | None = None,
    config_path: str | Path | None = None,
    template_dir: str | Path | None = None,
    output_tex_path: str | Path | None = None,
    output_base: str | Path | None = None,
) -> Path:
    root = Path(__file__).resolve().parent.parent
    config_path = config_path or root / "input" / "chapter_config.json"
    if output_base is None:
        output_base = get_output_base(root, config_path)
    output_base = Path(output_base)
    extracted_path = extracted_path or (output_base / "extracted_tasks.json")
    solved_path = solved_path or (output_base / "solved_answers.json")
    template_dir = template_dir or root / "templates"
    output_tex_path = output_tex_path or (output_base / "final_solution.tex")

    chapters, book_title, author_model = build_chapters(extracted_path, solved_path, config_path)
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(default=False),
    )
    template = env.get_template("main_template.tex")
    tex_content = template.render(
        chapters=chapters,
        book_title=book_title,
        author_model=author_model,
    )
    Path(output_tex_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_tex_path).write_text(tex_content, encoding="utf-8")
    return Path(output_tex_path)
