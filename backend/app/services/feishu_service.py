"""Feishu service 鈥?Open API integration for enterprise Feishu (閿愭嵎缃戠粶).

Uses Feishu Open API (Lark platform) with tenant access token.
Requires: FEISHU_APP_ID and FEISHU_APP_SECRET from Feishu Developer Console.

To get credentials:
1. Go to https://open.feishu.cn/app
2. Create an enterprise app (浼佷笟鑷\ue044缓搴旂敤)
3. Get App ID and App Secret from "Credentials" page
4. Configure permissions (scopes):
   - im:message:readonly
   - calendar:calendar:readonly
   - drive:drive:readonly
   - docx:document:readonly
5. Publish the app and get admin approval
"""
import os
import time
import httpx
import logging
import re
from urllib.parse import urlencode, urlparse
from app.config import settings
logger = logging.getLogger(__name__)
FEISHU_API_BASE = 'https://open.feishu.cn/open-apis'
FEISHU_DEFAULT_OAUTH_SCOPE = 'wiki:wiki:readonly docx:document:readonly minutes:minutes:readonly minutes:minutes.transcript:export minutes:minutes.basic:read'

def _get_windows_proxy() -> str | None:
    """Read the Windows system proxy setting from the registry."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings')
        enabled, _ = winreg.QueryValueEx(key, 'ProxyEnable')
        if enabled:
            server, _ = winreg.QueryValueEx(key, 'ProxyServer')
            winreg.CloseKey(key)
            if server:
                server = server.strip()
                if '=' in server:
                    parts = dict((p.split('=', 1) for p in server.split(';') if '=' in p))
                    server = parts.get('https') or parts.get('http') or server.split(';')[0].split('=')[-1]
                return f'http://{server}'
        winreg.CloseKey(key)
    except Exception:
        pass
    return None

class FeishuService:
    """Unified Feishu access via Open API."""

    def __init__(self):
        self.app_id = settings.feishu_app_id or os.environ.get('FEISHU_APP_ID', '')
        self.app_secret = settings.feishu_app_secret or os.environ.get('FEISHU_APP_SECRET', '')
        self.oauth_redirect_uri = settings.feishu_oauth_redirect_uri or os.environ.get('FEISHU_OAUTH_REDIRECT_URI', '')
        self._token: str | None = None
        self._token_expires_at: float = 0
        self._app_token: str | None = None
        self._app_token_expires_at: float = 0
        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_secret)

    def ensure_app_configured(self) -> None:
        if not self.is_configured:
            raise RuntimeError('Feishu not configured: set FEISHU_APP_ID and FEISHU_APP_SECRET')

    def build_oauth_authorize_url(self, redirect_uri: str | None=None, state: str='openapi', scope: str | None=None) -> str:
        """Build Feishu OAuth authorize URL for user access token flow."""
        if not self.app_id:
            raise RuntimeError('Feishu not configured: set FEISHU_APP_ID')
        redirect = redirect_uri or self.oauth_redirect_uri
        if not redirect:
            raise RuntimeError('redirect_uri is required or set FEISHU_OAUTH_REDIRECT_URI')
        scope = scope or FEISHU_DEFAULT_OAUTH_SCOPE
        query = urlencode({'app_id': self.app_id, 'redirect_uri': redirect, 'state': state, 'scope': scope})
        return f'{FEISHU_API_BASE}/authen/v1/authorize?{query}'

    async def exchange_oauth_code(self, code: str) -> dict:
        """Exchange OAuth authorization code for user access token."""
        self.ensure_app_configured()
        app_token = await self._get_app_token()
        client = await self._get_client()
        resp = await client.post(f'{FEISHU_API_BASE}/authen/v1/oidc/access_token', headers={'Authorization': f'Bearer {app_token}'}, json={'grant_type': 'authorization_code', 'code': code})
        try:
            data = resp.json()
        except Exception:
            data = {'raw_text': resp.text[:1000]}
        data['_http_status'] = resp.status_code
        return data

    async def exchange_oauth_code_v2(self, code: str, redirect_uri: str | None=None) -> dict:
        """Exchange OAuth authorization code using Feishu's OAuth v2 token endpoint."""
        self.ensure_app_configured()
        redirect = redirect_uri or self.oauth_redirect_uri
        client = await self._get_client()
        resp = await client.post(f'{FEISHU_API_BASE}/authen/v2/oauth/token', json={'grant_type': 'authorization_code', 'client_id': self.app_id, 'client_secret': self.app_secret, 'code': code, 'redirect_uri': redirect})
        try:
            data = resp.json()
        except Exception:
            data = {'raw_text': resp.text[:1000]}
        data['_http_status'] = resp.status_code
        return data

    async def refresh_user_access_token(self, refresh_token: str) -> dict:
        """Refresh Feishu user access token (OAuth v1 / OIDC)."""
        self.ensure_app_configured()
        app_token = await self._get_app_token()
        client = await self._get_client()
        resp = await client.post(f'{FEISHU_API_BASE}/authen/v1/oidc/refresh_access_token', headers={'Authorization': f'Bearer {app_token}'}, json={'grant_type': 'refresh_token', 'refresh_token': refresh_token})
        try:
            data = resp.json()
        except Exception:
            data = {'raw_text': resp.text[:1000]}
        data['_http_status'] = resp.status_code
        return data

    async def refresh_user_access_token_non_oidc(self, refresh_token: str) -> dict:
        """Refresh via non-OIDC endpoint (authen/v1/refresh_access_token).

        Compatible with tokens obtained via some v2 OAuth flows.
        """
        self.ensure_app_configured()
        app_token = await self._get_app_token()
        client = await self._get_client()
        resp = await client.post(f'{FEISHU_API_BASE}/authen/v1/refresh_access_token', headers={'Authorization': f'Bearer {app_token}'}, json={'grant_type': 'refresh_token', 'refresh_token': refresh_token})
        try:
            data = resp.json()
        except Exception:
            data = {'raw_text': resp.text[:1000]}
        data['_http_status'] = resp.status_code
        return data

    async def refresh_user_access_token_v2(self, refresh_token: str) -> dict:
        """Refresh via v2 token endpoint (authen/v2/oauth/token).

        Uses client credentials (client_id + client_secret) — no app_access_token needed.
        """
        self.ensure_app_configured()
        client = await self._get_client()
        resp = await client.post(f'{FEISHU_API_BASE}/authen/v2/oauth/token', json={'grant_type': 'refresh_token', 'client_id': self.app_id, 'client_secret': self.app_secret, 'refresh_token': refresh_token})
        try:
            data = resp.json()
        except Exception:
            data = {'raw_text': resp.text[:1000]}
        data['_http_status'] = resp.status_code
        return data

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            import os as _os
            proxy = _os.environ.get('HTTPS_PROXY') or _os.environ.get('https_proxy') or _os.environ.get('HTTP_PROXY') or _os.environ.get('http_proxy') or _get_windows_proxy() or None
            self._client = httpx.AsyncClient(timeout=30, proxy=proxy)
        return self._client

    async def _get_app_token(self) -> str:
        """Get or refresh app access token for OAuth APIs."""
        if self._app_token and time.time() < self._app_token_expires_at - 60:
            return self._app_token
        if not self.is_configured:
            raise RuntimeError('Feishu not configured: set FEISHU_APP_ID and FEISHU_APP_SECRET')
        client = await self._get_client()
        resp = await client.post(f'{FEISHU_API_BASE}/auth/v3/app_access_token/internal', json={'app_id': self.app_id, 'app_secret': self.app_secret})
        resp.raise_for_status()
        data = resp.json()
        if data.get('code') != 0:
            raise RuntimeError(f"Feishu app token failed: {data.get('msg', 'unknown')}")
        self._app_token = data['app_access_token']
        self._app_token_expires_at = time.time() + data.get('expire', 7200)
        return self._app_token

    async def _get_token(self) -> str:
        """Get or refresh tenant access token."""
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        if not self.is_configured:
            raise RuntimeError('Feishu not configured: set FEISHU_APP_ID and FEISHU_APP_SECRET')
        client = await self._get_client()
        resp = await client.post(f'{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal', json={'app_id': self.app_id, 'app_secret': self.app_secret})
        resp.raise_for_status()
        data = resp.json()
        if data.get('code') != 0:
            raise RuntimeError(f"Feishu auth failed: {data.get('msg', 'unknown')}")
        self._token = data['tenant_access_token']
        self._token_expires_at = time.time() + data.get('expire', 7200)
        return self._token

    async def search_messages(self, query: str, start_date: str, end_date: str) -> list[dict]:
        """Search Feishu messages within a time range.

        Uses the search API to find relevant messages across chats.
        """
        if not self.is_configured:
            return []
        try:
            token = await self._get_token()
            client = await self._get_client()
            results = []
            resp = await client.get(f'{FEISHU_API_BASE}/im/v1/messages', headers={'Authorization': f'Bearer {token}'}, params={'receive_id_type': 'open_id', 'page_size': 50})
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 0:
                    items = data.get('data', {}).get('items', [])
                    for item in items:
                        msg_type = item.get('msg_type', '')
                        body = item.get('body', {}).get('content', '')
                        create_time = item.get('create_time', '')
                        if create_time and start_date <= create_time[:10] <= end_date:
                            results.append({'msg_id': item.get('message_id'), 'chat_id': item.get('chat_id'), 'msg_type': msg_type, 'content': body[:500], 'create_time': create_time})
            return results
        except Exception as e:
            logger.warning(f'Feishu message search failed: {e}')
            return []

    async def get_calendar_events(self, start_date: str, end_date: str) -> list[dict]:
        """Get calendar events for a date range.

        Requires primary calendar access permission.
        """
        if not self.is_configured:
            return []
        try:
            token = await self._get_token()
            client = await self._get_client()
            resp = await client.get(f'{FEISHU_API_BASE}/calendar/v4/calendars/primary', headers={'Authorization': f'Bearer {token}'})
            if resp.status_code != 200:
                return []
            data = resp.json()
            calendar_id = data.get('data', {}).get('calendar_id', '')
            if not calendar_id:
                return []
            start_ts = f'{start_date}T00:00:00+08:00'
            end_ts = f'{end_date}T23:59:59+08:00'
            resp = await client.get(f'{FEISHU_API_BASE}/calendar/v4/calendars/{calendar_id}/events', headers={'Authorization': f'Bearer {token}'}, params={'start_time': start_ts, 'end_time': end_ts, 'page_size': 50})
            if resp.status_code != 200:
                return []
            data = resp.json()
            if data.get('code') != 0:
                return []
            events = data.get('data', {}).get('items', [])
            return [{'event_id': e.get('event_id'), 'summary': e.get('summary', ''), 'description': e.get('description', ''), 'start_time': e.get('start_time', {}).get('date_time', ''), 'end_time': e.get('end_time', {}).get('date_time', ''), 'organizer': e.get('organizer', {}).get('display_name', '')} for e in events]
        except Exception as e:
            logger.warning(f'Feishu calendar fetch failed: {e}')
            return []

    async def search_docs(self, query: str) -> list[dict]:
        """Search Feishu documents by title/content (deprecated — use search_user_docs)."""
        if not self.is_configured:
            return []
        try:
            token = await self._get_token()
            client = await self._get_client()
            resp = await client.get(f'{FEISHU_API_BASE}/drive/v1/files', headers={'Authorization': f'Bearer {token}'}, params={'page_size': 20})
            if resp.status_code != 200:
                return []
            data = resp.json()
            if data.get('code') != 0:
                return []
            files = data.get('data', {}).get('files', [])
            results = []
            for f in files:
                name = f.get('name', '')
                if query.lower() in name.lower():
                    results.append({'doc_id': f.get('token'), 'name': name, 'type': f.get('type'), 'url': f.get('url', '')})
            return results
        except Exception as e:
            logger.warning(f'Feishu doc search failed: {e}')
            return []

    async def search_files(self, query: str, user_access_token: str, page_size: int=50) -> dict:
        """Search files across Drive and Wiki using Feishu search API."""
        client = await self._get_client()
        files: list[dict] = []
        page_token = ''
        attempts: list[dict] = []
        while True:
            params: dict[str, str | int] = {'query': query, 'type': 'file', 'page_size': page_size, 'scope': 'my'}
            if page_token:
                params['page_token'] = page_token
            resp = await client.get(f'{FEISHU_API_BASE}/search/v2/search', headers={'Authorization': f'Bearer {user_access_token}'}, params=params)
            try:
                data = resp.json()
            except Exception:
                data = {'raw_text': resp.text[:1000]}
            attempts.append({'http_status': resp.status_code, 'code': data.get('code'), 'msg': data.get('msg') or data.get('message')})
            if resp.status_code != 200 or data.get('code') != 0:
                return {'ok': False, 'files': files, 'attempts': attempts, 'error': data}
            payload = data.get('data') or {}
            items = payload.get('items') or []
            for item in items:
                item_type = (item.get('type') or '').lower()
                if item_type not in ('docx', 'doc', 'docs', 'wiki', 'file', 'document'):
                    continue
                files.append({'name': item.get('name') or item.get('title') or '未命名', 'type': item_type, 'token': item.get('token') or item.get('file_token') or item.get('obj_token', ''), 'url': item.get('url') or item.get('link') or ''})
            if not payload.get('has_more'):
                break
            page_token = payload.get('page_token') or ''
            if not page_token:
                break
        return {'ok': True, 'files': files, 'attempts': attempts}

    async def get_doc_content(self, doc_id: str) -> str:
        """Get the text content of a Feishu document."""
        if not self.is_configured:
            return ''
        try:
            token = await self._get_token()
            client = await self._get_client()
            resp = await client.get(f'{FEISHU_API_BASE}/docx/v1/documents/{doc_id}/raw_content', headers={'Authorization': f'Bearer {token}'})
            if resp.status_code != 200:
                return ''
            data = resp.json()
            if data.get('code') != 0:
                return ''
            content = data.get('data', {}).get('content', '')
            import re
            return re.sub('<[^>]+>', '', content)
        except Exception as e:
            logger.warning(f'Feishu doc content fetch failed: {e}')
            return ''

    def extract_doc_ref(self, text: str) -> dict:
        """Extract a Feishu document token and probable type from a URL or raw token."""
        raw = (text or '').strip()
        url_match = re.search('https?://[^\\s)）>]+', raw)
        candidate = url_match.group(0) if url_match else raw.split()[0] if raw.split() else ''
        candidate = candidate.strip().strip('"\'<>')
        doc_type = 'unknown'
        token = candidate
        if candidate.startswith('http'):
            parsed = urlparse(candidate)
            parts = [p for p in parsed.path.split('/') if p]
            for kind in ('docx', 'docs', 'doc', 'wiki', 'minutes'):
                if kind in parts:
                    idx = parts.index(kind)
                    if idx + 1 < len(parts):
                        doc_type = kind
                        token = parts[idx + 1]
                        break
            else:
                token = parts[-1] if parts else ''
        token = token.split('?')[0].split('#')[0].strip()
        return {'input': raw, 'url_or_token': candidate, 'type': doc_type, 'token': token}

    async def resolve_wiki_node(self, wiki_token: str, access_token: str) -> dict:
        """Resolve a wiki node token to the underlying document object token/type."""
        client = await self._get_client()
        resp = await client.get(f'{FEISHU_API_BASE}/wiki/v2/spaces/get_node', headers={'Authorization': f'Bearer {access_token}'}, params={'token': wiki_token})
        try:
            data = resp.json()
        except Exception:
            data = {'raw_text': resp.text[:1000]}
        return {'label': 'wiki_get_node', 'path': '/wiki/v2/spaces/get_node', 'http_status': resp.status_code, 'code': data.get('code'), 'msg': data.get('msg') or data.get('message'), 'data': data.get('data') if isinstance(data, dict) else None}

    # ── Feishu Minutes (飞书妙记) API ──────────────────────────────────────

    async def get_minute_info(self, minute_token: str, access_token: str) -> dict:
        """Get basic info about a Feishu minute/meeting recording.

        API: GET /minutes/v1/minutes/{minute_token}
        """
        client = await self._get_client()
        path = f'/minutes/v1/minutes/{minute_token}'
        resp = await client.get(f'{FEISHU_API_BASE}{path}', headers={'Authorization': f'Bearer {access_token}'})
        try:
            data = resp.json()
        except Exception:
            data = {'raw_text': resp.text[:1000]}
        return {'label': 'minutes_get_info', 'path': path, 'http_status': resp.status_code, 'code': data.get('code'), 'msg': data.get('msg') or data.get('message'), 'data': data.get('data') if isinstance(data, dict) else None}

    async def get_minute_transcripts(self, minute_token: str, access_token: str, page_token: str = '', page_size: int = 100) -> dict:
        """Get transcripts (speaker turns) of a Feishu minute.

        API: GET /minutes/v1/minutes/{minute_token}/transcript
        Returns text/plain – the full transcript as raw text.
        """
        client = await self._get_client()
        path = f'/minutes/v1/minutes/{minute_token}/transcript'
        params: dict[str, str | int] = {'page_size': page_size}
        if page_token:
            params['page_token'] = page_token
        resp = await client.get(f'{FEISHU_API_BASE}{path}', headers={'Authorization': f'Bearer {access_token}'}, params=params)
        content_type = resp.headers.get('content-type', '')
        result: dict = {'label': 'minutes_transcripts', 'path': path, 'http_status': resp.status_code, 'code': None, 'msg': None, 'data': None}
        if resp.status_code == 200 and 'text/plain' in content_type:
            result['ok'] = True
            result['text'] = resp.text
        else:
            try:
                data = resp.json()
            except Exception:
                data = {'raw_text': resp.text[:1000]}
            result['code'] = data.get('code')
            result['msg'] = data.get('msg') or data.get('message')
            result['data'] = data.get('data') if isinstance(data, dict) else None
        return result

    async def get_minute_minutes(self, minute_token: str, access_token: str) -> dict:
        """Get the AI-generated minutes/summary of a Feishu minute.

        API: GET /minutes/v1/minutes/{minute_token}/minutes
        """
        client = await self._get_client()
        path = f'/minutes/v1/minutes/{minute_token}/minutes'
        resp = await client.get(f'{FEISHU_API_BASE}{path}', headers={'Authorization': f'Bearer {access_token}'})
        try:
            data = resp.json()
        except Exception:
            data = {'raw_text': resp.text[:1000]}
        return {'label': 'minutes_minutes', 'path': path, 'http_status': resp.status_code, 'code': data.get('code'), 'msg': data.get('msg') or data.get('message'), 'data': data.get('data') if isinstance(data, dict) else None}

    async def get_doc_content_debug(self, text_or_token: str, user_access_token: str | None=None) -> dict:
        """Read Feishu document content with debug metadata for skill testing."""
        ref = self.extract_doc_ref(text_or_token)
        auth_mode = 'user_access_token' if user_access_token else 'tenant_access_token'
        result = {'configured': self.is_configured, 'auth_mode': auth_mode, 'ref': ref, 'attempts': [], 'content': '', 'ok': False}
        if not user_access_token and (not self.is_configured):
            result['error'] = 'Feishu not configured: set FEISHU_APP_ID and FEISHU_APP_SECRET'
            return result
        if not ref['token']:
            result['error'] = 'No document token found in input'
            return result
        token = user_access_token or await self._get_token()
        client = await self._get_client()
        endpoints: list[tuple[str, str]] = []
        doc_type = ref['type']
        doc_token = ref['token']
        if doc_type == 'unknown':
            wiki_attempt = await self.resolve_wiki_node(doc_token, token)
            result['attempts'].append({k: v for k, v in wiki_attempt.items() if k != 'data'})
            if wiki_attempt.get('http_status') == 200 and wiki_attempt.get('code') == 0:
                node = (wiki_attempt.get('data') or {}).get('node') or {}
                obj_token = node.get('obj_token') or node.get('obj_token_alias')
                obj_type = node.get('obj_type') or node.get('type')
                result['wiki_node'] = {'node_token': doc_token, 'obj_token': obj_token, 'obj_type': obj_type, 'title': node.get('title')}
                if obj_token and obj_type:
                    doc_token = obj_token
                    doc_type = obj_type
                else:
                    result['warning'] = 'Unknown token looked like a wiki node, but obj_token/obj_type was missing.'
        if doc_type in {'docx', 'unknown'}:
            endpoints.append(('docx_raw_content', f'/docx/v1/documents/{doc_token}/raw_content'))
        if doc_type in {'docs', 'doc', 'unknown'}:
            endpoints.append(('doc_raw_content', f'/doc/v2/documents/{doc_token}/raw_content'))
        if doc_type == 'wiki':
            wiki_attempt = await self.resolve_wiki_node(doc_token, token)
            result['attempts'].append({k: v for k, v in wiki_attempt.items() if k != 'data'})
            if wiki_attempt.get('http_status') == 200 and wiki_attempt.get('code') == 0:
                node = (wiki_attempt.get('data') or {}).get('node') or {}
                obj_token = node.get('obj_token') or node.get('obj_token_alias')
                obj_type = node.get('obj_type') or node.get('type')
                result['wiki_node'] = {'node_token': doc_token, 'obj_token': obj_token, 'obj_type': obj_type, 'title': node.get('title')}
                if obj_token and obj_type:
                    doc_token = obj_token
                    doc_type = obj_type
                    if doc_type == 'docx':
                        endpoints.append(('docx_raw_content', f'/docx/v1/documents/{doc_token}/raw_content'))
                    elif doc_type in {'doc', 'docs'}:
                        endpoints.append(('doc_raw_content', f'/doc/v2/documents/{doc_token}/raw_content'))
                    else:
                        result['warning'] = f'Wiki node resolved to unsupported obj_type: {doc_type}'
                else:
                    result['warning'] = 'Wiki node resolved, but obj_token/obj_type was missing.'
            else:
                result['warning'] = 'Failed to resolve wiki node token to obj_token. Check wiki permission or use userAccessToken.'
        for label, path in endpoints:
            resp = await client.get(f'{FEISHU_API_BASE}{path}', headers={'Authorization': f'Bearer {token}'})
            attempt = {'label': label, 'path': path, 'http_status': resp.status_code}
            try:
                data = resp.json()
            except Exception:
                data = {'raw_text': resp.text[:1000]}
            attempt['code'] = data.get('code')
            attempt['msg'] = data.get('msg') or data.get('message')
            result['attempts'].append(attempt)
            if resp.status_code == 200 and data.get('code') == 0:
                content = data.get('data', {}).get('content', '')
                content = re.sub('<[^>]+>', '', content)
                result['content'] = content
                result['ok'] = bool(content)
                result['success_endpoint'] = label
                return result

        # ── Minutes / 飞书妙记 ──
        # Try minutes API for explicit 'minutes' tokens, or as a last-resort
        # fallback for 'unknown' tokens that failed docx/docs/wiki attempts.
        if doc_type in {'minutes', 'unknown'}:
            min_info = await self.get_minute_info(doc_token, token)
            result['attempts'].append({k: v for k, v in min_info.items() if k != 'data'})
            if min_info.get('http_status') == 200 and min_info.get('code') == 0:
                minute_data = (min_info.get('data') or {}).get('minute') or {}
                title = minute_data.get('title') or ''
                meeting_time = minute_data.get('meeting_time') or ''
                create_time = minute_data.get('create_time') or ''
                duration = minute_data.get('duration') or ''
                result['minute_info'] = {'title': title, 'meeting_time': meeting_time, 'create_time': create_time, 'duration': duration}

                # Fetch transcript (text/plain format)
                transcript_text = ''
                t_result = await self.get_minute_transcripts(doc_token, token)
                result['attempts'].append({k: v for k, v in t_result.items() if k not in ('data', 'text')})
                if t_result.get('ok'):
                    transcript_text = t_result.get('text') or ''

                # Build combined content
                parts: list[str] = []
                if title:
                    parts.append(f"会议标题：{title}")
                if meeting_time:
                    parts.append(f"会议时间：{meeting_time}")
                if duration:
                    try:
                        secs = int(duration) // 1000
                        mins, secs = divmod(secs, 60)
                        hours, mins = divmod(mins, 60)
                        parts.append(f"会议时长：{hours}时{mins}分{secs}秒" if hours else f"会议时长：{mins}分{secs}秒")
                    except (ValueError, TypeError):
                        parts.append(f"会议时长：{duration}ms")
                if transcript_text.strip():
                    parts.append('')
                    parts.append('## 会议转写')
                    parts.append('')
                    parts.append(transcript_text.strip())

                content = '\n'.join(parts).strip()
                if content:
                    result['content'] = content
                    result['ok'] = True
                    result['success_endpoint'] = 'minutes'
                    return result

        return result

    async def get_doc_content_debug_with_fallback(self, text_or_token: str, user_access_token: str | None=None) -> dict:
        """Try app identity first, then fall back to user access token if provided."""
        import time as _t; _t0 = _t.monotonic()
        ref = self.extract_doc_ref(text_or_token)
        if not user_access_token:
            result = await self.get_doc_content_debug(text_or_token)
            result['fallback'] = {'strategy': 'tenant_only', 'tenant_attempted': True, 'user_attempted': False, 'used': False}
            return result
        tenant_result = await self.get_doc_content_debug(text_or_token)
        if tenant_result.get('ok'):
            tenant_result['fallback'] = {'strategy': 'tenant_then_user', 'tenant_attempted': True, 'user_attempted': False, 'used': False, 'reason': 'tenant_access_token succeeded'}
            return tenant_result
        user_result = await self.get_doc_content_debug(text_or_token, user_access_token=user_access_token)
        user_result['fallback'] = {'strategy': 'tenant_then_user', 'tenant_attempted': True, 'user_attempted': True, 'used': True, 'reason': 'tenant_access_token failed; userAccessToken attempted', 'tenant_error': tenant_result.get('error'), 'tenant_warning': tenant_result.get('warning'), 'tenant_attempts': tenant_result.get('attempts') or []}
        return user_result

    async def get_root_folder_meta(self, user_access_token: str) -> dict:
        """Get the user's root folder metadata."""
        client = await self._get_client()
        resp = await client.get(f'{FEISHU_API_BASE}/drive/explorer/v2/root_folder/meta', headers={'Authorization': f'Bearer {user_access_token}'})
        try:
            data = resp.json()
        except Exception:
            data = {'raw_text': resp.text[:1000]}
        data['_http_status'] = resp.status_code
        return data

    async def list_drive_files(self, folder_token: str, user_access_token: str, page_size: int=50) -> dict:
        """List files under a drive folder token."""
        client = await self._get_client()
        files: list[dict] = []
        page_token = ''
        attempts: list[dict] = []
        while True:
            params = {'folder_token': folder_token, 'page_size': page_size}
            if page_token:
                params['page_token'] = page_token
            resp = await client.get(f'{FEISHU_API_BASE}/drive/v1/files', headers={'Authorization': f'Bearer {user_access_token}'}, params=params)
            try:
                data = resp.json()
            except Exception:
                data = {'raw_text': resp.text[:1000]}
            attempts.append({'http_status': resp.status_code, 'code': data.get('code'), 'msg': data.get('msg') or data.get('message')})
            if resp.status_code != 200 or data.get('code') != 0:
                return {'ok': False, 'files': files, 'attempts': attempts, 'error': data}
            payload = data.get('data') or {}
            files.extend(payload.get('files') or payload.get('items') or [])
            if not payload.get('has_more'):
                break
            page_token = payload.get('next_page_token') or ''
            if not page_token:
                break
        return {'ok': True, 'files': files, 'attempts': attempts}

    async def list_wiki_spaces(self, user_access_token: str, page_size: int=20) -> dict:
        """List wiki spaces the user has access to."""
        client = await self._get_client()
        spaces: list[dict] = []
        page_token = ''
        attempts: list[dict] = []
        while True:
            params: dict[str, str | int] = {'page_size': page_size}
            if page_token:
                params['page_token'] = page_token
            resp = await client.get(f'{FEISHU_API_BASE}/wiki/v2/spaces', headers={'Authorization': f'Bearer {user_access_token}'}, params=params)
            try:
                data = resp.json()
            except Exception:
                data = {'raw_text': resp.text[:1000]}
            attempts.append({'http_status': resp.status_code, 'code': data.get('code'), 'msg': data.get('msg') or data.get('message')})
            if resp.status_code != 200 or data.get('code') != 0:
                return {'ok': False, 'spaces': spaces, 'attempts': attempts, 'error': data}
            payload = data.get('data') or {}
            items = payload.get('items') or []
            spaces.extend(items)
            if not payload.get('has_more'):
                break
            page_token = payload.get('page_token') or ''
            if not page_token:
                break
        return {'ok': True, 'spaces': spaces, 'attempts': attempts}

    async def list_wiki_nodes(self, space_id: str, user_access_token: str, parent_token: str | None=None, page_size: int=50) -> dict:
        """List nodes in a wiki space, optionally under a parent node."""
        client = await self._get_client()
        nodes: list[dict] = []
        page_token = ''
        attempts: list[dict] = []
        while True:
            params: dict[str, str | int] = {'space_id': space_id, 'page_size': page_size}
            if parent_token:
                params['parent_node_token'] = parent_token
            if page_token:
                params['page_token'] = page_token
            resp = await client.get(f'{FEISHU_API_BASE}/wiki/v2/spaces/{space_id}/nodes', headers={'Authorization': f'Bearer {user_access_token}'}, params=params)
            try:
                data = resp.json()
            except Exception:
                data = {'raw_text': resp.text[:1000]}
            attempts.append({'http_status': resp.status_code, 'code': data.get('code'), 'msg': data.get('msg') or data.get('message')})
            if resp.status_code != 200 or data.get('code') != 0:
                return {'ok': False, 'nodes': nodes, 'attempts': attempts, 'error': data}
            payload = data.get('data') or {}
            items = payload.get('items') or payload.get('nodes') or []
            nodes.extend(items)
            if not payload.get('has_more'):
                break
            page_token = payload.get('page_token') or ''
            if not page_token:
                break
        return {'ok': True, 'nodes': nodes, 'attempts': attempts}

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
feishu_service = FeishuService()