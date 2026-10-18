"""AVEN Cloud: the AVEN AI server that lets people chat without an API key.

The desktop app never contains an API key. Instead it talks to the AVEN Cloud
server (see ``aven_cloud/`` in the repository), which keeps the provider key
on the server side. The server address is not a secret; it comes from:

1. the ``AVEN_CLOUD_URL`` environment variable (development / testing), or
2. ``assets/cloud.json`` written into the build by ``scripts/build_windows.ps1``.
"""

from __future__ import annotations

import json
import os

from app.paths import resource_path


def cloud_url() -> str:
    """Base URL of the AVEN Cloud API (ending in ``/v1``), or "" when not configured."""
    url = os.environ.get("AVEN_CLOUD_URL", "").strip()
    if not url:
        try:
            # utf-8-sig tolerates the byte-order mark Windows PowerShell 5.1 writes.
            data = json.loads(resource_path("cloud.json").read_text(encoding="utf-8-sig"))
            url = str(data.get("url", "")).strip() if isinstance(data, dict) else ""
        except (OSError, ValueError):
            url = ""
    if not url:
        return ""
    from app.config.settings import validate_base_url

    if validate_base_url(url) is not None:
        return ""
    url = url.rstrip("/")
    return url if url.endswith("/v1") else url + "/v1"
