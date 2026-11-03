"""Which paid features this computer may use: verified entitlements from the AVEN Cloud server.

The app never decides on its own that something is paid for. The server signs the
account's entitlements (Ed25519) and the app checks that signature with the server's
public key, the account id and the expiry before unlocking a paid category. A missing,
expired, forged or tampered token means no access.

Limitation (documented in the README): requests that go through AVEN Cloud are checked
by the server on every message. When a paid category runs on this computer (AVEN Local)
or with a personal API key, the check happens here; that blocks casual unlocking, but a
user who modifies the application itself could bypass a check that runs on their own
computer.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Claims:
    account: str
    entitlements: tuple[str, ...]
    issued: dt.datetime
    expires: dt.datetime

    def valid_at(self, moment: dt.datetime) -> bool:
        return self.issued - dt.timedelta(minutes=10) <= moment < self.expires


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _parse_time(value: object) -> dt.datetime:
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def verify(token: str, public_key_b64: str) -> Claims | None:
    """The token's claims if its signature is valid for ``public_key_b64``, else None."""
    if not token or not public_key_b64 or token.count(".") != 1:
        return None
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        payload_b64, signature_b64 = token.split(".")
        payload = _unb64(payload_b64)
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
        try:
            key.verify(_unb64(signature_b64), payload)
        except InvalidSignature:
            log.warning("Rejected an entitlement token with an invalid signature")
            return None
        data = json.loads(payload)
        if data.get("v") != 1:
            return None
        return Claims(
            account=str(data["account"]),
            entitlements=tuple(str(e) for e in data.get("entitlements", [])),
            issued=_parse_time(data["issued"]),
            expires=_parse_time(data["expires"]),
        )
    except (ValueError, KeyError, TypeError) as exc:
        log.warning("Rejected a malformed entitlement token (%s)", type(exc).__name__)
        return None


def has_entitlement(
    name: str, token: str, public_key_b64: str, account_id: str, now: dt.datetime | None = None
) -> bool:
    claims = verify(token, public_key_b64)
    if claims is None or claims.account != account_id:
        return False
    return name in claims.entitlements and claims.valid_at(now or dt.datetime.now(dt.UTC))


def expiry(token: str, public_key_b64: str) -> dt.datetime | None:
    claims = verify(token, public_key_b64)
    return claims.expires if claims else None
