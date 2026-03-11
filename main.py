# -*- coding: utf-8 -*-
"""
Textbook2Answer 主程序入口。
流程：PDF 切片 -> VLM 提取习题 -> 推理求解 -> LaTeX 组装。
输出按 book_title 写入 output/<book_title>/，便于多本书管理。
"""
import argparse
from pathlib import Path

from src.logger import logger, setup_log_file
from src.pdf_processor import get_output_base, load_chapter_config, run as run_pdf
from src.vlm_extractor import run as run_vlm
from src.reasoning_solver import run as run_solver
from src.latex_builder import run as run_latex


def main():
    parser = argparse.ArgumentParser(description="教材 PDF 转教辅级 LaTeX 参考答案")
    parser.add_argument("--skip-pdf", action="store_true", help="跳过 PDF 切片（使用已有 output/<book>/images）")
    parser.add_argument("--skip-extract", action="store_true", help="跳过 VLM 提取（使用已有 extracted_tasks.json）")
    parser.add_argument("--skip-solve", action="store_true", help="跳过推理求解（使用已有 solved_answers.json）")
    parser.add_argument("--only-latex", action="store_true", help="仅执行 LaTeX 组装")
    parser.add_argument("--config", type=str, default=None, help="input/chapter_config.json 路径")
    parser.add_argument("--pdf", type=str, default=None, help="教材 PDF 路径，默认 input/textbook.pdf")
    parser.add_argument("--provider", type=str, default="gemini", help="默认 API 配置名（兼容旧参数）。")
    parser.add_argument("--extract-provider", type=str, default=None, help="题目提取所用 API 配置名（如 gemini/glm46/custom1）。默认同 --provider")
    parser.add_argument("--solve-provider", type=str, default=None, help="题目解答所用 API 配置名（如 deepseek/gpt5/custom1）。默认同 --provider")
    parser.add_argument("--extract-model", type=str, default=None, help="覆盖提取模型名（可选）。默认使用 api_config.json 中该节点的 model")
    parser.add_argument("--solve-model", type=str, default=None, help="覆盖解答模型名（可选）。默认使用 api_config.json 中该节点的 model")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    config_path = Path(args.config) if args.config else root / "input" / "chapter_config.json"
    # 1) 若命令行提供 --pdf，则优先使用
    # 2) 否则尝试从 chapter_config.json 中读取 "pdf_path"
    # 3) 若均无，则回退为 input/textbook.pdf
    if args.pdf:
        pdf_path = Path(args.pdf)
    else:
        cfg = load_chapter_config(config_path)
        cfg_pdf = cfg.get("pdf_path")
        if cfg_pdf:
            pdf_path = Path(cfg_pdf)
            if not pdf_path.is_absolute():
                pdf_path = (root / pdf_path).resolve()
        else:
            pdf_path = root / "input" / "textbook.pdf"

    output_base = get_output_base(root, config_path)
    setup_log_file(output_base / "run.log")
    extract_provider = args.extract_provider or args.provider
    solve_provider = args.solve_provider or args.provider

    if args.only_latex:
        run_latex(config_path=config_path, output_base=output_base)
        logger.info("已生成 %s", output_base / "final_solution.tex")
        return

    if not args.skip_pdf:
        logger.info("Phase 1: PDF 切片...")
        run_pdf(config_path=config_path, pdf_path=pdf_path, output_base=output_base)
        logger.info("PDF 切片完成 -> %s", output_base / "images")
    else:
        logger.info("跳过 PDF 切片。")

    if not args.skip_extract:
        logger.info("Phase 2: VLM 提取习题...")
        run_vlm(
            config_path=config_path,
            pdf_path=pdf_path,
            output_base=output_base,
            provider=extract_provider,
            model=args.extract_model,
        )
        logger.info("提取完成 -> %s", output_base / "extracted_tasks.json")
    else:
        logger.info("跳过 VLM 提取。")

    if not args.skip_solve:
        logger.info("Phase 3: 推理求解...")
        run_solver(
            output_base=output_base,
            config_path=config_path,
            provider=solve_provider,
            model=args.solve_model,
        )
        logger.info("求解完成 -> %s", output_base / "solved_answers.json")
    else:
        logger.info("跳过推理求解。")

    logger.info("Phase 4: LaTeX 组装...")
    run_latex(config_path=config_path, output_base=output_base)
    logger.info("已生成 %s。请使用 xelatex 等本地编译得到 PDF。", output_base / "final_solution.tex")


if __name__ == "__main__":
    main()
