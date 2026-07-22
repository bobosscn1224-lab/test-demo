from __future__ import annotations
import os
import json
import asyncio
import inspect
import logging
import threading
from collections.abc import Awaitable, Callable
from datetime import datetime
from app.utils.file_parser import SUPPORTED_EXTENSIONS
from app.services.rag_service import rag_service
from app.services._paths import BACKEND_DIR
from app.services.json_store import atomic_write_json

logger = logging.getLogger(__name__)

SCAN_DEBOUNCE_SECONDS = 2.0
EXCLUDED_DIRS = {"Backup0928", "BACKUP1225", "backup", "BACKUP", ".git", "__pycache__", "node_modules"}
ProgressCallback = Callable[[dict], "None | Awaitable[None]"]


class FileScanner:
    """Scans configured directories and indexes files into the RAG knowledge base."""

    STATE_PATH = BACKEND_DIR / "data" / "scan_state.json"

    def __init__(self, watch_dirs: list[str] | None = None):
        self.watch_dirs: list[str] = [os.path.abspath(d) for d in (watch_dirs or []) if os.path.isdir(d)]
        self._observer = None
        self._known_files: dict[str, float] = {}  # path -> mtime
        self._watch_thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._scan_lock = asyncio.Lock()
        self._load_state()

    def _load_state(self) -> None:
        """Restore _known_files from persisted scan state."""
        try:
            if self.STATE_PATH.exists():
                with self.STATE_PATH.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                loaded = data.get("known_files", {})
                # Validate: only keep files that still exist on disk
                for path, mtime in loaded.items():
                    try:
                        if os.path.exists(path) and os.path.getmtime(path) <= mtime:
                            self._known_files[path] = mtime
                    except OSError:
                        pass
                logger.info("Loaded %d known files from scan state (%d still valid)",
                           len(loaded), len(self._known_files))
        except json.JSONDecodeError as exc:
            stamp = datetime.now().strftime("%Y%m%d%H%M%S")
            quarantine = self.STATE_PATH.with_name(f"{self.STATE_PATH.name}.corrupt-{stamp}")
            try:
                os.replace(str(self.STATE_PATH), str(quarantine))
                logger.warning("Corrupt scan state moved to %s: %s", quarantine, exc)
            except OSError:
                logger.warning("Failed to quarantine corrupt scan state: %s", exc)
        except Exception as exc:
            logger.warning("Failed to load scan state: %s", exc)

    def _save_state(self) -> None:
        """Persist _known_files to disk."""
        try:
            atomic_write_json(self.STATE_PATH, {
                "known_files": self._known_files,
                "last_scan": datetime.utcnow().isoformat(),
            })
        except Exception as exc:
            logger.warning("Failed to save scan state: %s", exc)

    @property
    def is_watching(self) -> bool:
        return self._observer is not None and self._observer.is_alive()

    def _empty_result(self, status: str) -> dict:
        return {
            "status": status,
            "added": 0,
            "updated": 0,
            "reindexed": 0,
            "skipped": 0,
            "scanned": 0,
            "deleted": 0,
            "errors": 0,
            "failed_files": [],
        }

    async def _emit_progress(self, callback: ProgressCallback | None, data: dict) -> None:
        if not callback:
            return
        result = callback(data)
        if inspect.isawaitable(result):
            await result

    async def full_scan(
        self,
        force_reindex: bool = False,
        progress_callback: ProgressCallback | None = None,
    ) -> dict:
        """Scan all watch directories and index files.

        By default this is an incremental scan: only new or modified files are
        indexed. Set force_reindex=True to rebuild every supported file so new
        parsing/chunking/OCR logic is applied to existing documents.
        """
        if not self.watch_dirs:
            return self._empty_result("no_dirs")

        if not rag_service.is_ready:
            await rag_service.initialize()
        if not rag_service.is_ready:
            return self._empty_result("rag_not_ready")

        if self._scan_lock.locked():
            return self._empty_result("busy")

        async with self._scan_lock:
            return await self._full_scan_locked(force_reindex, progress_callback)

    async def _full_scan_locked(
        self,
        force_reindex: bool = False,
        progress_callback: ProgressCallback | None = None,
    ) -> dict:

        added = 0
        updated = 0
        reindexed = 0
        skipped = 0
        scanned = 0
        deleted = 0
        errors = 0
        failed_files: list[str] = []

        current_files: dict[str, float] = {}
        supported_files: list[tuple[str, float]] = []

        for watch_dir in self.watch_dirs:
            for root, dirs, files in os.walk(watch_dir):
                dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
                for filename in files:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext not in SUPPORTED_EXTENSIONS:
                        continue
                    if filename.startswith("~$"):
                        continue
                    file_path = os.path.join(root, filename)
                    try:
                        mtime = os.path.getmtime(file_path)
                        current_files[file_path] = mtime
                    except OSError:
                        continue
                    supported_files.append((file_path, mtime))

        total_files = len(supported_files)
        await self._emit_progress(progress_callback, {
            "stage": "scanning",
            "scanned": 0,
            "total_files": total_files,
            "current_file": "",
        })

        for index, (file_path, mtime) in enumerate(supported_files, 1):
            try:
                scanned += 1
                await self._emit_progress(progress_callback, {
                    "stage": "indexing" if force_reindex else "scanning",
                    "scanned": scanned,
                    "total_files": total_files,
                    "current_file": file_path,
                    "added": added,
                    "updated": updated,
                    "reindexed": reindexed,
                    "skipped": skipped,
                    "deleted": deleted,
                    "errors": errors,
                })

                if force_reindex:
                    from app.services.rag_service import _make_doc_id
                    doc_id = _make_doc_id(file_path)
                    await rag_service.delete_doc(doc_id)
                    chunk_ids = await rag_service.index_file(file_path)
                    if chunk_ids:
                        reindexed += 1
                        logger.info("Force re-indexed file: %s (%d chunks)", file_path, len(chunk_ids))
                    else:
                        errors += 1
                        failed_files.append(file_path)
                elif file_path not in self._known_files:
                    # New file
                    chunk_ids = await rag_service.index_file(file_path)
                    if chunk_ids:
                        added += 1
                        logger.info("Indexed new file: %s (%d chunks)", file_path, len(chunk_ids))
                    else:
                        errors += 1
                        failed_files.append(file_path)
                elif self._known_files[file_path] < mtime:
                    # Updated file
                    from app.services.rag_service import _make_doc_id
                    doc_id = _make_doc_id(file_path)
                    await rag_service.delete_doc(doc_id)
                    chunk_ids = await rag_service.index_file(file_path)
                    if chunk_ids:
                        updated += 1
                        logger.info("Re-indexed updated file: %s", file_path)
                    else:
                        errors += 1
                        failed_files.append(file_path)
                else:
                    skipped += 1
            except Exception:
                errors += 1
                failed_files.append(file_path)
                logger.warning("Failed to index file during scan: %s", file_path, exc_info=True)

        # Detect deleted files
        for old_path in list(self._known_files):
            if old_path not in current_files:
                from app.services.rag_service import _make_doc_id
                doc_id = _make_doc_id(old_path)
                await rag_service.delete_doc(doc_id)
                deleted += 1
                logger.info("Removed deleted file from index: %s", old_path)

        self._known_files = current_files
        self._save_state()
        return {
            "status": "ok",
            "added": added,
            "updated": updated,
            "reindexed": reindexed,
            "skipped": skipped,
            "scanned": scanned,
            "deleted": deleted,
            "errors": errors,
            "failed_files": failed_files[:50],
        }

    async def scan_directory(self, directory: str) -> int:
        """Scan a single directory and index files. Returns count of indexed files."""
        if not os.path.isdir(directory):
            return 0

        if not rag_service.is_ready:
            return 0

        count = 0
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if ext not in SUPPORTED_EXTENSIONS:
                    continue
                if filename.startswith("~$"):
                    continue
                file_path = os.path.join(root, filename)
                try:
                    chunk_ids = await rag_service.index_file(file_path)
                    if chunk_ids:
                        self._known_files[file_path] = os.path.getmtime(file_path)
                        count += 1
                except Exception:
                    logger.warning("Failed to index %s", file_path, exc_info=True)
        return count

    def start_watching(self) -> None:
        """Start watchdog-based file monitoring in a background thread."""
        if not self.watch_dirs:
            logger.warning("No watch directories configured, skipping file watcher")
            return

        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("No running event loop, file watcher callbacks cannot schedule indexing")
            return

        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            logger.warning("watchdog not installed, file watcher unavailable")
            return

        scanner = self

        class Handler(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory:
                    scanner._schedule_reindex(event.src_path, "created")

            def on_modified(self, event):
                if not event.is_directory:
                    scanner._schedule_reindex(event.src_path, "modified")

            def on_deleted(self, event):
                if not event.is_directory:
                    scanner._schedule_delete(event.src_path)

        self._observer = Observer()
        for d in self.watch_dirs:
            if os.path.isdir(d):
                self._observer.schedule(Handler(), d, recursive=True)
                logger.info("Watching directory: %s", d)

        self._watch_thread = threading.Thread(target=self._observer.start, daemon=True)
        self._watch_thread.start()
        logger.info("File watcher started")

    def stop_watching(self) -> None:
        """Stop the file watcher."""
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            logger.info("File watcher stopped")

    def _schedule_reindex(self, file_path: str, reason: str) -> None:
        """Debounced re-index of a changed file."""
        if any(ex in file_path.split(os.sep) for ex in EXCLUDED_DIRS):
            return
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return

        loop = self._loop
        if not loop or loop.is_closed():
            return

        async def reindex():
            await asyncio.sleep(SCAN_DEBOUNCE_SECONDS)
            try:
                if not os.path.exists(file_path):
                    return
                from app.services.rag_service import _make_doc_id
                doc_id = _make_doc_id(file_path)
                await rag_service.delete_doc(doc_id)
                chunk_ids = await rag_service.index_file(file_path)
                if chunk_ids:
                    self._known_files[file_path] = os.path.getmtime(file_path)
                    self._save_state()
                    logger.info("Re-indexed %s file: %s (%d chunks)", reason, file_path, len(chunk_ids))
            except Exception:
                logger.warning("Failed to re-index %s", file_path, exc_info=True)

        asyncio.run_coroutine_threadsafe(reindex(), loop)

    def _schedule_delete(self, file_path: str) -> None:
        """Debounced deletion of a removed file from the index."""
        loop = self._loop
        if not loop or loop.is_closed():
            return

        async def remove():
            await asyncio.sleep(SCAN_DEBOUNCE_SECONDS)
            try:
                from app.services.rag_service import _make_doc_id
                doc_id = _make_doc_id(file_path)
                deleted = await rag_service.delete_doc(doc_id)
                self._known_files.pop(file_path, None)
                self._save_state()
                if deleted:
                    logger.info("Removed deleted file: %s", file_path)
            except Exception:
                logger.warning("Failed to remove %s from index", file_path, exc_info=True)

        asyncio.run_coroutine_threadsafe(remove(), loop)


file_scanner = FileScanner()
