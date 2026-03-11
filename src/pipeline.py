# -*- coding: utf-8 -*-
"""
Pipeline API  将四阶段流程封装为可供程序（包括 GUI/Web）调用的接口。

核心概念
--------
- **PipelineConfig**: 纯数据类，描述一次运行的全部参数。
- **PipelineEvent**: 结构化事件，由流水线向外推送进度/状态。
- **Pipeline**: 执行器，通过 ``event_handler`` 回调向 GUI 实时推送事件。

快速上手
--------
CLI 模式（直接运行所有阶段）::

    from src.pipeline import Pipeline, PipelineConfig
    cfg = PipelineConfig(config_path="input/chapter_config.json")
    Pipeline(cfg).run()

带进度回调（Streamlit / PyQt 等）::

    def my_handler(event: PipelineEvent):
        print(f"[{event.stage}] {event.message}  {event.current}/{event.total}")

    Pipeline(cfg, event_handler=my_handler).run()

GUI 日志接入::

    from src.logger import add_ui_handler
    add_ui_handler(lambda level, msg: ui_log_widget.append(f"[{level}] {msg}"))
"""
from __future__ import annotations

import dataclasses
import time
from pathlib import Path
from typing import Callable

from .logger import logger, setup_log_file
from .pdf_processor import get_output_base, load_chapter_config, run as _run_pdf
from .vlm_extractor import run as _run_vlm
from .reasoning_solver import run as _run_solver
from .latex_builder import run as _run_latex


# ---------------------------------------------------------------------------
# 事件类型常量
# ---------------------------------------------------------------------------

STAGE_PDF = "pdf"
STAGE_EXTRACT = "extract"
STAGE_SOLVE = "solve"
STAGE_LATEX = "latex"

EVENT_STAGE_START = "stage_start"
EVENT_STAGE_PROGRESS = "stage_progress"
EVENT_STAGE_COMPLETE = "stage_complete"
EVENT_STAGE_ERROR = "stage_error"
EVENT_PIPELINE_COMPLETE = "pipeline_complete"


@dataclasses.dataclass
class PipelineEvent:
    """
    流水线事件，由 Pipeline 实例通过 event_handler 回调传出。

    Attributes:
        type: 事件类型，取值为 EVENT_STAGE_* / EVENT_PIPELINE_COMPLETE。
        stage: 所属阶段，取值为 STAGE_* 常量。
        message: 人类可读的描述。
        current: 当前进度（如：已处理题目数）。
        total: 总量（0 表示未知）。
        elapsed: 本阶段已耗时（秒）。
        data: 附加数据字典，内容视事件类型而定。
    """
    type: str
    stage: str
    message: str = ""
    current: int = 0
    total: int = 0
    elapsed: float = 0.0
    data: dict = dataclasses.field(default_factory=dict)


# ---------------------------------------------------------------------------
# 配置类
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class PipelineConfig:
    """流水线配置，所有参数均有合理默认值。"""
    config_path: str | Path | None = None
    """chapter_config.json 路径，默认 input/chapter_config.json"""
    pdf_path: str | Path | None = None
    """教材 PDF 路径，默认读取 chapter_config.json 中的 pdf_path 字段"""
    extract_provider: str = "gemini"
    """题目提取所用 API 节点名（对应 api_config.json 中的键）"""
    solve_provider: str = "gemini"
    """题目求解所用 API 节点名"""
    extract_model: str | None = None
    """覆盖提取模型名（可选，留空则使用 api_config.json 中配置）"""
    solve_model: str | None = None
    """覆盖求解模型名（可选）"""
    max_workers: int = 1
    """并发求解线程数，>1 时并发调用 API"""
    skip_pdf: bool = False
    skip_extract: bool = False
    skip_solve: bool = False


# ---------------------------------------------------------------------------
# 核心 Pipeline 类
# ---------------------------------------------------------------------------

class Pipeline:
    """
    四阶段流水线执行器。

    Parameters:
        config: 运行配置。
        event_handler: 可选回调，接收 PipelineEvent，用于 GUI 进度更新。
    """

    def __init__(
        self,
        config: PipelineConfig | None = None,
        event_handler: Callable[[PipelineEvent], None] | None = None,
    ) -> None:
        self.config = config or PipelineConfig()
        self._event_handler = event_handler or (lambda _: None)
        self._root = Path(__file__).resolve().parent.parent
        self._resolve_paths()

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _resolve_paths(self) -> None:
        cfg = self.config
        root = self._root

        self.config_path = (
            Path(cfg.config_path) if cfg.config_path
            else root / "input" / "chapter_config.json"
        )

        if cfg.pdf_path:
            self.pdf_path = Path(cfg.pdf_path)
        else:
            try:
                chapter_cfg = load_chapter_config(self.config_path)
                cfg_pdf = chapter_cfg.get("pdf_path")
            except Exception:
                cfg_pdf = None
            if cfg_pdf:
                p = Path(cfg_pdf)
                self.pdf_path = p if p.is_absolute() else (root / p).resolve()
            else:
                self.pdf_path = root / "input" / "textbook.pdf"

        self.output_base = get_output_base(root, self.config_path)
        setup_log_file(self.output_base / "run.log")

    def _emit(self, event: PipelineEvent) -> None:
        """向外发送事件，同时写入 logger（异常不向上传播）。"""
        try:
            self._event_handler(event)
        except Exception as exc:
            logger.warning("event_handler 抛出异常，已忽略: %s", exc)

    def _run_stage(self, stage: str, label: str, runner: Callable[[], None]) -> None:
        """统一阶段执行框架：emit start  run  emit complete/error。"""
        self._emit(PipelineEvent(type=EVENT_STAGE_START, stage=stage, message=f"{label} 开始"))
        t0 = time.monotonic()
        try:
            runner()
        except Exception as exc:
            elapsed = time.monotonic() - t0
            logger.error("%s 失败: %s", label, exc)
            self._emit(PipelineEvent(
                type=EVENT_STAGE_ERROR, stage=stage,
                message=f"{label} 失败: {exc}",
                elapsed=elapsed, data={"error": str(exc)},
            ))
            raise
        elapsed = time.monotonic() - t0
        logger.info("%s 完成（%.1f 秒）", label, elapsed)
        self._emit(PipelineEvent(
            type=EVENT_STAGE_COMPLETE, stage=stage,
            message=f"{label} 完成", elapsed=elapsed,
        ))

    # ------------------------------------------------------------------
    # 单阶段公开方法（可供 GUI 按需调用）
    # ------------------------------------------------------------------

    def run_pdf(self) -> None:
        """Phase 1: PDF 切片，将教材页面渲染为 PNG。"""
        self._run_stage(
            STAGE_PDF, "PDF 切片",
            lambda: _run_pdf(
                config_path=self.config_path,
                pdf_path=self.pdf_path,
                output_base=self.output_base,
            ),
        )

    def run_extract(self) -> None:
        """Phase 2: VLM 提取习题（按章节）。"""
        self._run_stage(
            STAGE_EXTRACT, "VLM 提取习题",
            lambda: _run_vlm(
                config_path=self.config_path,
                pdf_path=self.pdf_path,
                output_base=self.output_base,
                provider=self.config.extract_provider,
                model=self.config.extract_model,
            ),
        )

    def run_solve(self) -> None:
        """Phase 3: 推理模型逐题求解，生成教辅级答案。"""
        self._run_stage(
            STAGE_SOLVE, "推理求解",
            lambda: _run_solver(
                output_base=self.output_base,
                config_path=self.config_path,
                provider=self.config.solve_provider,
                model=self.config.solve_model,
                max_workers=self.config.max_workers,
            ),
        )

    def run_latex(self) -> Path:
        """Phase 4: LaTeX 组装，生成 .tex 文件并返回路径。"""
        holder: list[Path] = []
        self._run_stage(
            STAGE_LATEX, "LaTeX 组装",
            lambda: holder.append(
                _run_latex(config_path=self.config_path, output_base=self.output_base)
            ),
        )
        return holder[0] if holder else (self.output_base / "final_solution.tex")

    # ------------------------------------------------------------------
    # 一键运行
    # ------------------------------------------------------------------

    def run(self) -> Path:
        """按顺序执行全部阶段，返回最终 .tex 文件路径。"""
        cfg = self.config
        t0 = time.monotonic()

        if not cfg.skip_pdf:
            self.run_pdf()
        else:
            logger.info("跳过 PDF 切片。")

        if not cfg.skip_extract:
            self.run_extract()
        else:
            logger.info("跳过 VLM 提取。")

        if not cfg.skip_solve:
            self.run_solve()
        else:
            logger.info("跳过推理求解。")

        tex_path = self.run_latex()

        total_elapsed = time.monotonic() - t0
        self._emit(PipelineEvent(
            type=EVENT_PIPELINE_COMPLETE, stage="",
            message=f"流水线全部完成（总耗时 {total_elapsed:.1f} 秒）",
            elapsed=total_elapsed,
            data={"tex_path": str(tex_path)},
        ))
        return tex_path

    # ------------------------------------------------------------------
    # 状态查询（供 GUI 展示断点续传状态）
    # ------------------------------------------------------------------

    @property
    def output_paths(self) -> dict[str, Path]:
        """返回各阶段输出文件路径字典（文件不一定已存在）。"""
        return {
            "images_dir": self.output_base / "images",
            "extracted_tasks": self.output_base / "extracted_tasks.json",
            "solved_answers": self.output_base / "solved_answers.json",
            "solve_failures": self.output_base / "solve_failures.json",
            "final_tex": self.output_base / "final_solution.tex",
            "run_log": self.output_base / "run.log",
        }

    @property
    def completed_stages(self) -> list[str]:
        """根据输出文件是否存在推断已完成阶段（供 GUI 初始化进度条）。"""
        paths = self.output_paths
        result = []
        if list((self.output_base / "images").glob("*.png")):
            result.append(STAGE_PDF)
        if paths["extracted_tasks"].exists():
            result.append(STAGE_EXTRACT)
        if paths["solved_answers"].exists():
            result.append(STAGE_SOLVE)
        if paths["final_tex"].exists():
            result.append(STAGE_LATEX)
        return result
