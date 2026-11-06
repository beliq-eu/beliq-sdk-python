"""The ``ruleset`` option of validate, against a real HTTP server on 127.0.0.1.

``POST /v1/validate`` reads the ``Beliq-Ruleset`` request header to choose the
rules a document is checked against. With no header, the API runs the key's
organisation default, which is ``latest`` unless the organisation chose
``previous``. So the client sends the header only when the caller sets the
option: a header sent by default would override that organisation choice.

The body says which channel applied: ``rulesetChannel``, ``rulesetFellBack``
and ``rulesetSunsetsOn``. ``validate-france-previous.json`` is the body of a
live validate with ``Beliq-Ruleset: previous``, the same one as beliq-sdk-node's
``test/fixtures/live-validate-france-previous.json``.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from beliq import AsyncBeliq, Beliq

API_KEY = "blq_test_key"
DOCUMENT = b"<Invoice/>"
FIXTURES = Path(__file__).parent / "fixtures"
PREVIOUS_BODY = (FIXTURES / "validate-france-previous.json").read_bytes()
# A validate body from a request that carried no Beliq-Ruleset header.
DEFAULT_BODY = (FIXTURES / "validate-invalid.json").read_bytes()


class Recorder:
    """A server on 127.0.0.1 that answers every POST with one body and records each request."""

    def __init__(self, body: bytes) -> None:
        self.requests: list[tuple[str, Message]] = []
        requests = self.requests

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                self.rfile.read(int(self.headers.get("content-length", "0")))
                requests.append((self.path, self.headers))
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def servers() -> Iterator[list[Recorder]]:
    started: list[Recorder] = []
    yield started
    for s in started:
        s.close()


def start(servers: list[Recorder], body: bytes = PREVIOUS_BODY) -> Recorder:
    s = Recorder(body)
    servers.append(s)
    return s


def test_ruleset_previous_sends_the_header(servers: list[Recorder]) -> None:
    """(1) ruleset="previous" sends Beliq-Ruleset: previous."""
    s = start(servers)
    with Beliq(API_KEY, base_url=s.base_url, max_retries=0) as beliq:
        beliq.validate(DOCUMENT, ruleset="previous")
    assert len(s.requests) == 1
    path, headers = s.requests[0]
    assert path.startswith("/v1/validate")
    assert headers.get_all("beliq-ruleset") == ["previous"]


def test_ruleset_previous_sends_the_header_async(servers: list[Recorder]) -> None:
    """(1) The same through AsyncBeliq."""
    s = start(servers)

    async def go() -> None:
        async with AsyncBeliq(API_KEY, base_url=s.base_url, max_retries=0) as beliq:
            await beliq.validate(DOCUMENT, ruleset="previous")

    asyncio.run(go())
    assert len(s.requests) == 1
    assert s.requests[0][1].get_all("beliq-ruleset") == ["previous"]


def test_pin_list_is_sent_as_given(servers: list[Recorder]) -> None:
    pins = "cii_xsd:D16B, en16931_cii_schematron:1.3.16"
    s = start(servers)
    with Beliq(API_KEY, base_url=s.base_url, max_retries=0) as beliq:
        beliq.validate(DOCUMENT, ruleset=pins)
    assert s.requests[0][1].get_all("beliq-ruleset") == [pins]


def test_no_ruleset_sends_no_header(servers: list[Recorder]) -> None:
    """(2) No ruleset option sends no Beliq-Ruleset header."""
    s = start(servers)
    with Beliq(API_KEY, base_url=s.base_url, max_retries=0) as beliq:
        beliq.validate(DOCUMENT)

    async def go() -> None:
        async with AsyncBeliq(API_KEY, base_url=s.base_url, max_retries=0) as beliq:
            await beliq.validate(DOCUMENT)

    asyncio.run(go())
    assert len(s.requests) == 2
    for _, headers in s.requests:
        assert headers.get_all("beliq-ruleset") is None


def test_channel_fields_are_typed(servers: list[Recorder]) -> None:
    """(3) rulesetChannel, rulesetFellBack and rulesetSunsetsOn come back as typed attributes."""
    s = start(servers)
    with Beliq(API_KEY, base_url=s.base_url, max_retries=0) as beliq:
        result = beliq.validate(DOCUMENT)
    assert result.ruleset_channel == "previous"
    assert result.ruleset_fell_back is False
    assert result.ruleset_sunsets_on == "2027-05-16"


def test_channel_fields_absent_are_none(servers: list[Recorder]) -> None:
    """(3) A body without the three fields gives None for each."""
    s = start(servers, DEFAULT_BODY)
    with Beliq(API_KEY, base_url=s.base_url, max_retries=0) as beliq:
        result = beliq.validate(DOCUMENT)
    assert result.ruleset_channel is None
    assert result.ruleset_fell_back is None
    assert result.ruleset_sunsets_on is None
