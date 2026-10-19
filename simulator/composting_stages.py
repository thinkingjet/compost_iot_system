"""The definition of the various compost stages that exist.
duration_days = (min, most_likely, max), in days.
temp_range / moisture_range / o2_range / co2_range = (min, max) envelope.
nh3_relative = (min, max) on a 0.0-1.0 relative-intensity scale, NOT an
    absolute ppm - no source measures ppm-NH3 inside a small bin, only
    the timing pattern (rises with temperature, peaks at thermophilic
    peak, near zero by maturation). See note on MQ-135 below.
Sources for temp/moisture/duration: see header of previous version /
compost_measured_data.md [A]-[H].
Additional sources for gas data (compost_gas_data.md):
  [I] Cornell Waste Management Institute - compost.css.cornell.edu/physics.html
      O2/CO2 baseline: O2 starts 15-20%, anaerobic risk below ~5%.
  [J] Stegenta et al. 2019, Sustainability (MDPI 11(8):2340)
      CO2 pore concentration mostly 2-3%, isolated spikes >10%.
  [K] Pagans et al. 2006, ScienceDirect - NH3 rises exponentially
      during thermophilic (>45C), linearly during final mesophilic.
  [L] PSLab - pslab.io/measuring-co2-with-mq135 - MQ-135 is a SnO2
      sensor cross-sensitive to NH3/NOx/CO/CO2/VOCs, calibrated
      against 100ppm NH3 reference. It does NOT cleanly measure CO2.
Sources for the Peak Decomposition rule and bin size:
  [M] US EPA 40 CFR 503 Appendix B - PFRP: >= 55C for 3 days (in-vessel or
      static pile), the sanitisation band Peak Decomposition is defined by.
  [N] Nurita et al. 2023 - small Indonesian Takakura baskets peak around 35C.
IMPORTANT: the MQ-135 physically reports one composite, cross-sensitive,
drifting analog value - not a clean gas concentration. Turning
o2_range/co2_range/nh3_relative into a single simulated sensor reading
(with the documented 24-48h warm-up and per-unit R0 drift) is a
separate sensor-response step, done later, not encoded here.

The gas envelopes below describe what the gas curve at the bottom of this
file gives in each stage of a full-size, looked-after pile. They are no longer
what the gases are drawn from: drawing them from the current stage's own range
made them jump the moment the stage changed, which gave the label away.

Ambient at the Mataram pilot site is ~24-32C year-round. Stage 0 cannot
start below ambient and Stage 4 converges to it, so both are floored at
28C rather than the temperate-climate figures.
"""
import math

STAGES = [
    {
        "id": 0,
        "name": "Early Mesophilic",
        "duration_days": (1, 2, 3),
        "temp_range": (28.0, 45.0),  # was 20.0 - pile can't start below ambient
        "moisture_range": (60.0, 65.0),
        "o2_range": (15.5, 21.0),
        "co2_range": (0.5, 5.5),
        "nh3_relative": (0.0, 0.2),
    },
    {
        "id": 1,
        "name": "Active Thermophilic",
        # how long a full-size pile takes to climb from 45C to holding 55C;
        # a bin that never holds 55C stays here for the whole hot phase
        "duration_days": (2, 3, 4),  # was (2,2,3) - min==most_likely is degenerate
        "temp_range": (45.0, 60.0),
        "moisture_range": (55.0, 60.0),
        "o2_range": (12.0, 17.5),
        "co2_range": (3.5, 9.0),
        "nh3_relative": (0.15, 0.55),
    },
    {
        "id": 2,
        "name": "Peak Decomposition",
        # the stretch the core holds at or above 55C [M], not a separate phase
        # in the literature: it starts once the core has stayed at PEAK_TEMP_C
        # for PEAK_HOLD_DAYS, and is skipped by a bin that never gets that hot.
        # 4-7 days clears the 3-day PFRP target with room to spare.
        "duration_days": (4, 5, 7),
        "temp_range": (55.0, 65.0),  # was 57.0 - now the PFRP band itself
        "moisture_range": (50.0, 58.0),
        "o2_range": (10.0, 16.5),
        "co2_range": (4.5, 11.0),
        "nh3_relative": (0.45, 0.95),
    },
    {
        "id": 3,
        "name": "Cooling",
        "duration_days": (5, 8, 10),
        "temp_range": (30.0, 60.0),
        "moisture_range": (45.0, 55.0),
        "o2_range": (11.0, 20.0),
        "co2_range": (1.0, 10.0),
        "nh3_relative": (0.0, 0.75),
    },
    {
        "id": 4,
        "name": "Maturation",
        "duration_days": (24, 30, 36),
        "temp_range": (28.0, 32.0),  # was (22.0, 30.0) - converges to ambient
        "moisture_range": (40.0, 50.0),
        "o2_range": (19.0, 21.0),
        "co2_range": (0.3, 2.0),
        "nh3_relative": (0.0, 0.1),
    },
]

# ---------------------------------------------------------------------------
# How any pile behaves, whatever its stage. simulator/generator.py and
# emulator/model.py both use these, so the two never disagree.

# a fresh batch starts somewhere in this range rather than always at the same
# 62.5 %, which let moisture work as a clock for the first few days
START_MOISTURE_PCT = (50.0, 65.0)

# Moisture lost per day. Most of it is the pile's own heat steaming water
# off, so a cool pile only loses a little. The same in every stage, so the
# drying rate doesn't change the moment the stage does (it used to be 15 % of
# each stage's moisture range, which also dried a cool, maturing pile at
# 0.75 % a day)
DRYING_PCT_PER_DAY = 1.2  # times (RESTING_DRYING + activity)
RESTING_DRYING = 0.25


def drying_per_day(activity):
    """Moisture (%) a pile at this activity (0-1) loses in a day."""
    return DRYING_PCT_PER_DAY * (RESTING_DRYING + activity)

# Active Thermophilic and Peak Decomposition are one hot phase on one heating
# curve. The label moves on to Peak Decomposition once the core has held
# PEAK_TEMP_C [M] for PEAK_HOLD_DAYS, so the heat is sustained, not a passing
# peak. A bin that never gets that hot - a small Takakura basket [N], a pile
# too dry to heat - stays in Active Thermophilic until the hot phase ends and
# then cools. Peak Decomposition ends with the hot phase, or sooner if the
# core drops below PEAK_TEMP_C for PEAK_EXIT_DAYS (long enough that a turn's
# brief dip doesn't count).
PEAK_TEMP_C = 55.0
PEAK_HOLD_DAYS = 0.25
PEAK_EXIT_DAYS = 0.5


def hot_phase_curve(start_temp, active_days, phase_days):
    """(target, tau) of the heating curve stages 1 and 2 share, in C and days.

    It heads for the top of Peak Decomposition's range. tau is set so a
    full-size, moist pile has held PEAK_TEMP_C for PEAK_HOLD_DAYS just as
    active_days (its Active Thermophilic length) run out; capped so the pile
    still gets near the top before phase_days end.
    """
    target = STAGES[2]["temp_range"][1]
    if start_temp >= PEAK_TEMP_C - 0.5:
        return target, max(0.25, phase_days * 0.3)
    crossing = max(0.25, active_days - PEAK_HOLD_DAYS)
    tau = crossing / math.log((target - start_temp) / (target - PEAK_TEMP_C))
    return target, max(0.25, min(tau, phase_days * 0.5))


# The gases follow one curve of how active the pile is,
#   activity = heat above ambient / (hottest stage temperature - ambient), 0-1,
# so they change smoothly with the temperature instead of jumping at a stage
# change. O2 and CO2 trade off one for one (respiratory quotient about 1), so
# O2 + CO2 stays near air's 21 %. At full activity O2 bottoms out near 10 %,
# above the 5 % survival floor [I], and CO2 tops out near 11 % [J].
AIR_O2_PCT = 20.9
AIR_CO2_PCT = 0.04
RESTING_O2_USE = 0.5   # %, a cool, finished pile still breathes a little
ACTIVE_O2_USE = 10.5   # %, the extra a pile at full activity uses
NH3_RISE = 2.5         # how steeply NH3 climbs with activity: exponential [K]


def o2_used(activity):
    """O2 (%) the microbes have taken out of the pile's air at this activity."""
    return RESTING_O2_USE + ACTIVE_O2_USE * activity


def pore_air(used):
    """(O2, CO2) % in the pile's air once `used` % of the oxygen is breathed:
    each % of O2 used comes back as a % of CO2."""
    return AIR_O2_PCT - used, AIR_CO2_PCT + used


def nh3_level(activity):
    """Relative NH3, 0-1: near zero in a cool pile, 1 at full activity."""
    return (math.exp(NH3_RISE * activity) - 1) / (math.exp(NH3_RISE) - 1)


def pile_gases(activity):
    """(O2 %, CO2 %, NH3 relative) of an undisturbed pile at this activity."""
    o2, co2 = pore_air(o2_used(activity))
    return o2, co2, nh3_level(activity)
