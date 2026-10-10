"""Composition root for all non-rendering game services.

The UI and match code only ever receive a ``Services`` object, which keeps
them decoupled from storage details (and lets tests build one on a temp DB).
"""
from __future__ import annotations

import logging
from pathlib import Path

from config import paths
from economy.shop import Shop
from economy.wallet import Wallet
from inventory.catalog import Catalog
from inventory.locker import Locker
from progression.rewards import Progression
from save_system.database import Database
from social.accounts import Account, AccountService
from social.backend import LocalSocialBackend
from social.friends import FriendService

log = logging.getLogger(__name__)


class Services:
    def __init__(self, db_path: Path | str | None = None, *, probe=None, seed_demo: bool = True):
        self.db = Database(db_path or paths.database_file())
        self.catalog = Catalog()
        self.wallet = Wallet(self.db)
        self.locker = Locker(self.db, self.catalog)
        self.shop = Shop(self.catalog, self.wallet, self.locker)
        self.progression = Progression(self.db, self.catalog, self.wallet, self.locker)
        self.accounts = AccountService(self.db)
        self.friends = FriendService(self.db)
        self.local_social = LocalSocialBackend(self.db, probe=probe)
        self.social = self.local_social          # swapped for RemoteSocialBackend while signed in online
        self.accounts.on_created(self._setup_new_account)
        if seed_demo:
            from social.demo_seed import seed_demo_content
            seed_demo_content(self)

    def _setup_new_account(self, account_id: int) -> None:
        is_demo = bool(self.db.scalar("SELECT is_demo FROM accounts WHERE id = ?", (account_id,), 0))
        self.wallet.open(account_id, starter_gift=0 if is_demo else 1000)
        self.locker.grant_defaults(account_id)

    def go_online(self, remote) -> None:
        self.social = remote

    def go_offline(self) -> None:
        self.social = self.local_social

    @property
    def online(self) -> bool:
        return self.social is not self.local_social

    # -- convenience ----------------------------------------------------
    def ensure_player(self, default_name: str = "Player") -> Account:
        """Return the active account, creating a first local profile if needed."""
        active = self.accounts.active_id
        if active is not None:
            try:
                return self.accounts.get(active)
            except ValueError:
                log.warning("Active account %s missing; picking another", active)
        humans = self.accounts.list(include_demo=False)
        account = humans[0] if humans else self.accounts.create(default_name, default_name)
        return self.accounts.set_active(account.id)

    @property
    def me(self) -> Account:
        return self.accounts.active()

    def close(self) -> None:
        self.db.close()
