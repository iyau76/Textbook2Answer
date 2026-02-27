# -*- coding: utf-8 -*-
"""
根据 input/chapter_config.json 将指定 PDF 页码渲染为高质量 PNG，保存到 output/<book_title>/images/。
使用 PyMuPDF (fitz)。
"""
import json
import re
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


def load_chapter_config(config_path: str | Path) -> dict:
    """加载章节配置。"""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def sanitize_book_title(title: str) -> str:
    """将书名转为可作目录名的字符串，去掉非法字符。"""
    if not title or not str(title).strip():
        return "default"
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", str(title).strip())
    return s[:80] if s else "default"


def get_output_base(root: Path, config_path: str | Path) -> Path:
    """根据 config 中的 book_title 得到该书输出根目录 output/<book_title>。"""
    config = load_chapter_config(config_path)
    title = config.get("book_title", "default")
    return root / "output" / sanitize_book_title(title)


def get_all_pages(chapter_config: dict) -> list[int]:
    """从章节配置中收集所有不重复的页码（PDF 物理页码，从 1 开始）。"""
    pages = set()
    for ch in chapter_config.get("chapters", []):
        for p in ch.get("pages", []):
            pages.add(int(p))
    return sorted(pages)


def render_pdf_pages(
    pdf_path: str | Path,
    page_numbers: list[int],
    output_dir: str | Path,
    dpi: int = 150,
) -> list[tuple[int, Path]]:
    """
    将 PDF 的指定页渲染为 PNG。
    page_numbers: PDF 物理页码列表（从 1 开始）。
    返回: [(page_num, output_path), ...]
    """
    if fitz is None:
        raise ImportError("请安装 PyMuPDF: pip install PyMuPDF")
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    result = []
    try:
        # fitz 页面索引从 0 开始
        for pnum in page_numbers:
            idx = pnum - 1
            if idx < 0 or idx >= len(doc):
                continue
            page = doc[idx]
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            out_name = f"page_{pnum}.png"
            out_path = output_dir / out_name
            pix.save(str(out_path))
            result.append((pnum, out_path))
    finally:
        doc.close()
    return result


def run(
    config_path: str | Path | None = None,
    pdf_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    output_base: str | Path | None = None,
):
    """
    主流程：读取 chapter_config.json，渲染指定页到 output/<book_title>/images/。
    output_base: 该书输出根目录（默认由 config 的 book_title 得到）；图片写入 output_base/images/。
    """
    root = Path(__file__).resolve().parent.parent
    config_path = config_path or root / "input" / "chapter_config.json"
    pdf_path = pdf_path or root / "input" / "textbook.pdf"
    if output_base is not None:
        output_dir = Path(output_base) / "images"
    elif output_dir is None:
        output_base = get_output_base(root, config_path)
        output_dir = output_base / "images"

    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"未找到教材 PDF: {pdf_path}")

    config = load_chapter_config(config_path)
    pages = get_all_pages(config)
    if not pages:
        return []
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return render_pdf_pages(pdf_path, pages, output_dir)


if __name__ == "__main__":
    run()
