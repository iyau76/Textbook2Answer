# -*- coding: utf-8 -*-
"""
通用工具函数和 CheckpointManager。
供 vlm_extractor 和 reasoning_solver 的断点续传逻辑复用。
"""
import json
from pathlib import Path
from typing import Any

from .logger import logger


class CheckpointManager:
    """
    轻量级断点续传管理器。
    将增量结果持久化到 JSON 文件，支持按任意键去重。

    典型用法（VLM 按章节）::

        cm = CheckpointManager(output_base / "extracted_tasks.json", id_key="page_num")
        if cm.is_done(page_num):
            continue
        ...
        cm.append(tasks)   # 追加并立即写盘

    典型用法（Solver 按题目）::

        cm = CheckpointManager(output_base / "solved_answers.json", id_key="question_id")
        if cm.is_done(qid):
            continue
        ...
        cm.upsert(answer)  # 按 key 更新并立即写盘
    """

    def __init__(self, checkpoint_file: Path, id_key: str = "question_id"):
        self._path = Path(checkpoint_file)
        self._id_key = id_key
        self._items: list[dict] = self._load()
        self._id_set: set[Any] = {item.get(id_key) for item in self._items if item.get(id_key) is not None}

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------
    def _load(self) -> list[dict]:
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return data
                logger.warning("Checkpoint 文件格式异常（非数组），将重新开始: %s", self._path)
            except Exception as exc:
                logger.warning("读取 checkpoint 失败，将重新开始: %s — %s", self._path, exc)
        return []

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def is_done(self, id_val: Any) -> bool:
        return id_val in self._id_set

    def get_all(self) -> list[dict]:
        return list(self._items)

    def get_by_id(self, id_val: Any) -> dict | None:
        for item in self._items:
            if item.get(self._id_key) == id_val:
                return item
        return None

    def __len__(self) -> int:
        return len(self._items)

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    def append(self, items: list[dict]) -> None:
        """批量追加（已存在的 id 不重复添加），立即写盘。"""
        for item in items:
            id_val = item.get(self._id_key)
            if id_val not in self._id_set:
                self._items.append(item)
                if id_val is not None:
                    self._id_set.add(id_val)
        self._save()

    def upsert(self, item: dict) -> None:
        """按 id_key 更新已有条目或追加新条目，立即写盘。"""
        id_val = item.get(self._id_key)
        for i, existing in enumerate(self._items):
            if existing.get(self._id_key) == id_val:
                self._items[i] = item
                self._save()
                return
        self._items.append(item)
        if id_val is not None:
            self._id_set.add(id_val)
        self._save()

    def remove(self, id_val: Any) -> None:
        """删除某 id 的条目（用于强制重跑）。"""
        self._items = [it for it in self._items if it.get(self._id_key) != id_val]
        self._id_set.discard(id_val)
        self._save()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._items, f, ensure_ascii=False, indent=2)


def safe_json_load(path: Path) -> list | dict | None:
    """安全读取 JSON 文件；失败时返回 None 并写日志。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.error("读取 JSON 文件失败: %s — %s", path, exc)
        return None
