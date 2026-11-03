"""AVEN Cloud: the AVEN AI server that lets people chat without an API key.

The desktop app never contains an API key. Instead it talks to the AVEN Cloud
server (see ``aven_cloud/`` in the repository), which keeps the provider key
on the server side. The server address is not a secret; it comes from:

1. the ``AVEN_CLOUD_URL`` environment variable (development / testing), or
2. ``assets/cloud.json`` written into the build by ``scripts/build_windows.ps1``.

The same file can carry the server's public entitlement key, used to verify which paid
features (such as AVEN CODE) an account has.
"""

from __future__ import annotations

import json
import os

from app.paths import resource_path


def _cloud_file() -> dict:
    try:
        # utf-8-sig tolerates the byte-order mark Windows PowerShell 5.1 writes.
        data = json.loads(resource_path("cloud.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def entitlement_public_key() -> str:
    """Base64 Ed25519 public key that verifies entitlements signed by the AVEN Cloud server ("" if none).

    It is public (it can only verify, not sign); the matching private key stays on the server.
    """
    key = os.environ.get("AVEN_ENTITLEMENT_PUBLIC_KEY", "").strip()
    return key or str(_cloud_file().get("entitlement_public_key", "")).strip()


def cloud_url() -> str:
    """Base URL of the AVEN Cloud API (ending in ``/v1``), or "" when not configured."""
    url = os.environ.get("AVEN_CLOUD_URL", "").strip() or str(_cloud_file().get("url", "")).strip()
    if not url:
        return ""
    from app.config.settings import validate_base_url

    if validate_base_url(url) is not None:
        return ""
    url = url.rstrip("/")
    return url if url.endswith("/v1") else url + "/v1"
