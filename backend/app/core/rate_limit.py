"""Simple in-memory rate limiter for chat endpoint."""
import time
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# {client_ip: [(timestamp,), ...]}
_store: dict[str, list[float]] = defaultdict(list)


def check(ip: str, max_requests: int = 20, window_sec: int = 60) -> bool:
    """Return True if request is allowed, False if rate limited."""
    now = time.time()
    cutoff = now - window_sec
    _store[ip] = [t for t in _store[ip] if t > cutoff]
    if len(_store[ip]) >= max_requests:
        logger.warning("Rate limit hit: %s (%d req/%ds)", ip, len(_store[ip]), window_sec)
        return False
    _store[ip].append(now)
    return True
