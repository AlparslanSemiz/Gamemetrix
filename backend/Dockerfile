FROM python:3.11-slim

WORKDIR /app

# Bağımlılıkları yükleyelim
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Tüm backend kodunu içeri aktaralım
COPY . .

EXPOSE 8000

# FastAPI uygulamasını ayağa kaldıralım
# Not: Eğer ana çalıştırma dosyan app/main.py içindeyse bu komut aynen kalır.
# --workers 1: one process only — a second worker would double the RSS on a 1GB host.
#   FastAPI's async event loop already handles many concurrent I/O-bound requests
#   (httpx calls to RAWG/Steam/etc, DB queries) on a single worker; this is a
#   concurrency ceiling, not a throughput one, as long as handlers stay non-blocking
#   (see app/services/background.py's run_in_executor pattern for CPU-bound work).
# --limit-concurrency 100: once 100 requests are in flight, uvicorn returns 503
#   to new ones immediately instead of queuing them — bounds worst-case memory
#   under a traffic spike or load test instead of degrading into swap thrash.
# --forwarded-allow-ips: trust X-Forwarded-* only from the compose network, where
#   nginx is the sole peer. '*' would let anything that reaches this port dictate
#   its own client IP and bypass the auth rate limiter. The port is `expose`d, not
#   published, so the docker bridge range is the full trust boundary.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --limit-concurrency 100 --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS:-172.16.0.0/12}\""]
