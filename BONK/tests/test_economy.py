import os
import unittest
from unittest import mock

from helpers import temp_profile, win_report

from bonk.economy.currency_manager import InsufficientFunds


class EconomyTests(unittest.TestCase):
    def setUp(self):
        self.p, self.dir = temp_profile()

    def test_starts_with_classic_skin_and_zero_coins(self):
        self.assertEqual(self.p.currency.balance, 0)
        self.assertEqual(self.p.skins.equipped, "classic")
        self.assertTrue(self.p.skins.is_owned("classic"))

    def test_cannot_buy_without_enough_coins(self):
        res = self.p.shop.purchase("minty")
        self.assertFalse(res.ok)
        self.assertEqual(res.code, "insufficient_funds")
        self.assertFalse(self.p.skins.is_owned("minty"))
        self.assertEqual(self.p.currency.balance, 0)

    def test_purchase_charges_once_even_on_double_click(self):
        self.p.currency.earn(1000, "test")
        first = self.p.shop.purchase("minty")
        second = self.p.shop.purchase("minty")
        self.assertTrue(first.ok)
        self.assertEqual(second.code, "already_owned")
        self.assertEqual(self.p.currency.balance, 1000 - 150)

    def test_purchase_is_persisted(self):
        self.p.currency.earn(1000, "test")
        self.assertTrue(self.p.shop.purchase("bubblegum").ok)
        from bonk.save.save_manager import SaveManager
        sm = SaveManager(self.dir)
        data = sm.load()
        self.assertIn("bubblegum", data["cosmetics"]["owned_skins"])
        self.assertEqual(data["wallet"]["coins"], 600)

    def test_failed_save_rolls_back_purchase(self):
        self.p.currency.earn(1000, "test")
        with mock.patch.object(self.p.store, "save", return_value=False):
            res = self.p.shop.purchase("minty")
        self.assertFalse(res.ok)
        self.assertEqual(res.code, "save_failed")
        self.assertEqual(self.p.currency.balance, 1000)
        self.assertFalse(self.p.skins.is_owned("minty"))
        # and it can be bought later without being treated as a duplicate transaction
        self.assertTrue(self.p.shop.purchase("minty").ok)
        self.assertEqual(self.p.currency.balance, 850)

    def test_locked_skin_requires_level(self):
        self.p.currency.earn(10000, "test")
        res = self.p.shop.purchase("royal")  # needs level 10
        self.assertEqual(res.code, "locked")
        self.assertEqual(self.p.currency.balance, 10000)

    def test_rank_locked_skin(self):
        self.p.currency.earn(10000, "test")
        self.assertEqual(self.p.shop.purchase("viking").code, "locked")
        self.p.ranks.apply(260)  # SILVER
        self.assertTrue(self.p.shop.purchase("viking").ok)

    def test_equip_requires_ownership(self):
        with self.assertRaises(PermissionError):
            self.p.skins.equip("cosmic")
        self.p.currency.earn(500, "test")
        self.p.shop.purchase("minty")
        self.p.skins.equip("minty")
        self.assertEqual(self.p.skins.equipped, "minty")

    def test_unknown_item(self):
        self.assertEqual(self.p.shop.purchase("does_not_exist").code, "unknown_item")

    def test_spend_more_than_balance_raises(self):
        with self.assertRaises(InsufficientFunds):
            self.p.currency.spend(5, "x")

    def test_transaction_ids_are_not_applied_twice(self):
        self.assertTrue(self.p.currency.earn(50, "x", "tx1"))
        self.assertFalse(self.p.currency.earn(50, "x", "tx1"))
        self.assertEqual(self.p.currency.balance, 50)

    def test_match_rewards_pay_coins_and_are_not_applied_twice(self):
        s1 = self.p.apply_match_report(win_report(), 3, match_id="m1")
        bal = self.p.currency.balance
        self.assertGreater(s1.total_coins, 100)
        self.assertGreaterEqual(bal, s1.total_coins)
        s2 = self.p.apply_match_report(win_report(), 3, match_id="m1")
        self.assertTrue(s2.duplicate)
        self.assertEqual(self.p.currency.balance, bal)

    def test_rarity_is_data_and_prices_fit_rarity_bands(self):
        cat = self.p.catalog
        for skin in cat.ordered():
            r = cat.rarity_of(skin)
            self.assertLessEqual(r.min_price, skin.price)
            self.assertLessEqual(skin.price, r.max_price)
        self.assertEqual({s.rarity for s in cat.ordered()},
                         {"COMMON", "RARE", "EPIC", "LEGENDARY", "MYTHIC"})

    def test_every_skin_has_its_assets(self):
        for skin in self.p.catalog.ordered():
            for path in skin.asset_paths():
                self.assertTrue(os.path.exists(path), path)


if __name__ == "__main__":
    unittest.main()
