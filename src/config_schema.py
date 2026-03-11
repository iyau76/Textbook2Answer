# -*- coding: utf-8 -*-
"""
配置验证模块 — 检查 api_config.json 和 chapter_config.json 的格式合法性。

命令行用法::

    python -m src.config_schema          # 检查默认路径的两份配置
    python -m src.config_schema --api config/api_config.json
    python -m src.config_schema --chapter input/chapter_config.json

编程用法::

    from src.config_schema import validate_api_config, validate_chapter_config
    errors = validate_api_config({"gemini": {...}})
    if errors:
        for e in errors:
            print(e)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# api_config.json 校验
# ---------------------------------------------------------------------------

_REQUIRED_API_FIELDS = ("api_key", "model")
_KNOWN_PROVIDERS = ("gemini", "openai_compatible")


def validate_api_config(config: dict[str, Any]) -> list[str]:
    """
    校验 api_config.json 内容格式。

    Returns:
        错误信息列表；为空则表示无错误。
    """
    errors: list[str] = []
    if not isinstance(config, dict):
        return ["api_config 根节点应为 JSON 对象（字典）"]

    for node_name, node in config.items():
        if not isinstance(node, dict):
            errors.append(f"节点 [{node_name}] 应为对象（字典），实际为 {type(node).__name__}")
            continue
        for field in _REQUIRED_API_FIELDS:
            if not node.get(field):
                errors.append(f"节点 [{node_name}] 缺少必填字段 '{field}'")
        provider = node.get("provider", "")
        if provider and provider not in _KNOWN_PROVIDERS:
            errors.append(
                f"节点 [{node_name}].provider = '{provider}' 未知，"
                f"已知值：{_KNOWN_PROVIDERS}"
            )
        timeout = node.get("timeout_seconds")
        if timeout is not None and not isinstance(timeout, (int, float)):
            errors.append(f"节点 [{node_name}].timeout_seconds 应为数字")
        retries = node.get("max_retries")
        if retries is not None and (not isinstance(retries, int) or retries < 0):
            errors.append(f"节点 [{node_name}].max_retries 应为非负整数")

    return errors


# ---------------------------------------------------------------------------
# chapter_config.json 校验
# ---------------------------------------------------------------------------

_REQUIRED_CHAPTER_FIELDS = ("chapter_name", "pages")


def validate_chapter_config(config: dict[str, Any]) -> list[str]:
    """
    校验 chapter_config.json 内容格式。

    Returns:
        错误信息列表；为空则表示无错误。
    """
    errors: list[str] = []
    if not isinstance(config, dict):
        return ["chapter_config 根节点应为 JSON 对象"]

    if not config.get("book_title"):
        errors.append("chapter_config 缺少 'book_title' 字段")

    chapters = config.get("chapters")
    if not isinstance(chapters, list) or len(chapters) == 0:
        errors.append("chapter_config 缺少 'chapters' 数组或数组为空")
        return errors

    all_pages: list[int] = []
    for i, ch in enumerate(chapters):
        prefix = f"chapters[{i}]"
        if not isinstance(ch, dict):
            errors.append(f"{prefix} 应为对象")
            continue
        for field in _REQUIRED_CHAPTER_FIELDS:
            if not ch.get(field):
                errors.append(f"{prefix} 缺少字段 '{field}'")
        pages = ch.get("pages", [])
        if not isinstance(pages, list) or len(pages) == 0:
            errors.append(f"{prefix} 'pages' 不能为空")
        else:
            for p in pages:
                try:
                    page_int = int(p)
                    if page_int <= 0:
                        errors.append(f"{prefix}.pages 包含非正页码：{p}")
                    all_pages.append(page_int)
                except (ValueError, TypeError):
                    errors.append(f"{prefix}.pages 包含非整数页码：{p!r}")

    # 检测重复页码
    seen: set[int] = set()
    for p in all_pages:
        if p in seen:
            errors.append(f"页码 {p} 在多个章节中出现（可能导致重复提取）")
        seen.add(p)

    return errors


# ---------------------------------------------------------------------------
# 文件级校验便捷函数
# ---------------------------------------------------------------------------

def validate_api_config_file(path: str | Path) -> list[str]:
    """从文件路径读取并校验 api_config.json。"""
    path = Path(path)
    if not path.exists():
        return [f"文件不存在: {path}"]
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"JSON 解析失败: {exc}"]
    return validate_api_config(config)


def validate_chapter_config_file(path: str | Path) -> list[str]:
    """从文件路径读取并校验 chapter_config.json。"""
    path = Path(path)
    if not path.exists():
        return [f"文件不存在: {path}"]
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"JSON 解析失败: {exc}"]
    return validate_chapter_config(config)


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="校验 Textbook2Answer 配置文件")
    root = Path(__file__).resolve().parent.parent
    parser.add_argument(
        "--api",
        default=None,
        help="api_config.json 路径，默认自动查找",
    )
    parser.add_argument(
        "--chapter",
        default=str(root / "input" / "chapter_config.json"),
        help="chapter_config.json 路径",
    )
    args = parser.parse_args()

    # 自动查找 api_config.json
    api_path: Path
    if args.api:
        api_path = Path(args.api)
    else:
        candidates = [root / "config" / "api_config.json", root / "api_config.json"]
        api_path = next((p for p in candidates if p.exists()), candidates[0])

    ok = True
    print(f"检查 api_config: {api_path}")
    for err in validate_api_config_file(api_path):
        print(f"  ✗ {err}")
        ok = False
    if ok:
        print("  ✓ api_config 格式正确")

    print(f"检查 chapter_config: {args.chapter}")
    chapter_ok = True
    for err in validate_chapter_config_file(args.chapter):
        print(f"  ✗ {err}")
        chapter_ok = False
    if chapter_ok:
        print("  ✓ chapter_config 格式正确")

    sys.exit(0 if (ok and chapter_ok) else 1)
