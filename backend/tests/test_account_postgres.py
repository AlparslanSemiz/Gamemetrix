import os
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.account_security import hash_secret
from app.models import AccountSession, AccountToken, AnalyticsEvent, User, UserCollection, VisitEvent
from app.rate_limit import limiter
from app.services.account_tokens import issue_token
from app.services.google_identity import discard_unverified_local_credentials


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")
DATABASE_NAME = TEST_DATABASE_URL.rsplit("/", 1)[-1].split("?", 1)[0]
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL or not DATABASE_NAME.endswith("_test"),
    reason="Set TEST_DATABASE_URL to a PostgreSQL database whose name ends with _test.",
)


@pytest.fixture()
def postgres_client():
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    yield client, testing_session
    client.close()
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def register_and_verify(client: TestClient, session_factory) -> None:
    response = client.post(
        "/api/account/register",
        headers={"Origin": "http://localhost:5173"},
        json={"display_name": "Test User", "email": "user@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 202
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == "user@example.com"))
        assert user is not None
        user.email_verified_at = datetime.now(UTC)
        db.commit()


def login(client: TestClient) -> None:
    response = client.post(
        "/api/account/login",
        headers={"Origin": "http://localhost:5173"},
        json={"email": "user@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 200


def csrf_headers(client: TestClient) -> dict[str, str]:
    return {"Origin": "http://localhost:5173", "X-CSRF-Token": client.cookies["gm_csrf"]}


def test_account_session_csrf_admin_separation_and_delete(postgres_client) -> None:
    client, sessions = postgres_client
    anonymous = client.get("/api/account/session")
    assert anonymous.status_code == 200
    assert anonymous.json() == {"account": None}
    register_and_verify(client, sessions)
    login(client)
    first_session_token = client.cookies["gm_session"]
    login(client)
    second_session_token = client.cookies["gm_session"]
    assert second_session_token != first_session_token
    with sessions() as db:
        first_session = db.scalar(
            select(AccountSession).where(AccountSession.token_hash == hash_secret(first_session_token))
        )
        assert first_session is not None and first_session.revoked_at is not None
    assert client.get("/api/account/me").status_code == 200
    assert client.get("/api/account/session").json()["account"]["email"] == "user@example.com"
    assert client.post("/api/account/logout", headers={"Origin": "http://localhost:5173"}).status_code == 403
    assert client.get("/admin/dashboard").status_code == 403
    assert client.post("/api/account/logout", headers=csrf_headers(client)).status_code == 200
    assert client.get("/api/account/session").json() == {"account": None}

    login(client)
    with sessions() as db:
        user = db.scalar(select(User).where(User.email == "user@example.com"))
        assert user is not None
        now = datetime.now(UTC)
        db.add(VisitEvent(user_id=user.id, visitor_id_hash="a" * 64, path="/account", created_at=now))
        db.add(AnalyticsEvent(user_id=user.id, event_type="login_completed", properties={}, created_at=now))
        db.commit()
    response = client.request(
        "DELETE",
        "/api/account",
        headers=csrf_headers(client),
        json={"confirmation": "DELETE", "current_password": "correct horse battery staple"},
    )
    assert response.status_code == 200
    with sessions() as db:
        assert db.scalar(select(func.count(User.id))) == 0
        assert db.scalar(select(func.count(VisitEvent.id))) == 0
        assert db.scalar(select(func.count(AnalyticsEvent.id))) == 0


def test_state_merge_is_idempotent_and_reset_token_is_single_use(postgres_client) -> None:
    client, sessions = postgres_client
    register_and_verify(client, sessions)
    login(client)
    with sessions() as db:
        from tests.test_seo import game_fixture
        game = game_fixture()
        db.add(game)
        db.commit()

        user = db.scalar(select(User).where(User.email == "user@example.com"))
        expired_token = issue_token(db, user, "reset_password", -1)

    expired_reset = {"token": expired_token, "password": "a newer secure passphrase"}
    assert client.post(
        "/api/account/password/reset",
        headers={"Origin": "http://localhost:5173"},
        json=expired_reset,
    ).status_code == 400

    payload = {
        "collections": {"watchlist": ["a-complete-test-game"]},
        "preferences": {"min_discount": 25, "min_score": 85, "upcoming_days": 30},
        "read_alerts": [],
        "dismissed_alerts": [],
    }
    assert client.post("/api/account/state/merge", headers=csrf_headers(client), json=payload).status_code == 200
    assert client.post("/api/account/state/merge", headers=csrf_headers(client), json=payload).status_code == 200
    with sessions() as db:
        assert db.scalar(select(func.count(UserCollection.id))) == 1
        user = db.scalar(select(User).where(User.email == "user@example.com"))
        token = issue_token(db, user, "reset_password", 1)

    reset = {"token": token, "password": "a newer secure passphrase"}
    assert client.post("/api/account/password/reset", headers={"Origin": "http://localhost:5173"}, json=reset).status_code == 200
    assert client.post("/api/account/password/reset", headers={"Origin": "http://localhost:5173"}, json=reset).status_code == 400


def test_account_token_endpoint_is_rate_limited(postgres_client) -> None:
    client, _ = postgres_client
    limiter.reset()
    responses = [
        client.post(
            "/api/account/email/verify",
            headers={"Origin": "http://localhost:5173"},
            json={"token": "x" * 48, "password": "not the registration password"},
        )
        for _ in range(11)
    ]
    assert all(response.status_code == 400 for response in responses[:10])
    assert responses[-1].status_code == 429
    limiter.reset()


def test_email_verification_requires_the_pending_registration_password(postgres_client) -> None:
    client, sessions = postgres_client
    response = client.post(
        "/api/account/register",
        headers={"Origin": "http://localhost:5173"},
        json={"display_name": "First Name", "email": "pending@example.com", "password": "first secure passphrase"},
    )
    assert response.status_code == 202

    # A later registration for the same still-unverified mailbox replaces the
    # pending credentials instead of preserving an attacker's chosen password.
    response = client.post(
        "/api/account/register",
        headers={"Origin": "http://localhost:5173"},
        json={"display_name": "Mailbox Owner", "email": "pending@example.com", "password": "second secure passphrase"},
    )
    assert response.status_code == 202
    with sessions() as db:
        user = db.scalar(select(User).where(User.email == "pending@example.com"))
        token = issue_token(db, user, "verify_email", 1)

    wrong = client.post(
        "/api/account/email/verify",
        headers={"Origin": "http://localhost:5173"},
        json={"token": token, "password": "first secure passphrase"},
    )
    assert wrong.status_code == 400
    with sessions() as db:
        account_token = db.scalar(select(AccountToken).where(AccountToken.token_hash == hash_secret(token)))
        assert account_token is not None and account_token.consumed_at is None

    verified = client.post(
        "/api/account/email/verify",
        headers={"Origin": "http://localhost:5173"},
        json={"token": token, "password": "second secure passphrase"},
    )
    assert verified.status_code == 200
    with sessions() as db:
        user = db.scalar(select(User).where(User.email == "pending@example.com"))
        assert user is not None and user.email_verified_at is not None


def test_verified_oauth_adoption_discards_unverified_local_credentials(postgres_client) -> None:
    client, sessions = postgres_client
    response = client.post(
        "/api/account/register",
        headers={"Origin": "http://localhost:5173"},
        json={"display_name": "Pending User", "email": "oauth@example.com", "password": "attacker chosen passphrase"},
    )
    assert response.status_code == 202

    with sessions() as db:
        user = db.scalar(select(User).where(User.email == "oauth@example.com"))
        assert user is not None and user.password_hash is not None
        issue_token(db, user, "reset_password", 1)
        now = datetime.now(UTC)
        discard_unverified_local_credentials(db, user, now)
        user.email_verified_at = now
        db.commit()

    with sessions() as db:
        user = db.scalar(select(User).where(User.email == "oauth@example.com"))
        assert user is not None and user.password_hash is None
        outstanding = db.scalar(
            select(func.count(AccountToken.id)).where(
                AccountToken.user_id == user.id,
                AccountToken.consumed_at.is_(None),
            )
        )
        assert outstanding == 0


def test_catalog_json_filters_are_executed_by_postgres_and_refresh_is_admin_only(postgres_client) -> None:
    client, sessions = postgres_client
    with sessions() as db:
        from tests.test_seo import game_fixture

        db.add(game_fixture(
            developer="Fixture Studio",
            publisher="Fixture Publishing",
            game_modes=["singleplayer"],
            playtime_minutes=600,
            award_count=1,
            source_scores=[
                {"source": "Metacritic", "score": 86, "scale": 100, "status": "live", "review_count": 25},
                {"source": "OpenCritic", "score": 87, "scale": 100, "status": "live", "review_count": 30},
                {"source": "IGDB", "score": 88, "scale": 100, "status": "live", "review_count": 35},
                {"source": "Steam", "score": 89, "scale": 100, "status": "live", "review_count": 500},
            ],
        ))
        db.commit()

    response = client.get(
        "/api/games",
        params={
            "genre": "RPG",
            "developer": "Fixture Studio",
            "publisher": "Fixture Publishing",
            "platform": "Steam",
            "min_ratings": 100,
            "max_ratings": 1000,
            "min_live_sources": 4,
            "player_mode": "singleplayer",
            "playtime_min_hours": 1,
            "playtime_max_hours": 20,
            "require_critic": True,
            "has_award": True,
            "sort": "review_count",
        },
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert [game["slug"] for game in response.json()["games"]] == ["a-complete-test-game"]

    assert client.get("/api/games/a-complete-test-game").status_code == 200
    denied_refresh = client.get("/api/games/a-complete-test-game", params={"refresh": True})
    assert denied_refresh.status_code == 403
