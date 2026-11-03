import json
import os
import tempfile
import textwrap
import unittest

from seeder import config
from seeder.client import ApiError
from seeder.registry import PROFILES, load_plugins
from seeder.runner import Seeder
from seeder.verifiers import VerifyError
from tests.fake_api import FakeApi

TOML = """
[api]
base_url = "{url}"

[run]
interval_seconds = 30
sample_period_seconds = 10
state_file = "{state}"
seed = 1
plugins_dir = "{plugins}"

[[accounts]]
name = "demo"
email = "demo@example.com"
password = "demo-password-1"
business_name = "Demo"
verifier = "none"

  [[accounts.gateways]]
  name = "Hub"
  hardware_id = "DEMO-HUB-0001"

    [[accounts.gateways.devices]]
    node_id = "PLUG-DEMO-0001"
    kind = "plug"
    name = "Mesin jahit"
    room = "Produksi"
    profile = "scheduled"
    params = {{ on_watts = 250, days = "daily", start = "00:00", end = "23:59" }}

    [[accounts.gateways.devices]]
    node_id = "CLAMP-DEMO-001"
    kind = "clamp"
    name = "Kompresor"
    room = "Produksi"
    profile = "cycling"
"""


class ApiCase(unittest.TestCase):
    def setUp(self):
        self.api = FakeApi()
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.addCleanup(self.api.close)
        self.path = os.path.join(self.dir.name, "demo.toml")
        self.state = os.path.join(self.dir.name, "state.json")
        self.plugins = os.path.join(self.dir.name, "plugins")
        os.makedirs(self.plugins)
        self.write(TOML)

    def write(self, text):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(text.format(url=self.api.url, state=self.state, plugins=self.plugins))

    def seeder(self):
        cfg = config.load(self.path)
        seeder = Seeder(cfg)
        seeder.client.pause = 0
        return seeder



class SeederTest(ApiCase):
    def test_a_new_account_that_needs_a_verifier_stops_with_a_clear_error(self):
        self.api.users.clear()
        seeder = self.seeder()
        seeder.cfg.accounts[0].verifier = "none"
        with self.assertRaises(VerifyError):
            seeder.provision()

    def test_provision_claims_the_gateway_and_pairs_every_device_once(self):
        self.api.users["demo@example.com"] = {"password": "demo-password-1", "verified": True}
        seeder = self.seeder()
        seeder.provision()
        self.assertEqual(sorted(d["name"] for d in self.api.devices.values()), ["Kompresor", "Mesin jahit"])
        self.assertEqual(list(self.api.rooms), ["Produksi"])
        seeder.provision()
        self.assertEqual(len(self.api.devices), 2)
        self.assertEqual(len(self.api.gateways), 1)

    def test_a_cycle_sends_samples_for_every_device_with_a_growing_sequence(self):
        self.api.users["demo@example.com"] = {"password": "demo-password-1", "verified": True}
        seeder = self.seeder()
        seeder.provision()
        runner = seeder.runners[0]
        runner.st["last_t"] = 1_800_000_000
        sent = runner.cycle(now=1_800_000_030)
        self.assertEqual(sent, 6)
        batch = self.api.batches[-1]
        self.assertEqual([n["nodeId"] for n in batch["nodes"]], ["PLUG-DEMO-0001", "CLAMP-DEMO-001"])
        self.assertEqual([s["t"] for s in batch["nodes"][0]["samples"]], [1_800_000_010, 1_800_000_020, 1_800_000_030])
        self.assertIn("r", batch["nodes"][0]["samples"][0])
        self.assertNotIn("r", batch["nodes"][1]["samples"][0])
        before = batch["seq"]
        runner.cycle(now=1_800_000_060)
        self.assertEqual(self.api.batches[-1]["seq"], before + 1)

    def test_the_state_survives_a_restart(self):
        self.api.users["demo@example.com"] = {"password": "demo-password-1", "verified": True}
        first = self.seeder()
        first.provision()
        first.runners[0].cycle(now=1_800_000_030)
        first.state.save()
        second = self.seeder()
        second.provision()
        self.assertEqual(len(self.api.gateways), 1)
        runner = second.runners[0]
        runner.cycle(now=1_800_000_060)
        self.assertEqual(self.api.batches[-1]["seq"], runner.st["seq"])
        with open(self.state, encoding="utf-8") as handle:
            self.assertIn("key", json.load(handle)["accounts"]["demo"]["DEMO-HUB-0001"])

    def test_a_lost_sequence_counter_is_found_again_from_expected_seq(self):
        self.api.users["demo@example.com"] = {"password": "demo-password-1", "verified": True}
        seeder = self.seeder()
        seeder.provision()
        runner = seeder.runners[0]
        runner.cycle(now=1_800_000_030)
        runner.st["seq"] = 0
        runner.cycle(now=1_800_000_060)
        seqs = [b["seq"] for b in self.api.batches]
        self.assertEqual(seqs, sorted(set(seqs)))

    def test_a_relay_command_switches_the_plug_and_is_reported(self):
        self.api.users["demo@example.com"] = {"password": "demo-password-1", "verified": True}
        seeder = self.seeder()
        seeder.provision()
        runner = seeder.runners[0]
        self.api.commands = [{"id": "cmd-1", "nodeId": "PLUG-DEMO-0001", "action": "off", "expiresAt": "2030-01-01T00:00:00Z"}]
        runner.cycle(now=1_800_000_030)
        runner.cycle(now=1_800_000_060)
        self.assertEqual(self.api.batches[-1]["results"], [{"id": "cmd-1", "ok": True}])
        self.assertEqual(self.api.batches[-1]["nodes"][0]["samples"][0]["p"], 0.0)

    def test_a_plugin_adds_a_profile(self):
        with open(os.path.join(self.plugins, "mine.py"), "w", encoding="utf-8") as handle:
            handle.write(textwrap.dedent("""
                from seeder.profiles import Profile, Reading
                from seeder.registry import profile

                @profile("flat-one-hundred")
                class Flat(Profile):
                    def sample(self, ctx):
                        return Reading(100.0)
            """))
        self.assertEqual(load_plugins(self.plugins), ["mine.py"])
        self.assertIn("flat-one-hundred", PROFILES)

    def test_a_wrong_file_is_named_in_the_error(self):
        self.write(TOML.replace('kind = "clamp"', 'kind = "meter"'))
        with self.assertRaises(config.ConfigError) as caught:
            config.load(self.path)
        self.assertIn("kind must be plug or clamp", str(caught.exception))

    def test_the_built_in_profiles_have_the_right_shape(self):
        import datetime
        import random

        from seeder.profiles import Context

        rng = random.Random(1)
        monday_noon = datetime.datetime(2026, 11, 2, 12, 0)
        monday_night = datetime.datetime(2026, 11, 2, 23, 0)
        scheduled = PROFILES["scheduled"]({"on_watts": 300, "standby_watts": 5}, rng)
        self.assertGreater(scheduled.sample(Context(0, monday_noon, 10, rng)).power, 150)
        self.assertLess(scheduled.sample(Context(0, monday_night, 10, rng)).power, 20)
        motor = PROFILES["motor"]({"degrade_after": "2026-11-01", "pf_degraded": 0.5}, rng)
        self.assertLess(motor.sample(Context(0, monday_noon, 10, rng)).pf, 0.7)


class RobustnessTest(ApiCase):
    """Tests of what happens when the API or the files misbehave"""

    def provisioned(self, toml=None):
        if toml:
            self.write(toml)
        self.api.users["demo@example.com"] = {"password": "demo-password-1", "verified": True}
        seeder = self.seeder()
        seeder.client.tries = 2
        seeder.provision()
        return seeder, seeder.runners[0]

    def test_a_long_outage_is_sent_in_a_batch_under_the_limit_of_5000_samples(self):
        devices = "".join(f"""
    [[accounts.gateways.devices]]
    node_id = "PLUG-DEMO-00{n}"
    kind = "plug"
    name = "Mesin {n}"
    room = "Produksi"
    profile = "constant"
""" for n in range(1, 7))
        head = TOML.split("    [[accounts.gateways.devices]]")[0]
        seeder, runner = self.provisioned(head + devices)
        runner.st["last_t"] = 1_800_000_000 - 3 * 3600
        sent = runner.cycle(now=1_800_000_000)
        self.assertGreater(sent, 0)
        self.assertLessEqual(sum(len(n["samples"]) for n in self.api.batches[-1]["nodes"]), 5000)

    def test_a_lost_answer_sends_the_same_batch_again_and_counts_the_energy_once(self):
        seeder, runner = self.provisioned()
        seeder.client.tries = 1
        runner.st["last_t"] = 1_800_000_000
        self.api.lose_answer = True
        with self.assertRaises(ApiError):
            runner.cycle(now=1_800_000_030)
        stored = self.api.batches[-1]
        self.assertIn("pending", runner.st)
        runner.cycle(now=1_800_000_040)
        self.assertNotIn("pending", runner.st)
        self.assertEqual(len([b for b in self.api.batches if b["seq"] == stored["seq"]]), 1)
        last = stored["nodes"][0]["samples"][-1]["e"]
        self.assertAlmostEqual(runner.devices[0].st["energy"], last + 0.0, delta=0.01)

    def test_a_batch_that_the_api_refuses_for_good_is_dropped(self):
        seeder, runner = self.provisioned()
        runner.st["last_t"] = 1_800_000_000
        self.api.fail_next = [422]
        runner.cycle(now=1_800_000_030)
        self.assertNotIn("pending", runner.st)
        self.assertEqual(runner.st["last_t"], 1_800_000_030)

    def test_a_rate_limit_keeps_the_batch_for_the_next_cycle(self):
        from seeder.client import RateLimitedError

        seeder, runner = self.provisioned()
        runner.st["last_t"] = 1_800_000_000
        self.api.fail_next = [429]
        with self.assertRaises(RateLimitedError):
            runner.cycle(now=1_800_000_030)
        self.assertIn("pending", runner.st)

    def test_a_key_that_the_api_forgot_is_replaced_by_enrolling_again(self):
        seeder, runner = self.provisioned()
        old = runner.st["key"]
        self.api.gateways.clear()
        seeder.once()
        self.assertNotEqual(runner.st.get("key", old), old)
        self.assertEqual(len(self.api.gateways), 1)

    def test_a_clock_that_went_back_does_not_stop_the_batches(self):
        seeder, runner = self.provisioned()
        runner.st["last_t"] = 1_800_000_500
        self.assertGreater(runner.cycle(now=1_800_000_030), 0)

    def test_an_unreadable_state_file_is_moved_aside(self):
        with open(self.state, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        self.api.users["demo@example.com"] = {"password": "demo-password-1", "verified": True}
        seeder = self.seeder()
        self.assertTrue(os.path.exists(self.state + ".corrupt"))
        seeder.provision()
        self.assertEqual(len(self.api.gateways), 1)

    def test_a_second_seeder_cannot_use_the_same_state(self):
        from seeder.state import State, StateLockedError

        first, second = State(self.state), State(self.state)
        first.lock()
        with self.assertRaises(StateLockedError):
            second.lock()

    def test_a_wrong_param_is_found_by_the_check(self):
        from seeder.runner import validate

        self.write(TOML.replace('days = "daily"', 'days = "mon-fr"'))
        with self.assertRaises(ValueError) as caught:
            validate(config.load(self.path))
        self.assertIn("PLUG-DEMO-0001", str(caught.exception))

    def test_a_wrong_password_stops_with_a_clear_error(self):
        from seeder.provision import AccountError

        self.api.users["demo@example.com"] = {"password": "another-password", "verified": True}
        seeder = self.seeder()
        with self.assertRaises(AccountError) as caught:
            seeder.provision()
        self.assertIn("not its password", str(caught.exception))

    def test_a_gateway_with_the_same_name_is_not_taken_over_without_adopt(self):
        from seeder.provision import AccountError

        self.api.users["demo@example.com"] = {"password": "demo-password-1", "verified": True}
        self.api.gateways["x"] = {"seq": 0, "name": "Hub"}
        with self.assertRaises(AccountError):
            self.seeder().provision()
        self.write(TOML.replace('hardware_id = "DEMO-HUB-0001"', 'hardware_id = "DEMO-HUB-0001"\n  adopt = true'))
        self.seeder().provision()

    def test_a_scenario_cuts_the_power_of_a_device(self):
        text = TOML + """
[[scenarios]]
name = "power cut"
mode = "off"
devices = ["PLUG-DEMO-0001"]
"""
        seeder, runner = self.provisioned(text)
        runner.st["last_t"] = 1_800_000_000
        runner.cycle(now=1_800_000_030)
        node = self.api.batches[-1]["nodes"][0]
        self.assertTrue(all(s["p"] == 0 for s in node["samples"]))
        self.assertGreater(self.api.batches[-1]["nodes"][1]["samples"][0]["p"], 0)

    def test_the_environment_and_set_override_the_file(self):
        cfg = config.load(self.path, env={"SEEDER_RUN_INTERVAL_SECONDS": "60", "SEEDER_API_USER_AGENT": "from-env"},
                          sets=["run.interval_seconds=45"])
        self.assertEqual(cfg.interval, 45)
        self.assertEqual(cfg.user_agent, "from-env")

    def test_http_to_a_remote_host_is_refused(self):
        self.write(TOML.replace("{url}", "http://api.example.com"))
        with self.assertRaises(config.ConfigError) as caught:
            config.load(self.path)
        self.assertIn("clear text", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
