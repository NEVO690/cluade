from __future__ import annotations

import base64
import datetime as dt
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.account.entitlements import has_entitlement, verify
from app.account.service import AccountError, AccountService
from app.config.secrets import CredentialStore


def keypair() -> tuple[Ed25519PrivateKey, str]:
    key = Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return key, base64.b64encode(raw).decode()


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def token(key: Ed25519PrivateKey, account="acc_1", entitlements=("aven_code",), hours=24) -> str:
    now = dt.datetime.now(dt.UTC)
    payload = json.dumps(
        {"v": 1, "account": account, "entitlements": list(entitlements),
         "issued": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
         "expires": (now + dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    ).encode()  # fmt: skip
    return f"{b64(payload)}.{b64(key.sign(payload))}"


def test_valid_entitlement_is_accepted() -> None:
    key, public = keypair()
    claims = verify(token(key), public)
    assert claims is not None and claims.entitlements == ("aven_code",)
    assert has_entitlement("aven_code", token(key), public, "acc_1")


def test_wrong_account_expired_forged_or_other_key_is_rejected() -> None:
    key, public = keypair()
    other, _other_public = keypair()
    assert not has_entitlement("aven_code", token(key), public, "acc_2")  # someone else's token
    assert not has_entitlement("aven_code", token(key, hours=-1), public, "acc_1")  # expired
    assert not has_entitlement("aven_code", token(other), public, "acc_1")  # signed by another key
    assert not has_entitlement("aven_code", token(key, entitlements=()), public, "acc_1")
    good = token(key)
    payload, signature = good.split(".")
    tampered = b64(base64.urlsafe_b64decode(payload + "==").replace(b"acc_1", b"acc_9"))
    assert verify(f"{tampered}.{signature}", public) is None
    for junk in ("", "abc", "a.b.c", "!!!.???"):
        assert verify(junk, public) is None
    assert verify(good, "") is None  # no public key in this build: nothing is unlocked


def test_account_service_without_server_unlocks_nothing(tmp_path) -> None:
    service = AccountService(CredentialStore(use_keyring=False), base_url="", public_key="", cache_path=tmp_path / "e")
    assert not service.available
    assert not service.has("aven_code")
    try:
        service.refresh()
    except AccountError as exc:
        assert "not connected" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected AccountError")


def test_account_service_reports_server_errors_and_rejects_insecure_urls(tmp_path) -> None:
    calls = []

    def transport(method, url, token_, body):
        calls.append((method, url, token_))
        if url.endswith("/accounts"):
            return 200, {"account_id": "acc_1", "token": "avk_secret"}
        if url.endswith("/billing/checkout"):
            return 200, {"url": "http://not-https.example"}
        return 402, {"error": {"message": "AVEN CODE needs an active subscription."}}

    _key, public = keypair()
    service = AccountService(
        CredentialStore(use_keyring=False), "https://cloud.example/v1", public, transport, tmp_path / "e"
    )
    for action in (service.refresh, lambda: service.checkout_url("aven_code")):
        try:
            action()
        except AccountError as exc:
            assert "subscription" in str(exc) or "secure" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("expected AccountError")
    assert calls[0] == ("POST", "https://cloud.example/v1/accounts", "")  # no token before signup
    assert calls[1][2] == "avk_secret"  # the account token is sent, never stored in plain settings
