"""Sync (Beliq) and async (AsyncBeliq) clients for the beliq API."""

from __future__ import annotations

import asyncio
import base64
import json
import random
import ssl
import time
from types import TracebackType
from typing import Any, Literal

import httpx

from ._build_request import (
    BuiltRequest,
    build_convert,
    build_generate,
    build_me,
    build_parse,
    build_validate,
)
from ._internal import DocumentInput, sniff_content_type, to_bytes
from .constants import (
    BACKOFF_BASE_SECONDS,
    BACKOFF_CEILING_SECONDS,
    DATABASE_UNAVAILABLE_CODE,
    DEFAULT_BASE_URL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_BUDGET_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    QUOTA_EXHAUSTED_CODE,
    RETRY_AFTER_JITTER_SECONDS,
    RETRYABLE_STATUSES,
)
from .errors import BeliqApiError, error_from_response, parse_envelope
from .types import (
    AccountInfo,
    ConvertMeta,
    ConvertResult,
    GenerateMeta,
    GenerateResult,
    Invoice,
    LostElement,
    LostElementsTruncated,
    ParseResult,
    RulesetArtifact,
    ValidationResult,
)

# blq_test_ marks a sandbox key; the server derives livemode from this exact prefix.
TEST_KEY_PREFIX = "blq_test_"


# How a failure is retried.
#
# "budget": an outage a wait can outlast, retried until the time budget is spent.
# A 503 DATABASE_UNAVAILABLE, a 502 or 503 with no beliq error code (the edge
# answered, or the pod that held the connection is gone), and a connection that
# could not be opened.
#
# "count": retried up to max_retries times. A 429 other than QUOTA_EXCEEDED, since
# each one counts toward the account's throttle, and a 502 or 503 with any other
# beliq code, ENGINE_UNAVAILABLE included, since an engine timeout answers that
# code too and a budget would run the same slow document dozens of times.
#
# Anything else is not retried, and a timeout or a connection lost after the
# request was sent raises httpx's own exception: the work may still be running on
# beliq's side, so a retry would run it, and charge it, a second time.
RetryClass = Literal["budget", "count"]

# httpx's errors for a connection that never opened: nothing reached the server,
# so nothing ran or was charged. httpx raises a refused connection, a DNS failure,
# a missing route and a failed TLS handshake all as ConnectError; the last is
# told apart by _is_tls_failure.
_BEFORE_SEND_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout)

# Clamped so a long run of attempts cannot overflow the float; the ceiling holds
# long before it.
_BACKOFF_MAX_EXPONENT = 64


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    """Seconds to wait before the next attempt.

    Uses the server's ``Retry-After`` in full when it sent one, otherwise
    exponential backoff. Jittered either way, so a fleet of clients that failed
    together does not all return at the same instant. The backoff is held to half
    the ceiling before its jitter of up to 100%, so no wait reaches the ceiling and
    clients at the cap still spread out.
    """
    if response is not None:
        header = response.headers.get("retry-after")
        if header:
            try:
                seconds = float(header)
            except ValueError:
                seconds = -1.0
            if seconds >= 0:
                return seconds + random.random() * RETRY_AFTER_JITTER_SECONDS
    backoff: float = min(
        BACKOFF_BASE_SECONDS * 2.0 ** min(attempt, _BACKOFF_MAX_EXPONENT),
        BACKOFF_CEILING_SECONDS / 2,
    )
    return backoff + random.random() * backoff


def _is_tls_failure(exc: BaseException) -> bool:
    """True when an ssl error caused it, such as a certificate that fails verification.

    No wait fixes that, so it is raised at once instead of retried for the budget.
    """
    seen: set[int] = set()
    cause: BaseException | None = exc
    while cause is not None and id(cause) not in seen:
        if isinstance(cause, ssl.SSLError):
            return True
        seen.add(id(cause))
        cause = cause.__cause__ or cause.__context__
    return False


def _error_code(response: httpx.Response) -> str | None:
    envelope = parse_envelope(response.content) or {}
    err = envelope.get("error")
    code = err.get("code") if isinstance(err, dict) else None
    return code if isinstance(code, str) and code else None


def _retry_class(response: httpx.Response) -> RetryClass | None:
    status = response.status_code
    if status not in RETRYABLE_STATUSES:
        return None
    code = _error_code(response)
    if status == 429:
        return None if code == QUOTA_EXHAUSTED_CODE else "count"
    if code is None:
        return "budget"
    return "budget" if status == 503 and code == DATABASE_UNAVAILABLE_CODE else "count"


class _Retries:
    """The retry decisions of one call, shared by the sync and async clients.

    ``max_retries`` is the caller's, None when it set none. Unset, only the
    failures retried by count are bounded, by DEFAULT_MAX_RETRIES; set, it bounds
    every retry. No attempt starts after ``budget`` seconds from the first one, so
    a Retry-After longer than the budget left ends the call at once.
    """

    def __init__(self, budget: float, max_retries: int | None) -> None:
        self._started = time.monotonic()
        self._budget = budget
        self._max_retries = max_retries
        self._retries = 0
        self._counted = 0

    def wait(self, kind: RetryClass | None, response: httpx.Response | None) -> float | None:
        """Seconds to wait before the next attempt, or None to give up."""
        if kind is None:
            return None
        if self._max_retries is not None:
            if self._retries >= self._max_retries:
                return None
        elif kind == "count" and self._counted >= DEFAULT_MAX_RETRIES:
            return None
        delay = _retry_delay(response, self._retries)
        if time.monotonic() - self._started + delay > self._budget:
            return None
        self._retries += 1
        if kind == "count":
            self._counted += 1
        return delay


def _request_kwargs(base_url: str, api_key: str, auth: str, req: BuiltRequest) -> dict[str, Any]:
    auth_header = {"Authorization": f"Bearer {api_key}"} if auth == "bearer" else {"X-API-Key": api_key}
    headers = {**req.headers, **auth_header}
    kwargs: dict[str, Any] = {"method": req.method, "url": f"{base_url}{req.path}", "headers": headers}
    if req.query:
        kwargs["params"] = req.query
    if req.accept:
        headers["Accept"] = req.accept
    if req.json_body is not None:
        kwargs["json"] = req.json_body
    elif req.raw_body is not None:
        kwargs["content"] = req.raw_body
        if req.content_type:
            headers["Content-Type"] = req.content_type
    return kwargs


def _raw_params(document: DocumentInput, content_type: str | None) -> tuple[bytes, str]:
    raw = to_bytes(document)
    return raw, content_type or sniff_content_type(raw)


def _data_from_json(resp: httpx.Response) -> dict[str, Any]:
    body = resp.content
    if resp.status_code >= 400:
        raise error_from_response(resp.status_code, body)
    env = parse_envelope(body)
    if env is not None and env.get("success") is False:
        raise error_from_response(resp.status_code, body)
    if env is None or env.get("data") is None:
        raise BeliqApiError("beliq: response was not a JSON envelope", status=resp.status_code)
    data = env["data"]
    if not isinstance(data, dict):
        raise BeliqApiError("beliq: response data was not an object", status=resp.status_code)
    return data


def _livemode_header(headers: httpx.Headers) -> bool | None:
    """Read the authoritative per-response mode from x-beliq-livemode."""
    raw = headers.get("x-beliq-livemode")
    if raw == "true":
        return True
    if raw == "false":
        return False
    return None


def _ruleset_artifacts(headers: httpx.Headers) -> list[RulesetArtifact] | None:
    """The x-ruleset-artifacts header is a JSON array of {key, version, fileSha256}."""
    raw = headers.get("x-ruleset-artifacts")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(parsed, list):
        return None
    return [RulesetArtifact.model_validate(item) for item in parsed]


def _lost_elements(headers: httpx.Headers) -> list[LostElement | LostElementsTruncated] | None:
    """The x-lost-elements header is a JSON array of LostElement, or of one truncation entry."""
    raw = headers.get("x-lost-elements")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(parsed, list):
        return None
    return [
        LostElementsTruncated.model_validate(item)
        if item.get("truncated") is True
        else LostElement.model_validate(item)
        for item in parsed
    ]


def _generate_meta(headers: httpx.Headers) -> GenerateMeta:
    return GenerateMeta(
        schematron_version=headers.get("x-schematron-version"),
        pdf_kind=headers.get("x-pdf-kind"),
        output_envelope=headers.get("x-output-envelope"),
        ruleset_sha256=headers.get("x-ruleset-sha256"),
        ruleset_artifacts=_ruleset_artifacts(headers),
        livemode=_livemode_header(headers),
    )


def _convert_meta(headers: httpx.Headers) -> ConvertMeta:
    count = headers.get("x-lost-elements-count")
    return ConvertMeta(
        source_format=headers.get("x-source-format"),
        target_format=headers.get("x-target-format"),
        profile_detected=headers.get("x-profile-detected"),
        lost_elements_count=int(count) if count is not None else None,
        lost_elements=_lost_elements(headers),
        conversion_tools=headers.get("x-conversion-tools"),
        livemode=_livemode_header(headers),
    )


def _generate_result(resp: httpx.Response, *, sealed: bool) -> GenerateResult:
    if resp.status_code >= 400:
        raise error_from_response(resp.status_code, resp.content)
    meta = _generate_meta(resp.headers)
    if sealed:
        env = parse_envelope(resp.content)
        if env is not None and env.get("success") is False:
            raise error_from_response(resp.status_code, resp.content)
        data = env.get("data") if env is not None else None
        if not isinstance(data, dict) or data.get("output") is None:
            raise BeliqApiError("beliq: seal response was not a JSON envelope", status=resp.status_code)
        content = base64.b64decode(data["output"])
        ctype = data.get("contentType") or "application/octet-stream"
        raw_validation = data.get("validationResult")
        return GenerateResult(
            content_type=ctype,
            content=content,
            xml=content.decode("utf-8") if "xml" in ctype else None,
            sha256=data.get("sha256"),
            validation_result=ValidationResult.model_validate(raw_validation) if raw_validation is not None else None,
            meta=meta,
        )
    ctype = resp.headers.get("content-type", "application/octet-stream")
    return GenerateResult(
        content_type=ctype,
        content=resp.content,
        xml=resp.content.decode("utf-8") if "xml" in ctype else None,
        meta=meta,
    )


def _convert_result(resp: httpx.Response) -> ConvertResult:
    if resp.status_code >= 400:
        raise error_from_response(resp.status_code, resp.content)
    return ConvertResult(
        content_type=resp.headers.get("content-type", "application/octet-stream"),
        content=resp.content,
        meta=_convert_meta(resp.headers),
    )


class Beliq:
    """Synchronous client for the beliq e-invoicing compliance API."""

    def __init__(  # noqa: PLR0913  # one keyword per client option, 2026-11-06
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        auth: str = "header",
        client: httpx.Client | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int | None = None,
        retry_budget: float = DEFAULT_RETRY_BUDGET_SECONDS,
    ) -> None:
        if not api_key:
            raise ValueError("beliq: api_key is required")
        self._api_key = api_key
        # True for a live key, False for a blq_test_ sandbox key, derived from the
        # prefix (the same rule the server applies). Available before any request;
        # the per-response x-beliq-livemode header is on generate/convert meta.
        self.livemode = not api_key.startswith(TEST_KEY_PREFIX)
        self._base_url = base_url.rstrip("/")
        self._auth = auth
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None
        self._max_retries = max_retries
        self._retry_budget = retry_budget

    def _send(self, req: BuiltRequest) -> httpx.Response:
        """Issue the request, retrying transient failures (see ``RetryClass``).

        Every wait follows the server's ``Retry-After`` in full. A retried answer
        that runs out of retries or budget is returned for the caller to raise; a
        connection that never opened raises httpx's ``ConnectError`` or
        ``ConnectTimeout`` once retrying ends, and a failed TLS handshake and any
        other transport error raise at once. A caller-supplied ``client`` keeps its own timeout, which
        this does not override.
        """
        kwargs = _request_kwargs(self._base_url, self._api_key, self._auth, req)
        retries = _Retries(self._retry_budget, self._max_retries)
        while True:
            try:
                response = self._client.request(**kwargs)
            except _BEFORE_SEND_ERRORS as exc:
                delay = None if _is_tls_failure(exc) else retries.wait("budget", None)
                if delay is None:
                    raise
            else:
                delay = retries.wait(_retry_class(response), response)
                if delay is None:
                    return response
            time.sleep(delay)

    def me(self) -> AccountInfo:
        return AccountInfo.model_validate(_data_from_json(self._send(build_me())))

    def generate(  # noqa: PLR0913  # size-cap baseline, 2026-10-13
        self,
        *,
        standard: str,
        invoice: Invoice,
        output: str = "xml",
        profile: str | None = None,
        facturx_profile: str | None = None,
        verify: bool | None = None,
        template: str | None = None,
        pdf_template_id: str | None = None,
        seal: bool = False,
        advanced: dict[str, Any] | None = None,
    ) -> GenerateResult:
        req = build_generate(
            standard=standard,
            invoice=invoice,
            output=output,
            profile=profile,
            facturx_profile=facturx_profile,
            verify=verify,
            template=template,
            pdf_template_id=pdf_template_id,
            sealed=seal,
            advanced=advanced,
        )
        return _generate_result(self._send(req), sealed=seal)

    def validate(
        self,
        document: DocumentInput,
        *,
        format: str | None = None,
        france_ctc: bool | None = None,
        content_type: str | None = None,
        advanced: dict[str, Any] | None = None,
        ruleset: str | None = None,
    ) -> ValidationResult:
        raw, ctype = _raw_params(document, content_type)
        req = build_validate(
            raw_body=raw,
            content_type=ctype,
            format=format,
            france_ctc=france_ctc,
            advanced=advanced,
            ruleset=ruleset,
        )
        return ValidationResult.model_validate(_data_from_json(self._send(req)))

    def parse(
        self,
        document: DocumentInput,
        *,
        format: str | None = None,
        content_type: str | None = None,
        advanced: dict[str, Any] | None = None,
    ) -> ParseResult:
        raw, ctype = _raw_params(document, content_type)
        req = build_parse(raw_body=raw, content_type=ctype, format=format, advanced=advanced)
        return ParseResult.model_validate(_data_from_json(self._send(req)))

    def convert(  # noqa: PLR0913  # size-cap baseline, 2026-10-13
        self,
        document: DocumentInput,
        *,
        target_format: str,
        source_format: str | None = None,
        target_profile: str | None = None,
        drop_france_ctc_overlay: bool | None = None,
        content_type: str | None = None,
        advanced: dict[str, Any] | None = None,
    ) -> ConvertResult:
        raw, ctype = _raw_params(document, content_type)
        req = build_convert(
            raw_body=raw,
            content_type=ctype,
            target_format=target_format,
            source_format=source_format,
            target_profile=target_profile,
            drop_france_ctc_overlay=drop_france_ctc_overlay,
            advanced=advanced,
        )
        return _convert_result(self._send(req))

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Beliq:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


class AsyncBeliq:
    """Asynchronous client for the beliq e-invoicing compliance API."""

    def __init__(  # noqa: PLR0913  # one keyword per client option, 2026-11-06
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        auth: str = "header",
        client: httpx.AsyncClient | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int | None = None,
        retry_budget: float = DEFAULT_RETRY_BUDGET_SECONDS,
    ) -> None:
        if not api_key:
            raise ValueError("beliq: api_key is required")
        self._api_key = api_key
        # True for a live key, False for a blq_test_ sandbox key, derived from the
        # prefix (the same rule the server applies). Available before any request;
        # the per-response x-beliq-livemode header is on generate/convert meta.
        self.livemode = not api_key.startswith(TEST_KEY_PREFIX)
        self._base_url = base_url.rstrip("/")
        self._auth = auth
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None
        self._max_retries = max_retries
        self._retry_budget = retry_budget

    async def _send(self, req: BuiltRequest) -> httpx.Response:
        """Issue the request, retrying transient failures. See ``Beliq._send``."""
        kwargs = _request_kwargs(self._base_url, self._api_key, self._auth, req)
        retries = _Retries(self._retry_budget, self._max_retries)
        while True:
            try:
                response = await self._client.request(**kwargs)
            except _BEFORE_SEND_ERRORS as exc:
                delay = None if _is_tls_failure(exc) else retries.wait("budget", None)
                if delay is None:
                    raise
            else:
                delay = retries.wait(_retry_class(response), response)
                if delay is None:
                    return response
            await asyncio.sleep(delay)

    async def me(self) -> AccountInfo:
        return AccountInfo.model_validate(_data_from_json(await self._send(build_me())))

    async def generate(  # noqa: PLR0913  # size-cap baseline, 2026-10-13
        self,
        *,
        standard: str,
        invoice: Invoice,
        output: str = "xml",
        profile: str | None = None,
        facturx_profile: str | None = None,
        verify: bool | None = None,
        template: str | None = None,
        pdf_template_id: str | None = None,
        seal: bool = False,
        advanced: dict[str, Any] | None = None,
    ) -> GenerateResult:
        req = build_generate(
            standard=standard,
            invoice=invoice,
            output=output,
            profile=profile,
            facturx_profile=facturx_profile,
            verify=verify,
            template=template,
            pdf_template_id=pdf_template_id,
            sealed=seal,
            advanced=advanced,
        )
        return _generate_result(await self._send(req), sealed=seal)

    async def validate(
        self,
        document: DocumentInput,
        *,
        format: str | None = None,
        france_ctc: bool | None = None,
        content_type: str | None = None,
        advanced: dict[str, Any] | None = None,
        ruleset: str | None = None,
    ) -> ValidationResult:
        raw, ctype = _raw_params(document, content_type)
        req = build_validate(
            raw_body=raw,
            content_type=ctype,
            format=format,
            france_ctc=france_ctc,
            advanced=advanced,
            ruleset=ruleset,
        )
        return ValidationResult.model_validate(_data_from_json(await self._send(req)))

    async def parse(
        self,
        document: DocumentInput,
        *,
        format: str | None = None,
        content_type: str | None = None,
        advanced: dict[str, Any] | None = None,
    ) -> ParseResult:
        raw, ctype = _raw_params(document, content_type)
        req = build_parse(raw_body=raw, content_type=ctype, format=format, advanced=advanced)
        return ParseResult.model_validate(_data_from_json(await self._send(req)))

    async def convert(  # noqa: PLR0913  # size-cap baseline, 2026-10-13
        self,
        document: DocumentInput,
        *,
        target_format: str,
        source_format: str | None = None,
        target_profile: str | None = None,
        drop_france_ctc_overlay: bool | None = None,
        content_type: str | None = None,
        advanced: dict[str, Any] | None = None,
    ) -> ConvertResult:
        raw, ctype = _raw_params(document, content_type)
        req = build_convert(
            raw_body=raw,
            content_type=ctype,
            target_format=target_format,
            source_format=source_format,
            target_profile=target_profile,
            drop_france_ctc_overlay=drop_france_ctc_overlay,
            advanced=advanced,
        )
        return _convert_result(await self._send(req))

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> AsyncBeliq:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
