import asyncio
import json
import os
import uuid
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from app.config import settings as app_settings
from app.core.database import engine, Base

logger = logging.getLogger(__name__)


class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"

    def render(self, content) -> bytes:
        return json.dumps(content, ensure_ascii=False, indent=None, separators=(",", ":")).encode("utf-8")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Initialize RAG knowledge base (with timeout to prevent event loop blocking)
    try:
        from app.services.rag_service import rag_service
        await asyncio.wait_for(rag_service.initialize(), timeout=10.0)
        logger.info("RAG service initialized")
    except asyncio.TimeoutError:
        logger.warning("RAG service initialization timed out (skipping)")
    except Exception:
        logger.warning("RAG service initialization failed", exc_info=True)

    # Initialize file scanner (watch dirs only — no auto-scan on startup)
    # Users trigger scans manually from the Knowledge page UI
    try:
        from app.services.file_scanner import file_scanner
        watch_dirs_raw = app_settings.watch_dirs
        try:
            watch_dirs = json.loads(watch_dirs_raw) if isinstance(watch_dirs_raw, str) else watch_dirs_raw
        except json.JSONDecodeError:
            watch_dirs = []
        if watch_dirs:
            file_scanner.watch_dirs = [os.path.abspath(d) for d in watch_dirs if os.path.isdir(d)]
            logger.info("File scanner configured with %d watch dirs (idle until manual scan)", len(file_scanner.watch_dirs))
    except Exception:
        logger.warning("File scanner initialization failed", exc_info=True)

    # Start periodic session cleanup background task (runs every hour, 24h TTL)
    try:
        from app.skills import get_registry
        from app.skills.session_cleanup import periodic_cleanup
        _cleanup_task = asyncio.create_task(
            periodic_cleanup(get_registry(), interval=3600, ttl=86400)
        )
        logger.info("Session cleanup background task started")
    except Exception:
        logger.warning("Session cleanup task failed to start", exc_info=True)

    yield

    # Shutdown
    try:
        from app.services.file_scanner import file_scanner
        file_scanner.stop_watching()
    except Exception:
        pass
    await engine.dispose()


app = FastAPI(title="数字分身 API", version="2.0.0", lifespan=lifespan, default_response_class=UTF8JSONResponse)

app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global exception handlers ──────────────────────────────────
from fastapi.responses import JSONResponse

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning("HTTP %s on %s: %s", exc.status_code, request.url.path, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "code": exc.status_code, "detail": exc.detail},
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "code": 500, "detail": "Internal server error"},
    )

# ── Legacy routes (保持兼容，逐步迁移) ──────────────────────────
from app.routes import chat, persona, sessions, health, skills, settings, knowledge, openapi_feishu, proxy

app.include_router(chat.router)
app.include_router(persona.router)
app.include_router(sessions.router)
app.include_router(health.router)
app.include_router(skills.router)
app.include_router(settings.router)
app.include_router(knowledge.router)
app.include_router(openapi_feishu.router)
app.include_router(proxy.router)

# ── v1 Feature APIs (NEW — 独立于技能系统) ──────────────────────
from app.api import feature_router
app.include_router(feature_router)


# ── Image generation endpoint (independent of skill routing) ──
from pydantic import BaseModel as _PydanticBaseModel

class ImageGenRequest(_PydanticBaseModel):
    prompt: str
    session_id: str | None = None

@app.post("/api/image-gen")
async def image_gen_endpoint(req: ImageGenRequest):
    """Generate image via Agnes. Returns {success, image_url, prompt, error}."""
    import asyncio as _asyncio
    from app.services.image_gen_service import generate_image, ImageGenResult
    from app.config import settings as _settings

    if not _settings.agnes_api_key:
        return {"success": False, "error": "Agnes API key not configured"}

    filename = f"gen_{uuid.uuid4().hex[:8]}.png"
    from app.services._paths import PUBLIC_DIR
    out_dir = str(PUBLIC_DIR)
    os.makedirs(out_dir, exist_ok=True)
    output_path = os.path.join(out_dir, filename)

    result = await generate_image(req.prompt, output_path, size="1024x1024")
    if not result.success:
        return {"success": False, "error": result.error}

    download_url = f"/api/skills/download/{filename}"
    return {
        "success": True,
        "image_url": download_url,
        "download_url": download_url,
        "prompt": req.prompt,
        "backend": result.backend,
        "path": result.path,
    }

# ── Simple file upload for batch PPTX tool ────────────────────
from fastapi import UploadFile, File
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a single image file. Returns the server path."""
    from app.services._paths import DATA_DIR
    uploads_dir = DATA_DIR / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    ext = os.path.splitext(file.filename)[1] or ".png"
    dest = uploads_dir / f"{uuid.uuid4().hex}{ext}"
    content = await file.read()
    dest.write_bytes(content)
    return {"path": str(dest.resolve()), "filename": file.filename}

# ── System restart endpoint ─────────────────────────────────────
@app.post("/api/system/restart")
async def restart_server():
    """Kill this server, clear caches, and restart with fresh code."""
    import subprocess, sys
    from app.services._paths import BACKEND_DIR
    backend_dir = str(BACKEND_DIR)

    restart_script = (
        "import os, sys, subprocess, time, shutil\n"
        "time.sleep(1)\n"
        "# Kill all uvicorn on port 8011\n"
        "result = subprocess.run(['netstat','-ano'], capture_output=True, text=True)\n"
        "for line in result.stdout.split('\\n'):\n"
        "    if ':8011' in line and 'LISTENING' in line:\n"
        "        pid = line.strip().split()[-1]\n"
        "        try:\n"
        "            subprocess.run(['taskkill','/F','/PID',pid], capture_output=True)\n"
        "        except:\n"
        "            pass\n"
        "time.sleep(1)\n"
        "# Clear cache\n"
        "backend_dir = " + repr(backend_dir) + "\n"
        "for root, dirs, files in os.walk(backend_dir):\n"
        "    for d in dirs:\n"
        "        if d == '__pycache__':\n"
        "            p = os.path.join(root, d)\n"
        "            shutil.rmtree(p, ignore_errors=True)\n"
        "    for f in files:\n"
        "        if f.endswith('.pyc'):\n"
        "            try: os.remove(os.path.join(root, f))\n"
        "            except: pass\n"
        "# Restart\n"
        "subprocess.Popen(\n"
        "    [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8011'],\n"
        "    cwd=backend_dir,\n"
        "    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,\n"
        ")\n"
    )
    subprocess.Popen(
        [sys.executable, '-c', restart_script],
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
    )
    return {"ok": True, "message": "Server restart initiated. Refresh in ~3 seconds."}


@app.get("/app/app_4k9rvfdqrdezp/feishu-oauth-callback", response_class=HTMLResponse)
async def feishu_oauth_callback_alias(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    from datetime import datetime
    from app.routes.knowledge import feishu_kb_last_callback

    feishu_kb_last_callback.clear()
    feishu_kb_last_callback.update({
        "received_at": datetime.now().isoformat(),
        "path": "/app/app_4k9rvfdqrdezp/feishu-oauth-callback",
        "has_code": bool(code),
        "state": state,
        "error": error,
    })

    if state == "knowledge_feishu_import":
        from app.routes.knowledge import FEISHU_KB_OAUTH_SCOPE

        if error:
            return HTMLResponse(f"""
            <!doctype html>
            <html lang="zh-CN">
            <head><meta charset="utf-8" /><title>Feishu OAuth</title></head>
            <body style="font-family: system-ui, sans-serif; padding: 32px; line-height: 1.6;">
              <h2>Feishu knowledge import authorization failed</h2>
              <p>Feishu returned error: {error}</p>
              <p>Return to Knowledge page and click "show diagnostics".</p>
            </body>
            </html>
            """)

        if not code:
            return HTMLResponse(f"""
            <!doctype html>
            <html lang="zh-CN">
            <head><meta charset="utf-8" /><title>Feishu OAuth</title></head>
            <body style="font-family: system-ui, sans-serif; padding: 32px; line-height: 1.6;">
              <h2>Feishu knowledge import callback reached, but code is missing</h2>
              <p>The backend callback was reached, but Feishu did not include an authorization code.</p>
              <p><b>state:</b> {state}</p>
              <p>Return to Knowledge page and click "show diagnostics".</p>
            </body>
            </html>
            """)

        from app.services.feishu_service import feishu_service
        from app.routes.knowledge import _save_feishu_kb_token

        try:
            # Build redirect_uri from the request — must match what was used
            # in the authorization step (frontend sends 127.0.0.1:8001).
            redirect_uri = str(request.url.remove_query_params(["code", "state", "error"]))
            feishu_kb_last_callback["exchange_redirect_uri"] = redirect_uri
            data = await feishu_service.exchange_oauth_code_v2(code, redirect_uri=redirect_uri)
            feishu_kb_last_callback["exchange_response"] = data
            token_data = data.get("data") or data
            if data.get("code") == 0 and token_data.get("access_token"):
                _save_feishu_kb_token(token_data)
                feishu_kb_last_callback["saved"] = True
                return HTMLResponse(f"""
                <!doctype html>
                <html lang="zh-CN">
                <head><meta charset="utf-8" /><title>Feishu OAuth</title></head>
                <body style="font-family: system-ui, sans-serif; padding: 32px; line-height: 1.6;">
                  <h2>Feishu knowledge import authorized</h2>
                  <p>The authorization token has been saved. Return to the Knowledge page and click preview.</p>
                  <p><b>scope:</b> {FEISHU_KB_OAUTH_SCOPE}</p>
                </body>
                </html>
                """)
            return HTMLResponse(f"""
            <!doctype html>
            <html lang="zh-CN">
            <head><meta charset="utf-8" /><title>Feishu OAuth</title></head>
            <body style="font-family: system-ui, sans-serif; padding: 32px; line-height: 1.6;">
              <h2>Feishu knowledge import authorization failed</h2>
              <pre>{data}</pre>
            </body>
            </html>
            """)
        except Exception as exc:
            feishu_kb_last_callback["exception"] = f"{exc.__class__.__name__}: {str(exc) or 'no detail'}"
            return HTMLResponse(f"""
            <!doctype html>
            <html lang="zh-CN">
            <head><meta charset="utf-8" /><title>Feishu OAuth</title></head>
            <body style="font-family: system-ui, sans-serif; padding: 32px; line-height: 1.6;">
              <h2>Feishu knowledge import authorization failed</h2>
              <p>{exc.__class__.__name__}: {str(exc) or 'no detail'}</p>
            </body>
            </html>
            """)

    from app.routes.openapi_feishu import oauth_callback

    return await oauth_callback(request=request, code=code, state=state, error=error)
