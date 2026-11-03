"""AVEN AI account on the AVEN Cloud server: registration, subscriptions and entitlements.

The account token is a secret and is kept in the operating system's credential store.
The signed entitlement token is not a secret (it only proves what the server granted)
and is cached in the data folder so paid features keep working briefly while offline.
Stripe is never contacted from the app; checkout and subscription management open
Stripe's own pages in the browser, created by the server.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.account.entitlements import expiry, has_entitlement
from app.config.cloud import cloud_url, entitlement_public_key
from app.config.secrets import CredentialStore
from app.paths import user_data_dir

log = logging.getLogger(__name__)

ACCOUNT_ID_KEY = "aven_account_id"
ACCOUNT_TOKEN_KEY = "aven_account_token"  # noqa: S105 - name of the credential, not a secret
TIMEOUT = 20

# (method, url, bearer token, json body) -> (status code, json response)
Transport = Callable[[str, str, str, dict | None], tuple[int, dict]]


class AccountError(Exception):
    """User-facing account or subscription problem."""


@dataclass
class AccountStatus:
    account_id: str
    entitlements: list[str] = field(default_factory=list)
    subscriptions: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class Price:
    amount: int
    currency: str
    interval: str

    def __str__(self) -> str:
        value = f"{self.amount / 100:,.2f} {self.currency.upper()}"
        return f"{value} / {self.interval}" if self.interval else value


def urllib_transport(method: str, url: str, token: str, body: dict | None) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if not url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        raise AccountError("The AVEN AI server address must use https.")
    request = urllib.request.Request(url, data=data, method=method, headers=headers)  # noqa: S310 - checked above
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 - https AVEN Cloud URL
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except ValueError:
            return exc.code, {}
    except (urllib.error.URLError, OSError) as exc:
        raise AccountError("Could not reach the AVEN AI server. Check your internet connection.") from exc
    except ValueError as exc:
        raise AccountError("The AVEN AI server sent an invalid response.") from exc


class AccountService:
    def __init__(
        self,
        credentials: CredentialStore,
        base_url: str | None = None,
        public_key: str | None = None,
        transport: Transport | None = None,
        cache_path: Path | None = None,
    ) -> None:
        self.credentials = credentials
        self.base_url = cloud_url() if base_url is None else base_url.rstrip("/")
        self.public_key = entitlement_public_key() if public_key is None else public_key
        self.transport = transport or urllib_transport
        self.cache_path = cache_path or (user_data_dir() / "entitlement.json")

    # --- state ----------------------------------------------------------------------------
    @property
    def available(self) -> bool:
        """True when this build can verify paid features (server address and public key set)."""
        return bool(self.base_url and self.public_key)

    @property
    def account_id(self) -> str:
        return self.credentials.get_key(ACCOUNT_ID_KEY) or ""

    @property
    def token(self) -> str:
        return self.credentials.get_key(ACCOUNT_TOKEN_KEY) or ""

    def _cached_token(self) -> str:
        try:
            return str(json.loads(self.cache_path.read_text(encoding="utf-8")).get("token", ""))
        except (OSError, ValueError, AttributeError):
            return ""

    def _store_token(self, token: str | None) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps({"token": token or ""}), encoding="utf-8")
        except OSError as exc:
            log.warning("Could not cache the entitlement: %s", type(exc).__name__)

    def has(self, entitlement: str) -> bool:
        """True only with a valid, unexpired, server-signed entitlement for this account."""
        if not self.available or not self.account_id:
            return False
        return has_entitlement(entitlement, self._cached_token(), self.public_key, self.account_id)

    def entitlement_expiry(self):
        return expiry(self._cached_token(), self.public_key)

    # --- server calls -------------------------------------------------------------------------
    def _call(self, method: str, path: str, body: dict | None = None, auth: bool = True) -> dict:
        if not self.base_url:
            raise AccountError("This build of AVEN AI is not connected to the AVEN AI server.")
        status, data = self.transport(method, f"{self.base_url}{path}", self.token if auth else "", body)
        if status >= 400:
            message = (data.get("error") or {}).get("message") if isinstance(data, dict) else None
            raise AccountError(message or f"The AVEN AI server returned an error (HTTP {status}).")
        return data

    def ensure_account(self) -> str:
        if self.account_id and self.token:
            return self.account_id
        data = self._call("POST", "/accounts", {}, auth=False)
        account_id, token = str(data.get("account_id", "")), str(data.get("token", ""))
        if not account_id.startswith("acc_") or not token.startswith("avk_"):
            raise AccountError("The AVEN AI server sent an invalid account.")
        self.credentials.save_key(ACCOUNT_ID_KEY, account_id)
        self.credentials.save_key(ACCOUNT_TOKEN_KEY, token)
        return account_id

    def refresh(self) -> AccountStatus:
        """Ask the server what this account may use and cache the signed answer."""
        self.ensure_account()
        data = self._call("GET", "/account")
        self._store_token(data.get("entitlement_token"))
        return AccountStatus(
            account_id=self.account_id,
            entitlements=[e for e in data.get("entitlements", []) if self.has(e)],
            subscriptions=list(data.get("subscriptions", [])),
        )

    def checkout_url(self, product: str) -> str:
        self.ensure_account()
        url = str(self._call("POST", "/billing/checkout", {"product": product}).get("url", ""))
        if not url.startswith("https://"):
            raise AccountError("The AVEN AI server did not return a secure checkout page.")
        return url

    def portal_url(self) -> str:
        self.ensure_account()
        url = str(self._call("POST", "/billing/portal", {}).get("url", ""))
        if not url.startswith("https://"):
            raise AccountError("The AVEN AI server did not return a secure page.")
        return url

    def price(self, product: str) -> Price | None:
        """The price as configured in Stripe (None when billing is off or unknown); never made up."""
        data = self._call("GET", "/billing/config", auth=False)
        info = (data.get("products") or {}).get(product) if data.get("enabled") else None
        if not info or info.get("amount") is None or not info.get("currency"):
            return None
        return Price(int(info["amount"]), str(info["currency"]), str(info.get("interval") or ""))

    def billing_mode(self) -> str:
        """'test', 'live' or 'disabled' as reported by the server."""
        return str(self._call("GET", "/billing/config", auth=False).get("mode", "disabled"))
