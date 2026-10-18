from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable
from .store import Store, now


def safe_error(exc: Exception) -> str:
    message = str(exc)[:1200]
    message = re.sub(r"(?i)(access_token|refresh_token|client_secret|api_key|token|code)=([^&\s]+)", r"\1=[redacted]", message)
    return f"{type(exc).__name__}: {message}"


class TaskManager:
    def __init__(self, store: Store):
        self.store = store
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="trade-task")
        self._lifecycle_lock = threading.RLock()
        self._accepting = True
        self._futures = set()
        # A prior process may have stopped mid-task. Never silently reexecute a send.
        for task in store.list("tasks"):
            if task.get("state") in {"queued", "running"}:
                task.update(state="interrupted", error="上次程序退出；请核对进度后按指令继续，邮件不得整批重发")
                store.put("tasks", task, task["id"])

    def submit(self, kind: str, func: Callable, *args, **kwargs) -> dict:
        with self._lifecycle_lock:
            if not self._accepting:
                raise ValueError("程序正在退出，请重新打开后再启动任务")
            return self._submit(kind, func, *args, **kwargs)

    def _submit(self, kind: str, func: Callable, *args, **kwargs) -> dict:
        task = self.store.put("tasks", {"kind": kind, "state": "queued", "result": None, "error": None})
        def run():
            self.store.put("tasks", {**task, "state": "running", "started_at": now()}, task["id"])
            try:
                result = func(*args, **kwargs)
                self.store.put("tasks", {**task, "state": "completed", "finished_at": now(), "result": result}, task["id"])
            except Exception as exc:
                error = safe_error(exc)
                self.store.put("tasks", {**task, "state": "failed", "finished_at": now(), "error": error}, task["id"])
                self.store.event("task_failed", {"task_id": task["id"], "kind": kind, "error": error})
        future = self.pool.submit(run)
        self._futures.add(future)
        future.add_done_callback(self._finished)
        return task

    def _finished(self, future):
        with self._lifecycle_lock:
            self._futures.discard(future)

    def try_quiesce(self) -> bool:
        """Atomically refuse new work only when all submitted work has ended."""
        with self._lifecycle_lock:
            if any(not future.done() for future in self._futures):
                return False
            self._accepting = False
            return True

    def close(self):
        with self._lifecycle_lock:
            self._accepting = False
        self.pool.shutdown(wait=False, cancel_futures=True)
