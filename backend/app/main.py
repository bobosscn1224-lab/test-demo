import json
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
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

    # Initialize RAG knowledge base
    try:
        from app.services.rag_service import rag_service
        await rag_service.initialize()
        logger.info("RAG service initialized")
    except Exception:
        logger.warning("RAG service initialization failed (dependencies may be missing)", exc_info=True)

    # Initialize file scanner if WATCH_DIRS configured
    try:
        from app.services.file_scanner import file_scanner
        watch_dirs_raw = app_settings.watch_dirs
        try:
            watch_dirs = json.loads(watch_dirs_raw) if isinstance(watch_dirs_raw, str) else watch_dirs_raw
        except json.JSONDecodeError:
            watch_dirs = []
        if watch_dirs:
            file_scanner.watch_dirs = [os.path.abspath(d) for d in watch_dirs if os.path.isdir(d)]
            if file_scanner.watch_dirs:
                # Seed _known_files from existing ChromaDB metadata so full_scan
                # won't re-index everything on first run
                from app.utils.file_parser import SUPPORTED_EXTENSIONS
                from app.services.file_scanner import EXCLUDED_DIRS
                import os as _os
                count = 0
                for watch_dir in file_scanner.watch_dirs:
                    for root, dirs, files in _os.walk(watch_dir):
                        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
                        for filename in files:
                            ext = _os.path.splitext(filename)[1].lower()
                            if ext not in SUPPORTED_EXTENSIONS:
                                continue
                            fp = _os.path.join(root, filename)
                            try:
                                file_scanner._known_files[fp] = _os.path.getmtime(fp)
                                count += 1
                            except OSError:
                                pass
                logger.info("Seeded %d known files from watch dirs", count)
                file_scanner.start_watching()
                logger.info("File scanner initialized with %d directories, watching for changes", len(file_scanner.watch_dirs))
    except Exception:
        logger.warning("File scanner initialization failed", exc_info=True)

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

from app.routes import chat, persona, sessions, health, skills, settings, knowledge, openapi_feishu

app.include_router(chat.router)
app.include_router(persona.router)
app.include_router(sessions.router)
app.include_router(health.router)
app.include_router(skills.router)
app.include_router(settings.router)
app.include_router(knowledge.router)
app.include_router(openapi_feishu.router)


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
