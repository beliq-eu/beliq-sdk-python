"""The retry budget against a real HTTP server on 127.0.0.1.

While beliq's database is out, the API answers 503 ``DATABASE_UNAVAILABLE`` with
``Retry-After: 30``. Two of the three database outages beliq has measured lasted
about 9 and 12 minutes, the third 33. A client that stops after 3 retries gives up about 2 minutes in, and one that
raises on a refused connection gives up at once, so every caller loses its call.
These cases hold the client to a time budget instead: it rides a window shorter
than the budget, gives up once the budget is spent, follows the server's
``Retry-After`` in full, and keeps its own backoff under a ceiling.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import beliq.client
from beliq import Beliq, BeliqApiError

API_KEY = "blq_test_key"
ME_BODY = (Path(__file__).parent / "fixtures" / "me.json").read_bytes()

# The scaled-down backoff of case 4: base and ceiling in tens of ms instead of 0.5 s and 30 s.
SCALED_BASE_SECONDS = 0.01
SCALED_CEILING_SECONDS = 0.2
# Scheduling noise on a loaded CI runner, on top of the ceiling.
SLACK_SECONDS = 0.3


@dataclass
class Answer:
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""


OK = Answer(200, {"content-type": "application/json"}, ME_BODY)

# The edge's own 503: no beliq envelope, no error code, no Retry-After.
EDGE_503 = Answer(503, {"content-type": "text/plain"}, b"Service Unavailable")


def database_unavailable(retry_after: str | None = None) -> Answer:
    headers = {"content-type": "application/json"}
    if retry_after is not None:
        headers["retry-after"] = retry_after
    body = {"success": False, "error": {"code": "DATABASE_UNAVAILABLE", "message": "The database is unavailable."}}
    return Answer(503, headers, json.dumps(body).encode())


# What the server answers to its n-th request (0-based), t seconds after the first one.
Decide = Callable[[int, float], Answer]


class Stub:
    """A server on 127.0.0.1 that records when each request arrived."""

    def __init__(self, decide: Decide, port: int = 0) -> None:
        self.arrivals: list[float] = []
        first: list[float] = []
        lock = threading.Lock()
        arrivals = self.arrivals

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                with lock:
                    now = time.monotonic()
                    if not first:
                        first.append(now)
                    arrivals.append(now - first[0])
                    answer = decide(len(arrivals) - 1, now - first[0])
                self.send_response(answer.status)
                for name, value in answer.headers.items():
                    self.send_header(name, value)
                self.send_header("content-length", str(len(answer.body)))
                self.end_headers()
                self.wfile.write(answer.body)

            def log_message(self, format: str, *args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.port = self.server.server_address[1]
        self.listening_at = time.monotonic()
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def stubs() -> Iterator[list[Stub]]:
    started: list[Stub] = []
    yield started
    for s in started:
        s.close()


def start(stubs: list[Stub], decide: Decide) -> Stub:
    s = Stub(decide)
    stubs.append(s)
    return s


def free_port() -> int:
    """A port nothing listens on yet: bound once to learn a free number, then closed."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port


def listen_later(stubs: list[Stub], port: int, delay: float, decide: Decide) -> threading.Thread:
    def go() -> None:
        time.sleep(delay)
        stubs.append(Stub(decide, port))

    thread = threading.Thread(target=go, daemon=True)
    thread.start()
    return thread


def client(port: int, **kwargs: object) -> Beliq:
    return Beliq(API_KEY, base_url=f"http://127.0.0.1:{port}", timeout=5.0, **kwargs)  # type: ignore[arg-type]


@pytest.fixture
def scaled_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(beliq.client, "BACKOFF_BASE_SECONDS", SCALED_BASE_SECONDS)
    # raising=False, so this also ran, red, against the client before the ceiling existed.
    monkeypatch.setattr(beliq.client, "BACKOFF_CEILING_SECONDS", SCALED_CEILING_SECONDS, raising=False)


def test_1_rides_a_database_window_inside_the_budget(stubs: list[Stub]) -> None:
    s = start(stubs, lambda _n, t: database_unavailable("1") if t < 20.0 else OK)
    started = time.monotonic()

    result = client(s.port, retry_budget=30.0).me()

    assert result.org.name == "Acme GmbH"
    assert time.monotonic() - started >= 20.0
    assert len(s.arrivals) > 4


def test_2_ends_in_the_503_once_the_budget_is_spent(stubs: list[Stub]) -> None:
    budget = 8.0
    s = start(stubs, lambda _n, _t: database_unavailable("1"))
    started = time.monotonic()

    with pytest.raises(BeliqApiError) as caught:
        client(s.port, retry_budget=budget).me()
    elapsed = time.monotonic() - started

    assert caught.value.status == 503
    assert caught.value.code == "DATABASE_UNAVAILABLE"
    # It stops when the next wait (1 s plus up to 0.25 s of jitter) would start an
    # attempt past the budget, so no earlier than one wait before it ends.
    assert elapsed >= budget - 1.25 - SLACK_SECONDS
    assert elapsed <= budget + SLACK_SECONDS


def test_3_a_refused_connection_inside_the_budget_ends_in_success(stubs: list[Stub]) -> None:
    port = free_port()
    listen_later(stubs, port, 3.0, lambda _n, _t: OK)

    result = client(port).me()

    assert result.org.name == "Acme GmbH"


@pytest.mark.usefixtures("scaled_backoff")
def test_4a_refused_connections_end_within_one_ceiling_of_the_window(stubs: list[Stub]) -> None:
    port = free_port()
    thread = listen_later(stubs, port, 2.0, lambda _n, _t: OK)

    client(port).me()
    done = time.monotonic()
    thread.join()

    assert done - stubs[-1].listening_at <= SCALED_CEILING_SECONDS + SLACK_SECONDS


@pytest.mark.usefixtures("scaled_backoff")
def test_4b_no_wait_after_a_bare_503_exceeds_the_ceiling(stubs: list[Stub]) -> None:
    window = 2.0
    s = start(stubs, lambda _n, t: EDGE_503 if t < window else OK)

    client(s.port).me()

    gaps = [b - a for a, b in zip(s.arrivals, s.arrivals[1:], strict=False)]
    assert max(gaps) <= SCALED_CEILING_SECONDS + SLACK_SECONDS
    assert s.arrivals[-1] - window <= SCALED_CEILING_SECONDS + SLACK_SECONDS


@pytest.mark.usefixtures("scaled_backoff")
def test_4c_a_run_with_retry_after_then_one_without_stays_under_the_ceiling(stubs: list[Stub]) -> None:
    run = 20

    def decide(n: int, _t: float) -> Answer:
        if n < run:
            return database_unavailable("0")
        return database_unavailable() if n == run else OK

    s = start(stubs, decide)

    client(s.port).me()

    assert len(s.arrivals) == run + 2
    assert s.arrivals[run + 1] - s.arrivals[run] <= SCALED_CEILING_SECONDS + SLACK_SECONDS


def test_5_a_retry_after_past_the_budget_left_ends_at_once(stubs: list[Stub]) -> None:
    s = start(stubs, lambda n, _t: database_unavailable("60") if n == 0 else OK)
    started = time.monotonic()

    with pytest.raises(BeliqApiError) as caught:
        client(s.port, retry_budget=5.0).me()

    assert caught.value.code == "DATABASE_UNAVAILABLE"
    assert time.monotonic() - started < 1.0
    assert len(s.arrivals) == 1
