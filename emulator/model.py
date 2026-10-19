"""
A live model of one compost pile, advanced one small step at a time.

This is simulator/generator.py turned from "make a whole cycle at once" into
"what does the pile look like now". The maths is the same: temperature eases
towards the far end of each stage's range, moisture evaporates faster when
the pile is active, and the gases follow how active the pile is, whatever
the stage. The stage table and those shared curves come from the simulator
(composting_stages.py), so the two can never disagree about what a stage
looks like.

Active Thermophilic and Peak Decomposition share one heating curve: the
stage becomes Peak Decomposition once the core has held 55 C, and a bin that
never gets that hot goes on to Cooling without it. heat_factor sizes the heat
above ambient for the bin: 1.0 is the full-size pile the stage table
describes, about 0.2 a small Takakura basket that peaks near 35 C.

What's new is that the pile reacts to what you do to it:
  - turning aerates it: O2 jumps, CO2 falls, the core cools for a while,
    and a hot stage runs a little longer on the fresh oxygen
  - water raises moisture; a pile left to dry out cools off and stalls
    (reported in summary()["faults"]), and a waterlogged one goes short of
    oxygen
  - fresh feedstock starts a new batch from the first stage
"""
import math
import random
import sys
from pathlib import Path

try:
    import composting_stages  # noqa: F401
except ImportError:
    # running from a checkout rather than the Docker image, where the file
    # is copied in next to this one
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "simulator"))

from composting_stages import (  # noqa: E402
    PEAK_EXIT_DAYS,
    PEAK_HOLD_DAYS,
    PEAK_TEMP_C,
    STAGES,
    START_MOISTURE_PCT,
    drying_per_day,
    hot_phase_curve,
    nh3_level,
    o2_used,
    pore_air,
)

# same per-sensor noise as the simulator
NOISE = {
    "temperature_c": 0.5,
    "moisture_pct": 1.0,
    "o2_pct": 0.3,
    "co2_pct": 0.2,
    "nh3_relative": 0.03,
}

# what the sensors can physically report, from
# mock-data/compostiq_mock_dataset.schema.json
SENSOR_LIMITS = {
    "temperature_c": (0.0, 100.0),
    "moisture_pct": (0.0, 100.0),
    "o2_pct": (0.0, 25.0),
    "co2_pct": (0.0, 15.0),
    "nh3_relative": (0.0, 1.0),
}

# how long each after-effect takes to fade (1/e), in simulated days
AERATION_FADE_DAYS = 0.4
COOLING_FADE_DAYS = 0.3

TURN_COOLING = 0.2  # share of the heat above ambient lost when turned
TURN_FRESH_AIR = 0.6  # share of the used-up O2 a turn puts back
TURN_MOISTURE_LOSS = 1.5
TURN_STAGE_EXTENSION_DAYS = 0.5
MAX_STAGE_EXTENSION_DAYS = 3.0
HOT_STAGES = (1, 2)
COOLING_STAGE = 3

WATER_STEP_PCT = 6.0
WATER_COOLING_C = 1.5

MOISTURE_FLOOR = 15.0
MOISTURE_CEILING = 85.0
# below DRY_STALL microbes slow right down; below DRY_DEAD they stop. 40 % is
# the bottom of the 40-60 % working range (Cornell, LSU); it was 45 %, which
# slowed down piles that started a little drier halfway through the hot phase
DRY_STALL = 40.0
DRY_DEAD = 30.0
WATERLOGGED = 65.0
SOAKED_O2_USE = 0.4  # extra O2 used up per % of moisture above WATERLOGGED

GLOBAL_PEAK_TEMP = max(stage["temp_range"][1] for stage in STAGES)
LAST_STAGE = len(STAGES) - 1

ACTIONS = ("turn", "water", "feedstock")


def _clamp(value, low, high):
    return max(low, min(high, value))


class CompostModel:
    def __init__(self, rng=None, ambient_temp_c=28.0, start_stage=0, heat_factor=1.0):
        self.rng = rng or random.Random()
        self.ambient = ambient_temp_c
        self.heat_factor = max(0.0, heat_factor)
        self.batch_day = 0.0
        self.aeration = 0.0
        self.cooling = 0.0
        self.turns = 0
        self.waterings = 0
        # how long the core has stayed at or above PEAK_TEMP_C, or below it, in days
        self.hot_hold = 0.0
        self.below_peak = 0.0

        first = STAGES[start_stage]
        if start_stage == 0:
            # stage 0 can't start below ambient (see composting_stages.py)
            temp = max(self.ambient, first["temp_range"][0])
            self.moisture = self.rng.uniform(*START_MOISTURE_PCT)
        else:
            temp = sum(first["temp_range"]) / 2
            self.moisture = self.rng.uniform(*first["moisture_range"])
        self._enter_stage(start_stage, temp)

    # ------------------------------------------------------------ stages ---

    def _enter_stage(self, stage_id, start_temp):
        stage = STAGES[stage_id]
        low, likely, high = stage["duration_days"]
        natural = self.rng.triangular(low, high, likely)

        self.stage_id = stage_id
        self.stage_day = 0.0
        self.stage_duration = natural
        self.stage_extension = 0.0
        self.stage_start_temp = start_temp
        # the temperature curve can outlast the stage: stages 1 and 2 share one
        self.curve_day = 0.0
        if stage_id == 1:
            low, likely, high = STAGES[2]["duration_days"]
            self.curve_length = natural + self.rng.triangular(low, high, likely)
            self.target_temp, self.tau = hot_phase_curve(start_temp, natural, self.curve_length)
        else:
            self.curve_length = natural
            # head for the far end of the range, as generator.get_temp_target does
            temp_low, temp_high = stage["temp_range"]
            self.target_temp = temp_high if start_temp <= (temp_low + temp_high) / 2 else temp_low
            # based on the natural length, so extending a stage doesn't slow it down
            self.tau = max(0.25, natural * 0.3)

    def _start_peak(self):
        # same heating curve, new label: the core has now held 55 C
        self.stage_id = 2
        self.stage_day = 0.0
        self.stage_duration = max(0.0, self.curve_length - self.curve_day)

    @property
    def stage(self):
        return STAGES[self.stage_id]

    @property
    def cured(self):
        return self.stage_id == LAST_STAGE and self.stage_day >= self.stage_duration

    # -------------------------------------------------------- the physics ---

    def _curve_temp(self):
        # generator.get_true_temp: fast at first, then levelling off
        return self.target_temp + (self.stage_start_temp - self.target_temp) * math.exp(
            -self.curve_day / self.tau
        )

    def _dryness(self):
        # 1 = moist enough to work normally, 0 = too dry for microbes
        return _clamp((self.moisture - DRY_DEAD) / (DRY_STALL - DRY_DEAD), 0.0, 1.0)

    def true_temp(self):
        # the curve is for a full-size bin; a smaller one keeps less of the
        # heat, and a pile never sits below ambient on its own
        heat = max(0.0, self._curve_temp() - self.ambient) * self.heat_factor * self._dryness()
        return self.ambient + heat - self.cooling

    def _activity(self, temp):
        return _clamp((temp - self.ambient) / (GLOBAL_PEAK_TEMP - self.ambient), 0.0, 1.0)

    def true_values(self):
        temp = self.true_temp()
        activity = self._activity(temp)

        # generator.get_true_gases: one curve for every stage, so the gases
        # change with the temperature, not with the stage label
        used = o2_used(activity)
        # fresh air from a turn, fading back to the pile's own balance
        used *= 1 - TURN_FRESH_AIR * self.aeration
        # water fills the air gaps, so a soaked pile runs short of oxygen
        used += max(0.0, self.moisture - WATERLOGGED) * SOAKED_O2_USE
        o2, co2 = pore_air(used)
        nh3 = nh3_level(activity) + 0.15 * self.aeration * activity  # turning lets trapped ammonia out

        return {
            "temperature_c": temp,
            "moisture_pct": self.moisture,
            "o2_pct": o2,
            "co2_pct": co2,
            "nh3_relative": nh3,
        }

    def step(self, dt_days):
        temp = self.true_temp()
        activity = self._activity(temp)
        dryness = self._dryness()

        # generator.update_moisture, without the random turning: that's
        # the user's job now
        self.moisture -= drying_per_day(activity) * dt_days
        self.moisture = _clamp(self.moisture, MOISTURE_FLOOR, MOISTURE_CEILING)

        self.aeration *= math.exp(-dt_days / AERATION_FADE_DAYS)
        self.cooling *= math.exp(-dt_days / COOLING_FADE_DAYS)
        if temp >= PEAK_TEMP_C:
            self.hot_hold += dt_days
            self.below_peak = 0.0
        else:
            self.hot_hold = 0.0
            self.below_peak += dt_days

        # a dry pile stalls: its stage clock slows along with the microbes
        clock = dt_days * max(dryness, 0.05)
        self.stage_day += clock
        self.curve_day += clock
        self.batch_day += dt_days

        if self.stage_id == 1 and self.hot_hold >= PEAK_HOLD_DAYS:
            self._start_peak()
        elif self.stage_id == 2 and self.below_peak >= PEAK_EXIT_DAYS:
            # dropped out of the 55 C band (dried out, say): it's cooling now
            self._enter_stage(COOLING_STAGE, self._curve_temp())
        elif self.curve_day >= self.curve_length and self.stage_id < LAST_STAGE:
            # the hot phase cools next, with or without Peak Decomposition
            next_stage = COOLING_STAGE if self.stage_id in HOT_STAGES else self.stage_id + 1
            self._enter_stage(next_stage, self._curve_temp())

    def read(self):
        """One noisy sensor reading, clamped to what the hardware can report."""
        reading = {}
        for field, value in self.true_values().items():
            noisy = value + self.rng.gauss(0, NOISE[field])
            low, high = SENSOR_LIMITS[field]
            decimals = 3 if field == "nh3_relative" else 2
            reading[field] = round(_clamp(noisy, low, high), decimals)
        return reading

    def faults(self):
        """What's wrong with the pile, as the fault codes in simulator/mock_data.py.

        A dried-out pile still has a stage (it picks up where it left off once
        watered), so it's flagged here instead of passing for Cooling or
        Maturation. A cured batch is finished, so nothing is flagged.
        """
        if self.cured:
            return []
        found = []
        if self.moisture < DRY_STALL:
            # below the working range: the microbes are slowing down
            found.append("dry_pile")
        if self.moisture < DRY_DEAD:
            # too dry for microbes: no heat, and the stage has stopped moving
            found.append("stalled_pile")
        return found

    # ---------------------------------------------------------- actions ---

    def turn(self):
        self.turns += 1
        self.aeration = 1.0
        self.cooling += TURN_COOLING * max(0.0, self.true_temp() - self.ambient)
        self.moisture = _clamp(self.moisture - TURN_MOISTURE_LOSS, MOISTURE_FLOOR, MOISTURE_CEILING)
        if self.stage_id in HOT_STAGES and self.stage_extension < MAX_STAGE_EXTENSION_DAYS:
            self.stage_extension += TURN_STAGE_EXTENSION_DAYS
            self.stage_duration += TURN_STAGE_EXTENSION_DAYS
            self.curve_length += TURN_STAGE_EXTENSION_DAYS

    def add_water(self):
        self.waterings += 1
        self.moisture = _clamp(self.moisture + WATER_STEP_PCT, MOISTURE_FLOOR, MOISTURE_CEILING)
        self.cooling += WATER_COOLING_C

    def add_feedstock(self):
        # fresh greens: a new batch starts warming from where the pile is now,
        # as a full-size bin would see it
        stage0 = STAGES[0]
        heat = self.true_temp() - self.ambient
        if self.heat_factor > 0:
            heat /= self.heat_factor
        start = _clamp(self.ambient + heat, self.ambient, sum(stage0["temp_range"]) / 2)
        self.moisture = _clamp(self.moisture + 3.0, MOISTURE_FLOOR, MOISTURE_CEILING)
        self.cooling = 0.0
        self.hot_hold = 0.0
        self.below_peak = 0.0
        self.batch_day = 0.0
        self._enter_stage(0, start)

    def apply(self, action):
        if action == "turn":
            self.turn()
        elif action == "water":
            self.add_water()
        elif action == "feedstock":
            self.add_feedstock()
        else:
            raise ValueError(f"unknown action {action!r}")

    # ------------------------------------------------------- persistence ---

    _SAVED = (
        "batch_day", "aeration", "cooling", "turns", "waterings", "moisture",
        "stage_id", "stage_day", "stage_duration", "stage_extension",
        "stage_start_temp", "target_temp", "tau", "curve_day", "curve_length", "hot_hold",
        "below_peak",
    )

    def to_dict(self):
        return {name: getattr(self, name) for name in self._SAVED}

    @classmethod
    def from_dict(cls, saved, rng=None, ambient_temp_c=28.0, heat_factor=1.0):
        # state saved before stages 1 and 2 shared a curve: each stage's curve
        # ran on the stage clock
        saved = {"curve_day": saved.get("stage_day"), "curve_length": saved.get("stage_duration"),
                 "hot_hold": 0.0, "below_peak": 0.0, **saved}
        model = cls(rng=rng, ambient_temp_c=ambient_temp_c, heat_factor=heat_factor)
        for name in cls._SAVED:
            setattr(model, name, type(getattr(model, name))(saved[name]))
        if not 0 <= model.stage_id <= LAST_STAGE:
            raise ValueError("saved stage_id out of range")
        return model

    def summary(self):
        """What the emulator knows but a real device never would."""
        return {
            "stage_id": self.stage_id,
            "stage_name": self.stage["name"],
            "stage_day": round(self.stage_day, 2),
            "stage_length_days": round(self.stage_duration, 2),
            "batch_day": round(self.batch_day, 2),
            "cured": self.cured,
            "turns": self.turns,
            "waterings": self.waterings,
            "true_temperature_c": round(self.true_temp(), 2),
            "faults": self.faults(),
            # the healthy band for each sensor at this stage
            "expected": {
                "temperature_c": self.stage["temp_range"],
                "moisture_pct": self.stage["moisture_range"],
                "o2_pct": self.stage["o2_range"],
                "co2_pct": self.stage["co2_range"],
                "nh3_relative": self.stage["nh3_relative"],
            },
            "stages": [stage["name"] for stage in STAGES],
        }
