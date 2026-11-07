"""A connection lost after the request was sent, against a real socket on 127.0.0.1.

beliq charges a compute request before it runs, and runs it to the end after the
client has gone, so a connection lost after the send can mean the work ran and was
charged. beliq does not charge a repeat of a charged request again inside 15
minutes, up to 10 repeats. A repeat is the same request from the same
organisation and mode, where "the same" covers the route, query, Content-Type,
Accept and body, and on validate the ruleset selection that applies
(https://docs.beliq.eu/api-reference/errors/#repeated-requests-are-not-charged-again).
So the client retries such a loss, by the count, with the same request bytes on
every attempt. It does not retry its own timeout: a repeat runs
the engine again and takes as long as the first attempt did.

The stub reads the whole request before it decides, so each loss below comes after
the send. Closing the socket raises httpx.RemoteProtocolError, resetting it
httpx.ReadError; both were read from httpx 0.28.1.
"""

from __future__ import annotations

import asyncio
import json
import socket
import struct
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
import pytest

import beliq.client
from beliq import AsyncBeliq, Beliq, BeliqApiError
from beliq.constants import DEFAULT_MAX_RETRIES

API_KEY = "blq_test_key"
VALIDATE_BODY = (Path(__file__).parent / "fixtures" / "validate-invalid.json").read_bytes()
DOCUMENT = b"<rsm:CrossIndustryInvoice/>"

# The client's deadline in case 5, and how long after the request the stub answers.
SHORT_TIMEOUT_SECONDS = 0.5
ANSWER_AFTER_SECONDS = 2.0

Drop = Literal["close", "reset"]


@dataclass
class Answer:
    status: int
    body: bytes
    delay: float = 0.0


Step = Drop | Answer

VALID = Answer(200, VALIDATE_BODY)


def engine_unavailable() -> Answer:
    body = {"success": False, "error": {"code": "ENGINE_UNAVAILABLE", "message": "The engine is unavailable."}}
    return Answer(503, json.dumps(body).encode())


def _read_request(conn: socket.socket) -> bytes:
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(65536)
        if not chunk:
            return data
        data += chunk
    head, _, body = data.partition(b"\r\n\r\n")
    length = 0
    for line in head.split(b"\r\n")[1:]:
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"content-length":
            length = int(value)
    while len(body) < length:
        chunk = conn.recv(65536)
        if not chunk:
            break
        body += chunk
    return head + b"\r\n\r\n" + body


class RawServer:
    """One request per connection. ``decide`` gets the request's index, 0-based."""

    def __init__(self, decide: Callable[[int], Step]) -> None:
        self.requests: list[bytes] = []
        self._decide = decide
        self._lock = threading.Lock()
        self._sock = socket.socket()
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen()
        self.port: int = self._sock.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self) -> None:
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        request = _read_request(conn)
        with self._lock:
            index = len(self.requests)
            self.requests.append(request)
            step = self._decide(index)
        try:
            if step == "reset":
                conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            elif isinstance(step, Answer):
                time.sleep(step.delay)
                head = (
                    f"HTTP/1.1 {step.status} X\r\ncontent-type: application/json\r\n"
                    f"content-length: {len(step.body)}\r\nconnection: close\r\n\r\n"
                )
                conn.sendall(head.encode() + step.body)
        except OSError:
            pass  # the client gave up first
        finally:
            conn.close()

    def close(self) -> None:
        self._sock.close()


@pytest.fixture
def servers() -> Iterator[list[RawServer]]:
    started: list[RawServer] = []
    yield started
    for s in started:
        s.close()


@pytest.fixture(autouse=True)
def fast_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(beliq.client, "BACKOFF_BASE_SECONDS", 0.001)


def start(servers: list[RawServer], decide: Callable[[int], Step]) -> RawServer:
    s = RawServer(decide)
    servers.append(s)
    return s


def client(port: int, **kwargs: object) -> Beliq:
    kwargs.setdefault("timeout", 5.0)
    return Beliq(API_KEY, base_url=f"http://127.0.0.1:{port}", **kwargs)  # type: ignore[arg-type]


def validate(c: Beliq) -> object:
    return c.validate(DOCUMENT, format="cii")


@pytest.mark.parametrize("drop", ["close", "reset"])
def test_1_a_connection_lost_after_the_send_is_retried(servers: list[RawServer], drop: Drop) -> None:
    s = start(servers, lambda n: drop if n == 0 else VALID)

    result = client(s.port).validate(DOCUMENT, format="cii")

    assert result.format == "cii"
    assert len(s.requests) == 2
    # The same bytes on both attempts, which is what makes the second one a repeat.
    assert s.requests[0] == s.requests[1]


@pytest.mark.parametrize("drop", ["close", "reset"])
def test_1b_the_async_client_retries_it_too(servers: list[RawServer], drop: Drop) -> None:
    s = start(servers, lambda n: drop if n == 0 else VALID)

    async def go() -> object:
        async with AsyncBeliq(API_KEY, base_url=f"http://127.0.0.1:{s.port}", timeout=5.0) as c:
            return await c.validate(DOCUMENT, format="cii")

    result = asyncio.run(go())

    assert getattr(result, "format", None) == "cii"
    assert len(s.requests) == 2
    assert s.requests[0] == s.requests[1]


def test_2_the_count_bounds_it_and_httpx_own_error_is_raised(servers: list[RawServer]) -> None:
    s = start(servers, lambda _n: "close")

    # The short budget makes a client that retried it by the budget fail here in
    # seconds rather than hang.
    with pytest.raises(httpx.RemoteProtocolError) as caught:
        validate(client(s.port, retry_budget=5.0))

    assert not isinstance(caught.value, BeliqApiError)
    assert len(s.requests) == DEFAULT_MAX_RETRIES + 1


def test_3_a_lost_connection_and_engine_answers_share_one_count(servers: list[RawServer]) -> None:
    s = start(servers, lambda n: "reset" if n == 0 else engine_unavailable())

    with pytest.raises(BeliqApiError) as caught:
        validate(client(s.port))

    assert caught.value.code == "ENGINE_UNAVAILABLE"
    assert len(s.requests) == DEFAULT_MAX_RETRIES + 1


def test_4_max_retries_zero_does_not_retry_it(servers: list[RawServer]) -> None:
    s = start(servers, lambda n: "close" if n == 0 else VALID)

    with pytest.raises(httpx.RemoteProtocolError):
        validate(client(s.port, max_retries=0))

    assert len(s.requests) == 1


def test_5_the_clients_own_timeout_is_not_retried(servers: list[RawServer]) -> None:
    s = start(servers, lambda _n: Answer(VALID.status, VALID.body, delay=ANSWER_AFTER_SECONDS))

    with pytest.raises(httpx.ReadTimeout):
        validate(client(s.port, timeout=SHORT_TIMEOUT_SECONDS))

    assert len(s.requests) == 1
