import os


os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://test:test@127.0.0.1:5432/gamemetrix_test"),
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-that-is-longer-than-thirty-two-characters")
os.environ.setdefault("ACCOUNT_EMAIL_DELIVERY", "log")
os.environ.setdefault("ACCOUNT_BASE_URL", "http://localhost:5173")
os.environ.setdefault("ENV", "test")
