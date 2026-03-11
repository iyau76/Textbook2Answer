# -*- coding: utf-8 -*-
"""
后台任务队列系统。
支持暂停/恢复/取消任务。
"""
import json
import threading
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any
from datetime import datetime


class TaskStatus(Enum):
    """任务状态。"""
    PENDING = "pending"          # 等待中
    RUNNING = "running"          # 运行中
    PAUSED = "paused"            # 暂停中
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"            # 失败
    CANCELLED = "cancelled"      # 已取消


@dataclass
class TaskConfig:
    """任务配置。"""
    project_id: str
    action: str
    extract_provider: Optional[str] = None
    solve_provider: Optional[str] = None
    extract_model: Optional[str] = None
    solve_model: Optional[str] = None
    

@dataclass
class TaskProgress:
    """任务进度。"""
    current_step: str = ""           # 当前步骤
    current_item: int = 0            # 当前处理的项
    total_items: int = 0             # 总项数
    percentage: float = 0.0          # 完成百分比
    message: str = ""                # 进度信息


@dataclass
class Task:
    """后台任务。"""
    task_id: str
    config: TaskConfig
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    progress: TaskProgress = field(default_factory=TaskProgress)
    elapsed_seconds: float = 0.0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        data = asdict(self)
        data['status'] = self.status.value
        data['progress'] = asdict(self.progress)
        return data


class TaskQueue:
    """任务队列管理器。"""

    def __init__(self, queue_dir: Optional[Path | str] = None):
        self.queue_dir = Path(queue_dir) if queue_dir else Path.cwd() / ".t2a_queue"
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        
        self.tasks: Dict[str, Task] = {}
        self.task_threads: Dict[str, threading.Thread] = {}
        self.task_events: Dict[str, threading.Event] = {}  # 用于暂停/恢复
        self.task_lock = threading.Lock()
        
        self._load_queue()

    def _get_queue_file(self) -> Path:
        """获取队列文件路径。"""
        return self.queue_dir / "queue.json"

    def _load_queue(self) -> None:
        """从文件加载队列。"""
        queue_file = self._get_queue_file()
        if not queue_file.exists():
            return
        
        try:
            with open(queue_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for task_data in data.get("tasks", []):
                    task_id = task_data["task_id"]
                    config = TaskConfig(**task_data["config"])
                    progress = TaskProgress(**task_data.get("progress", {}))
                    
                    task = Task(
                        task_id=task_id,
                        config=config,
                        status=TaskStatus(task_data.get("status", "pending")),
                        created_at=task_data.get("created_at", ""),
                        started_at=task_data.get("started_at"),
                        completed_at=task_data.get("completed_at"),
                        progress=progress,
                        elapsed_seconds=task_data.get("elapsed_seconds", 0.0),
                        error_message=task_data.get("error_message"),
                    )
                    self.tasks[task_id] = task
        except Exception:
            pass

    def _save_queue(self) -> None:
        """保存队列到文件。"""
        queue_file = self._get_queue_file()
        data = {
            "timestamp": datetime.now().isoformat(),
            "tasks": [task.to_dict() for task in self.tasks.values()]
        }
        try:
            with open(queue_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add_task(
        self,
        task_id: str,
        project_id: str,
        action: str,
        extract_provider: Optional[str] = None,
        solve_provider: Optional[str] = None,
        extract_model: Optional[str] = None,
        solve_model: Optional[str] = None,
    ) -> Task:
        """添加任务到队列。"""
        with self.task_lock:
            if task_id in self.tasks:
                raise ValueError(f"Task {task_id} already exists")
            
            config = TaskConfig(
                project_id=project_id,
                action=action,
                extract_provider=extract_provider,
                solve_provider=solve_provider,
                extract_model=extract_model,
                solve_model=solve_model,
            )
            
            task = Task(task_id=task_id, config=config)
            self.tasks[task_id] = task
            self.task_events[task_id] = threading.Event()
            self.task_events[task_id].set()  # 初始设置为已触发（未暂停）
            
            self._save_queue()
            return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务。"""
        with self.task_lock:
            return self.tasks.get(task_id)

    def list_tasks(self, status: Optional[TaskStatus] = None) -> List[Task]:
        """列出任务。"""
        with self.task_lock:
            if status:
                return [t for t in self.tasks.values() if t.status == status]
            return list(self.tasks.values())

    def update_task_status(self, task_id: str, status: TaskStatus, message: Optional[str] = None) -> None:
        """更新任务状态。"""
        with self.task_lock:
            if task_id not in self.tasks:
                return
            
            task = self.tasks[task_id]
            task.status = status
            
            if status == TaskStatus.RUNNING and not task.started_at:
                task.started_at = datetime.now().isoformat()
            elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                task.completed_at = datetime.now().isoformat()
            
            if message:
                task.error_message = message
            
            self._save_queue()

    def update_task_progress(
        self,
        task_id: str,
        current_step: str = "",
        current_item: int = 0,
        total_items: int = 0,
        message: str = "",
    ) -> None:
        """更新任务进度。"""
        with self.task_lock:
            if task_id not in self.tasks:
                return
            
            task = self.tasks[task_id]
            task.progress.current_step = current_step
            task.progress.current_item = current_item
            task.progress.total_items = total_items
            task.progress.message = message
            
            if total_items > 0:
                task.progress.percentage = (current_item / total_items) * 100.0
            
            if task.started_at:
                start_time = datetime.fromisoformat(task.started_at)
                task.elapsed_seconds = (datetime.now() - start_time).total_seconds()

    def pause_task(self, task_id: str) -> bool:
        """暂停任务。"""
        with self.task_lock:
            if task_id not in self.tasks:
                return False
            
            task = self.tasks[task_id]
            if task.status != TaskStatus.RUNNING:
                return False
            
            task.status = TaskStatus.PAUSED
            if task_id in self.task_events:
                self.task_events[task_id].clear()  # 清除事件，线程会在等待此事件时阻塞
            
            self._save_queue()
            return True

    def resume_task(self, task_id: str) -> bool:
        """恢复任务。"""
        with self.task_lock:
            if task_id not in self.tasks:
                return False
            
            task = self.tasks[task_id]
            if task.status != TaskStatus.PAUSED:
                return False
            
            task.status = TaskStatus.RUNNING
            if task_id in self.task_events:
                self.task_events[task_id].set()  # 设置事件，线程会继续运行
            
            self._save_queue()
            return True

    def cancel_task(self, task_id: str) -> bool:
        """取消任务。"""
        with self.task_lock:
            if task_id not in self.tasks:
                return False
            
            task = self.tasks[task_id]
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return False
            
            task.status = TaskStatus.CANCELLED
            if task_id in self.task_events:
                self.task_events[task_id].set()  # 设置事件，任务应检查此标志提前退出
            
            self._save_queue()
            return True

    def check_pause_flag(self, task_id: str) -> None:
        """检查暂停标志（任务在长时间操作中应定期调用）。"""
        if task_id in self.task_events:
            self.task_events[task_id].wait()  # 如果事件被清除（暂停），此处会阻塞

    def is_task_cancelled(self, task_id: str) -> bool:
        """检查任务是否被取消。"""
        with self.task_lock:
            if task_id not in self.tasks:
                return False
            return self.tasks[task_id].status == TaskStatus.CANCELLED

    def clear_completed_tasks(self, older_than_hours: int = 24) -> int:
        """清空已完成的旧任务。"""
        cutoff_time = datetime.now().timestamp() - (older_than_hours * 3600)
        removed = 0
        
        with self.task_lock:
            tasks_to_remove = []
            for task_id, task in self.tasks.items():
                if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                    if task.completed_at:
                        completed_time = datetime.fromisoformat(task.completed_at).timestamp()
                        if completed_time < cutoff_time:
                            tasks_to_remove.append(task_id)
            
            for task_id in tasks_to_remove:
                del self.tasks[task_id]
                self.task_events.pop(task_id, None)
                removed += 1
            
            if removed > 0:
                self._save_queue()
        
        return removed
