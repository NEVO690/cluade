"""Accounts, Stripe subscriptions (test mode) and signed entitlements.

Stripe's network API is replaced by a fake gateway; webhook signatures are produced and
verified exactly like Stripe's (HMAC-SHA256 over "timestamp.payload").
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from billing import Billing, BillingConfig  # noqa: E402
from server import Config, create_app  # noqa: E402
from tests.test_server import Upstream  # noqa: E402

WEBHOOK_SECRET = "whsec_test_secret"
PRICE = "price_aven_code_test"


def new_key() -> str:
    raw = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    return base64.b64encode(raw).decode()


class FakeGateway:
    def __init__(self) -> None:
        self.checkouts: list[dict] = []
        self.subscriptions: dict[str, dict] = {}

    def create_checkout(self, **params) -> str:
        self.checkouts.append(params)
        return "https://checkout.stripe.com/c/pay/cs_test_123"

    def create_portal(self, customer: str, return_url: str) -> str:
        return f"https://billing.stripe.com/p/session/test_{customer}"

    def retrieve_subscription(self, sub_id: str) -> dict:
        return self.subscriptions[sub_id]

    def retrieve_price(self, price_id: str) -> dict:
        return {"id": price_id, "unit_amount": 1500, "currency": "usd", "recurring": {"interval": "month"}}


def subscription(sub_id="sub_1", status="active", account="", days=30, cancel=False, price=PRICE) -> dict:
    end = int(time.time()) + days * 86_400
    return {
        "id": sub_id,
        "object": "subscription",
        "customer": "cus_1",
        "status": status,
        "cancel_at_period_end": cancel,
        "metadata": {"account_id": account} if account else {},
        "items": {"data": [{"price": {"id": price}, "current_period_end": end}]},
    }


@pytest.fixture
def env():
    key = new_key()
    config = BillingConfig(
        stripe_secret_key="sk_test_123", webhook_secret=WEBHOOK_SECRET, prices={"aven_code": PRICE},
        signing_key=key, db_path=":memory:", public_url="https://cloud.aven.example",
    )  # fmt: skip
    gateway = FakeGateway()
    billing = Billing.create(config, gateway)
    upstream = Upstream()
    client = TestClient(create_app(Config(service="anthropic", api_key="k"), upstream.client(), billing))
    return client, gateway, billing, key


def signed(payload: dict, secret: str = WEBHOOK_SECRET) -> tuple[bytes, dict]:
    body = json.dumps(payload).encode()
    stamp = int(time.time())
    signature = hmac.new(secret.encode(), f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
    return body, {"Stripe-Signature": f"t={stamp},v1={signature}", "Content-Type": "application/json"}


def event(kind: str, obj: dict, event_id: str = "evt_1") -> dict:
    return {"id": event_id, "object": "event", "type": kind, "data": {"object": obj}}


def new_account(client: TestClient) -> tuple[str, str]:
    data = client.post("/v1/accounts").json()
    return data["account_id"], data["token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def chat(client: TestClient, token: str, category: str):
    return client.post(
        "/v1/chat/completions",
        json={"model": "aven-2", "stream": False, "messages": [{"role": "user", "content": "Hi"}]},
        headers={**auth(token), "X-AVEN-Category": category},
    )


def verify_token(token: str, private_key_b64: str) -> dict:
    payload_b64, signature_b64 = token.split(".")
    pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
    payload = base64.urlsafe_b64decode(pad(payload_b64))
    public = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key_b64)).public_key()
    raw = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    Ed25519PublicKey.from_public_bytes(raw).verify(base64.urlsafe_b64decode(pad(signature_b64)), payload)
    return json.loads(payload)


def activate(client: TestClient, gateway: FakeGateway, account_id: str, **sub) -> None:
    gateway.subscriptions["sub_1"] = subscription(account=account_id, **sub)
    session = {"object": "checkout.session", "mode": "subscription", "client_reference_id": account_id,
               "subscription": "sub_1", "customer": "cus_1"}  # fmt: skip
    body, headers = signed(event("checkout.session.completed", session, "evt_checkout"))
    assert client.post("/v1/billing/webhook", content=body, headers=headers).status_code == 200


def test_new_account_has_no_paid_access(env) -> None:
    client, _gateway, _billing, key = env
    account_id, token = new_account(client)
    status = client.get("/v1/account", headers=auth(token)).json()
    assert status["entitlements"] == []
    claims = verify_token(status["entitlement_token"], key)
    assert claims["account"] == account_id and claims["entitlements"] == []
    assert chat(client, token, "code").status_code == 402  # AVEN CODE is paid
    assert chat(client, token, "aven").status_code == 200  # AVEN AI is free
    assert chat(client, "", "python").status_code == 200  # free categories need no account


def test_account_endpoints_require_a_valid_token(env) -> None:
    client, *_ = env
    assert client.get("/v1/account").status_code == 401
    assert client.get("/v1/account", headers=auth("avk_made_up")).status_code == 401
    assert client.post("/v1/billing/checkout", json={"product": "aven_code"}).status_code == 401


def test_checkout_is_created_server_side_with_the_configured_price(env) -> None:
    client, gateway, _billing, _key = env
    account_id, token = new_account(client)
    response = client.post("/v1/billing/checkout", json={"product": "aven_code"}, headers=auth(token))
    assert response.json() == {"url": "https://checkout.stripe.com/c/pay/cs_test_123"}
    params = gateway.checkouts[0]
    assert params["mode"] == "subscription"
    assert params["line_items"] == [{"price": PRICE, "quantity": 1}]
    assert params["client_reference_id"] == account_id
    assert params["success_url"].startswith("https://cloud.aven.example/billing/done")
    assert client.post("/v1/billing/checkout", json={"product": "other"}, headers=auth(token)).status_code == 400


def test_payment_activates_aven_code_only_after_a_verified_webhook(env) -> None:
    client, gateway, _billing, key = env
    account_id, token = new_account(client)
    activate(client, gateway, account_id)
    status = client.get("/v1/account", headers=auth(token)).json()
    assert status["entitlements"] == ["aven_code"]
    claims = verify_token(status["entitlement_token"], key)
    assert claims["entitlements"] == ["aven_code"]
    assert chat(client, token, "code").status_code == 200
    # A second checkout for an active subscription is refused.
    assert client.post("/v1/billing/checkout", json={"product": "aven_code"}, headers=auth(token)).status_code == 409


def test_forged_webhooks_are_rejected(env) -> None:
    client, gateway, _billing, _key = env
    account_id, token = new_account(client)
    gateway.subscriptions["sub_1"] = subscription(account=account_id)
    payload = event("customer.subscription.created", subscription(account=account_id), "evt_forged")
    body, headers = signed(payload, secret="whsec_wrong")
    assert client.post("/v1/billing/webhook", content=body, headers=headers).status_code == 400
    plain = json.dumps(payload).encode()
    assert (
        client.post("/v1/billing/webhook", content=plain, headers={"Content-Type": "application/json"}).status_code
        == 400
    )
    assert client.get("/v1/account", headers=auth(token)).json()["entitlements"] == []
    assert chat(client, token, "code").status_code == 402


@pytest.mark.parametrize("status", ["past_due", "unpaid", "canceled", "incomplete_expired"])
def test_failed_payment_or_cancellation_removes_access(env, status) -> None:
    client, gateway, _billing, _key = env
    account_id, token = new_account(client)
    activate(client, gateway, account_id)
    kind = "customer.subscription.deleted" if status == "canceled" else "customer.subscription.updated"
    body, headers = signed(event(kind, subscription(account=account_id, status=status), "evt_change"))
    assert client.post("/v1/billing/webhook", content=body, headers=headers).status_code == 200
    assert client.get("/v1/account", headers=auth(token)).json()["entitlements"] == []
    assert chat(client, token, "code").status_code == 402


def test_invoice_payment_failed_rereads_the_subscription(env) -> None:
    client, gateway, _billing, _key = env
    account_id, token = new_account(client)
    activate(client, gateway, account_id)
    gateway.subscriptions["sub_1"] = subscription(account=account_id, status="past_due")
    body, headers = signed(event("invoice.payment_failed", {"object": "invoice", "subscription": "sub_1"}, "evt_inv"))
    client.post("/v1/billing/webhook", content=body, headers=headers)
    assert chat(client, token, "code").status_code == 402


def test_cancel_at_period_end_keeps_access_until_the_period_ends(env) -> None:
    client, gateway, _billing, key = env
    account_id, token = new_account(client)
    activate(client, gateway, account_id, cancel=True, days=2)
    status = client.get("/v1/account", headers=auth(token)).json()
    assert status["entitlements"] == ["aven_code"]
    assert status["subscriptions"][0]["cancel_at_period_end"] is True
    claims = verify_token(status["entitlement_token"], key)
    # The signed entitlement never outlives the paid period (ISO-8601 UTC strings compare in time order).
    assert claims["expires"] <= status["subscriptions"][0]["current_period_end"]
    # Period over without a renewal reported: no access.
    body, headers = signed(event("customer.subscription.updated", subscription(account=account_id, days=-1), "evt_end"))
    client.post("/v1/billing/webhook", content=body, headers=headers)
    assert client.get("/v1/account", headers=auth(token)).json()["entitlements"] == []


def test_duplicate_webhooks_are_processed_once(env) -> None:
    client, gateway, billing, _key = env
    account_id, _token = new_account(client)
    activate(client, gateway, account_id)
    body, headers = signed(
        event("customer.subscription.updated", subscription(account=account_id, status="canceled"), "evt_dup")
    )
    client.post("/v1/billing/webhook", content=body, headers=headers)
    # Stripe retries the same event; an older "active" replay with the same id must not undo it.
    body2, headers2 = signed(event("customer.subscription.updated", subscription(account=account_id), "evt_dup"))
    client.post("/v1/billing/webhook", content=body2, headers=headers2)
    assert billing.entitlements_for(_token) == []


def test_billing_config_reports_test_mode_and_the_stripe_price(env) -> None:
    client, *_ = env
    data = client.get("/v1/billing/config").json()
    assert data["enabled"] is True and data["mode"] == "test"
    assert data["products"]["aven_code"] == {"amount": 1500, "currency": "usd", "interval": "month"}
    assert data["public_key"]


def test_without_stripe_configuration_paid_categories_stay_locked() -> None:
    billing = Billing.create(BillingConfig(db_path=":memory:"))
    client = TestClient(create_app(Config(service="anthropic", api_key="k"), Upstream().client(), billing))
    _account, token = new_account(client)
    assert client.get("/v1/billing/config").json()["enabled"] is False
    response = chat(client, token, "code")
    assert response.status_code == 402
    assert "not available" in response.json()["error"]["message"]
    assert client.post("/v1/billing/checkout", json={"product": "aven_code"}, headers=auth(token)).status_code == 503


def test_portal_needs_a_stripe_customer(env) -> None:
    client, gateway, _billing, _key = env
    account_id, token = new_account(client)
    assert client.post("/v1/billing/portal", headers=auth(token)).status_code == 404
    activate(client, gateway, account_id)
    assert client.post("/v1/billing/portal", headers=auth(token)).json()["url"].endswith("cus_1")


def test_desktop_app_unlocks_aven_code_only_with_a_server_signed_entitlement(env, tmp_path) -> None:
    """The real desktop AccountService against this server, in-process."""
    desktop = ROOT.parent / "aven_ai_desktop"
    sys.path.insert(0, str(desktop))
    from app.account.service import AccountService
    from app.config.secrets import CredentialStore

    client, gateway, billing, _key = env

    def transport(method, url, token, body):
        path = url.removeprefix("https://cloud.aven.example/v1")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        response = client.request(method, "/v1" + path, json=body, headers=headers)
        return response.status_code, response.json()

    account = AccountService(
        CredentialStore(use_keyring=False), base_url="https://cloud.aven.example/v1",
        public_key=billing.signer.public_key_b64(), transport=transport, cache_path=tmp_path / "e.json",
    )  # fmt: skip
    assert account.available
    status = account.refresh()
    assert status.entitlements == [] and not account.has("aven_code")
    assert account.checkout_url("aven_code").startswith("https://checkout.stripe.com/")
    assert str(account.price("aven_code")) == "15.00 USD / month"

    activate(client, gateway, account.account_id)
    assert account.refresh().entitlements == ["aven_code"]
    assert account.has("aven_code")

    # Editing the cached entitlement (for example adding a product) breaks the signature.
    cached = json.loads((tmp_path / "e.json").read_text())
    payload, signature = cached["token"].split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["entitlements"].append("made_with_aven")
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    (tmp_path / "e.json").write_text(json.dumps({"token": f"{forged}.{signature}"}))
    assert not account.has("aven_code")
