from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app.services.feishu_service import FEISHU_DEFAULT_OAUTH_SCOPE, feishu_service


router = APIRouter(prefix="/openapi/feishu", tags=["openapi-feishu"])


class ReadFeishuDocRequest(BaseModel):
    url: str = Field(..., description="Feishu/Lark document URL or document token")
    userAccessToken: str | None = Field(None, description="Optional Feishu user access token")


class FeishuAuthorizeUrlRequest(BaseModel):
    redirectUri: str | None = Field(None, description="OAuth callback URL configured in Feishu app security settings")
    state: str = Field("openapi", description="OAuth state")
    scope: str | None = Field(None, description="OAuth scopes")


class FeishuAccessTokenRequest(BaseModel):
    code: str = Field(..., description="Authorization code from Feishu OAuth callback")


class FeishuRefreshTokenRequest(BaseModel):
    refreshToken: str = Field(..., description="Feishu OAuth refresh token")


@router.post("/oauth/authorize-url")
async def build_authorize_url(req: FeishuAuthorizeUrlRequest):
    try:
        url = feishu_service.build_oauth_authorize_url(
            redirect_uri=req.redirectUri,
            state=req.state,
            scope=req.scope,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "authorizeUrl": url,
        "url": url,
        "state": req.state,
        "scope": req.scope or FEISHU_DEFAULT_OAUTH_SCOPE,
    }


@router.get("/auth-url")
async def get_auth_url(
    redirect_uri: str | None = Query(None, description="OAuth callback URL configured in Feishu app security settings"),
    state: str = Query("openapi", description="OAuth state"),
    scope: str | None = Query(None, description="OAuth scopes"),
):
    try:
        url = feishu_service.build_oauth_authorize_url(
            redirect_uri=redirect_uri,
            state=state,
            scope=scope,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"url": url}


@router.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(
    request: Request,
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
):
    """Debug callback page for OpenAPI OAuth flow.

    For state=openapi, do not exchange token here. Show code for manual copy.
    """
    if state == "knowledge_feishu_import":
        from datetime import datetime
        from app.routes.knowledge import feishu_kb_last_callback

        feishu_kb_last_callback.clear()
        feishu_kb_last_callback.update({
            "received_at": datetime.now().isoformat(),
            "path": "/openapi/feishu/oauth/callback",
            "has_code": bool(code),
            "state": state,
            "error": error,
        })

    safe_code = code or ""
    safe_state = state or ""
    if error:
        body = f"""
        <h2>飞书授权返回错误</h2>
        <p><b>error:</b> {error}</p>
        <p><b>state:</b> {safe_state}</p>
        """
    elif safe_code and safe_state == "knowledge_feishu_import":
        try:
            redirect_uri = str(request.url.remove_query_params(["code", "state", "error"]))
            data = await feishu_service.exchange_oauth_code_v2(safe_code, redirect_uri=redirect_uri)
            token_data = data.get("data") or data
            if data.get("code") == 0 and token_data.get("access_token"):
                from app.routes.knowledge import _save_feishu_kb_token, FEISHU_KB_OAUTH_SCOPE

                _save_feishu_kb_token(token_data)
                from app.routes.knowledge import feishu_kb_last_callback
                feishu_kb_last_callback["exchange_redirect_uri"] = redirect_uri
                feishu_kb_last_callback["exchange_response"] = data
                body = f"""
                <h2>Feishu knowledge import authorized</h2>
                <p>The authorization token has been saved. Return to the Knowledge page and click preview.</p>
                <p><b>scope:</b> {FEISHU_KB_OAUTH_SCOPE}</p>
                <p><b>state:</b> {safe_state}</p>
                """
            else:
                body = f"""
                <h2>Feishu knowledge import authorization failed</h2>
                <p>Feishu returned an error while exchanging the authorization code.</p>
                <pre>{data}</pre>
                <p><b>state:</b> {safe_state}</p>
                """
        except Exception as exc:
            body = f"""
            <h2>Feishu knowledge import authorization failed</h2>
            <p>{exc.__class__.__name__}: {str(exc) or 'no detail'}</p>
            <p><b>state:</b> {safe_state}</p>
            """
    elif safe_code:
        body = f"""
        <h2>飞书授权成功</h2>
        <p>请复制下面的 code，回到数字分身聊天窗口粘贴，或调用 <code>/openapi/feishu/oauth/exchange</code>。</p>
        <label>code</label>
        <textarea id="code" readonly>{safe_code}</textarea>
        <button onclick="navigator.clipboard.writeText(document.getElementById('code').value)">复制 code</button>
        <h3>接口调用示例</h3>
        <pre>{{
  "code": "{safe_code}"
}}</pre>
        <p><b>state:</b> {safe_state}</p>
        """
    else:
        body = f"""
        <h2>飞书授权回调缺少 code</h2>
        <p><b>state:</b> {safe_state}</p>
        """
    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <title>飞书 OAuth 回调</title>
      <style>
        body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 32px; line-height: 1.6; }}
        textarea {{ width: 100%; max-width: 900px; height: 92px; font-size: 15px; padding: 10px; }}
        button {{ margin-top: 10px; padding: 8px 14px; cursor: pointer; }}
        pre {{ background: #f3f4f6; padding: 12px; border-radius: 8px; max-width: 900px; overflow: auto; }}
      </style>
    </head>
    <body>{body}</body>
    </html>
    """


@router.post("/oauth/access-token")
async def exchange_access_token(req: FeishuAccessTokenRequest):
    code = (req.code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="code is required")
    try:
        data = await feishu_service.exchange_oauth_code(code)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{exc.__class__.__name__}: {str(exc) or 'no detail'}") from exc
    return {
        "ok": data.get("code") == 0,
        "code": data.get("code"),
        "msg": data.get("msg") or data.get("message"),
        "data": data.get("data"),
    }


@router.post("/oauth/exchange")
async def exchange_oauth_code(req: FeishuAccessTokenRequest):
    return await exchange_access_token(req)


@router.post("/oauth/refresh-token")
async def refresh_access_token(req: FeishuRefreshTokenRequest):
    refresh_token = (req.refreshToken or "").strip()
    if not refresh_token:
        raise HTTPException(status_code=400, detail="refreshToken is required")
    try:
        data = await feishu_service.refresh_user_access_token(refresh_token)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{exc.__class__.__name__}: {str(exc) or 'no detail'}") from exc
    return {
        "ok": data.get("code") == 0,
        "code": data.get("code"),
        "msg": data.get("msg") or data.get("message"),
        "data": data.get("data"),
    }


@router.post("/read-doc")
async def read_doc(req: ReadFeishuDocRequest):
    """Read Feishu document or minutes content.

    Supports: docx, docs (old doc), wiki nodes, and minutes (飞书妙记/会议纪要).

    Mode 1: app identity only. The app must be added as a document collaborator.
    Mode 2: userAccessToken. Reads documents that the user token can access.
    """
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url is required")

    try:
        result = await feishu_service.get_doc_content_debug_with_fallback(
            url,
            user_access_token=req.userAccessToken,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "ok": False,
                "error": f"{exc.__class__.__name__}: {str(exc) or 'no detail'}",
            },
        ) from exc

    content = result.get("content") or ""
    return {
        "ok": bool(result.get("ok")),
        "authMode": result.get("auth_mode"),
        "doc": result.get("ref"),
        "wikiNode": result.get("wiki_node"),
        "content": content,
        "contentLength": len(content),
        "debug": {
            "configured": result.get("configured"),
            "attempts": result.get("attempts") or [],
            "fallback": result.get("fallback"),
            "successEndpoint": result.get("success_endpoint"),
            "warning": result.get("warning"),
            "error": result.get("error"),
        },
    }
