"""
Watchdog 文件变更监听器 + SSE 推送

监控 PROJECT_ROOT/.webnovel/ 下的运行态文件与 observability 目录，
通过 SSE 通知前端刷新数据与任务状态。
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer


class _WebnovelFileHandler(FileSystemEventHandler):
    WATCH_NAMES = {"state.json", "index.db", "workflow_state.json"}
    WATCH_SUFFIXES = {".json", ".jsonl", ".db", ".md"}

    def __init__(self, notify_callback):
        super().__init__()
        self._notify = notify_callback

    def on_modified(self, event):
        self._handle(event, "modified")

    def on_created(self, event):
        self._handle(event, "created")

    def _handle(self, event: FileModifiedEvent | FileCreatedEvent, kind: str):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.name in self.WATCH_NAMES or "observability" in path.parts or path.suffix in self.WATCH_SUFFIXES:
            self._notify(event.src_path, kind)


class FileWatcher:
    def __init__(self):
        self._observer: Observer | None = None
        self._subscribers: list[asyncio.Queue] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._watched_dirs: set[str] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=128)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    def _on_change(self, path: str, kind: str):
        msg = json.dumps({"file": Path(path).name, "path": path, "kind": kind, "ts": time.time()})
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._dispatch, msg)

    def _dispatch(self, msg: str):
        for q in self._subscribers:
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(json.dumps({"kind": "overflow", "ts": time.time()}))
                except asyncio.QueueFull:
                    pass

    def start(self, watch_dir: Path, loop: asyncio.AbstractEventLoop):
        self.watch(watch_dir, loop)

    def watch(self, watch_dir: Path, loop: asyncio.AbstractEventLoop):
        resolved = str(Path(watch_dir).resolve())
        self._loop = loop
        if self._observer is None:
            handler = _WebnovelFileHandler(self._on_change)
            self._observer = Observer()
            self._observer.daemon = True
            self._observer.schedule(handler, resolved, recursive=True)
            self._observer.start()
            self._watched_dirs.add(resolved)
            return
        if resolved in self._watched_dirs:
            return
        handler = _WebnovelFileHandler(self._on_change)
        self._observer.schedule(handler, resolved, recursive=True)
        self._watched_dirs.add(resolved)

    def stop(self):
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=3)
            self._observer = None
        self._watched_dirs.clear()
