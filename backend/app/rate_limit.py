import ipaddress

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
    host = request.client.host if request.client else "unknown"
    return _bucket_ipv6(host)


def _bucket_ipv6(host: str) -> str:
    """Collapse an IPv6 address to its /64: one subscriber owns the whole /64, so a
    per-address key would hand an attacker 2**64 fresh buckets."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if address.version == 4:
        return host
    if address.ipv4_mapped is not None:
        return str(address.ipv4_mapped)
    return str(ipaddress.ip_network(f"{host}/64", strict=False))


limiter = Limiter(
    key_func=get_client_ip,
    storage_uri=get_settings().RATE_LIMIT_STORAGE_URI,
)
