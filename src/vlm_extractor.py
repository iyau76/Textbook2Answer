# -*- coding: utf-8 -*-
"""
视觉提取模块：根据 chapter_config 与 output/images/ 下的图片，调用 VLM 提取习题，
生成 output/extracted_tasks.json。输出格式严格符合文档 schema。
"""
import json
import re
from pathlib import Path

from .api_client import APIClient
from .pdf_processor import load_chapter_config, get_all_pages, get_output_base, render_pdf_pages


EXTRACT_SYSTEM = """你是一个专业的教材解析专家。你的任务是从教材页面图片中提取所有的课后习题。

要求：
1. 必须输出纯净的 JSON 数组，每个元素包含字段：question_id, content, has_image。
2. question_id 保留教材中的原始题号（如 "1", "2-1", "2-2" 等）。
3. content 为该题的完整文字题干。若题干中含数学符号或公式，必须用 LaTeX 并包在 $...$（行内）或 \\[ \\]（独立公式）中，例如 $\\\\mathcal{E}$、$\\\\mathbf{k}$、$\\\\epsilon_r \\\\neq 0$、\\[ E = mc^2 \\]。禁止在文字中单独写 \\\\mathcal、\\\\mathbf、\\\\neq 等而不加 $，否则生成的文档会报“allowed only in math mode”错误。
4. 如果题目旁边的配图是解题不可或缺的（如电路图、几何图形、数据图表），将 has_image 设为 true，否则设为 false。
5. 不要输出任何 markdown 标记（如 ```json），只输出一个合法的 JSON 数组。
6. 如果习题用英文书写，请务必将习题内容翻译成中文。

JSON 与 LaTeX 转义（必须严格遵守，否则会出现乱码）：
- 在 JSON 字符串中，反斜杠是转义符。\\f 会被解析为换页符、\\t 会被解析为制表符，导致 \\frac 变成 rac、\\theta 变成 heta。
- 因此所有 LaTeX 命令的反斜杠必须写成双反斜杠，例如：\\\\frac{1}{2}、\\\\theta、\\\\alpha、\\\\begin{equation}。这样解析后才能得到正确的 \\frac、\\theta。
- 换行请直接使用真实换行，不要在字符串里写 \\n 表示换行。

禁止 Markdown 语法：
- 不要使用 **加粗** 或 1. 2. 列表。加粗请用 LaTeX：\\\\textbf{文字}；列表请用 \\\\begin{itemize} \\\\item ... \\\\end{itemize}。"""

def _sanitize_task_content(s: str) -> str:
    """
    对题干做保守的 LaTeX 纠错，减少 VLM 偶发的不合规输出导致编译失败。
    目标：不追求完美语义，只尽量避免明显的“必须在数学模式”错误。
    """
    if not s:
        return ""
    s = s.strip()

    # 1) cases 环境必须在数学模式：若出现 begin/end{cases} 但没有显示数学包裹，则包一层 \[...\]
    if ("\\begin{cases}" in s) and ("\\end{cases}" in s):
        has_display = ("\\[" in s and "\\]" in s) or ("\\begin{equation}" in s) or ("\\begin{align" in s)
        if not has_display:
            s = s.replace("\\begin{cases}", "\\[\\begin{cases}")
            s = s.replace("\\end{cases}", "\\end{cases}\\]")

    # 2) \infty 这类纯数学符号，若全文没有任何数学环境符号，则简单包成 $\\infty$
    if "\\infty" in s and ("$" not in s) and ("\\[" not in s) and ("\\begin{equation}" not in s):
        s = re.sub(r"\\\\infty", r"$\\\\infty$", s)

    return s



def _fix_json_control_chars(s: str) -> str:
    """将 JSON 字符串值内的未转义控制字符（如换行、制表）转为合法转义，避免 Invalid control character。"""
    result = []
    i = 0
    in_string = False
    escape_next = False
    while i < len(s):
        c = s[i]
        if escape_next:
            result.append(c)
            escape_next = False
            i += 1
            continue
        if c == "\\" and in_string:
            result.append(c)
            escape_next = True
            i += 1
            continue
        if c == '"':
            result.append(c)
            in_string = not in_string
            i += 1
            continue
        if in_string and ord(c) < 32:
            # 控制字符转为 JSON 转义
            if c == "\n":
                result.append("\\n")
            elif c == "\r":
                result.append("\\r")
            elif c == "\t":
                result.append("\\t")
            else:
                result.append(f"\\u{ord(c):04x}")
            i += 1
            continue
        result.append(c)
        i += 1
    return "".join(result)


def _fix_json_invalid_escapes(s: str) -> str:
    """修复 JSON 中非法反斜杠（如 LaTeX \\frac、\\alpha），使 json.loads 能解析。"""
    result = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            n = s[i + 1]
            if n in '"\\/bfnrt':
                result.append(s[i : i + 2])
                i += 2
                continue
            if n == "u" and i + 5 <= len(s):
                hex_part = s[i + 2 : i + 6]
                if len(hex_part) == 4 and all(c in "0123456789abcdefABCDEF" for c in hex_part):
                    result.append(s[i : i + 6])
                    i += 6
                    continue
            result.append("\\\\")
            result.append(n)
            i += 2
            continue
        result.append(s[i])
        i += 1
    return "".join(result)


def _extract_json_array(text: str) -> list:
    """从模型输出中截取 JSON 数组，尽量容错（含非法反斜杠时先修复再解析）。"""
    text = text.strip()
    for start in ("```json", "```"):
        if text.startswith(start):
            text = text[len(start) :].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    start_idx = text.find("[")
    if start_idx == -1:
        obj_idx = text.find("{")
        if obj_idx != -1:
            depth = 0
            end = -1
            for i in range(obj_idx, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end > 0:
                segment = _fix_json_invalid_escapes(text[obj_idx:end])
                segment = _fix_json_control_chars(segment)
                return [json.loads(segment)]
        raise ValueError("未找到 JSON 数组或对象")
    depth = 0
    end_idx = -1
    for i in range(start_idx, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                end_idx = i + 1
                break
    if end_idx == -1:
        raise ValueError("JSON 数组未闭合")
    segment = _fix_json_invalid_escapes(text[start_idx:end_idx])
    segment = _fix_json_control_chars(segment)
    return json.loads(segment)


def extract_tasks_from_image(
    client: APIClient,
    image_path: str | Path,
    chapter_name: str,
    page_num: int,
    images_output_dir: str | Path,
    root: str | Path | None = None,
    output_base: str | Path | None = None,
    model: str | None = None,
) -> list[dict]:
    """
    对单张页面图调用 VLM，提取习题列表。为每条记录补充 chapter_name, page_num, image_path。
    image_path 存为相对项目根路径，供后续推理模块定位图片。若提供 root 与 output_base，则 rel_path = (output_base/images/page_N.png).relative_to(root)。
    """
    image_path = Path(image_path)
    images_output_dir = Path(images_output_dir)
    if root is not None and output_base is not None:
        root, output_base = Path(root), Path(output_base)
        rel_path = (output_base / "images" / f"page_{page_num}.png").relative_to(root).as_posix()
    else:
        rel_path = f"output/images/page_{page_num}.png"

    user = f"当前章节名：{chapter_name}\n本页 PDF 页码：{page_num}\n请从本张教材页面图片中提取所有课后习题，输出 JSON 数组（仅 question_id, content, has_image）。"
    raw = client.chat(
        [{"role": "system", "content": EXTRACT_SYSTEM}, {"role": "user", "content": user}],
        image_path=str(image_path),
        model=model,
    )
    items = _extract_json_array(raw)
    out = []
    for it in items:
        rec = {
            "chapter_name": chapter_name,
            "question_id": str(it.get("question_id", "")),
            "content": _sanitize_task_content(str(it.get("content", ""))),
            "has_image": bool(it.get("has_image", False)),
            "page_num": page_num,
            "image_path": rel_path,
        }
        out.append(rec)
    return out


def run(
    config_path: str | Path | None = None,
    pdf_path: str | Path | None = None,
    images_dir: str | Path | None = None,
    output_json_path: str | Path | None = None,
    output_base: str | Path | None = None,
    provider: str = "gemini",
    model: str | None = None,
) -> list[dict]:
    """
    主流程：
    1) 若未传 output_base，则根据 config 的 book_title 得到 output/<book_title>；
    2) 若 images_dir 下缺少某页图，则根据 config 与 pdf 渲染补全；
    3) 按章节与页码逐页调用 VLM 提取习题；
    4) 合并为列表并写入 output_base/extracted_tasks.json。
    """
    root = Path(__file__).resolve().parent.parent
    config_path = config_path or root / "input" / "chapter_config.json"
    pdf_path = pdf_path or root / "input" / "textbook.pdf"
    if output_base is None:
        output_base = get_output_base(root, config_path)
    output_base = Path(output_base)
    images_dir = images_dir or (output_base / "images")
    output_json_path = output_json_path or (output_base / "extracted_tasks.json")

    config = load_chapter_config(config_path)
    all_pages = get_all_pages(config)
    if not all_pages:
        raise ValueError("chapter_config 中未配置任何页码")

    # 确保所需页面图存在
    images_dir = Path(images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)
    for pnum in all_pages:
        png = images_dir / f"page_{pnum}.png"
        if not png.exists() and Path(pdf_path).exists():
            render_pdf_pages(pdf_path, [pnum], images_dir)

    # 页码 -> 章节名（取第一个包含该页的章节）
    page_to_chapter = {}
    for ch in config.get("chapters", []):
        name = ch.get("chapter_name", "")
        for p in ch.get("pages", []):
            page_to_chapter[int(p)] = name

    # 断点续传：已存在的 extracted_tasks.json 中已提取的页码不再重复调用 VLM
    Path(output_json_path).parent.mkdir(parents=True, exist_ok=True)
    if Path(output_json_path).exists():
        with open(output_json_path, "r", encoding="utf-8") as f:
            all_tasks = json.load(f)
        done_pages = {t["page_num"] for t in all_tasks}
    else:
        all_tasks = []
        done_pages = set()

    client = APIClient(provider=provider)
    for pnum in all_pages:
        if pnum in done_pages:
            continue
        chapter_name = page_to_chapter.get(pnum, "")
        img = images_dir / f"page_{pnum}.png"
        if not img.exists():
            continue
        tasks = extract_tasks_from_image(
            client, img, chapter_name, pnum, images_dir, root=root, output_base=output_base, model=model
        )
        all_tasks.extend(tasks)
        done_pages.add(pnum)
        # 每处理完一页立即写回，便于断点续传
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(all_tasks, f, ensure_ascii=False, indent=2)
    return all_tasks
