import datetime as dt

import pytest

from economy.shop import PurchaseError
from economy.wallet import InsufficientFunds
from game.services import Services


def test_new_account_gets_gift_and_defaults(services):
    acc = services.ensure_player("Tester")
    assert services.wallet.balance(acc.id) == 1000
    loadout = services.locker.equipped(acc.id)
    assert loadout["outfit"] == "outfit_vex_runner"
    assert loadout["pickaxe"] == "pickaxe_iron_pick"
    assert services.locker.owns(acc.id, "glider_wing_sail")


def test_wallet_never_goes_negative(services):
    acc = services.ensure_player("Tester")
    with pytest.raises(InsufficientFunds):
        services.wallet.debit(acc.id, 5000, "too much")
    assert services.wallet.balance(acc.id) == 1000
    services.wallet.credit(acc.id, 250, "match")
    assert services.wallet.balance(acc.id) == 1250
    kinds = [t.kind for t in services.wallet.history(acc.id)]
    assert kinds == ["earn", "gift"]


def test_daily_rotation_is_deterministic(services):
    day = dt.date(2026, 10, 10)
    a = services.shop.storefront(day)
    b = services.shop.storefront(day)
    assert [i.id for i in a.all] == [i.id for i in b.all]
    assert len(a.featured) == 2 and len(a.daily) == 6
    assert all(i.purchasable for i in a.all)
    assert len({i.id for i in a.all}) == 8
    other = services.shop.storefront(day + dt.timedelta(days=1))
    assert [i.id for i in other.all] != [i.id for i in a.all]


def test_purchase_flow_and_persistence(tmp_path):
    db = tmp_path / "persist.db"
    svc = Services(db, seed_demo=False)
    acc = svc.ensure_player("Buyer")
    day = dt.date(2026, 10, 10)
    item = min(svc.shop.storefront(day).all, key=lambda i: i.price)
    balance = svc.shop.purchase(acc.id, item.id, date=day)
    assert balance == 1000 - item.price
    assert svc.locker.owns(acc.id, item.id)
    with pytest.raises(PurchaseError):
        svc.shop.purchase(acc.id, item.id, date=day)      # already owned
    svc.locker.equip(acc.id, item.id)
    svc.close()

    reopened = Services(db, seed_demo=False)                # simulate a restart
    acc2 = reopened.ensure_player()
    assert acc2.id == acc.id
    assert reopened.wallet.balance(acc.id) == 1000 - item.price
    assert reopened.locker.owns(acc.id, item.id)
    assert reopened.locker.equipped(acc.id)[item.type] == item.id
    reopened.close()


def test_cannot_buy_without_funds_or_outside_rotation(services):
    acc = services.ensure_player("Broke")
    day = dt.date(2026, 10, 10)
    front = services.shop.storefront(day)
    missing = next(i for i in services.catalog.shop_items() if i not in front.all)
    with pytest.raises(PurchaseError):
        services.shop.purchase(acc.id, missing.id, date=day)
    services.wallet.debit(acc.id, 1000, "spend all")
    with pytest.raises(PurchaseError):
        services.shop.purchase(acc.id, front.all[0].id, date=day)
    assert not services.locker.owns(acc.id, front.all[0].id)
    assert services.wallet.balance(acc.id) == 0


def test_equip_requires_ownership(services):
    from inventory.locker import LockerError
    acc = services.ensure_player("Tester")
    with pytest.raises(LockerError):
        services.locker.equip(acc.id, "outfit_ember_ronin")


def test_catalog_has_no_gameplay_stats(services):
    banned = {"damage", "health", "shield", "speed", "armor"}
    for item in services.catalog.items.values():
        assert not banned & set(item.extra), f"{item.id} must be purely cosmetic"
