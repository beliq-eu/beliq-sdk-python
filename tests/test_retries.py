"""Timeout and retry behaviour.

The former 30s default timeout sat *below* beliq's measured p95 for a document
request, so the client aborted work the server went on to finish and the caller
could not tell whether the document had been produced. And nothing was retried,
even though beliq's own docs tell customers to retry 429 and 503 and both arrive
with a ``Retry-After`` saying exactly when.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
import respx

from beliq import Beliq
from beliq.constants import DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT_SECONDS
from beliq.errors import BeliqApiError

API_KEY = "blq_test_key"
ME_URL = "https://api.beliq.eu/v1/me"
FIXTURES = Path(__file__).parent / "fixtures"


def _client(**kwargs: object) -> Beliq:
    kwargs.setdefault("max_retries", DEFAULT_MAX_RETRIES)
    return Beliq(API_KEY, **kwargs)  # type: ignore[arg-type]


def _ok() -> httpx.Response:
    """A real /v1/me envelope; AccountInfo validates the whole shape."""
    return httpx.Response(200, text=(FIXTURES / "me.json").read_text())


def _err(status: int, code: str, retry_after: str | None = "0") -> httpx.Response:
    headers = {"retry-after": retry_after} if retry_after is not None else {}
    return httpx.Response(status, json={"success": False, "error": {"code": code, "message": code}}, headers=headers)


def test_default_timeout_exceeds_measured_p95() -> None:
    """A client deadline below the server's own is what caused abandoned work."""
    assert DEFAULT_TIMEOUT_SECONDS >= 60.0


@respx.mock
def test_retries_503_then_succeeds() -> None:
    route = respx.get(ME_URL).mock(side_effect=[_err(503, "ENGINE_UNAVAILABLE"), _ok()])
    result = _client().me()
    assert route.call_count == 2
    assert result.org.name == "Acme GmbH"


@respx.mock
def test_retries_429_honouring_retry_after() -> None:
    route = respx.get(ME_URL).mock(side_effect=[_err(429, "RATE_LIMITED"), _ok()])
    _client().me()
    assert route.call_count == 2


# Seconds to the end of a monthly billing window, which is what beliq sends on a
# spent quota. Retrying it clamps to MAX_RETRY_AFTER_SECONDS and sleeps that per
# attempt, so the caller meets its own deadline instead of the quota message.
WINDOW_REMAINING_SECONDS = str(29 * 24 * 60 * 60)


@respx.mock
def test_does_not_retry_spent_monthly_quota() -> None:
    route = respx.get(ME_URL).mock(
        return_value=_err(429, "QUOTA_EXCEEDED", retry_after=WINDOW_REMAINING_SECONDS)
    )
    with pytest.raises(BeliqApiError) as excinfo:
        _client().me()
    assert excinfo.value.status == 429
    assert excinfo.value.code == "QUOTA_EXCEEDED"
    assert route.call_count == 1


@respx.mock
@pytest.mark.parametrize("code", ["RATE_LIMITED", "ACCOUNT_THROTTLED"])
def test_still_retries_the_429s_that_waiting_clears(code: str) -> None:
    route = respx.get(ME_URL).mock(side_effect=[_err(429, code), _ok()])
    _client().me()
    assert route.call_count == 2


@respx.mock
def test_async_client_does_not_retry_spent_monthly_quota() -> None:
    from beliq import AsyncBeliq

    route = respx.get(ME_URL).mock(
        return_value=_err(429, "QUOTA_EXCEEDED", retry_after=WINDOW_REMAINING_SECONDS)
    )

    async def go() -> object:
        client = AsyncBeliq(API_KEY, max_retries=2)
        try:
            return await client.me()
        finally:
            await client.aclose()

    with pytest.raises(BeliqApiError) as excinfo:
        asyncio.run(go())
    assert excinfo.value.code == "QUOTA_EXCEEDED"
    assert route.call_count == 1


@respx.mock
def test_does_not_retry_504() -> None:
    # The one status where a retry can duplicate a document: the work may still
    # be running server-side.
    route = respx.get(ME_URL).mock(return_value=_err(504, "ENGINE_UNAVAILABLE"))
    with pytest.raises(BeliqApiError):
        _client().me()
    assert route.call_count == 1


@respx.mock
def test_does_not_retry_client_error() -> None:
    route = respx.get(ME_URL).mock(return_value=_err(403, "INVALID_API_KEY", retry_after=None))
    with pytest.raises(BeliqApiError) as excinfo:
        _client().me()
    assert excinfo.value.status == 403
    assert route.call_count == 1


@respx.mock
def test_gives_up_after_max_retries() -> None:
    route = respx.get(ME_URL).mock(return_value=_err(503, "ENGINE_UNAVAILABLE"))
    with pytest.raises(BeliqApiError) as excinfo:
        _client(max_retries=2).me()
    assert excinfo.value.status == 503
    # First attempt plus two retries.
    assert route.call_count == 3


@respx.mock
def test_max_retries_zero_disables_retrying() -> None:
    route = respx.get(ME_URL).mock(return_value=_err(503, "ENGINE_UNAVAILABLE"))
    with pytest.raises(BeliqApiError):
        _client(max_retries=0).me()
    assert route.call_count == 1


@respx.mock
def test_timeout_is_not_retried() -> None:
    # Our own deadline firing says nothing about whether the server finished, so
    # retrying could produce a second document.
    route = respx.get(ME_URL).mock(side_effect=httpx.ReadTimeout("timed out"))
    with pytest.raises(httpx.ReadTimeout):
        _client().me()
    assert route.call_count == 1


@respx.mock
def test_malformed_retry_after_falls_back_to_backoff() -> None:
    # A non-numeric header must not raise or hang; it just means "use backoff".
    route = respx.get(ME_URL).mock(side_effect=[_err(503, "ENGINE_UNAVAILABLE", retry_after="soon"), _ok()])
    _client().me()
    assert route.call_count == 2


@respx.mock
def test_async_client_retries_too() -> None:
    from beliq import AsyncBeliq

    route = respx.get(ME_URL).mock(side_effect=[_err(503, "ENGINE_UNAVAILABLE"), _ok()])

    async def go() -> object:
        client = AsyncBeliq(API_KEY, max_retries=2)
        try:
            return await client.me()
        finally:
            await client.aclose()

    result = asyncio.run(go())
    assert route.call_count == 2
    assert result.org.name == "Acme GmbH"
