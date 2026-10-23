import dataclasses
import json
import random
import stat
import unittest
from datetime import datetime, timedelta, timezone

from device import BACKFILL_STEP_MINUTES, BackfillError, Device, PairingError, pile_at
from tests.fake_cloud import FakeCloud
from tests.helpers import make_settings


class DeviceTest(unittest.TestCase):
    def setUp(self):
        self.cloud = FakeCloud().start()
        self.addCleanup(self.cloud.stop)
        # no history after pairing, so the uplink tests see plain readings;
        # the history has tests of its own at the bottom
        self.settings = make_settings(self.cloud.url, backfill_days=0)
        self.device = self.new_device()

    def new_device(self, **overrides):
        # threads are never started: tests drive readings and uploads by hand
        return Device(dataclasses.replace(self.settings, **overrides))

    def pair(self, device=None, set_up=True):
        # pairing, then "Confirm registration" in the dashboard
        (device or self.device).pair(self.cloud.issue_code())
        if set_up:
            self.cloud.set_up_all()

    def reading_and_upload(self, device=None):
        device = device or self.device
        with device.lock:
            device._take_reading()
        device._upload_once()

    # ------------------------------------------------------------ pairing ---

    def test_the_device_powers_on_and_off(self):
        self.device.start()
        self.device.stop()
        self.assertEqual(self.device.status()["events"][-1]["text"], "power on")

    def test_a_new_device_has_a_fake_mac_and_no_pairing(self):
        uid = self.device.store.device_uid
        self.assertRegex(uid, r"^02(:[0-9A-F]{2}){5}$")
        self.assertEqual(self.device.status()["pairing"]["state"], "unpaired")

    def test_pairing_stores_the_key_and_starts_uploads(self):
        self.pair()
        status = self.device.status()
        self.assertEqual(status["pairing"]["state"], "paired")
        self.assertTrue(status["pairing"]["api_key_hint"].startswith("••••"))
        self.assertNotIn(self.device.credentials.api_key, json.dumps(status))

        self.reading_and_upload()
        self.assertEqual(len(self.cloud.records), 1)
        record = self.cloud.records[0]
        self.assertEqual(set(record) - {"device_id"},
                         {"timestamp", "temperature", "moisture_percent", "o2_percent", "co2_percent", "nh3_ratio"})
        self.assertTrue(record["timestamp"].endswith("+00:00"))
        self.assertEqual(self.device.status()["cloud"]["state"], "ok")

    def test_the_pairing_survives_a_restart(self):
        self.pair()
        uid = self.device.store.device_uid
        restarted = self.new_device()
        self.assertEqual(restarted.store.device_uid, uid)
        self.assertEqual(restarted.status()["pairing"]["state"], "paired")
        self.reading_and_upload(restarted)
        self.assertEqual(len(self.cloud.records), 1)

    def test_the_state_file_is_private(self):
        self.pair()
        mode = stat.S_IMODE(self.settings.state_file.stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_bad_codes_are_refused_with_a_useful_message(self):
        with self.assertRaisesRegex(PairingError, "6 digits"):
            self.device.pair("12ab")
        with self.assertRaisesRegex(PairingError, "wasn't recognised"):
            self.device.pair("000000" if "000000" not in self.cloud.codes else "999999")

    def test_a_code_works_once(self):
        code = self.cloud.issue_code()
        self.device.pair(code)
        other = self.new_device(state_file=self.settings.state_file.with_name("other.json"))
        with self.assertRaisesRegex(PairingError, "already been used"):
            other.pair(code)

    def test_pairing_twice_needs_a_factory_reset(self):
        self.pair()
        with self.assertRaisesRegex(PairingError, "already paired"):
            self.pair()
        self.device.factory_reset()
        self.pair()
        self.assertEqual(self.device.status()["pairing"]["state"], "paired")

    def test_an_unreachable_cloud_is_reported(self):
        device = self.new_device(cloud_api_url="http://127.0.0.1:9",
                                 state_file=self.settings.state_file.with_name("x.json"))
        with self.assertRaisesRegex(PairingError, "Couldn't reach the cloud"):
            device.pair("123456")

    def test_factory_reset_keeps_the_hardware_id_and_the_pile(self):
        self.pair()
        uid = self.device.store.device_uid
        self.device.apply_action("turn")
        self.device.factory_reset()
        self.assertEqual(self.device.store.device_uid, uid)
        self.assertEqual(self.device.model.turns, 1)
        self.assertIsNone(self.device.credentials)

    # ------------------------------------------------------------- uplink ---

    def test_unpaired_readings_are_not_kept(self):
        self.reading_and_upload()
        self.assertEqual(self.device.status()["cloud"]["queued"], 0)
        self.assertEqual(self.cloud.records, [])

    def test_offline_readings_are_kept_and_sent_later(self):
        self.pair()
        self.cloud.fail_next = [503]
        self.reading_and_upload()
        status = self.device.status()["cloud"]
        self.assertEqual(status["state"], "error")
        self.assertEqual(status["queued"], 1)
        self.assertGreater(status["retry_in_seconds"], 0)

        with self.device.lock:
            self.device._take_reading()
        self.device.retry_now()
        self.device._upload_once()
        self.assertEqual(len(self.cloud.records), 2)
        self.assertEqual(self.device.status()["cloud"]["queued"], 0)

    def test_a_full_queue_drops_the_oldest(self):
        self.device = self.new_device(queue_max=3)
        self.pair()
        self.reading_and_upload()  # the first upload is what tells it setup is done
        self.device.uploads_paused = True
        for _ in range(5):
            self.reading_and_upload()
        status = self.device.status()["cloud"]
        self.assertEqual((status["queued"], status["dropped_total"]), (3, 2))

    def test_a_revoked_key_unpairs_the_device(self):
        self.pair()
        self.cloud.revoke_all()
        self.reading_and_upload()
        status = self.device.status()
        self.assertEqual(status["pairing"]["state"], "unpaired")
        self.assertEqual(status["cloud"]["state"], "revoked")
        self.assertIsNone(self.new_device().credentials)  # cleared on disk too

    # ------------------------------------------------ setup in the dashboard ---

    def test_a_freshly_paired_device_waits_for_setup(self):
        self.pair(set_up=False)
        self.assertEqual(self.device.status()["cloud"]["state"], "awaiting_setup")
        self.reading_and_upload()
        status = self.device.status()["cloud"]
        self.assertEqual((status["state"], status["sent_total"]), ("awaiting_setup", 0))
        self.assertEqual(self.cloud.records, [])

    def test_waiting_for_setup_keeps_only_the_newest_reading(self):
        self.pair(set_up=False)
        for _ in range(5):
            self.reading_and_upload()
        status = self.device.status()["cloud"]
        self.assertEqual((status["queued"], status["dropped_total"]), (1, 0))
        self.assertEqual(self.device.queue[-1][1]["timestamp"], self.device.latest["timestamp"])

    def test_waiting_for_setup_checks_back_at_a_steady_pace(self):
        self.pair(set_up=False)
        for _ in range(4):
            self.reading_and_upload()
            self.device.retry_at = 0  # let the next check through straight away
        self.reading_and_upload()
        self.assertLessEqual(self.device.status()["cloud"]["retry_in_seconds"],
                             self.settings.setup_check_seconds)

    def test_readings_start_once_the_dashboard_sets_the_device_up(self):
        self.pair(set_up=False)
        self.reading_and_upload()
        self.cloud.set_up_all()
        self.device.retry_now()
        self.reading_and_upload()
        status = self.device.status()
        self.assertEqual(status["cloud"]["state"], "ok")
        self.assertEqual(len(self.cloud.records), 1)  # only the newest, not the backlog
        self.assertIn("setup finished", status["events"][0]["text"])

    def test_a_device_taken_out_of_its_bin_waits_for_setup_again(self):
        self.pair()
        self.reading_and_upload()
        self.cloud.not_set_up.add(self.device.credentials.device_id)
        self.reading_and_upload()
        self.assertEqual(self.device.status()["cloud"]["state"], "awaiting_setup")

    def test_a_batch_the_cloud_can_never_accept_is_dropped(self):
        self.pair()
        self.cloud.fail_next = [422]
        self.reading_and_upload()
        status = self.device.status()["cloud"]
        self.assertEqual((status["state"], status["queued"], status["dropped_total"]), ("rejected", 0, 1))

    def test_paused_uploads_keep_readings(self):
        self.pair()
        self.device.set_uploads_paused(True)
        self.reading_and_upload()
        self.assertEqual((self.device.status()["cloud"]["queued"], len(self.cloud.records)), (1, 0))
        self.device.set_uploads_paused(False)
        self.device._upload_once()
        self.assertEqual(len(self.cloud.records), 1)

    def test_a_key_is_never_sent_to_a_different_cloud(self):
        self.pair()
        moved = self.new_device(cloud_api_url="http://127.0.0.1:9")
        self.assertEqual(moved.status()["pairing"]["state"], "other_cloud")
        self.reading_and_upload(moved)
        self.assertEqual(moved.status()["cloud"]["queued"], 0)
        self.assertIsNone(moved.status()["cloud"]["last_attempt_at"])

    # ------------------------------------------------- a batch in the past ---

    def set_up_and_sending(self):
        self.pair()
        self.reading_and_upload()  # the first upload shows the cloud takes readings

    def send_everything(self):
        while self.device.queue:
            self.device._upload_once()

    def test_a_batch_in_the_past_sends_its_history_up_to_now(self):
        self.set_up_and_sending()
        before = datetime.now(timezone.utc)
        self.device.start_batch_in_past(3)

        stamps = [datetime.fromisoformat(record["timestamp"]) for _, record in self.device.queue]
        self.assertEqual(len(stamps), 3 * 48 + 1)
        steps = {later - earlier for earlier, later in zip(stamps, stamps[1:])}
        self.assertEqual(steps, {timedelta(minutes=BACKFILL_STEP_MINUTES)})
        self.assertLess(abs(stamps[-1] - before), timedelta(seconds=5))
        self.assertEqual(stamps[-1] - stamps[0], timedelta(days=3))

        # the live pile carries on from the end of that history
        pile = self.device.status()["pile"]
        self.assertAlmostEqual(pile["batch_day"], 3.0, places=2)
        self.assertEqual(self.device.latest["timestamp"], self.device.queue[-1][1]["timestamp"])
        self.assertIn("started a batch 3 days ago: 145 readings", self.device.status()["events"][0]["text"])

        self.send_everything()
        self.assertEqual(len(self.cloud.records), 1 + 145)

    def test_a_batch_in_the_past_starts_at_the_starting_point_and_is_looked_after(self):
        self.device = self.new_device(state_file=self.settings.state_file.with_name("new.json"), start_stage=3)
        self.assertEqual(self.device.model.stage_id, 3)  # a cooling pile...
        self.device.set_start_point({"stage": 0, "progress": 0})
        self.set_up_and_sending()
        self.device.start_batch_in_past(12)
        first = self.device.queue[0][1]
        self.assertLess(first["temperature"], 40)  # ...replaced by fresh feedstock, the starting point
        self.assertGreater(self.device.model.waterings, 0)
        moisture = [record["moisture_percent"] for _, record in self.device.queue]
        self.assertGreater(min(moisture), 45)  # watered below 50 %, so it never stalls

    def test_a_batch_in_the_past_drops_the_old_piles_unsent_readings(self):
        self.set_up_and_sending()
        self.device.set_uploads_paused(True)
        for _ in range(3):
            self.reading_and_upload()
        self.device.start_batch_in_past(1)
        status = self.device.status()
        self.assertEqual((status["cloud"]["queued"], status["cloud"]["dropped_total"]), (49, 3))
        self.assertIn("3 unsent readings of the old pile dropped", status["events"][0]["text"])

    def test_a_batch_in_the_past_waits_until_the_cloud_takes_readings(self):
        self.pair(set_up=False)
        self.reading_and_upload()
        with self.assertRaises(BackfillError) as refused:
            self.device.start_batch_in_past(2)
        self.assertEqual(refused.exception.status, 409)
        self.assertIn("set it up in the dashboard", refused.exception.message)
        self.assertEqual(self.device.status()["backfill"]["blocked"], refused.exception.message)

        # set up, but nothing sent since this start: it might have been moved out of its bin
        self.cloud.set_up_all()
        restarted = self.new_device()
        with self.assertRaises(BackfillError):
            restarted.start_batch_in_past(2)
        self.reading_and_upload(restarted)
        restarted.start_batch_in_past(2)
        self.assertIsNone(restarted.status()["backfill"]["blocked"])

    def test_a_batch_in_the_past_has_to_fit_the_queue(self):
        self.device = self.new_device(queue_max=200)
        self.set_up_and_sending()
        self.assertEqual(self.device.status()["backfill"]["max_days"], 4)  # 200 readings x 30 min
        for days in (0, 5, -1):
            with self.assertRaisesRegex(BackfillError, "between 1 and 4 days"):
                self.device.start_batch_in_past(days)
        self.device.start_batch_in_past(4)
        self.assertEqual(self.device.status()["cloud"]["dropped_total"], 0)


    # --------------------------------------------------- the starting point ---

    def test_a_pile_can_start_part_way_through_any_stage(self):
        for stage, progress in ((0, 50), (2, 40), (3, 60), (4, 90)):
            model = pile_at(random.Random(3), 28.0, stage, progress)
            self.assertEqual(model.stage_id, stage)
            self.assertAlmostEqual(model.stage_progress, progress / 100, delta=0.05)
            self.assertGreater(model.moisture, 45)  # looked after on the way there

    def test_a_pile_that_leaves_a_stage_early_starts_the_next_one(self):
        # Active Thermophilic ends as soon as the core has held 55 C, so near its end
        # some piles are already in Peak Decomposition
        landed = {pile_at(random.Random(seed), 28.0, 1, 95).stage_id for seed in range(40)}
        self.assertEqual(landed, {1, 2})
        for seed in range(40):
            model = pile_at(random.Random(seed), 28.0, 1, 95)
            if model.stage_id == 2:
                self.assertLess(model.stage_progress, 0.05)

    def test_a_new_device_starts_its_pile_at_the_starting_point(self):
        device = self.new_device(state_file=self.settings.state_file.with_name("new.json"),
                                 start_stage=2, start_progress=50)
        self.assertEqual(device.model.stage_id, 2)
        self.assertEqual(device.status()["start"]["stage"], 2)

    def test_the_starting_point_is_checked_and_kept(self):
        for bad in ({"history_days": 21}, {"history_days": -1}, {"stage": 5}, {"progress": 96},
                    {"progress": True}, {"stage": "2"}, {"history_days": 2.5}):
            with self.assertRaises(BackfillError, msg=bad):
                self.device.set_start_point(bad)
        self.device.set_start_point({"history_days": 15, "stage": 2, "progress": 40})
        preview = self.device.status()["start"]["preview"]

        restarted = self.new_device(backfill_days=3, start_stage=0)  # the page's choice wins
        start = restarted.status()["start"]
        self.assertEqual((start["history_days"], start["stage"], start["progress"]), (15, 2, 40))
        self.assertEqual(start["preview"], preview)  # the same batch, not a new one

    def test_a_changed_setting_counts_unless_the_page_set_it(self):
        self.device.set_start_point({"stage": 2})
        restarted = self.new_device(backfill_days=7, start_progress=30)
        start = restarted.status()["start"]
        self.assertEqual((start["history_days"], start["stage"], start["progress"]), (7, 2, 30))

    def test_too_many_days_from_the_settings_are_cut_to_fit_the_queue(self):
        device = self.new_device(state_file=self.settings.state_file.with_name("new.json"),
                                 queue_max=200, backfill_days=10)
        self.assertEqual(device.status()["start"]["history_days"], 4)

    def test_the_preview_is_the_batch_that_gets_sent(self):
        self.device.set_start_point({"history_days": 3, "stage": 2, "progress": 40})
        preview = self.device.status()["start"]["preview"]
        self.assertEqual((preview["begins"]["stage_name"], preview["begins"]["progress"]), ("Peak Decomposition", 40))

        self.set_up_and_sending()
        self.device.start_batch_in_past()
        start = self.device.status()["start"]
        self.assertEqual(start["last_batch"]["begins"], preview["begins"])
        self.assertEqual(start["last_batch"]["readings"], 3 * 48 + 1)
        pile = self.device.status()["pile"]
        self.assertEqual((pile["stage_id"], round(self.device.model.stage_progress * 100)),
                         (preview["now"]["stage_id"], preview["now"]["progress"]))
        self.assertIn("started a batch 3 days ago at 40 % through Peak Decomposition",
                      self.device.status()["events"][0]["text"])

    def test_with_no_history_the_pile_just_moves_to_the_starting_point(self):
        self.device.set_start_point({"history_days": 0, "stage": 3, "progress": 50})
        self.device.start_batch_in_past()  # unpaired: no cloud needed
        self.assertEqual(self.device.model.stage_id, 3)
        self.assertIn("pile moved to 50 % through Cooling", self.device.status()["events"][0]["text"])

    # -------------------------------------- the history sent after pairing ---

    def test_the_history_goes_the_first_time_the_cloud_takes_readings(self):
        self.device = self.new_device(backfill_days=2)
        self.pair(set_up=False)
        self.reading_and_upload()
        status = self.device.status()
        self.assertEqual((status["cloud"]["state"], status["cloud"]["queued"]), ("awaiting_setup", 0))
        self.assertTrue(status["start"]["pending"])

        self.cloud.set_up_all()
        self.device.retry_now()
        self.reading_and_upload()  # an empty batch: stores nothing, but it's accepted
        status = self.device.status()
        self.assertEqual(status["cloud"]["queued"], 2 * 48 + 1)
        self.assertFalse(status["start"]["pending"])
        self.assertIn("sending the 97 held", status["events"][0]["text"])

        self.send_everything()
        stamps = [datetime.fromisoformat(record["timestamp"]) for record in self.cloud.records]
        # only the history, in order: no live reading from the old pile in front of it
        self.assertEqual(len(stamps), 2 * 48 + 1)
        self.assertEqual(stamps, sorted(stamps))
        self.assertEqual(stamps[-1] - stamps[0], timedelta(days=2))

    def test_the_history_goes_once_per_pairing(self):
        self.device = self.new_device(backfill_days=1)
        self.pair()
        self.reading_and_upload()
        self.send_everything()
        self.reading_and_upload()
        self.assertEqual(len(self.cloud.records), 49 + 1)  # the history, then one live reading

        restarted = self.new_device(backfill_days=1)
        self.reading_and_upload(restarted)
        self.assertEqual(len(self.cloud.records), 49 + 2)

        restarted.factory_reset()
        self.pair(restarted)
        self.assertTrue(restarted.status()["start"]["pending"])

    def test_a_restart_before_setup_still_sends_the_history(self):
        self.device = self.new_device(backfill_days=1)
        self.pair(set_up=False)
        self.reading_and_upload()
        restarted = self.new_device(backfill_days=1)
        self.cloud.set_up_all()
        self.reading_and_upload(restarted)
        self.assertEqual(restarted.status()["cloud"]["queued"], 49)

    def test_no_history_means_nothing_is_sent_later_either(self):
        self.pair()
        self.reading_and_upload()
        self.device.set_start_point({"history_days": 5})
        self.reading_and_upload()
        self.assertEqual(len(self.cloud.records), 2)  # plain readings; the moment has passed

    def test_a_device_paired_before_there_was_a_history_keeps_its_pile(self):
        self.pair()
        saved = json.loads(self.settings.state_file.read_text())
        del saved["history_pending"]
        self.settings.state_file.write_text(json.dumps(saved))
        upgraded = self.new_device(backfill_days=5)
        self.assertFalse(upgraded.status()["start"]["pending"])
        self.reading_and_upload(upgraded)
        self.assertEqual(len(self.cloud.records), 1)

    # ------------------------------------- the history held from power-on ---

    def fresh_device(self, **overrides):
        return self.new_device(state_file=self.settings.state_file.with_name("fresh.json"), **overrides)

    def test_a_new_device_holds_its_history_from_power_on(self):
        before = datetime.now(timezone.utc)
        device = self.fresh_device(backfill_days=2)
        status = device.status()
        self.assertTrue(status["start"]["pending"])
        self.assertEqual((status["start"]["held"], status["cloud"]["queued"]), (2 * 48 + 1, 0))
        self.assertAlmostEqual(status["pile"]["batch_day"], 2.0, places=2)
        stamps = [datetime.fromisoformat(record["timestamp"]) for record in device.held]
        self.assertEqual(stamps[-1] - stamps[0], timedelta(days=2))
        self.assertLess(abs(stamps[-1] - before), timedelta(seconds=5))
        self.assertIn("held until the cloud takes", status["events"][0]["text"])

    def test_readings_after_the_history_are_held_at_its_spacing(self):
        device = self.fresh_device(backfill_days=1)
        last = datetime.fromisoformat(device.held[-1]["timestamp"])
        with device.lock:
            for minutes in (10, 31, 45, 62):
                device._keep_reading({**device.latest, "timestamp": (last + timedelta(minutes=minutes)).isoformat()})
        self.assertEqual(len(device.held), 49 + 2)  # 31 and 62 minutes on
        self.assertEqual(device.status()["cloud"]["queued"], 0)

    def test_the_held_history_and_what_came_after_go_once_set_up(self):
        self.device = self.fresh_device(backfill_days=1)
        last = datetime.fromisoformat(self.device.held[-1]["timestamp"])
        with self.device.lock:
            self.device._keep_reading({**self.device.latest, "timestamp": (last + timedelta(hours=1)).isoformat()})
        self.pair()
        self.device._upload_once()
        self.assertEqual(self.device.status()["cloud"]["queued"], 50)
        self.send_everything()
        stamps = [datetime.fromisoformat(record["timestamp"]) for record in self.cloud.records]
        self.assertEqual((len(stamps), stamps[-1] - stamps[0]), (50, timedelta(days=1, hours=1)))
        self.assertEqual(self.device.status()["start"]["last_batch"]["readings"], 50)

    def test_the_held_history_survives_a_restart(self):
        device = self.fresh_device(backfill_days=1)
        held, day = list(device.held), device.model.batch_day
        restarted = self.fresh_device(backfill_days=1)
        self.assertEqual(list(restarted.held), held)
        self.assertAlmostEqual(restarted.model.batch_day, day, places=6)

    def test_a_changed_setting_remakes_the_held_history_on_restart(self):
        self.fresh_device(backfill_days=1)
        restarted = self.fresh_device(backfill_days=3)
        self.assertEqual(restarted.status()["start"]["held"], 3 * 48 + 1)

    def test_changing_the_starting_point_before_pairing_remakes_the_held_history(self):
        device = self.fresh_device(backfill_days=1)
        device.set_start_point({"history_days": 2, "stage": 2, "progress": 40})
        self.assertEqual(device.status()["start"]["held"], 2 * 48 + 1)
        self.assertEqual(device.held_begins["stage_name"], "Peak Decomposition")
        device.start_batch_in_past(3)  # unpaired: held, no cloud needed
        self.assertEqual(device.status()["start"]["held"], 3 * 48 + 1)
        device.set_start_point({"history_days": 0})
        self.assertEqual((device.status()["start"]["held"], device.status()["start"]["pending"]), (0, False))

    def test_a_factory_reset_keeps_what_is_held_for_the_next_pairing(self):
        self.device = self.fresh_device(backfill_days=1)
        self.pair(set_up=False)
        self.device.factory_reset()
        self.assertEqual(self.device.status()["start"]["held"], 49)
        self.pair()
        self.device._upload_once()
        self.assertEqual(self.device.status()["cloud"]["queued"], 49)

    def test_a_refused_empty_batch_backs_off(self):
        self.device = self.new_device(backfill_days=1)
        self.pair()
        self.cloud.fail_next = [422]
        self.device._upload_once()
        status = self.device.status()
        self.assertEqual(status["cloud"]["state"], "rejected")
        self.assertGreater(status["cloud"]["retry_in_seconds"], 0)
        self.assertTrue(status["start"]["pending"])

if __name__ == "__main__":
    unittest.main()
