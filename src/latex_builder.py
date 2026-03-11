# -*- coding: utf-8 -*-
"""
将 extracted_tasks.json 与 solved_answers.json 按 question_id 合并，
注入 Jinja2 模板，生成 output/final_solution.tex。
"""
import json
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .logger import logger
from .pdf_processor import get_output_base


def load_config(config_path: str | Path) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _clean_latex_text(s: str) -> str:
    """对大模型输出的 LaTeX 文本进行清洗，解决冗余转义和特殊字符问题。"""
    if not s:
        return ""

    # 1. 修复由于模型抛出的带下划线的错误信息导致编译失败的问题
    s = re.sub(r"\[解答生成失败.*?\]", lambda m: m.group(0).replace("_", "\\_"), s)

    # 2. 修复误写的字面量 \n：将 \\n 与 \n 都还原成真实换行
    # 先处理双反斜杠，避免下一步重复匹配
    s = s.replace("\\\\n", "\n")
    s = s.replace("\\n", "\n")

    # 2.5 修复 Markdown 加粗 (**文本** -> \textbf{文本})
    s = re.sub(r'\*\*(.*?)\*\*', r'\\textbf{\1}', s)

    # 3. 修复过度的转义（如 \\\\textbf -> \\textbf）
    # 优先替换常见的命令
    for cmd in ["textbf", "begin", "end", "item", "frac", "label", "ref", "cite", "mathbb", "mathcal"]:
        s = s.replace(f"\\\\\\\\{cmd}", f"\\{cmd}")
    # 处理遗留的 \\\\ -> \\
    s = s.replace("\\\\\\\\", "\\\\")

    # 4. 修复漏转义的正文保留字：_、%、&
    # 将文本切分为数学环境和非数学环境
    math_pattern = r"(\$\$.*?\$\$|\$.*?\$|\\\[.*?\\\]|\\begin\{equation\}.*?\\end\{equation\}|\\begin\{align\*?\}.*?\\end\{align\*?\}|\\begin\{cases\}.*?\\end\{cases\})"
    parts = re.split(math_pattern, s, flags=re.DOTALL)

    for i in range(len(parts)):
        if i % 2 == 0:
            # 这是非数学模式（纯文本区域）
            text = parts[i]
            # 加前视断言防止重复转义
            text = re.sub(r"(?<!\\)_", r"\_", text)
            text = re.sub(r"(?<!\\)%", r"\%", text)
            text = re.sub(r"(?<!\\)&", r"\&", text)
            parts[i] = text
        else:
            # 这是数学模式（公式区域）
            text = parts[i]
            # 修复大模型自身可能生成的错误下划线转义 (如 \epsilon\_ -> \epsilon_)
            text = text.replace(r"\_", "_")
            parts[i] = text

    s = "".join(parts)

    # 4.1 对于 \label, \ref 等内部的 \_ 进行复原，避免编译错误
    def unescape_labels(m):
        return m.group(0).replace(r"\_", "_")

    s = re.sub(r"\\(label|ref|eqref|cite)\{.*?\}", unescape_labels, s)

    # 5. 修复特例：在 cases/aligned 等环境中缺少的 \\ （模型偶尔漏掉）
    # 同时修复极少量情况下出现的单个\而不是\\的问题
    def fix_cases(m):
        inner = m.group(1)
        # 修复所有单独的 \ 换行（应该是 \\ 换行）
        inner = re.sub(r'(?<!\\)\\\s*\n', r'\\\\\n', inner)
        if "\\\\" not in inner and "\n" in inner.strip():
            # 把内部的换行变成 \\ + 换行
            inner = inner.replace("\n", "\\\\\n")
        return f"\\begin{{cases}}{inner}\\end{{cases}}"

    s = re.sub(r"\\begin\{cases\}(.*?)\\end\{cases\}", fix_cases, s, flags=re.DOTALL)

    # 6. 顺手牵羊：修复某些漏掉反斜杠的 frac (例如 rac)
    # 只能做简单推断，比如数字/变量接 rac{
    # 但更容易遇到的是纯丢了一个反斜杠变成 \frac 而不是 \\frac （在 JSON 中），后来又被 json 变成了 frac。
    # 如果模型输出了 frac{，补上。
    # 这里用正则替换独立的 frac{ 为 \frac{ （前提是它前面没有反斜杠）
    s = re.sub(r"(?<!\\)frac\{", r"\\frac{", s)

    return s


def _norm(s: str) -> str:
    """规范化：strip；空或仅空白视为空字符串。同时调用清洗函数。"""
    if not s:
        return ""
    s = s.strip()
    return _clean_latex_text(s)


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

    logger.info("构建完成：%d 个章节，共 %d 道题", len(chapters), sum(len(c["tasks"]) for c in chapters))
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
    logger.info("LaTeX 文件已写入: %s", output_tex_path)
    return Path(output_tex_path)
