from __future__ import annotations
import asyncio
import logging
import time
try:
    import winreg
except ImportError:
    winreg = None  # type: ignore
from fastapi import APIRouter

router = APIRouter(prefix="/api/proxy", tags=["proxy"])
logger = logging.getLogger(__name__)

WSL_TIMEOUT = 18  # seconds for connect
WSL_QUICK = 6     # seconds for quick checks
PROXY_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
PROXY_SERVER = "127.0.0.1:8888"

VPN_SERVERS = ["us", "us10427", "us9473", "us8094", "us9856", "jp", "sg"]

# Health tracking
_health_state: dict = {"last_error": None, "reconnect_count": 0, "last_ok_at": None}
_health_task: asyncio.Task | None = None

# ── Windows proxy helpers ────────────────────────────────────────

def _set_windows_proxy(enable: bool) -> None:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, PROXY_REG_PATH, 0, winreg.KEY_SET_VALUE)
        if enable:
            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, PROXY_SERVER)
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
        else:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key)
        logger.info("Windows proxy %s", "enabled" if enable else "disabled")
    except Exception as e:
        logger.warning("Windows proxy error: %s", e)


def _get_windows_proxy_enabled() -> bool:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, PROXY_REG_PATH, 0, winreg.KEY_READ)
        value, _ = winreg.QueryValueEx(key, "ProxyEnable")
        winreg.CloseKey(key)
        return bool(value)
    except Exception:
        return False


# ── WSL command runner ───────────────────────────────────────────

async def _run_wsl(cmd: str, timeout: int = WSL_TIMEOUT) -> tuple[int, str, str]:
    import subprocess as _sp
    loop = asyncio.get_running_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: _sp.run(
                ["wsl", "bash", "-c", cmd], capture_output=True, timeout=timeout,
            )),
            timeout=timeout + 5,
        )
        return (result.returncode,
                result.stdout.decode("utf-8", errors="replace"),
                result.stderr.decode("utf-8", errors="replace"))
    except (asyncio.TimeoutError, _sp.TimeoutExpired):
        return (-1, "", "timeout")


# ── VPN helpers ──────────────────────────────────────────────────

def _parse_vpn_status(output: str) -> dict:
    result = {"connected": False, "ip": None, "country": None, "server": None}
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("Status:"):
            result["connected"] = "Connected" in line
        elif line.startswith("IP:"):
            result["ip"] = line.split(":", 1)[1].strip()
        elif line.startswith("Country:"):
            result["country"] = line.split(":", 1)[1].strip()
        elif line.startswith("Server:"):
            result["server"] = line.split(":", 1)[1].strip()
    return result


async def _vpn_daemon_alive() -> bool:
    """Check if NordVPN daemon is responsive."""
    code, stdout, _ = await _run_wsl("nordvpn status", timeout=WSL_QUICK)
    if code != 0:
        return False
    return "Status:" in stdout


async def _restart_vpn_daemon() -> bool:
    """Force-restart the NordVPN daemon. Returns True if successful."""
    logger.info("Restarting NordVPN daemon...")
    # Force kill all nordvpn processes
    await _run_wsl("sudo pkill -9 nordvpnd 2>/dev/null; sudo pkill -9 nordvpn 2>/dev/null; sleep 2", timeout=5)
    # Start daemon
    await _run_wsl("sudo nordvpnd &", timeout=3)
    await asyncio.sleep(4)
    # Verify
    alive = await _vpn_daemon_alive()
    if alive:
        logger.info("NordVPN daemon restarted successfully")
    else:
        logger.error("NordVPN daemon failed to restart")
    return alive


async def _ensure_daemon() -> bool:
    """Ensure NordVPN daemon is alive; restart if needed. Returns True if daemon is OK."""
    if await _vpn_daemon_alive():
        return True
    logger.warning("NordVPN daemon dead — restarting...")
    return await _restart_vpn_daemon()


async def _try_connect(server: str, timeout: int = WSL_TIMEOUT) -> bool:
    """Try connecting to a VPN server. Returns True if successful."""
    code, stdout, stderr = await _run_wsl(f"nordvpn connect {server}", timeout=timeout)
    combined = (stdout + stderr).lower()
    if code == 0 or "connected" in combined:
        # Verify
        code2, stdout2, _ = await _run_wsl("nordvpn status", timeout=WSL_QUICK)
        vpn = _parse_vpn_status(stdout2)
        if vpn["connected"]:
            logger.info("✓ Connected to %s (%s)", vpn.get("server", server), vpn.get("ip"))
            return True
    return False


# ── API endpoints ────────────────────────────────────────────────

@router.get("/status")
async def get_proxy_status():
    code, stdout, _ = await _run_wsl("nordvpn status", timeout=WSL_QUICK)
    vpn = _parse_vpn_status(stdout) if code == 0 else {"connected": False, "ip": None, "country": None, "server": None}

    code, _, _ = await _run_wsl("service tinyproxy status", timeout=WSL_QUICK)
    proxy_running = code == 0

    return {
        "vpn_connected": vpn["connected"],
        "vpn_ip": vpn["ip"],
        "vpn_country": vpn["country"],
        "vpn_server": vpn["server"],
        "proxy_running": proxy_running,
        "windows_proxy_enabled": _get_windows_proxy_enabled(),
        "last_error": _health_state["last_error"],
        "reconnect_count": _health_state["reconnect_count"],
    }


@router.post("/connect/{server_id}")
async def connect_to_server(server_id: str):
    """Connect to a specific VPN server with daemon auto-restart."""
    _health_state["last_error"] = None
    steps = []

    # Step 1: Ensure daemon
    steps.append("检查守护进程")
    if not await _ensure_daemon():
        _health_state["last_error"] = "守护进程无法启动"
        return {"ok": False, "error": "NordVPN 守护进程无法启动，请手动在 WSL 中运行 sudo nordvpnd &", "steps": steps}

    # Step 2: Disconnect cleanly
    steps.append("断开旧连接")
    await _run_wsl("nordvpn disconnect", timeout=5)

    # Step 3: Connect
    steps.append(f"连接 {server_id}")
    connected = await _try_connect(server_id)
    if not connected:
        # Try fallback servers
        for fallback in VPN_SERVERS:
            if fallback == server_id:
                continue
            steps.append(f"重试 {fallback}")
            connected = await _try_connect(fallback)
            if connected:
                break

    if not connected:
        _health_state["last_error"] = f"无法连接到 {server_id}"
        return {"ok": False, "error": f"无法连接到 VPN 服务器 ({server_id})，所有备用服务器均失败", "steps": steps}

    # Step 4: Restart tinyproxy
    steps.append("启动代理")
    code, _, stderr = await _run_wsl("service tinyproxy restart", timeout=5)
    if code != 0:
        _health_state["last_error"] = f"tinyproxy: {stderr}"
        return {"ok": False, "error": f"tinyproxy 启动失败: {stderr}", "steps": steps}

    # Step 5: Enable Windows proxy
    steps.append("开启系统代理")
    _set_windows_proxy(enable=True)

    # Read final status
    code, stdout, _ = await _run_wsl("nordvpn status", timeout=WSL_QUICK)
    vpn = _parse_vpn_status(stdout)

    _health_state["reconnect_count"] += 1
    _health_state["last_ok_at"] = time.time()

    return {
        "ok": True,
        "vpn_connected": vpn["connected"],
        "vpn_ip": vpn["ip"],
        "vpn_country": vpn["country"],
        "vpn_server": vpn["server"],
        "proxy_running": True,
        "windows_proxy_enabled": True,
        "steps": steps,
    }


@router.post("/stop")
async def stop_proxy():
    errors = []
    await _run_wsl("service tinyproxy stop", timeout=5)
    await _run_wsl("nordvpn disconnect", timeout=8)
    _set_windows_proxy(enable=False)
    _health_state["last_error"] = None
    return {"ok": True, "vpn_connected": False, "proxy_running": False, "windows_proxy_enabled": False, "errors": errors if errors else None}


@router.post("/repair")
async def repair():
    """Full repair: kill daemon, restart, reconnect. One-click fix."""
    logger.info("Repair: full reset initiated")
    _health_state["last_error"] = None
    steps = ["强制重启守护进程"]

    # Kill everything
    await _run_wsl("sudo pkill -9 nordvpnd 2>/dev/null; sudo pkill -9 nordvpn 2>/dev/null; sleep 2", timeout=5)
    await _run_wsl("sudo nordvpnd &", timeout=3)
    await asyncio.sleep(4)

    if not await _vpn_daemon_alive():
        # One more try
        await _run_wsl("sudo nordvpnd &", timeout=3)
        await asyncio.sleep(5)

    steps.append("设置 NordLynx")
    await _run_wsl("nordvpn set technology nordlynx", timeout=5)

    steps.append("连接 VPN")
    connected = False
    for server in VPN_SERVERS:
        steps.append(f"尝试 {server}")
        if await _try_connect(server, timeout=20):
            connected = True
            break

    if not connected:
        _health_state["last_error"] = "repair: 所有服务器连接失败"
        return {"ok": False, "error": "修复失败：所有 VPN 服务器均无法连接", "steps": steps}

    steps.append("启动 tinyproxy")
    await _run_wsl("service tinyproxy restart", timeout=5)
    steps.append("开启系统代理")
    _set_windows_proxy(enable=True)

    code, stdout, _ = await _run_wsl("nordvpn status", timeout=WSL_QUICK)
    vpn = _parse_vpn_status(stdout)

    _health_state["last_ok_at"] = time.time()
    return {"ok": True, "vpn_connected": vpn["connected"], "vpn_ip": vpn["ip"], "vpn_country": vpn["country"], "vpn_server": vpn["server"], "proxy_running": True, "windows_proxy_enabled": True, "steps": steps}


@router.put("/toggle")
async def toggle_proxy():
    code, stdout, _ = await _run_wsl("nordvpn status", timeout=WSL_QUICK)
    vpn = _parse_vpn_status(stdout)
    if vpn["connected"]:
        return await stop_proxy()
    else:
        return await connect_to_server("us")


# ── Server list (static) ─────────────────────────────────────────

SERVER_LIST = [
    {"id": "us", "label": "🇺🇸 美国 (自动)"},
    {"id": "us10427", "label": "🇺🇸 美国 #10427"},
    {"id": "us9473", "label": "🇺🇸 美国 #9473"},
    {"id": "us8094", "label": "🇺🇸 美国 #8094"},
    {"id": "us9856", "label": "🇺🇸 美国 #9856"},
    {"id": "us9422", "label": "🇺🇸 美国 #9422"},
    {"id": "jp", "label": "🇯🇵 日本 (自动)"},
    {"id": "sg", "label": "🇸🇬 新加坡 (自动)"},
    {"id": "de", "label": "🇩🇪 德国 (自动)"},
]


@router.get("/servers")
async def get_servers():
    return {"servers": SERVER_LIST}

