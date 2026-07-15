import json
import logging
import asyncio
import uuid
import os
import time
from datetime import datetime
from urllib.parse import urlencode
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from app.services.rag_service import rag_service
from app.services.file_scanner import file_scanner
from app.services.feishu_service import feishu_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
scan_tasks: dict[str, dict] = {}

FEISHU_KB_TOKEN_PATH = os.path.abspath(os.path.join("data", "feishu_kb_import_user_token.json"))
FEISHU_KB_IMPORTED_PATH = os.path.abspath(os.path.join("data", "feishu_kb_imported_docs.json"))
FEISHU_KB_OAUTH_STATE = "knowledge_feishu_import"
FEISHU_KB_OAUTH_SCOPE_RAW = os.environ.get(
    "FEISHU_KB_OAUTH_SCOPE",
    "drive:drive:readonly drive:drive.metadata:readonly wiki:wiki:readonly docx:document:readonly space:document:retrieve minutes:minutes:readonly minutes:minutes.transcript:export minutes:minutes.basic:read",
)
_scope_parts = [
    scope for scope in FEISHU_KB_OAUTH_SCOPE_RAW.split()
    if scope != "doc:document:readonly"
]
for _required_scope in ("drive:drive.metadata:readonly", "offline_access"):
    if _required_scope not in _scope_parts:
        _scope_parts.append(_required_scope)
FEISHU_KB_OAUTH_SCOPE = " ".join(_scope_parts)
feishu_kb_last_callback: dict = {}


class WatchDirsConfig(BaseModel):
    watch_dirs: list[str]


class FeishuOAuthCode(BaseModel):
    code: str


class FeishuPreviewRequest(BaseModel):
    folder_token: str | None = None
    max_docs: int = 500
    recurse: bool = False
    include_wiki: bool = True


class FeishuImportDoc(BaseModel):
    name: str
    type: str | None = None
    token: str | None = None
    url: str


class FeishuImportRequest(BaseModel):
    docs: list[FeishuImportDoc]


class FeishuDocPreviewRequest(BaseModel):
    url: str
    name: str | None = None


class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"
    def render(self, content) -> bytes:
        return json.dumps(content, ensure_ascii=False, indent=None, separators=(",", ":")).encode("utf-8")


@router.get("/stats")
async def get_stats():
    stats = await rag_service.get_stats()
    stats["watch_dirs"] = file_scanner.watch_dirs
    stats["is_watching"] = file_scanner.is_watching
    return UTF8JSONResponse(stats)


@router.post("/scan")
async def trigger_scan(force: bool = False, background: bool = False):
    if background:
        task_id = str(uuid.uuid4())
        scan_tasks[task_id] = {
            "task_id": task_id,
            "state": "running",
            "status": "running",
            "force": force,
            "started_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "added": 0,
            "updated": 0,
            "reindexed": 0,
            "skipped": 0,
            "scanned": 0,
            "total_files": 0,
            "deleted": 0,
            "errors": 0,
            "failed_files": [],
            "current_file": "",
            "total_chunks": 0,
            "unique_docs": 0,
        }
        asyncio.create_task(_run_scan_task(task_id, force))
        return UTF8JSONResponse(scan_tasks[task_id])

    result = await file_scanner.full_scan(force_reindex=force)
    stats = await rag_service.get_stats()
    result["total_chunks"] = stats.get("total_chunks", 0)
    result["unique_docs"] = stats.get("unique_docs", 0)
    return UTF8JSONResponse(result)


@router.get("/scan/{task_id}")
async def get_scan_task(task_id: str):
    task = scan_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Scan task not found")
    return UTF8JSONResponse(task)


async def _run_scan_task(task_id: str, force: bool):
    task = scan_tasks[task_id]

    async def on_progress(update: dict):
        task.update(update)
        task["updated_at"] = datetime.now().isoformat()

    try:
        result = await file_scanner.full_scan(force_reindex=force, progress_callback=on_progress)
        stats = await rag_service.get_stats()
        result["total_chunks"] = stats.get("total_chunks", 0)
        result["unique_docs"] = stats.get("unique_docs", 0)
        task.update(result)
        task["state"] = "completed" if result.get("status") == "ok" else "failed"
        task["finished_at"] = datetime.now().isoformat()
        task["updated_at"] = task["finished_at"]
    except Exception as exc:
        logger.warning("Background scan failed", exc_info=True)
        task["state"] = "failed"
        task["status"] = "error"
        task["error"] = str(exc)
        task["finished_at"] = datetime.now().isoformat()
        task["updated_at"] = task["finished_at"]


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    import os

    upload_dir = os.path.join("data", "uploads", "knowledge")
    os.makedirs(upload_dir, exist_ok=True)

    safe_name = os.path.basename(file.filename or "upload")
    if not safe_name or safe_name in {".", ".."}:
        safe_name = "upload"
    file_path = os.path.abspath(os.path.join(upload_dir, safe_name))
    upload_root = os.path.abspath(upload_dir)
    if os.path.commonpath([upload_root, file_path]) != upload_root:
        raise HTTPException(status_code=400, detail="Invalid filename")

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    chunk_ids = await rag_service.index_file(file_path)
    stats = await rag_service.get_stats()

    return UTF8JSONResponse({
        "filename": file.filename,
        "file_path": file_path,
        "chunks": len(chunk_ids),
        "total_chunks": stats.get("total_chunks", 0),
        "unique_docs": stats.get("unique_docs", 0),
    })


@router.delete("/{doc_id}")
async def delete_document(doc_id: str):
    deleted = await rag_service.delete_doc(doc_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    stats = await rag_service.get_stats()
    return UTF8JSONResponse({"deleted_chunks": deleted, "total_chunks": stats.get("total_chunks", 0)})


@router.get("/search")
async def search_knowledge(q: str, top_k: int = 5):
    results = await rag_service.search_raw(q, top_k)
    return UTF8JSONResponse({"query": q, "results": results, "count": len(results)})


@router.get("/config")
async def get_config():
    return UTF8JSONResponse({
        "watch_dirs": file_scanner.watch_dirs,
        "is_watching": file_scanner.is_watching,
    })


@router.post("/config")
async def update_config(config: WatchDirsConfig):
    import os
    valid_dirs = [os.path.abspath(d) for d in config.watch_dirs if os.path.isdir(d)]
    file_scanner.watch_dirs = valid_dirs

    if file_scanner.is_watching:
        file_scanner.stop_watching()
    file_scanner.start_watching()

    return UTF8JSONResponse({
        "watch_dirs": valid_dirs,
        "is_watching": file_scanner.is_watching,
    })


# ── Corrections (self-learning) ──────────────────────────────

class CorrectionCreate(BaseModel):
    question: str
    correct_answer: str


@router.get("/corrections")
async def list_corrections():
    corrections = await rag_service.list_corrections()
    return UTF8JSONResponse({"corrections": corrections, "count": len(corrections)})


@router.post("/corrections")
async def add_correction(req: CorrectionCreate):
    cid = await rag_service.add_correction(
        question=req.question,
        correct_answer=req.correct_answer,
        source="api",
    )
    return UTF8JSONResponse({"id": cid, "question": req.question, "correct_answer": req.correct_answer})


@router.delete("/corrections/{correction_id}")
async def delete_correction(correction_id: str):
    ok = await rag_service.delete_correction(correction_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Correction not found")
    return UTF8JSONResponse({"deleted": correction_id})


@router.get("/feishu/status")
async def feishu_import_status():
    token = await _get_valid_feishu_kb_token()
    token_file_exists = os.path.exists(FEISHU_KB_TOKEN_PATH)
    return UTF8JSONResponse({
        "authorized": bool(token),
        "scope": FEISHU_KB_OAUTH_SCOPE,
        "state": FEISHU_KB_OAUTH_STATE,
        "token_path": FEISHU_KB_TOKEN_PATH,
        "token_file_exists": token_file_exists,
        "last_callback": feishu_kb_last_callback,
    })


@router.get("/_feishu/debug")
async def feishu_import_debug():
    token_data = _load_feishu_kb_token()
    token_summary = None
    if token_data:
        now = time.time()
        token_summary = {
            "has_access_token": bool(token_data.get("access_token")),
            "has_refresh_token": bool(token_data.get("refresh_token")),
            "expires_in_seconds": int(float(token_data.get("expires_at") or 0) - now),
            "refresh_expires_in_seconds": int(float(token_data.get("refresh_expires_at") or 0) - now),
            "scope": token_data.get("scope"),
            "saved_at": token_data.get("saved_at"),
        }
    return UTF8JSONResponse({
        "step": "debug_state",
        "configured": {
            "app_id_prefix": (feishu_service.app_id or "")[:10],
            "has_app_secret": bool(feishu_service.app_secret),
            "redirect_uri": feishu_service.oauth_redirect_uri,
            "scope": FEISHU_KB_OAUTH_SCOPE,
            "state": FEISHU_KB_OAUTH_STATE,
        },
        "token": {
            "path": FEISHU_KB_TOKEN_PATH,
            "exists": os.path.exists(FEISHU_KB_TOKEN_PATH),
            "summary": token_summary,
        },
        "last_callback": feishu_kb_last_callback,
    })


@router.get("/feishu/auth-url")
async def feishu_import_auth_url(
    redirect_uri: str | None = Query(None, description="OAuth callback URL. Prefer the frontend app URL so it can capture code."),
):
    try:
        redirect = redirect_uri or feishu_service.oauth_redirect_uri
        if not redirect:
            raise RuntimeError("redirect_uri is required or set FEISHU_OAUTH_REDIRECT_URI")
        if not feishu_service.app_id:
            raise RuntimeError("Feishu not configured: set FEISHU_APP_ID")
        query = urlencode({
            "client_id": feishu_service.app_id,
            "redirect_uri": redirect,
            "response_type": "code",
            "state": FEISHU_KB_OAUTH_STATE,
            "scope": FEISHU_KB_OAUTH_SCOPE,
        })
        url = f"https://accounts.feishu.cn/open-apis/authen/v1/authorize?{query}"
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UTF8JSONResponse({
        "url": url,
        "redirect_uri": redirect,
        "scope": FEISHU_KB_OAUTH_SCOPE,
        "state": FEISHU_KB_OAUTH_STATE,
        "token_path": FEISHU_KB_TOKEN_PATH,
    })


@router.post("/feishu/oauth")
async def feishu_import_oauth(req: FeishuOAuthCode):
    code = _extract_feishu_code(req.code)
    if not code:
        raise HTTPException(status_code=400, detail="code is required")
    try:
        data = await feishu_service.exchange_oauth_code_v2(code)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{exc.__class__.__name__}: {str(exc) or 'no detail'}") from exc
    if data.get("code") != 0:
        raise HTTPException(status_code=400, detail={
            "stage": "oauth_exchange",
            "code": data.get("code"),
            "msg": data.get("msg") or data.get("message") or data.get("raw_text"),
            "http_status": data.get("_http_status"),
            "response": data,
        })
    token_data = data.get("data") or data
    if not token_data.get("access_token"):
        raise HTTPException(status_code=400, detail={
            "stage": "oauth_exchange",
            "message": "Feishu response did not include access_token",
            "response": data,
        })
    _save_feishu_kb_token(token_data)
    return UTF8JSONResponse({"ok": True, "authorized": True, "scope": FEISHU_KB_OAUTH_SCOPE})


@router.get("/feishu/search")
async def feishu_search(q: str, max_docs: int = 500):
    token = await _get_valid_feishu_kb_token()
    if not token:
        raise HTTPException(status_code=401, detail={
            "stage": "auth",
            "message": "Feishu knowledge import is not authorized",
            "token_path": FEISHU_KB_TOKEN_PATH,
            "scope": FEISHU_KB_OAUTH_SCOPE,
            "last_callback": feishu_kb_last_callback,
        })
    # Fetch all docs from Drive (recursive) + Wiki, then filter locally by keyword
    result = await _preview_feishu_docs(token, None, max_docs, recurse=True)
    # Also fetch wiki
    wiki_docs, _wiki_spaces = await _collect_wiki_docs(token, max_docs)
    # Merge all
    all_docs = result.get("docs", [])
    existing_urls = {d.get("url", "") for d in all_docs}
    for wd in wiki_docs:
        if wd.get("url") and wd["url"] not in existing_urls:
            wd["source_type"] = "wiki"
            all_docs.append(wd)
            existing_urls.add(wd["url"])

    # Local keyword filter
    q_lower = q.strip().lower()
    matched = []
    for doc in all_docs:
        name = (doc.get("name") or "").lower()
        if q_lower in name:
            matched.append(doc)
        if len(matched) >= max_docs:
            break

    return UTF8JSONResponse({
        "query": q,
        "docs": matched,
        "total": len(matched),
    })


class FeishuUrlImportRequest(BaseModel):
    url: str


@router.post("/feishu/direct-import")
async def feishu_direct_import(req: FeishuUrlImportRequest):
    """Import a single Feishu document by URL directly into the knowledge base."""
    token = await _get_valid_feishu_kb_token()
    if not token:
        raise HTTPException(status_code=401, detail={
            "stage": "auth",
            "message": "Feishu knowledge import is not authorized",
            "token_path": FEISHU_KB_TOKEN_PATH,
            "scope": FEISHU_KB_OAUTH_SCOPE,
            "last_callback": feishu_kb_last_callback,
        })
    result = await feishu_service.get_doc_content_debug(req.url.strip(), user_access_token=token)
    content = result.get("content") or ""
    if not content:
        safe = dict(result)
        safe.pop("content", None)
        raise HTTPException(status_code=400, detail={
            "stage": "direct_import",
            "message": "Failed to read document content",
            "api_result": safe,
        })
    wiki_node = result.get("wiki_node") or {}
    title = (wiki_node.get("title") or
             req.url.strip().split("/")[-1] or
             "飞书文档")
    metadata = {
        "source": title,
        "file_path": req.url.strip(),
        "doc_type": "feishu",
        "import_method": "direct_url",
    }
    chunk_ids = await rag_service.index_text(content, metadata)
    # Record import
    from time import time as _time_seconds
    records = _load_feishu_import_records()
    records[req.url.strip()] = {
        "name": title,
        "url": req.url.strip(),
        "chunks": len(chunk_ids),
        "imported_at": _time_seconds(),
    }
    _save_feishu_import_records(records)
    stats = await rag_service.get_stats()
    return UTF8JSONResponse({
        "ok": True,
        "title": title,
        "url": req.url.strip(),
        "chunks": len(chunk_ids),
        "content_length": len(content),
        "total_chunks": stats.get("total_chunks", 0),
        "unique_docs": stats.get("unique_docs", 0),
    })


@router.post("/feishu/preview")
async def feishu_import_preview(req: FeishuPreviewRequest):
    token = await _get_valid_feishu_kb_token()
    if not token:
        raise HTTPException(status_code=401, detail={
            "stage": "auth",
            "message": "Feishu knowledge import is not authorized",
            "token_path": FEISHU_KB_TOKEN_PATH,
            "scope": FEISHU_KB_OAUTH_SCOPE,
            "last_callback": feishu_kb_last_callback,
        })
    folder_token = (req.folder_token or "").strip() or None
    max_docs = max(1, min(int(req.max_docs or 500), 1000))
    recurse = bool(req.recurse)
    include_wiki = bool(req.include_wiki) if req.include_wiki is not None else True
    result = await _preview_feishu_docs(token, folder_token, max_docs, recurse=recurse)

    # Also fetch wiki docs if requested
    if include_wiki:
        wiki_docs, wiki_spaces = await _collect_wiki_docs(token, max_docs)
        result["wiki_spaces"] = wiki_spaces[:30]
        result["wiki_docs"] = wiki_docs[:max_docs]
        result["wiki_total_docs"] = len(wiki_docs)
        # Merge wiki docs into main doc list (with source prefix)
        existing_urls = {d.get("url", "") for d in result.get("docs", [])}
        for wd in wiki_docs:
            if wd.get("url") and wd["url"] not in existing_urls:
                # Mark wiki docs so frontend can distinguish them
                wd["source_type"] = "wiki"
                result["docs"].append(wd)
                existing_urls.add(wd["url"])
        result["total_docs"] = len(result["docs"])

    return UTF8JSONResponse(result)


@router.post("/feishu/import")
async def feishu_import_docs(req: FeishuImportRequest):
    token = await _get_valid_feishu_kb_token()
    if not token:
        raise HTTPException(status_code=401, detail={
            "stage": "auth",
            "message": "Feishu knowledge import is not authorized",
            "token_path": FEISHU_KB_TOKEN_PATH,
            "scope": FEISHU_KB_OAUTH_SCOPE,
            "last_callback": feishu_kb_last_callback,
        })
    successes = []
    failures = []
    for doc in req.docs[:100]:
        result = await feishu_service.get_doc_content_debug(doc.url, user_access_token=token)
        content = result.get("content") or ""
        if not content:
            attempts = result.get("attempts") or []
            reason = result.get("warning") or result.get("error") or "empty content"
            if attempts:
                reason += "; " + "; ".join(
                    f"{a.get('label')}: HTTP {a.get('http_status')}, code={a.get('code')}, msg={a.get('msg')}"
                    for a in attempts[-2:]
                )
            safe_result = dict(result)
            safe_result.pop("content", None)
            failures.append({"name": doc.name, "reason": reason, "api_result": safe_result})
            continue
        metadata = {
            "source": doc.name,
            "file_path": doc.url,
            "doc_type": "feishu",
            "feishu_token": doc.token,
            "feishu_type": doc.type,
            "feishu_sync_scope": "knowledge_page",
        }
        try:
            chunk_ids = await rag_service.index_text(content, metadata)
            record = _record_feishu_import(doc, len(chunk_ids))
            successes.append({"name": doc.name, "chunks": len(chunk_ids), "record": record})
        except Exception as exc:
            failures.append({"name": doc.name, "reason": str(exc)})
    stats = await rag_service.get_stats()
    return UTF8JSONResponse({
        "ok": bool(successes),
        "successes": successes,
        "failures": failures,
        "total_chunks": stats.get("total_chunks", 0),
        "unique_docs": stats.get("unique_docs", 0),
    })


@router.post("/feishu/doc-preview")
async def feishu_doc_preview(req: FeishuDocPreviewRequest):
    try:
        return await _feishu_doc_preview_impl(req)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Feishu doc preview failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail={
            "stage": "doc_preview",
            "message": f"Preview failed: {exc.__class__.__name__}: {str(exc) or 'no details'}",
        })


async def _feishu_doc_preview_impl(req: FeishuDocPreviewRequest):
    token = await _get_valid_feishu_kb_token()
    if not token:
        raise HTTPException(status_code=401, detail={
            "stage": "auth",
            "message": "Feishu knowledge import is not authorized",
            "token_path": FEISHU_KB_TOKEN_PATH,
            "scope": FEISHU_KB_OAUTH_SCOPE,
            "last_callback": feishu_kb_last_callback,
        })
    result = await feishu_service.get_doc_content_debug(req.url, user_access_token=token)
    content = result.get("content") or ""

    # Handle wiki nodes that are not documents (sheet, bitable, etc.)
    wiki_node = result.get("wiki_node") or {}
    obj_type = (wiki_node.get("obj_type") or "").lower()
    if not content and obj_type and obj_type not in ("doc", "docx", "docs", ""):
        return UTF8JSONResponse({
            "name": req.name,
            "url": req.url,
            "content_length": 0,
            "preview": f"此文档类型为「{obj_type}」，暂不支持在线预览。请在飞书中打开查看。",
            "truncated": False,
            "wiki_node": wiki_node,
            "unsupported_type": obj_type,
        })

    if not content:
        safe_result = dict(result)
        safe_result.pop("content", None)
        raise HTTPException(status_code=400, detail={
            "stage": "doc_preview",
            "message": "Failed to read Feishu document content",
            "api_result": safe_result,
        })
    return UTF8JSONResponse({
        "name": req.name,
        "url": req.url,
        "content_length": len(content),
        "preview": content[:8000],
        "truncated": len(content) > 8000,
        "wiki_node": result.get("wiki_node"),
        "success_endpoint": result.get("success_endpoint"),
    })


@router.get("/feishu/imported")
async def feishu_imported_docs():
    def _sort_key(item: dict):
        v = item.get("imported_at", 0)
        if isinstance(v, str):
            # Parse legacy ISO-format records
            try:
                from datetime import datetime
                return datetime.fromisoformat(v).timestamp()
            except (ValueError, TypeError):
                return 0
        return float(v) if v else 0
    records = sorted(_load_feishu_import_records().values(), key=_sort_key, reverse=True)
    return UTF8JSONResponse({"docs": records, "count": len(records)})


async def _preview_feishu_docs(token: str, folder_token: str | None, max_docs: int, recurse: bool = False) -> dict:
    if not folder_token:
        root = await feishu_service.get_root_folder_meta(token)
        if root.get("code") != 0:
            raise HTTPException(status_code=400, detail={
                "stage": "root_folder_meta",
                "message": "Failed to get Feishu root folder",
                "code": root.get("code"),
                "msg": root.get("msg") or root.get("message"),
                "http_status": root.get("_http_status"),
                "response": root,
            })
        data = root.get("data") or {}
        folder_token = data.get("token") or data.get("folder_token")
        if not folder_token:
            raise HTTPException(status_code=400, detail="Root folder metadata did not include folder_token")

    # Collect all files recursively or from single folder
    all_files, all_folders = await _collect_drive_files_recursive(
        token, folder_token, max_docs, recurse=recurse
    )

    docs = []
    skipped = []
    imported_records = _load_feishu_import_records()
    for item in all_files:
        file_type = (item.get("type") or item.get("file_type") or "").lower()
        name = item.get("name") or item.get("title") or "Untitled"
        file_token = item.get("token") or item.get("file_token")
        url = item.get("url") or item.get("shortcut_url") or ""
        if file_type in {"docx", "doc", "docs"}:
            if url and any(marker in url for marker in ("/docx/", "/docs/", "/doc/", "/wiki/")):
                key = _feishu_doc_key(file_token, url)
                imported = imported_records.get(key)
                docs.append({
                    "name": name,
                    "type": file_type,
                    "token": file_token,
                    "url": url,
                    "imported": bool(imported),
                    "imported_at": imported.get("imported_at") if imported else None,
                    "chunks": imported.get("chunks") if imported else None,
                })
            else:
                skipped.append({"name": name, "type": file_type, "reason": "No readable document URL returned by Feishu Drive"})

    return {
        "folder_token": folder_token,
        "docs": docs[:max_docs],
        "total_docs": len(docs),
        "folders": all_folders[:100],
        "folders_total": len(all_folders),
        "skipped": skipped[:50],
        "recurse": recurse,
    }


async def _collect_drive_files_recursive(
    token: str, folder_token: str, max_docs: int, recurse: bool = False, _depth: int = 0
) -> tuple[list[dict], list[dict]]:
    """Collect files from a folder, optionally recursing into subfolders."""
    all_files: list[dict] = []
    all_folders: list[dict] = []

    if _depth > 5 or len(all_files) >= max_docs:
        return all_files, all_folders

    listed = await feishu_service.list_drive_files(folder_token, token)
    if not listed.get("ok"):
        return all_files, all_folders

    subfolders = []
    for item in listed.get("files") or []:
        file_type = (item.get("type") or item.get("file_type") or "").lower()
        file_token = item.get("token") or item.get("file_token")
        name = item.get("name") or item.get("title") or "Untitled"
        if file_type == "folder" and file_token:
            subfolders.append({"name": name, "token": file_token})
        else:
            all_files.append(item)

    all_folders.extend(subfolders)

    if recurse and len(all_files) < max_docs:
        for sf in subfolders:
            sf_files, sf_folders = await _collect_drive_files_recursive(
                token, sf["token"], max_docs - len(all_files), recurse=True, _depth=_depth + 1
            )
            all_files.extend(sf_files)
            all_folders.extend(sf_folders)
            if len(all_files) >= max_docs:
                break

    return all_files, all_folders


async def _collect_wiki_docs(token: str, max_docs: int) -> tuple[list[dict], list[dict]]:
    """Collect documents from all accessible wiki spaces (recursive into sub-nodes)."""
    all_docs: list[dict] = []
    all_spaces: list[dict] = []

    spaces_result = await feishu_service.list_wiki_spaces(token)
    if not spaces_result.get("ok"):
        return all_docs, all_spaces

    for space in spaces_result.get("spaces") or []:
        space_id = space.get("space_id")
        space_name = space.get("name") or "未命名空间"
        if not space_id:
            continue
        all_spaces.append({"name": space_name, "space_id": space_id})

        if len(all_docs) >= max_docs:
            break

        # Recursively collect all document nodes
        await _collect_wiki_nodes_recursive(token, space_id, space_name, None, all_docs, max_docs)

    return all_docs, all_spaces


async def _collect_wiki_nodes_recursive(
    token: str, space_id: str, space_name: str,
    parent_token: str | None, all_docs: list[dict], max_docs: int, _depth: int = 0,
) -> None:
    """Recursively collect wiki document nodes, traversing into sub-folders."""
    if _depth > 5 or len(all_docs) >= max_docs:
        return

    nodes_result = await feishu_service.list_wiki_nodes(space_id, token, parent_token=parent_token)
    if not nodes_result.get("ok"):
        return

    subfolder_tokens: list[str] = []
    for node in nodes_result.get("nodes") or []:
        if len(all_docs) >= max_docs:
            return

        node_type = (node.get("node_type") or "").lower()
        obj_type = (node.get("obj_type") or "").lower()
        title = node.get("title") or "未命名"
        node_token = node.get("node_token") or ""
        has_child = node.get("has_child") or node.get("has_child_page") or False

        url = node.get("url") or ""
        if not url:
            doc_token = node.get("obj_token") or node_token
            if doc_token:
                url = f"https://{feishu_service.app_id}.feishu.cn/wiki/{doc_token}"

        # If this node has children, queue for recursive traversal (even if it's also a doc)
        if has_child and node_token:
            subfolder_tokens.append(node_token)

        # Include if it's a doc/wiki type (not sheet/bitable)
        supported = ("doc" in obj_type or "docx" in obj_type or "wiki" in obj_type
                     or obj_type in ("", "origin") or "document" in obj_type
                     or node_type in ("origin", "folder", "doc", "docx", "wiki"))
        if not supported and not has_child:
            continue

        if node_token and supported:
            all_docs.append({
                "name": f"[Wiki:{space_name}] {title}",
                "type": "docx",
                "token": node_token,
                "url": url,
                "imported": False,
                "source_type": "wiki",
            })

    # Recurse into sub-folders
    for child_token in subfolder_tokens:
        await _collect_wiki_nodes_recursive(
            token, space_id, space_name, child_token, all_docs, max_docs, _depth + 1,
        )


def _feishu_doc_key(token: str | None, url: str | None) -> str:
    return token or url or ""


def _load_feishu_import_records() -> dict:
    try:
        if not os.path.exists(FEISHU_KB_IMPORTED_PATH):
            return {}
        with open(FEISHU_KB_IMPORTED_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_feishu_import_records(records: dict) -> None:
    os.makedirs(os.path.dirname(FEISHU_KB_IMPORTED_PATH), exist_ok=True)
    with open(FEISHU_KB_IMPORTED_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def _record_feishu_import(doc: FeishuImportDoc, chunks: int) -> dict:
    from time import time as _time_seconds
    records = _load_feishu_import_records()
    key = _feishu_doc_key(doc.token, doc.url)
    record = {
        "key": key,
        "name": doc.name,
        "type": doc.type,
        "token": doc.token,
        "url": doc.url,
        "chunks": chunks,
        "imported_at": _time_seconds(),
    }
    if key:
        records[key] = record
        _save_feishu_import_records(records)
    return record


def _extract_feishu_code(text: str) -> str:
    from urllib.parse import parse_qs, urlparse

    value = (text or "").strip()
    parsed = urlparse(value)
    if parsed.query:
        code = parse_qs(parsed.query).get("code", [""])[0]
        if code:
            return code.strip()
    return value.replace("code:", "").replace("code：", "").strip()


async def _get_valid_feishu_kb_token() -> str | None:
    data = _load_feishu_kb_token()
    if not data:
        return None
    now = time.time()
    access_token = data.get("access_token")
    expires_at = float(data.get("expires_at") or 0)
    if access_token and now < expires_at - 120:
        return access_token
    refresh_token = data.get("refresh_token")
    refresh_expires_at = float(data.get("refresh_expires_at") or 0)
    if refresh_token and now < refresh_expires_at - 120:
        try:
            # Try v2 endpoint first (same as token exchange), then v1 non-OIDC
            refreshed = await feishu_service.refresh_user_access_token_v2(refresh_token)
            if refreshed.get("code") == 0 and refreshed.get("data", {}).get("access_token"):
                _save_feishu_kb_token(refreshed["data"])
                logger.info("Feishu KB token refreshed via v2")
                return refreshed["data"]["access_token"]
            logger.warning("Feishu KB v2 refresh: code=%s msg=%s, trying v1...",
                          refreshed.get("code"), refreshed.get("msg"))
            refreshed = await feishu_service.refresh_user_access_token_non_oidc(refresh_token)
            if refreshed.get("code") == 0 and refreshed.get("data", {}).get("access_token"):
                _save_feishu_kb_token(refreshed["data"])
                logger.info("Feishu KB token refreshed via v1")
                return refreshed["data"]["access_token"]
            logger.warning("Feishu KB both refresh failed: v1 code=%s msg=%s",
                          refreshed.get("code"), refreshed.get("msg"))
        except Exception as exc:
            logger.warning("Feishu KB token refresh exception: %s", exc)
            return None
    return None


def _load_feishu_kb_token() -> dict | None:
    try:
        if not os.path.exists(FEISHU_KB_TOKEN_PATH):
            return None
        with open(FEISHU_KB_TOKEN_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        saved_scope = set((data.get("scope") or "").split())
        required_scope = set(FEISHU_KB_OAUTH_SCOPE.split())
        if saved_scope and not required_scope.issubset(saved_scope):
            return None
        return data
    except Exception:
        return None


def _save_feishu_kb_token(token_data: dict) -> None:
    os.makedirs(os.path.dirname(FEISHU_KB_TOKEN_PATH), exist_ok=True)
    now = time.time()
    expires_in = int(token_data.get("expires_in") or 0)
    refresh_expires_in = int(token_data.get("refresh_expires_in") or 0)
    # If feishu returns refresh_token but no refresh_expires_in, default to 30 days
    if not refresh_expires_in and token_data.get("refresh_token"):
        refresh_expires_in = 30 * 24 * 3600
    saved = {
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token"),
        "expires_at": now + expires_in,
        "refresh_expires_at": now + refresh_expires_in,
        "scope": FEISHU_KB_OAUTH_SCOPE,
        "saved_at": now,
    }
    with open(FEISHU_KB_TOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump(saved, f, ensure_ascii=False, indent=2)
