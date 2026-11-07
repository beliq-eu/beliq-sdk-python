"""Timeout and retry behaviour.

The former 30s default timeout sat *below* beliq's measured p95 for a document
request, so the client aborted work the server went on to finish and the caller
could not tell whether the document had been produced. And nothing was retried,
even though beliq's own docs tell customers to retry 429 and 503 and both arrive
with a ``Retry-After`` saying exactly when.
"""

from __future__ import annotations

import asyncio
import socket
import threading
from pathlib import Path

import httpx
import pytest
import respx

import beliq.client
from beliq import AsyncBeliq, Beliq
from beliq.constants import DEFAULT_MAX_RETRIES, DEFAULT_RETRY_BUDGET_SECONDS, DEFAULT_TIMEOUT_SECONDS
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
# spent quota. No wait clears it sooner, so it is raised at once and names the cause.
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
@pytest.mark.usefixtures("fast_backoff")
def test_refused_connection_raises_httpx_connect_error_once_retrying_ends() -> None:
    # The README tells callers to catch httpx.TransportError beside BeliqApiError.
    route = respx.get(ME_URL).mock(side_effect=httpx.ConnectError("connection refused"))
    with pytest.raises(httpx.ConnectError) as caught:
        _client().me()
    assert not isinstance(caught.value, BeliqApiError)
    assert route.call_count == DEFAULT_MAX_RETRIES + 1


@respx.mock
@pytest.mark.usefixtures("fast_backoff")
@pytest.mark.parametrize(
    "error",
    [httpx.ReadError("reset"), httpx.WriteError("broken pipe"), httpx.RemoteProtocolError("closed")],
)
def test_a_connection_lost_after_it_opened_is_retried_by_the_count(error: httpx.TransportError) -> None:
    # beliq does not charge a repeat of a charged request inside 15 minutes, so a
    # retry of a charged request is not charged again. tests/test_retry_lost_connection.py runs the
    # close and the reset against a real socket. The short budget makes a client
    # that retried it by the budget fail here in seconds rather than hang.
    route = respx.get(ME_URL).mock(side_effect=error)
    with pytest.raises(type(error)):
        Beliq(API_KEY, retry_budget=5.0).me()
    assert route.call_count == DEFAULT_MAX_RETRIES + 1


@respx.mock
@pytest.mark.parametrize(
    "error",
    [httpx.WriteTimeout("timed out"), httpx.PoolTimeout("timed out"), httpx.LocalProtocolError("bad header")],
)
def test_other_transport_errors_are_not_retried(error: httpx.TransportError) -> None:
    # A timeout is this client's own deadline, and a repeat would take as long
    # again; a local protocol error is the same on every attempt.
    route = respx.get(ME_URL).mock(side_effect=error)
    with pytest.raises(type(error)):
        Beliq(API_KEY).me()
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


@pytest.fixture
def fast_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(beliq.client, "BACKOFF_BASE_SECONDS", 0.001)


class FakeClock:
    """Stands in for the time module in beliq.client: sleeping moves the clock."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(beliq.client, "time", fake)
    return fake


# More failures than the count allows, so only a class the count does not bound
# gets through them.
PAST_THE_COUNT = DEFAULT_MAX_RETRIES + 3


@respx.mock
def test_database_unavailable_is_retried_past_the_count() -> None:
    route = respx.get(ME_URL).mock(side_effect=[_err(503, "DATABASE_UNAVAILABLE")] * PAST_THE_COUNT + [_ok()])
    Beliq(API_KEY).me()
    assert route.call_count == PAST_THE_COUNT + 1


@respx.mock
@pytest.mark.parametrize("status", [502, 503])
def test_a_5xx_with_no_beliq_code_is_retried_past_the_count(status: int) -> None:
    bare = httpx.Response(status, text="Bad Gateway", headers={"retry-after": "0"})
    route = respx.get(ME_URL).mock(side_effect=[bare] * PAST_THE_COUNT + [_ok()])
    Beliq(API_KEY).me()
    assert route.call_count == PAST_THE_COUNT + 1


@respx.mock
@pytest.mark.usefixtures("fast_backoff")
@pytest.mark.parametrize("error", [httpx.ConnectError("refused"), httpx.ConnectTimeout("timed out")])
def test_a_connection_that_never_opened_is_retried_past_the_count(error: httpx.TransportError) -> None:
    route = respx.get(ME_URL).mock(side_effect=[error] * PAST_THE_COUNT + [_ok()])
    Beliq(API_KEY).me()
    assert route.call_count == PAST_THE_COUNT + 1


@respx.mock
@pytest.mark.parametrize(
    ("status", "code"),
    [
        (503, "ENGINE_UNAVAILABLE"),
        (502, "ENGINE_UNAVAILABLE"),
        (503, "CONVERSION_TOOL_UNAVAILABLE"),
        (502, "DATABASE_UNAVAILABLE"),
        (429, "RATE_LIMITED"),
        (429, "ACCOUNT_THROTTLED"),
    ],
)
def test_coded_answers_are_retried_by_the_count_only(status: int, code: str) -> None:
    # An engine timeout answers ENGINE_UNAVAILABLE too, and each retried 429 counts
    # toward the account's throttle, so these keep the count.
    route = respx.get(ME_URL).mock(return_value=_err(status, code))
    with pytest.raises(BeliqApiError) as caught:
        Beliq(API_KEY).me()
    assert caught.value.code == code
    assert route.call_count == DEFAULT_MAX_RETRIES + 1


@respx.mock
@pytest.mark.usefixtures("fast_backoff")
def test_max_retries_set_by_the_caller_caps_the_budget_class() -> None:
    route = respx.get(ME_URL).mock(return_value=_err(503, "DATABASE_UNAVAILABLE"))
    # A short budget, so a client that ignored the cap would fail here in seconds.
    with pytest.raises(BeliqApiError):
        Beliq(API_KEY, max_retries=2, retry_budget=2.0).me()
    assert route.call_count == 3


@respx.mock
def test_max_retries_zero_stops_a_refused_connection_too() -> None:
    route = respx.get(ME_URL).mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(httpx.ConnectError):
        Beliq(API_KEY, max_retries=0, retry_budget=2.0).me()
    assert route.call_count == 1


@respx.mock
def test_retry_budget_zero_disables_retrying() -> None:
    route = respx.get(ME_URL).mock(return_value=_err(503, "DATABASE_UNAVAILABLE"))
    with pytest.raises(BeliqApiError):
        Beliq(API_KEY, retry_budget=0).me()
    assert route.call_count == 1


@respx.mock
def test_retry_after_longer_than_30_seconds_is_waited_in_full(clock: FakeClock) -> None:
    # The header was capped at 30 s before the budget existed; now the budget is
    # what keeps one header from hanging a call, so the server's value holds.
    respx.get(ME_URL).mock(side_effect=[_err(503, "DATABASE_UNAVAILABLE", retry_after="45"), _ok()])
    Beliq(API_KEY).me()
    assert len(clock.sleeps) == 1
    assert 45.0 <= clock.sleeps[0] < 45.25


@respx.mock
def test_stops_at_the_exported_default_budget(clock: FakeClock) -> None:
    # Retry-After: 60 against a 900 s budget: attempts at 0, 60, ... 840 s, and the
    # wait after the one at 840 s would start an attempt past the budget.
    route = respx.get(ME_URL).mock(return_value=_err(503, "DATABASE_UNAVAILABLE", retry_after="60"))
    with pytest.raises(BeliqApiError):
        Beliq(API_KEY).me()
    assert route.call_count == int(DEFAULT_RETRY_BUDGET_SECONDS // 60)
    assert clock.now <= DEFAULT_RETRY_BUDGET_SECONDS


@respx.mock
def test_no_backoff_wait_reaches_the_ceiling(clock: FakeClock) -> None:
    bare = httpx.Response(503, text="Service Unavailable")
    respx.get(ME_URL).mock(side_effect=[bare] * 40 + [_ok()])
    Beliq(API_KEY).me()
    assert max(clock.sleeps) < beliq.client.BACKOFF_CEILING_SECONDS


@respx.mock
@pytest.mark.usefixtures("fast_backoff")
def test_async_client_retries_by_the_budget_too() -> None:
    route = respx.get(ME_URL).mock(
        side_effect=[httpx.ConnectError("refused"), *[_err(503, "DATABASE_UNAVAILABLE")] * PAST_THE_COUNT, _ok()]
    )

    async def go() -> object:
        client = AsyncBeliq(API_KEY)
        try:
            return await client.me()
        finally:
            await client.aclose()

    asyncio.run(go())
    assert route.call_count == PAST_THE_COUNT + 2



def test_a_failed_tls_handshake_is_raised_at_once() -> None:
    # TLS against a socket that answers plain HTTP: httpx raises ConnectError
    # caused by ssl.SSLError, the same chain as a certificate that fails
    # verification. No wait fixes it. The short budget makes a client that
    # retried it fail here in seconds rather than hang.
    accepted: list[int] = []
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen()
        srv.settimeout(5.0)

        def serve() -> None:
            while True:
                try:
                    conn, _ = srv.accept()
                except OSError:
                    return
                accepted.append(1)
                with conn:
                    conn.recv(4096)
                    conn.sendall(b"HTTP/1.1 400 Bad Request\r\ncontent-length: 0\r\n\r\n")

        threading.Thread(target=serve, daemon=True).start()
        with pytest.raises(httpx.ConnectError):
            Beliq(API_KEY, base_url=f"https://127.0.0.1:{srv.getsockname()[1]}", retry_budget=2.0).me()
    assert accepted == [1]
