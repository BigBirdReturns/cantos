"""Offline safety/interpretation tests. No account fields or provider logins."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import tui_watch as w


CONFIG = {"team_name": "Example Team", "team_handle": "example-team"}
# Structural text observed in the real loaded empty menu, with identity replaced.
DASHBOARD = """Hot Aisle
USER SETTINGS
TEAMS & COMPUTE
Team @example-team
n create new team
Hot Aisle › Example Team
Loading balance information...
Bare Metal Servers
No bare metal servers
Virtual Machines
No virtual machines
n provision new resources
Hot Aisle › Example Team
Account Balance
Available Balance: $100.00
Hourly Rate: $0.00/hour
Status: No active resources
"""
MENU = """Hot Aisle › Example Team › Provision Resources - Example Team
Provision resources
Select a resource type to provision for your team.
Capacity and Availability
Available Resources
{rows}
enter provision selected VM
"""


class ParserTests(unittest.TestCase):
    def test_loaded_no_items_only_inside_provision_page(self):
        self.assertEqual(w.classify_menu(DASHBOARD + MENU.format(rows="No items."), CONFIG)["classification"], "no_offer")
        self.assertEqual(w.classify_menu("Hot Aisle\nNo items.", CONFIG)["classification"], "unknown")

    def test_dashboard_identity_and_loaded_state(self):
        self.assertEqual(w.dashboard_state(DASHBOARD, CONFIG), "ready")
        self.assertEqual(w.dashboard_state(DASHBOARD.replace("@example-team", "@other"), CONFIG), "unknown")
        self.assertEqual(w.dashboard_state(DASHBOARD.replace("Example Team", "Another Team"), CONFIG), "unknown")
        self.assertEqual(w.dashboard_state(DASHBOARD.replace("Example Team", "Example Team Other"), CONFIG), "unknown")
        self.assertEqual(w.dashboard_state(DASHBOARD + "Hot Aisle\nUSER SETTINGS\nn create new team", CONFIG), "unknown")
        self.assertEqual(w.dashboard_state(DASHBOARD.split("Account Balance")[0], CONFIG), "unknown")

    def test_active_rate_prevents_menu_entry(self):
        self.assertEqual(w.dashboard_state(DASHBOARD.replace("$0.00/hour", "$2.99/hour"), CONFIG), "active_resources")

    def test_loaders_and_changed_page_are_unknown(self):
        for rows in ("Loading...", "Please wait", "Brand new UI", ""):
            self.assertEqual(w.classify_menu(MENU.format(rows=rows), CONFIG)["classification"], "unknown")
        self.assertEqual(w.classify_menu(MENU.format(rows="No items.").replace("Example Team", "Other"), CONFIG)["classification"], "unknown")
        self.assertEqual(w.classify_menu(MENU.format(rows="No items.").replace("Example Team", "Example Team Other"), CONFIG)["classification"], "unknown")
        self.assertEqual(w.classify_menu(MENU.format(rows="No items.\nNew unrecognized resource row"), CONFIG)["classification"], "unknown")

    def test_one_gpu_candidate_is_not_delivered(self):
        for row in ("1x MI300X VM $2.99/hour", "MI300X Virtual Machine 1 GPU $2.99/hour", "MI300X x1 VM"):
            result = w.classify_menu(MENU.format(rows=row), CONFIG)
            self.assertEqual(result["classification"], "candidate")
            self.assertIn(row, result["menu_text"])

    def test_other_counts_do_not_match_one(self):
        for row in ("2x MI300X VM", "8x MI300X Bare Metal", "MI300X VM 8 GPUs", "11x MI300X VM"):
            self.assertEqual(w.classify_menu(MENU.format(rows=row), CONFIG)["classification"], "no_offer")
        for row in ("MI300X VM $2.99/hour", "MI300X 1 GPU", "1x MI300X Bare Metal"):
            self.assertEqual(w.classify_menu(MENU.format(rows=row), CONFIG)["classification"], "candidate_review_required")
        self.assertEqual(w.classify_menu(MENU.format(rows="8x MI300X Bare Metal\nmore below"), CONFIG)["classification"], "unknown")

    def test_terminal_escape_stripping(self):
        raw = b"\x1b_Gbinary-secret\x1b\\\x1b]0;window\x07\x1b[2JNo items.\r\n"
        self.assertEqual(w.clean_terminal(raw), "No items.")

    def test_coloured_auto_entry_preserves_exact_team_and_key_hint(self):
        # Observed remote TUI: populated root was skipped, SGR split each label.
        auto = DASHBOARD[DASHBOARD.index('Hot Aisle \u203a'):]
        coloured = auto.replace(' ', '\x1b[0m \x1b[1;38;5;205m')
        text = w.clean_terminal(coloured)
        self.assertEqual(w.dashboard_state(text, CONFIG), 'ready')
        self.assertEqual(w.dashboard_state(text.replace('Example Team', 'Other Team'), CONFIG), 'unknown')
        self.assertEqual(w.dashboard_state(text.replace('$0.00/hour', '$2.99/hour'), CONFIG), 'active_resources')

    def test_proxy_environment_uses_estate_cleanup_without_mutating_parent(self):
        from unittest.mock import Mock
        estate = Mock()
        original = {'SHELL': 'cmd.exe', 'RETAIN': 'value'}
        estate._ssh_child_environment.return_value = original
        self.assertEqual(w.ssh_environment(estate), {'RETAIN': 'value'})
        self.assertEqual(original['SHELL'], 'cmd.exe')
        estate._ssh_child_environment.return_value = None
        self.assertIsNone(w.ssh_environment(estate))

    def test_scroll_only_expected_provision_page_with_hidden_resource_list(self):
        page = ('Hot Aisle \u203a Example Team \u203a Provision Resources - Example Team\n'
                'Capacity and Availability\nmore below - b/pgup page up / f/pgdn page down\n')
        self.assertTrue(w.needs_page_down(page, CONFIG))
        self.assertFalse(w.needs_page_down(page.replace('Example Team', 'Another Team'), CONFIG))
        self.assertFalse(w.needs_page_down(page + 'Hot Aisle \u203a Example Team\n', CONFIG))
        self.assertFalse(w.needs_page_down(page + 'Available Resources\nNo items.\n', CONFIG))


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.config = dict(CONFIG, state_dir=str(self.state), expires_utc="2099-01-01T00:00:00Z", interval_seconds=1800)

    def test_stop_and_expiry_never_load_transport(self):
        (self.state / "STOP").touch()
        with patch.object(w, "load_estate", side_effect=AssertionError("network reached")):
            self.assertEqual(w.run_once(self.config, force=True)["classification"], "stopped")
            (self.state / "STOP").unlink()
            self.config["expires_utc"] = "2000-01-01T00:00:00Z"
            self.assertEqual(w.run_once(self.config, force=True)["classification"], "expired")

    def test_lock_and_interval_prevent_runaway_logins(self):
        with w.sample_lock(self.state):
            self.assertEqual(w.run_once(self.config)["classification"], "locked")
        (self.state / "latest.json").write_text(json.dumps({"started_utc": w.utcnow().isoformat()}))
        with patch.object(w, "load_estate", side_effect=AssertionError("network reached")):
            self.assertEqual(w.run_once(self.config)["classification"], "interval_hold")

    def test_front_door_failure_never_contacts_provider_and_is_retained(self):
        from unittest.mock import Mock
        estate = Mock()
        estate.write_artifacts.return_value = (self.state / "ssh_config", self.state / "known_hosts")
        estate.run_peer_script.return_value = {"ok": False, "classification": "TIMEOUT", "peer": "OCTO-N01"}
        config = dict(self.config, estate_root=str(self.state))
        with patch.object(w, "load_estate", return_value=estate), patch.object(w, "capture", side_effect=AssertionError("provider reached")):
            result = w.run_once(config)
        self.assertEqual(result["classification"], "unknown")
        self.assertFalse(result["provisioned"])
        self.assertTrue((self.state / "observations.jsonl").is_file())
        self.assertEqual(json.loads((self.state / "latest.json").read_text())["classification"], "unknown")
        self.assertFalse((self.state / "sample.lock").exists())

    def test_transport_exception_is_retained_not_retried(self):
        with patch.object(w, "load_estate", side_effect=OSError("transport unavailable")) as load:
            result = w.run_once(self.config)
        self.assertEqual(result["classification"], "unknown")
        self.assertEqual(load.call_count, 1)
        self.assertIn("OSError", result["error"])
        self.assertEqual(w.run_once(self.config)["classification"], "interval_hold")


if __name__ == "__main__":
    unittest.main()
