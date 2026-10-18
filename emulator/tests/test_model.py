import random
import unittest

from model import (
    LAST_STAGE,
    PEAK_HOLD_DAYS,
    PEAK_TEMP_C,
    SENSOR_LIMITS,
    START_MOISTURE_PCT,
    CompostModel,
)

STEP = 30 / 1440  # the simulator's 30-minute sample interval, in days


def run(model, days):
    for _ in range(int(days / STEP)):
        model.step(STEP)


class ModelTest(unittest.TestCase):
    def setUp(self):
        self.model = CompostModel(random.Random(1))

    def test_a_watered_pile_goes_through_every_stage_and_cures(self):
        seen = set()
        for _ in range(int(80 / STEP)):
            self.model.step(STEP)
            seen.add(self.model.stage_id)
            if self.model.moisture < 50:
                self.model.add_water()
        self.assertEqual(seen, set(range(LAST_STAGE + 1)))
        self.assertTrue(self.model.cured)

    def test_the_hot_stages_get_hot(self):
        peak = 0
        for _ in range(int(12 / STEP)):
            self.model.step(STEP)
            peak = max(peak, self.model.true_temp())
        self.assertGreater(peak, 57)

    def test_readings_stay_inside_what_the_sensors_can_report(self):
        for _ in range(int(40 / STEP)):
            self.model.step(STEP)
            for field, value in self.model.read().items():
                low, high = SENSOR_LIMITS[field]
                self.assertTrue(low <= value <= high, f"{field}={value}")

    def test_turning_lets_air_in_and_cools_the_core(self):
        run(self.model, 6)  # into the hot stages
        before = self.model.true_values()
        self.model.turn()
        after = self.model.true_values()
        self.assertGreater(after["o2_pct"], before["o2_pct"] + 5)
        self.assertLess(after["co2_pct"], before["co2_pct"])
        self.assertLess(after["temperature_c"], before["temperature_c"])

    def test_turning_wears_off(self):
        run(self.model, 6)
        self.model.turn()
        boosted = self.model.true_values()["o2_pct"]
        run(self.model, 2)
        self.assertLess(self.model.true_values()["o2_pct"], boosted - 5)

    def test_water_raises_moisture(self):
        before = self.model.moisture
        self.model.add_water()
        self.assertAlmostEqual(self.model.moisture, before + 6)

    def test_a_dry_pile_stalls_and_water_brings_it_back(self):
        run(self.model, 3)  # Active Thermophilic, still heating up
        self.model.moisture = 32
        dry = self.model.true_temp()
        stage_day = self.model.stage_day
        run(self.model, 1)
        self.assertLess(self.model.stage_day - stage_day, 0.3)  # clock nearly stopped
        for _ in range(4):
            self.model.add_water()
        run(self.model, 1)
        self.assertGreater(self.model.true_temp(), dry + 10)

    def test_a_soaked_pile_runs_short_of_oxygen(self):
        run(self.model, 20)  # maturation, normally airy
        normal = self.model.true_values()["o2_pct"]
        self.model.moisture = 80
        self.assertLess(self.model.true_values()["o2_pct"], normal - 5)

    def test_feedstock_starts_a_new_batch(self):
        run(self.model, 20)
        self.model.add_feedstock()
        self.assertEqual(self.model.stage_id, 0)
        self.assertEqual(self.model.batch_day, 0)

    def test_the_gases_dont_jump_when_the_stage_changes(self):
        before, changes = self.model.true_values(), 0
        for _ in range(int(60 / STEP)):
            stage = self.model.stage_id
            self.model.step(STEP)
            after = self.model.true_values()
            if self.model.stage_id != stage:
                changes += 1
                for field, most in (("o2_pct", 0.3), ("co2_pct", 0.3), ("nh3_relative", 0.05)):
                    self.assertLess(abs(after[field] - before[field]), most, f"{field} into stage {self.model.stage_id}")
            before = after
        self.assertGreaterEqual(changes, 3)

    def test_o2_and_co2_trade_off_and_o2_stays_survivable(self):
        for _ in range(int(60 / STEP)):
            self.model.step(STEP)
            if self.model.moisture < 50:
                self.model.add_water()
            if self.model.stage_id in (1, 2) and self.model.stage_day < STEP:
                self.model.turn()
            gases = self.model.true_values()
            self.assertAlmostEqual(gases["o2_pct"] + gases["co2_pct"], 21, delta=0.1)
            self.assertGreaterEqual(gases["o2_pct"], 5)

    def test_batches_start_at_different_moistures(self):
        starts = [CompostModel(random.Random(seed)).moisture for seed in range(20)]
        low, high = START_MOISTURE_PCT
        self.assertTrue(all(low <= moisture <= high for moisture in starts))
        self.assertGreater(max(starts) - min(starts), 8)

    def test_heat_factor_scales_the_heat_above_ambient(self):
        half = CompostModel(random.Random(1), heat_factor=0.5)
        run(self.model, 4)
        run(half, 4)
        self.assertAlmostEqual(half.true_temp() - 28, 0.5 * (self.model.true_temp() - 28), delta=0.5)

    def test_a_small_basket_peaks_near_35_and_skips_peak_decomposition(self):
        basket = CompostModel(random.Random(1), heat_factor=0.2)
        peak, seen = 0, set()
        for _ in range(int(80 / STEP)):
            basket.step(STEP)
            if basket.moisture < 50:
                basket.add_water()
            peak = max(peak, basket.true_temp())
            seen.add(basket.stage_id)
        self.assertTrue(32 < peak < 40, peak)
        self.assertEqual(seen, {0, 1, 3, 4})
        self.assertTrue(basket.cured)

    def test_peak_decomposition_starts_once_the_core_has_held_55(self):
        temps = []
        while self.model.stage_id < 2 and len(temps) < 20 / STEP:
            temps.append(self.model.true_temp())
            self.model.step(STEP)
        self.assertEqual(self.model.stage_id, 2)
        held = 0
        for temp in reversed(temps):
            if temp < PEAK_TEMP_C:
                break
            held += 1
        self.assertAlmostEqual(held * STEP, PEAK_HOLD_DAYS, delta=1.5 * STEP)

    def test_a_pile_that_drops_out_of_the_55_band_is_cooling(self):
        while self.model.stage_id < 2:
            self.model.step(STEP)
        self.model.moisture = 32
        run(self.model, 1)
        self.assertEqual(self.model.stage_id, 3)

    def test_a_dried_out_pile_is_flagged_and_water_clears_it(self):
        run(self.model, 3)
        self.model.moisture = 45
        self.assertEqual(self.model.summary()["faults"], [])
        self.model.moisture = 35
        self.assertEqual(self.model.summary()["faults"], ["dry_pile"])
        self.model.moisture = 25
        self.assertEqual(self.model.summary()["faults"], ["dry_pile", "stalled_pile"])
        for _ in range(4):
            self.model.add_water()
        self.assertEqual(self.model.summary()["faults"], [])

    def test_state_round_trips(self):
        run(self.model, 5)
        self.model.turn()
        copy = CompostModel.from_dict(self.model.to_dict(), random.Random(1))
        self.assertEqual(copy.to_dict(), self.model.to_dict())
        self.assertAlmostEqual(copy.true_temp(), self.model.true_temp())

    def test_state_saved_before_the_shared_hot_curve_still_loads(self):
        run(self.model, 5)
        saved = self.model.to_dict()
        for name in ("curve_day", "curve_length", "hot_hold", "below_peak"):
            del saved[name]
        copy = CompostModel.from_dict(saved, random.Random(1))
        self.assertEqual(copy.curve_day, saved["stage_day"])
        self.assertEqual(copy.curve_length, saved["stage_duration"])

    def test_unknown_action_is_refused(self):
        with self.assertRaises(ValueError):
            self.model.apply("stir")


if __name__ == "__main__":
    unittest.main()
