"""Accounts, Stripe subscriptions and signed entitlements for AVEN Cloud.

Security model
- Stripe keys live only on this server (environment variables). The desktop app never
  sees them and never reports a payment itself.
- A subscription changes only through Stripe: verified webhooks (signature checked with
  the webhook secret) and direct reads from the Stripe API. Nothing the app sends can
  mark an account as paid.
- The server decides access: paid categories (AVEN CODE) are checked on every chat
  request, and ``/v1/account`` returns the account's entitlements signed with an
  Ed25519 key, which the app verifies with the matching public key before unlocking
  paid features that run on the user's computer.

Configuration (all optional; billing is off until the Stripe values are set)
- STRIPE_SECRET_KEY        sk_test_... (test mode) or sk_live_... (live mode)
- STRIPE_WEBHOOK_SECRET    whsec_... for the /v1/billing/webhook endpoint
- STRIPE_PRICE_AVEN_CODE   the Stripe Price id of the AVEN CODE subscription (the price
                           itself is set in Stripe, never in code)
- AVEN_ENTITLEMENT_SIGNING_KEY  base64 Ed25519 private key (see scripts/new_signing_key.py)
- AVEN_BILLING_DB          SQLite path for accounts and subscriptions (default ./billing.db;
                           use a persistent disk in production)
- AVEN_PUBLIC_URL          this server's public https URL (for Stripe's return pages)
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import logging
import os
import secrets
import sqlite3
import threading
from dataclasses import dataclass, field

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

log = logging.getLogger("aven_cloud.billing")

# product (= entitlement name) -> environment variable with its Stripe Price id
PRODUCTS = {"aven_code": "STRIPE_PRICE_AVEN_CODE"}
# Categories that need an entitlement (kept in sync with the app's categories.json)
PAID_CATEGORIES = {"code": "aven_code"}
ACTIVE_STATUSES = ("active", "trialing")  # past_due, unpaid, canceled, incomplete… are not paid
ENTITLEMENT_LIFETIME = dt.timedelta(hours=24)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass
class BillingConfig:
    stripe_secret_key: str = ""
    webhook_secret: str = ""
    prices: dict[str, str] = field(default_factory=dict)  # product -> Stripe price id
    signing_key: str = ""  # base64 raw Ed25519 private key
    db_path: str = "billing.db"
    public_url: str = ""

    @classmethod
    def from_env(cls) -> BillingConfig:
        return cls(
            stripe_secret_key=os.environ.get("STRIPE_SECRET_KEY", "").strip(),
            webhook_secret=os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip(),
            prices={p: os.environ.get(var, "").strip() for p, var in PRODUCTS.items() if os.environ.get(var)},
            signing_key=os.environ.get("AVEN_ENTITLEMENT_SIGNING_KEY", "").strip(),
            # Without Stripe there is nothing to keep, so nothing is written to disk.
            db_path=os.environ.get(
                "AVEN_BILLING_DB", "billing.db" if os.environ.get("STRIPE_SECRET_KEY") else ":memory:"
            ),
            public_url=os.environ.get("AVEN_PUBLIC_URL", "").strip().rstrip("/"),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.stripe_secret_key and self.webhook_secret and self.prices and self.signing_key)

    @property
    def mode(self) -> str:
        if self.stripe_secret_key.startswith(("sk_test_", "rk_test_")):
            return "test"
        if self.stripe_secret_key.startswith(("sk_live_", "rk_live_")):
            return "live"
        return "disabled"


# --- storage ------------------------------------------------------------------------------------


class Store:
    """Accounts and subscriptions in SQLite (thread-safe, one connection)."""

    def __init__(self, path: str) -> None:
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, created TEXT NOT NULL,
                    stripe_customer TEXT UNIQUE
                );
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id), product TEXT NOT NULL,
                    status TEXT NOT NULL, current_period_end TEXT, cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
                    updated TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS processed_events (id TEXT PRIMARY KEY, received TEXT NOT NULL);
                """
            )

    def create_account(self) -> tuple[str, str]:
        account_id = "acc_" + secrets.token_hex(12)
        token = "avk_" + secrets.token_urlsafe(32)
        with self._lock, self.conn:
            self.conn.execute(
                "INSERT INTO accounts (id, token_hash, created) VALUES (?, ?, ?)",
                (account_id, hash_token(token), _iso(_now())),
            )
        return account_id, token

    def account_for_token(self, token: str) -> sqlite3.Row | None:
        if not token.startswith("avk_"):
            return None
        with self._lock:
            return self.conn.execute("SELECT * FROM accounts WHERE token_hash = ?", (hash_token(token),)).fetchone()

    def account(self, account_id: str) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()

    def account_for_customer(self, customer: str) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute("SELECT * FROM accounts WHERE stripe_customer = ?", (customer,)).fetchone()

    def set_customer(self, account_id: str, customer: str) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                "UPDATE accounts SET stripe_customer = ? "
                "WHERE id = ? AND (stripe_customer IS NULL OR stripe_customer = ?)",
                (customer, account_id, customer),
            )

    def upsert_subscription(
        self, sub_id: str, account_id: str, product: str, status: str, period_end: str | None, cancel_at_end: bool
    ) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                """INSERT INTO subscriptions (id, account_id, product, status, current_period_end,
                       cancel_at_period_end, updated) VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET status = excluded.status,
                       current_period_end = excluded.current_period_end,
                       cancel_at_period_end = excluded.cancel_at_period_end, updated = excluded.updated""",
                (sub_id, account_id, product, status, period_end, int(cancel_at_end), _iso(_now())),
            )

    def subscriptions(self, account_id: str) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(
                "SELECT * FROM subscriptions WHERE account_id = ? ORDER BY updated DESC", (account_id,)
            ).fetchall()

    def first_time_event(self, event_id: str) -> bool:
        """Record a webhook event id; False if it was already processed (Stripe retries deliveries)."""
        with self._lock, self.conn:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO processed_events (id, received) VALUES (?, ?)", (event_id, _iso(_now()))
            )
            return cur.rowcount == 1


# --- entitlements -------------------------------------------------------------------------------


def active_entitlements(
    store: Store, account_id: str, now: dt.datetime | None = None
) -> tuple[list[str], dt.datetime | None]:
    """(entitlements, earliest period end) from the account's subscriptions as last reported by Stripe."""
    now = now or _now()
    names: set[str] = set()
    ends: list[dt.datetime] = []
    for sub in store.subscriptions(account_id):
        if sub["status"] not in ACTIVE_STATUSES:
            continue
        end = (
            dt.datetime.fromisoformat(sub["current_period_end"].replace("Z", "+00:00"))
            if sub["current_period_end"]
            else None
        )
        if end is not None and end < now:
            continue  # period over and no renewal reported
        names.add(sub["product"])
        if end is not None:
            ends.append(end)
    return sorted(names), (min(ends) if ends else None)


class Signer:
    def __init__(self, private_key_b64: str) -> None:
        raw = base64.b64decode(private_key_b64)
        self.key = Ed25519PrivateKey.from_private_bytes(raw)

    def public_key_b64(self) -> str:
        from cryptography.hazmat.primitives import serialization

        raw = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return base64.b64encode(raw).decode("ascii")

    def sign(self, account_id: str, entitlements: list[str], period_end: dt.datetime | None) -> str:
        now = _now()
        expires = now + ENTITLEMENT_LIFETIME
        if entitlements and period_end is not None:
            expires = min(expires, period_end)
        payload = json.dumps(
            {
                "v": 1,
                "account": account_id,
                "entitlements": entitlements,
                "issued": _iso(now),
                "expires": _iso(expires),
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return f"{_b64(payload)}.{_b64(self.key.sign(payload))}"


# --- Stripe ---------------------------------------------------------------------------------------


class StripeGateway:
    """The few Stripe calls the server makes (replaced by a fake in tests)."""

    def __init__(self, secret_key: str) -> None:
        import stripe

        self.client = stripe.StripeClient(secret_key, max_network_retries=2)

    def create_checkout(self, **params) -> str:
        return self.client.checkout.sessions.create(params=params).url

    def create_portal(self, customer: str, return_url: str) -> str:
        return self.client.billing_portal.sessions.create(params={"customer": customer, "return_url": return_url}).url

    def retrieve_subscription(self, sub_id: str) -> dict:
        return self.client.subscriptions.retrieve(sub_id).to_dict()

    def retrieve_price(self, price_id: str) -> dict:
        return self.client.prices.retrieve(price_id).to_dict()


def verify_webhook(payload: bytes, signature: str, secret: str) -> dict:
    """Parse a Stripe webhook after checking its signature (raises on a bad signature)."""
    import stripe

    return stripe.Webhook.construct_event(payload, signature, secret).to_dict()


def _period_end(subscription: dict) -> str | None:
    # Newer Stripe API versions report the period on each subscription item.
    end = subscription.get("current_period_end")
    if end is None:
        items = (subscription.get("items") or {}).get("data") or []
        ends = [i.get("current_period_end") for i in items if i.get("current_period_end")]
        end = min(ends) if ends else None
    return _iso(dt.datetime.fromtimestamp(end, dt.UTC)) if end else None


def _products(subscription: dict, prices: dict[str, str]) -> list[str]:
    by_price = {price: product for product, price in prices.items()}
    items = (subscription.get("items") or {}).get("data") or []
    return sorted({by_price[i["price"]["id"]] for i in items if i.get("price", {}).get("id") in by_price})


# --- routes ---------------------------------------------------------------------------------------


def bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    return auth[7:].strip() if auth.lower().startswith("bearer ") else ""


@dataclass
class Billing:
    config: BillingConfig
    store: Store
    signer: Signer | None
    gateway: StripeGateway | None
    _price_cache: dict = field(default_factory=dict)

    @classmethod
    def create(cls, config: BillingConfig, gateway: StripeGateway | None = None) -> Billing:
        signer = Signer(config.signing_key) if config.signing_key else None
        if gateway is None and config.stripe_secret_key:
            gateway = StripeGateway(config.stripe_secret_key)
        return cls(config, Store(config.db_path), signer, gateway)

    def entitlements_for(self, token: str) -> list[str]:
        account = self.store.account_for_token(token)
        return active_entitlements(self.store, account["id"])[0] if account else []

    def check_category(self, token: str, category: str) -> JSONResponse | None:
        """None if ``token`` may use ``category``, else the error response to send."""
        needed = PAID_CATEGORIES.get(category)
        if not needed:
            return None
        if not self.config.enabled:
            return _error(402, "AVEN CODE subscriptions are not available on this server yet.", "payment_required")
        if needed not in self.entitlements_for(token):
            return _error(402, "AVEN CODE needs an active subscription.", "payment_required")
        return None

    def sync_subscription(self, subscription: dict, account_id: str | None = None) -> None:
        customer = subscription.get("customer")
        if isinstance(customer, dict):
            customer = customer.get("id")
        account = self.store.account(account_id) if account_id else None
        if account is None:
            account_id = (subscription.get("metadata") or {}).get("account_id")
            account = self.store.account(account_id) if account_id else None
        if account is None and customer:
            account = self.store.account_for_customer(customer)
        if account is None:
            log.warning("Subscription %s has no matching account", subscription.get("id"))
            return
        if customer:
            self.store.set_customer(account["id"], customer)
        for product in _products(subscription, self.config.prices):
            self.store.upsert_subscription(
                subscription["id"],
                account["id"],
                product,
                subscription.get("status", "incomplete"),
                _period_end(subscription),
                bool(subscription.get("cancel_at_period_end")),
            )

    def handle_event(self, event: dict) -> None:
        kind = event.get("type", "")
        obj = (event.get("data") or {}).get("object") or {}
        if kind == "checkout.session.completed" and obj.get("mode") == "subscription":
            account_id = obj.get("client_reference_id")
            if obj.get("subscription") and self.gateway is not None:
                # Read the subscription from Stripe instead of trusting the event body alone.
                self.sync_subscription(self.gateway.retrieve_subscription(obj["subscription"]), account_id)
        elif kind in (
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        ):
            # Events can arrive out of order: always apply the subscription's current state from Stripe.
            current = obj
            if self.gateway is not None and obj.get("id"):
                try:
                    current = self.gateway.retrieve_subscription(obj["id"])
                except Exception as exc:
                    log.warning("Could not re-read subscription %s: %s", obj.get("id"), type(exc).__name__)
            self.sync_subscription(current)
        elif kind == "invoice.payment_failed":
            sub_id = obj.get("subscription") or ((obj.get("parent") or {}).get("subscription_details") or {}).get(
                "subscription"
            )
            if sub_id and self.gateway is not None:
                self.sync_subscription(self.gateway.retrieve_subscription(sub_id))
            log.info("Payment failed for subscription %s", sub_id)

    def price_info(self, product: str) -> dict | None:
        price_id = self.config.prices.get(product)
        if not price_id or self.gateway is None:
            return None
        if product not in self._price_cache:
            try:
                price = self.gateway.retrieve_price(price_id)
            except Exception as exc:  # Stripe unreachable: show no price rather than a wrong one
                log.warning("Could not read price %s: %s", price_id, type(exc).__name__)
                return None
            recurring = price.get("recurring") or {}
            self._price_cache[product] = {
                "amount": price.get("unit_amount"),
                "currency": price.get("currency"),
                "interval": recurring.get("interval"),
            }
        return self._price_cache[product]


def _error(status: int, message: str, kind: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"message": message, "type": kind}})


def router(billing: Billing, allow_signup) -> APIRouter:
    api = APIRouter()
    config = billing.config

    def account_or_error(request: Request):
        account = billing.store.account_for_token(bearer(request))
        if account is None:
            return None, _error(401, "Unknown or missing AVEN account.", "authentication_error")
        return account, None

    @api.post("/v1/accounts")
    async def create_account(request: Request):
        if not allow_signup(request):
            return _error(429, "Too many accounts created from this network. Try again later.", "rate_limit_error")
        account_id, token = billing.store.create_account()
        return {"account_id": account_id, "token": token}

    @api.get("/v1/account")
    async def account_status(request: Request):
        account, error = account_or_error(request)
        if error:
            return error
        names, period_end = active_entitlements(billing.store, account["id"])
        subs = [
            {
                "product": s["product"],
                "status": s["status"],
                "current_period_end": s["current_period_end"],
                "cancel_at_period_end": bool(s["cancel_at_period_end"]),
            }
            for s in billing.store.subscriptions(account["id"])
        ]
        token = billing.signer.sign(account["id"], names, period_end) if billing.signer else None
        return {"account_id": account["id"], "entitlements": names, "subscriptions": subs, "entitlement_token": token}

    @api.get("/v1/billing/config")
    async def billing_config():
        return {
            "enabled": config.enabled,
            "mode": config.mode if config.enabled else "disabled",
            "products": {p: billing.price_info(p) for p in config.prices} if config.enabled else {},
            "public_key": billing.signer.public_key_b64() if billing.signer else None,
        }

    @api.post("/v1/billing/checkout")
    async def checkout(request: Request):
        account, error = account_or_error(request)
        if error:
            return error
        if not config.enabled or billing.gateway is None:
            return _error(503, "Subscriptions are not available on this server yet.", "server_error")
        try:
            body = await request.json()
        except ValueError:
            body = {}
        product = body.get("product") if isinstance(body, dict) else None
        if product not in config.prices:
            return _error(400, "Unknown product.", "invalid_request_error")
        if product in active_entitlements(billing.store, account["id"])[0]:
            return _error(409, "This account already has an active subscription.", "invalid_request_error")
        base = config.public_url or str(request.base_url).rstrip("/")
        params = {
            "mode": "subscription",
            "line_items": [{"price": config.prices[product], "quantity": 1}],
            "client_reference_id": account["id"],
            "subscription_data": {"metadata": {"account_id": account["id"], "product": product}},
            "success_url": f"{base}/billing/done?result=success",
            "cancel_url": f"{base}/billing/done?result=cancelled",
        }
        if account["stripe_customer"]:
            params["customer"] = account["stripe_customer"]
        try:
            url = billing.gateway.create_checkout(**params)
        except Exception as exc:
            log.error("Checkout failed: %s", type(exc).__name__)
            return _error(502, "Could not start the checkout. Please try again.", "server_error")
        return {"url": url}

    @api.post("/v1/billing/portal")
    async def portal(request: Request):
        account, error = account_or_error(request)
        if error:
            return error
        if billing.gateway is None or not account["stripe_customer"]:
            return _error(404, "There is no subscription to manage for this account.", "invalid_request_error")
        base = config.public_url or str(request.base_url).rstrip("/")
        try:
            url = billing.gateway.create_portal(account["stripe_customer"], f"{base}/billing/done?result=portal")
        except Exception as exc:
            log.error("Portal failed: %s", type(exc).__name__)
            return _error(502, "Could not open subscription management. Please try again.", "server_error")
        return {"url": url}

    @api.post("/v1/billing/webhook")
    async def webhook(request: Request):
        if not config.webhook_secret:
            return _error(503, "Webhooks are not configured.", "server_error")
        payload = await request.body()
        try:
            event = verify_webhook(payload, request.headers.get("stripe-signature", ""), config.webhook_secret)
        except Exception:
            log.warning("Rejected a webhook with an invalid signature")
            return _error(400, "Invalid signature.", "invalid_request_error")
        if billing.store.first_time_event(event["id"]):
            billing.handle_event(event)
        return {"received": True}

    @api.get("/billing/done")
    async def done(result: str = "success"):
        messages = {
            "success": "Thanks! Your subscription is being activated. Return to AVEN AI and click Refresh.",
            "cancelled": "The checkout was cancelled. Nothing was charged.",
            "portal": "You can return to AVEN AI now.",
        }
        text = messages.get(result, messages["portal"])
        return HTMLResponse(
            f"<!doctype html><meta charset=utf-8><title>AVEN AI</title>"
            f"<body style='font-family:sans-serif;max-width:560px;margin:80px auto'><h1>AVEN AI</h1><p>{text}</p>"
        )

    return api
