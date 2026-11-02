"""Regression tests: one Telegram admin alert per app order.

Only the immediate authorized /notify-order webhook sends that alert.
Supabase reconciliation must still merge app orders into bot state but may
not send Telegram messages, even on the 5-minute free-plan polling cycle.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


class AppOrderTelegramNoDuplicates(unittest.TestCase):
    def test_syntax_all_runtime_files(self):
        for name in ("bot.py", "sync_wrapper.py", "bot_runtime_launcher.py",
                     "bot_runtime_free_guard.py"):
            with self.subTest(name=name):
                ast.parse((ROOT / name).read_text(encoding="utf-8"),
                          filename=name)

    def test_both_cloud_sync_paths_are_silent(self):
        for name in ("sync_wrapper.py", "bot_runtime_launcher.py"):
            source = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                # The compatibility helper may remain defined, but neither
                # sync implementation is permitted to invoke it.
                self.assertNotIn("for order in new_app_orders:", source)
                self.assertNotIn("new_app_orders.append(", source)
                self.assertIn("merged_orders[key] = merged_order", source)
                self.assertIn("_write_json(ORDERS_FILE, merged_orders)", source)
                self.assertIn("_pull_orders", source)

    def test_initial_immediate_telegram_alert_still_exists(self):
        source = (ROOT / "bot.py").read_text(encoding="utf-8")
        self.assertIn('if self.path != "/notify-order":', source)
        self.assertIn('supplied != ORDER_NOTIFY_SECRET', source)
        self.assertIn('f"🚨 YANGI ILOVA BUYURTMASI {label}', source)
        self.assertIn("send(int(ADMIN_ID), text)", source)

    def test_five_minute_sync_preserved_without_telegram_alert(self):
        guard = (ROOT / "bot_runtime_free_guard.py").read_text(encoding="utf-8")
        self.assertIn('new_delta = "time.sleep(5 * 60)"', guard)
        self.assertIn('threading.Thread(target=sync_loop', (
            ROOT / "sync_wrapper.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
