from fastapi import Request
from slowapi import Limiter

from .config import get_settings


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(
    key_func=get_client_ip,
    storage_uri=get_settings().RATE_LIMIT_STORAGE_URI,
)
