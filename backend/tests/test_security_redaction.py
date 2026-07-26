import httpx
import pytest

from app.integrations.hltb.client import _bounded_text, _same_origin_url
from app.services.admin_audit import redact_query


def test_admin_audit_query_redacts_credentials_and_tokens() -> None:
    query = redact_query(
        "limit=20&token=header.payload.signature&password=hunter2&oauth_code=secret"
    )

    assert query is not None
    assert "limit=20" in query
    assert "header.payload.signature" not in query
    assert "hunter2" not in query
    assert "secret" not in query
    assert query.count("%5BREDACTED%5D") == 3


def test_hltb_script_urls_are_restricted_to_the_expected_https_origin() -> None:
    assert _same_origin_url("/_next/static/app.js") == (
        "https://howlongtobeat.com/_next/static/app.js"
    )
    assert _same_origin_url("https://howlongtobeat.com/app.js") is not None
    assert _same_origin_url("http://howlongtobeat.com/app.js") is None
    assert _same_origin_url("//evil.example/app.js") is None
    assert _same_origin_url("https://howlongtobeat.com.evil.example/app.js") is None


def test_hltb_response_body_is_bounded() -> None:
    response = httpx.Response(
        200,
        content=b"x" * (2 * 1024 * 1024 + 1),
        request=httpx.Request("GET", "https://howlongtobeat.com/app.js"),
    )

    with pytest.raises(httpx.DecodingError):
        _bounded_text(response)
