import pytest
from pydantic import ValidationError

from app.routers.analytics import AnalyticsEventPayload, PageViewPayload, _clean_path, _clean_referrer


def test_analytics_strips_query_fragments_and_referrer_credentials() -> None:
    assert _clean_path("https://gamemetrix.me/game/test?token=secret#score") == "/game/test"
    assert _clean_referrer("https://user:pass@google.com/search?q=private") == "https://google.com/search"


def test_analytics_rejects_unbounded_or_non_finite_properties() -> None:
    with pytest.raises(ValidationError):
        AnalyticsEventPayload(event_type="share", properties={"x" * 65: "value"})
    with pytest.raises(ValidationError):
        AnalyticsEventPayload(event_type="share", properties={"score": float("nan")})


def test_analytics_accepts_only_opaque_ids_and_event_specific_values() -> None:
    PageViewPayload(
        path="/",
        visitor_id="2df74679-4e9e-4104-9812-6a090f9c4626",
        language="en-US",
        timezone="Europe/Berlin",
    )
    AnalyticsEventPayload(
        event_type="store_outbound",
        visitor_id="2df74679-4e9e-4104-9812-6a090f9c4626",
        properties={"game_slug": "complete-test-game", "store": "Steam"},
    )
    with pytest.raises(ValidationError):
        PageViewPayload(path="/", visitor_id="person@example.com")
    with pytest.raises(ValidationError):
        AnalyticsEventPayload(
            event_type="store_outbound",
            properties={"game_slug": "complete-test-game", "store": "person@example.com"},
        )
