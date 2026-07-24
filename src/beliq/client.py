"""Sync (Beliq) and async (AsyncBeliq) clients for the beliq API."""

from __future__ import annotations

import base64
import json
from types import TracebackType
from typing import Any

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
from .constants import DEFAULT_BASE_URL
from .errors import BeliqApiError, error_from_response, parse_envelope
from .types import (
    AccountInfo,
    ConvertMeta,
    ConvertResult,
    GenerateMeta,
    GenerateResult,
    Invoice,
    ParseResult,
    RulesetArtifact,
    ValidationResult,
)

# blq_test_ marks a sandbox key; the server derives livemode from this exact prefix.
TEST_KEY_PREFIX = "blq_test_"


def _request_kwargs(base_url: str, api_key: str, auth: str, req: BuiltRequest) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}"} if auth == "bearer" else {"X-API-Key": api_key}
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
    lost_elements: list[str] | None = None
    lost_raw = headers.get("x-lost-elements")
    if lost_raw:
        try:
            parsed = json.loads(lost_raw)
            if isinstance(parsed, list):
                lost_elements = [str(x) for x in parsed]
        except ValueError:
            pass
    count = headers.get("x-lost-elements-count")
    return ConvertMeta(
        source_format=headers.get("x-source-format"),
        target_format=headers.get("x-target-format"),
        profile_detected=headers.get("x-profile-detected"),
        lost_elements_count=int(count) if count is not None else None,
        lost_elements=lost_elements,
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

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        auth: str = "header",
        client: httpx.Client | None = None,
        timeout: float = 30.0,
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

    def _send(self, req: BuiltRequest) -> httpx.Response:
        return self._client.request(**_request_kwargs(self._base_url, self._api_key, self._auth, req))

    def me(self) -> AccountInfo:
        return AccountInfo.model_validate(_data_from_json(self._send(build_me())))

    def generate(
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
    ) -> ValidationResult:
        raw, ctype = _raw_params(document, content_type)
        req = build_validate(raw_body=raw, content_type=ctype, format=format, france_ctc=france_ctc, advanced=advanced)
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

    def convert(
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

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        auth: str = "header",
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
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

    async def _send(self, req: BuiltRequest) -> httpx.Response:
        return await self._client.request(
            **_request_kwargs(self._base_url, self._api_key, self._auth, req)
        )

    async def me(self) -> AccountInfo:
        return AccountInfo.model_validate(_data_from_json(await self._send(build_me())))

    async def generate(
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
    ) -> ValidationResult:
        raw, ctype = _raw_params(document, content_type)
        req = build_validate(raw_body=raw, content_type=ctype, format=format, france_ctc=france_ctc, advanced=advanced)
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

    async def convert(
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
