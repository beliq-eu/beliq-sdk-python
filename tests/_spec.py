"""The vendored spec, read once for the tests that hold the SDK to it."""

import json
from pathlib import Path
from typing import Any

SPEC: dict[str, Any] = json.loads((Path(__file__).parent.parent / "openapi.json").read_text())


def validate_data_props() -> dict[str, Any]:
    """The properties of `data` in the 200 of `POST /v1/validate`."""
    return SPEC["paths"]["/v1/validate"]["post"]["responses"]["200"]["content"]["application/json"]["schema"][
        "properties"
    ]["data"]["properties"]
