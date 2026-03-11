# -*- coding: utf-8 -*-
"""
视觉提取模块：根据 chapter_config 与 output/images/ 下的图片，调用 VLM 提取习题，
生成 output/extracted_tasks.json。输出格式严格符合文档 schema。
"""
import json
import re
from pathlib import Path

from .api_client import APIClient
from .logger import logger
from .pdf_processor import load_chapter_config, get_all_pages, get_output_base, render_pdf_pages


EXTRACT_SYSTEM = """你是一个专业的教材解析专家。你的任务是从一章教材的多张页面图片中提取所有的课后习题。

要求：
1. 必须输出纯净的 JSON 数组，每个元素包含字段：question_id, content, has_image, page_num。
2. question_id 保留教材中的原始题号（如 "1", "2-1", "2-2" 等）。
3. content 为该题的完整文字题干。若题干中含数学符号或公式，必须用 LaTeX 并包在 $...$（行内）或 \\[ \\]（独立公式）中，例如 $\\mathcal{E}$、$\\mathbf{k}$、$\\epsilon_r \\neq 0$。\\[ E = mc^2 \\]。禁止在文字中单独写 \\mathcal、\\mathbf、\\neq 等而不加 $，否则生成的文档会报“allowed only in math mode”错误。
4. 如果题目旁边的配图是解题不可或缺的（如电路图、几何图形、数据图表），将 has_image 设为 true，否则设为 false。
5. 对于跨页被截断的习题，请自动拼接完整的题目（上下文推理），保证其为一道完整的题。
6. page_num 请判断这道题主要发生在哪一教材页码（填入数字即可），不能确定则填本章的第一页。
7. 不要输出任何 markdown 标记（如 ```json），只输出一个合法的 JSON 数组。
8. 如果习题用英文书写，请务必将习题内容翻译成中文。

JSON 与 LaTeX 转义：
- 建议你使用原生的 LaTeX 语法进行公式表达即可，例如：\\frac{1}{2}、\\theta、\\alpha、\\begin{equation}、\\end{equation} 等等。按照写 LaTeX 源码的直觉来即可。
- 对于换行，你可以使用字面量的回车换行，不需要在字符串里硬写控制字符 \\n。

禁止 Markdown 语法：
- 不要使用 **加粗** 或 1. 2. 列表。加粗请用 LaTeX：\\textbf{文字}；列表请用 \\begin{itemize} \\item ... \\end{itemize}。"""

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
            s = s
            s = s

    # 2) \infty 这类纯数学符号，若全文没有任何数学环境符号，则简单包成 $\\infty$
    if "\\infty" in s and ("$" not in s) and ("\\[" not in s) and ("\\begin{equation}" not in s):
        s = s

    return s



def _clean_json_string(s: str) -> str:
    """清理并修复大模型输出的 JSON 字符串，使其符合标准 JSON 格式。"""
    if not s:
        return s
    
    start_idx = s.find('{')
    arr_start_idx = s.find('[')
    if start_idx == -1 and arr_start_idx == -1:
        return s
    start = start_idx if arr_start_idx == -1 else (arr_start_idx if start_idx == -1 else min(start_idx, arr_start_idx))
    
    end_idx = s.rfind('}')
    arr_end_idx = s.rfind(']')
    end = end_idx if arr_end_idx == -1 else (arr_end_idx if end_idx == -1 else max(end_idx, arr_end_idx))
    
    if end < start:
        return s
        
    json_str = s[start:end+1]
    
    json_str = re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', r'\\\\', json_str)
    
    result = []
    in_string = False
    escape_next = False
    
    for i, c in enumerate(json_str):
        if escape_next:
            result.append(c)
            escape_next = False
            continue
        if c == '\\':
            result.append(c)
            escape_next = True
            continue
        if c == '"':
            in_string = not in_string
            result.append(c)
            continue
        if in_string:
            if c == '\n':
                result.append('\\n')
            elif c == '\r':
                result.append('\\r')
            elif c == '\t':
                result.append('\\t')
            elif ord(c) < 32:
                result.append(f"\\u{ord(c):04x}")
            else:
                result.append(c)
        else:
            result.append(c)
            
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
                segment = _clean_json_string(text[obj_idx:end])
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
    segment = _clean_json_string(text[start_idx:end_idx])
    return json.loads(segment)


def extract_tasks_from_chapter(
    client: APIClient,
    chapter_name: str,
    page_nums: list[int],
    images_output_dir: str | Path,
    root: str | Path | None = None,
    output_base: str | Path | None = None,
    model: str | None = None,
) -> list[dict]:
    """
    对指定章节的多张页面图调用 VLM，提取习题列表。为每条记录补充 chapter_name, page_num, image_path。
    """
    images_output_dir = Path(images_output_dir)
    image_paths = []
    
    for pnum in page_nums:
        img_path = images_output_dir / f"page_{pnum}.png"
        image_paths.append(str(img_path))

    pages_str = ", ".join(map(str, page_nums))
    user = f"当前章节名：{chapter_name}\n包含的本节所有教材页码：{pages_str}\n请结合上下文，如果发现跨页或者分开的题目能够组装成连贯的一道题，请予以拼装，确保题目的完整性。输出提取完成的 JSON 数组。"
    
    raw = client.chat(
        [{"role": "system", "content": EXTRACT_SYSTEM}, {"role": "user", "content": user}],
        image_paths=image_paths,
        model=model,
    )
    items = _extract_json_array(raw)
    out = []
    for it in items:
        pnum = it.get("page_num")
        try:
            pnum = int(pnum)
        except (ValueError, TypeError):
            pnum = page_nums[0] if page_nums else 0
            
        if root is not None and output_base is not None:
            rel_path = (Path(str(output_base)) / "images" / f"page_{pnum}.png").relative_to(Path(str(root))).as_posix()
        else:
            rel_path = f"output/images/page_{pnum}.png"

        rec = {
            "chapter_name": chapter_name,
            "question_id": str(it.get("question_id", "")),
            "content": _sanitize_task_content(str(it.get("content", ""))),
            "has_image": bool(it.get("has_image", False)),
            "page_num": pnum,
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
    if Path(str(output_json_path)).exists():
        with open(output_json_path, "r", encoding="utf-8") as f:
            all_tasks = json.load(f)
        done_pages = {int(t["page_num"]) for t in all_tasks if t.get("page_num") is not None}
    else:
        all_tasks = []
        done_pages = set()

    client = APIClient(provider=provider)
    for ch in config.get("chapters", []):
        chapter_name = ch.get("chapter_name", "")
        pages = ch.get("pages", [])
        if not pages:
            continue
            
        # 如果这一章有任何一页已经提取过，则跳过（断点续传保守策略）
        if any(int(p) in done_pages for p in pages):
            logger.info("章节 [%s] 已提取，跳过", chapter_name)
            continue

        valid_pages = []
        for pnum in pages:
            img = images_dir / f"page_{pnum}.png"
            if img.exists():
                valid_pages.append(pnum)
                
        if not valid_pages:
            continue
            
        logger.info("提取章节 [%s]，共 %d 页...", chapter_name, len(valid_pages))
        tasks = extract_tasks_from_chapter(
            client, chapter_name, valid_pages, images_dir, root=root, output_base=output_base, model=model
        )
        logger.info("章节 [%s]: 提取到 %d 道题", chapter_name, len(tasks))
        all_tasks.extend(tasks)
        done_pages.update(valid_pages)
        
        # 每处理完一章立即写回，便于断点续传
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(all_tasks, f, ensure_ascii=False, indent=2)
            
    return all_tasks
