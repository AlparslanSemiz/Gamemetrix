from fastapi import Request
from slowapi import Limiter

from .config import get_settings


def get_client_ip(request: Request) -> str:
    """
    Resolved peer address, used as the rate-limit key.

    Deliberately reads only request.client — never X-Forwarded-For / X-Real-IP
    directly. Uvicorn runs with --proxy-headers --forwarded-allow-ips and has
    already applied those headers *if and only if* the peer is a trusted proxy.
    Re-parsing them here would restore the spoof: anyone able to reach the app
    could set their own key and get unlimited attempts against the auth endpoints.
    """
    return request.client.host if request.client else "unknown"


limiter = Limiter(
    key_func=get_client_ip,
    storage_uri=get_settings().RATE_LIMIT_STORAGE_URI,
)
