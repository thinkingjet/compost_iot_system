"""
The device itself: sensors, pairing and the uplink to the cloud.

Two background loops run for as long as the device is powered on:

  sampler   every READING_INTERVAL_SECONDS, advance the pile by
            READING_INTERVAL_SECONDS x TIME_SCALE of compost time and take a
            reading. Readings are stamped with the real wall-clock time, as a
            real device with NTP would, so only the pile runs fast.
  uploader  sends queued readings to the cloud in batches. If the cloud is
            down it backs off and keeps the readings (up to QUEUE_MAX, oldest
            dropped first) until it comes back.

The cloud's stage model reads timestamps as real time, so it needs history
before it can say anything. The device page sets a starting point: a batch N
days back, so far through one of its stages. The first time the cloud takes
this device's readings after pairing, the device runs that batch up to now
and sends its history, a reading every BACKFILL_STEP_MINUTES, then carries on
live from where it ends; start_batch_in_past() does the same on demand. With
TIME_SCALE above 1 the live pile then runs faster than its timestamps, which
the stage model can't follow for long.

Pairing gives the device its key, but the cloud only takes its readings once
the user has confirmed the registration in the dashboard and given the device
a name and a bin. Until then /records answers 409, and the device waits in
"awaiting_setup": it checks back every SETUP_CHECK_SECONDS and holds only its
newest reading, so readings from before it was set up never land in a bin.

The web page (web.py) only ever calls the public methods here.
"""
import itertools
import logging
import random
import re
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from cloud import CloudClient, CloudError, CloudUnreachable
from model import ACTIONS, LAST_STAGE, STAGES, CompostModel
from state import Credentials, StateFile, fake_mac

log = logging.getLogger(__name__)

HISTORY_LENGTH = 120
EVENT_LOG_LENGTH = 20
BACKOFF_FIRST_SECONDS = 5
BACKOFF_MAX_SECONDS = 300
CODE_PATTERN = re.compile(r"^\d{6}$")
# a batch started in the past: one reading per half hour of its history (the
# simulator's sample rate), and looked after: watered when it gets this dry
BACKFILL_STEP_MINUTES = 30
BACKFILL_WATER_BELOW_PCT = 50.0
# a starting point can be up to this far through its stage, in %
MAX_START_PROGRESS = 95
# longer than any batch takes to cure (about 60 days at most), so getting a
# fresh pile to any starting point always ends
MAX_PREROLL_DAYS = 90
AWAITING_SETUP = ("Paired. Finish setting up this device in the dashboard (confirm the "
                  "registration, then give it a name and a bin) and readings will start.")

# sensor names on the device -> field names the API's /records expects
API_FIELDS = {
    "temperature_c": "temperature",
    "moisture_pct": "moisture_percent",
    "o2_pct": "o2_percent",
    "co2_pct": "co2_percent",
    "nh3_relative": "nh3_ratio",
}

PAIRING_ERRORS = {
    404: "That code wasn't recognised, or it has expired. Get a new code from the dashboard.",
    409: "That code has already been used. Get a new code from the dashboard.",
    410: "That code has expired. Get a new code from the dashboard.",
    429: "Too many attempts. Wait a few minutes, then try again.",
}


class PairingError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


class BackfillError(Exception):
    """Why a starting point or a batch in the past is refused, with the HTTP status for the page."""
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def to_api_record(reading):
    record = {"timestamp": reading["timestamp"]}
    for field, api_field in API_FIELDS.items():
        record[api_field] = reading[field]
    return record


def _tend(model):
    """Move a looked-after pile on one BACKFILL_STEP_MINUTES step, watering it when it gets dry."""
    model.step(BACKFILL_STEP_MINUTES / 1440)
    if model.moisture < BACKFILL_WATER_BELOW_PCT:
        model.add_water()


def pile_at(rng, ambient_temp_c, stage, progress):
    """A looked-after batch of fresh feedstock, run on until it is `progress` %
    of the way through `stage`.

    A stage can end before that: Active Thermophilic becomes Peak
    Decomposition as soon as the core has held 55 C. The pile then stops at
    the start of the stage it moved on to.
    """
    model = CompostModel(rng, ambient_temp_c)
    for _ in range(MAX_PREROLL_DAYS * 1440 // BACKFILL_STEP_MINUTES):
        if model.stage_id > stage or (model.stage_id == stage and model.stage_progress >= progress / 100):
            break
        _tend(model)
    return model


def _describe(start):
    point = f"{start['progress']} % through {STAGES[start['stage']]['name']}"
    days = start["history_days"]
    if not days:
        return f"{point}, no history"
    return f"{days} day{'s' if days != 1 else ''} of history from {point}"


def _where(model):
    return {"stage_id": model.stage_id, "stage_name": model.stage["name"],
            "progress": round(model.stage_progress * 100), "cured": model.cured}


class Device:
    def __init__(self, settings, cloud=None):
        self.settings = settings
        self.cloud = cloud or CloudClient(settings)
        self.lock = threading.RLock()
        self.pairing_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.wake_uploader = threading.Event()
        self.threads = []
        self.rng = random.Random(settings.seed)

        self.store = StateFile(settings.state_file)
        self.store.load()
        self.store.device_uid = settings.device_uid or self.store.device_uid or fake_mac()
        self.start_point = self._restore_start()
        self.model = self._restore_model()
        self.store.model = self.model.to_dict()
        self.store.save()
        # where the starting point's batch begins, and where it is by now
        self.start_preview = self._preview(self.start_point)
        # the last batch sent this run: {"at", "days", "readings", "begins"}
        self.last_batch = None

        self.history = deque(maxlen=HISTORY_LENGTH)
        self.events = deque(maxlen=EVENT_LOG_LENGTH)
        self.latest = None

        # (seq, record) pairs, so a successful upload removes exactly what it
        # sent even if the queue overflowed while the request was in flight
        self.queue = deque()
        self.seq = 0
        # bumped whenever the credentials change, so an upload that was in
        # flight during an unpair can't act on the old key's result
        self.generation = 0

        self.uploads_paused = False
        self.retry_at = 0.0
        self.failures = 0
        self.uplink = {
            "state": "idle",
            "message": None,
            "last_attempt_at": None,
            "last_success_at": None,
            "sent_total": 0,
            "dropped_total": 0,
        }
        self._log_event("power on")

    def _restore_model(self):
        if self.store.model:
            try:
                return CompostModel.from_dict(self.store.model, self.rng, self.settings.ambient_temp_c)
            except (KeyError, TypeError, ValueError) as error:
                log.warning("saved pile state is unusable (%s); starting a new batch", error)
        return pile_at(self.rng, self.settings.ambient_temp_c, self.start_point["stage"], self.start_point["progress"])

    def _restore_start(self):
        """The starting point: what was set on the page, the settings for the rest.

        Only what the page set is saved, so a changed setting still counts for
        anything the page hasn't touched.
        """
        limit = self.max_backfill_days()
        days = self.settings.backfill_days
        if days > limit:
            log.warning("BACKFILL_DAYS=%d doesn't fit the upload queue; sending %d days", days, limit)
            days = limit
        start = {"history_days": days, "stage": self.settings.start_stage, "progress": self.settings.start_progress}
        saved = self.store.start if isinstance(self.store.start, dict) else {}
        chosen = {name: saved[name] for name in start if name in saved}
        try:
            start = self._checked_start({**start, **chosen})
        except BackfillError as error:
            log.warning("saved starting point is unusable (%s); using the settings", error)
            chosen = {}
        # one batch per device, so changing how much history to send only moves where it ends
        seed = saved.get("seed")
        if not isinstance(seed, int) or isinstance(seed, bool):
            seed = self.rng.randrange(2 ** 32)
        self.store.start = {**chosen, "seed": seed}
        return {**start, "seed": seed}

    # ----------------------------------------------------------- lifecycle ---

    def start(self):
        with self.lock:
            self._take_reading()
        for name, target in (("sampler", self._sampler_loop), ("uploader", self._uploader_loop)):
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
            self.threads.append(thread)

    def stop(self):
        self.stop_event.set()
        self.wake_uploader.set()
        for thread in self.threads:
            thread.join(timeout=self.settings.http_timeout_seconds + 1)
        with self.lock:
            self._save()

    def _save(self):
        self.store.model = self.model.to_dict()
        try:
            self.store.save()
        except OSError as error:
            log.error("couldn't save state to %s: %s", self.store.path, error)

    def _log_event(self, text):
        self.events.appendleft({"at": utc_now(), "text": text})
        log.info(text)

    # ------------------------------------------------------------- pairing ---

    @property
    def credentials(self):
        return self.store.credentials

    def _pairing_state(self):
        creds = self.credentials
        if creds is None:
            return "unpaired"
        if creds.cloud_api_url != self.settings.cloud_api_url:
            return "other_cloud"
        return "paired"

    def pair(self, code):
        code = (code or "").strip().replace(" ", "")
        if not CODE_PATTERN.match(code):
            raise PairingError("The pairing code is the 6 digits shown in the dashboard.")
        with self.lock:
            if self.credentials is not None:
                raise PairingError("This device is already paired. Factory reset it to pair again.", 409)
        if not self.pairing_lock.acquire(blocking=False):
            raise PairingError("Pairing is already in progress.", 409)
        try:
            api_key, device_id = self.cloud.redeem_code(code, self.store.device_uid)
        except CloudUnreachable as error:
            raise PairingError(f"Couldn't reach the cloud at {self.settings.cloud_api_url} ({error}).", 502)
        except CloudError as error:
            message = PAIRING_ERRORS.get(error.status, f"The cloud refused the code: {error.detail}")
            raise PairingError(message, 400 if error.status < 500 else 502)
        finally:
            self.pairing_lock.release()

        with self.lock:
            self.store.credentials = Credentials(
                device_id=device_id,
                api_key=api_key,
                paired_at=utc_now(),
                cloud_api_url=self.settings.cloud_api_url,
            )
            self.generation += 1
            self.queue.clear()
            self.failures = 0
            self.retry_at = 0.0
            # sent the first time the cloud takes this pairing's readings
            self.store.history_pending = True
            self._set_uplink("awaiting_setup", AWAITING_SETUP)
            self._save()
            self._log_event(f"paired as device {device_id or '(id not given)'}; "
                            "waiting for setup in the dashboard")
        self.wake_uploader.set()

    def _forget_credentials(self, reason):
        self.store.credentials = None
        self.store.history_pending = False
        self.generation += 1
        self.queue.clear()
        self.failures = 0
        self.retry_at = 0.0
        self._save()
        self._log_event(reason)

    def factory_reset(self):
        # wipes pairing, not the hardware ID or the compost in the bin
        with self.lock:
            self._forget_credentials("factory reset: pairing cleared")
            self._set_uplink("idle", None)

    # --------------------------------------------------------------- pile ---

    def apply_action(self, action):
        if action not in ACTIONS:
            raise ValueError(f"unknown action {action!r}")
        labels = {"turn": "pile turned", "water": "water added", "feedstock": "fresh feedstock added"}
        with self.lock:
            self.model.apply(action)
            self._log_event(labels[action])
            # read straight away, so the effect shows without waiting a cycle
            self._take_reading()
        self.wake_uploader.set()

    def _sampler_loop(self):
        interval = self.settings.reading_interval_seconds
        dt_days = interval * self.settings.time_scale / 86400
        while not self.stop_event.wait(interval):
            with self.lock:
                self.model.step(dt_days)
                self._take_reading()
            self.wake_uploader.set()

    def _take_reading(self, save=True):
        self._keep_reading({"timestamp": utc_now(), **self.model.read()})
        if save:
            self._save()

    def _keep_reading(self, reading):
        self.latest = reading
        self.history.append(reading)
        # an unpaired device has nowhere to send readings, so it doesn't keep them,
        # and until its history has gone the history replaces them anyway
        if self._pairing_state() == "paired" and not self._history_due():
            self.seq += 1
            self.queue.append((self.seq, to_api_record(reading)))
            # not set up yet: only the newest reading is worth sending later
            limit = 1 if self.uplink["state"] == "awaiting_setup" else self.settings.queue_max
            while len(self.queue) > limit:
                self.queue.popleft()
                if limit > 1:
                    self.uplink["dropped_total"] += 1

    def max_backfill_days(self):
        # the whole history has to fit in the upload queue
        return int(self.settings.queue_max * BACKFILL_STEP_MINUTES / 1440)

    def _backfill_blocker(self):
        """Why a batch can't be started in the past right now, or None."""
        if self._pairing_state() != "paired":
            return "Pair the device first."
        # before setup the queue keeps only the newest reading, so the history would be lost;
        # after a restart, wait for the first upload to show the cloud still takes readings
        if self.uplink["state"] == "awaiting_setup" or self.uplink["last_success_at"] is None:
            return "Wait until the cloud is taking this device's readings (set it up in the dashboard first)."
        return None

    # ------------------------------------------------------ starting point ---

    def _checked_start(self, values):
        """history_days, stage and progress from `values`, or BackfillError for the first that's out of range."""
        limit = self.max_backfill_days()
        rules = {
            "history_days": (0, limit, f"History is between 0 and {limit} days."),
            "stage": (0, LAST_STAGE, "Pick one of the five stages."),
            "progress": (0, MAX_START_PROGRESS, f"How far through the stage is between 0 and {MAX_START_PROGRESS} %."),
        }
        checked = {}
        for name, (low, high, message) in rules.items():
            value = values[name]
            if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
                raise BackfillError(message)
            checked[name] = value
        return checked

    def set_start_point(self, changes):
        """Change any of history_days, stage and progress.

        Until this pairing's history has gone, this is what will be sent; after
        that, start_batch_in_past() uses it.
        """
        with self.lock:
            self.start_point = {**self._checked_start({**self.start_point, **changes}), "seed": self.start_point["seed"]}
            self.store.start = {**self.store.start, **{name: self.start_point[name] for name in changes if name in self.start_point}}
            self.start_preview = self._preview(self.start_point)
            self._save()
            self._log_event(f"starting point set: {_describe(self.start_point)}")

    def _simulate_batch(self, start, now):
        """The starting point's batch: where it begins, the pile it ends as, and
        a reading every BACKFILL_STEP_MINUTES from history_days before `now` up to `now`.

        Its random numbers come from the starting point's seed, so a preview and
        the batch it previews are the same pile.
        """
        model = pile_at(random.Random(start["seed"]), self.settings.ambient_temp_c, start["stage"], start["progress"])
        begins = _where(model)
        steps = start["history_days"] * 1440 // BACKFILL_STEP_MINUTES
        readings = []
        for i in range(steps + 1):
            if i:
                _tend(model)
            at = now - timedelta(minutes=(steps - i) * BACKFILL_STEP_MINUTES)
            readings.append({"timestamp": at.isoformat(timespec="milliseconds"), **model.read()})
        # live readings carry on with the device's own random numbers
        model.rng = self.rng
        return begins, model, readings

    def _preview(self, start):
        begins, model, _ = self._simulate_batch(start, datetime.now(timezone.utc))
        return {"begins": begins, "now": _where(model)}

    def _history_due(self):
        """Paired, and the starting point's history still has to go."""
        return (self.store.history_pending and self.start_point["history_days"] > 0
                and self._pairing_state() == "paired")

    def _run_batch(self, start):
        """Replace the pile with the starting point's batch and queue its history, ending now."""
        days = start["history_days"]
        superseded = 0
        if days:
            # unsent readings of the old pile would land in the middle of the new batch's history
            superseded = len(self.queue)
            self.queue.clear()
            self.uplink["dropped_total"] += superseded
            self.history.clear()
        begins, self.model, readings = self._simulate_batch(start, datetime.now(timezone.utc))
        for reading in readings:
            self._keep_reading(reading)
        self._save()
        self.last_batch = {"at": utc_now(), "days": days, "readings": len(readings), "begins": begins}

        point = f"{begins['progress']} % through {begins['stage_name']}"
        if not days:
            self._log_event(f"pile moved to {point}")
            return
        fresh = begins["stage_id"] == 0 and begins["progress"] == 0
        note = f"; {superseded} unsent readings of the old pile dropped" if superseded else ""
        self._log_event(f"started a batch {days} day{'s' if days != 1 else ''} ago"
                        f"{'' if fresh else ' at ' + point}: {len(readings)} readings of its history queued{note}")

    def start_batch_in_past(self, days=None):
        """Replaces the pile with the starting point's batch, begun `days` ago
        (the starting point's history_days if None), and queues its history.

        The batch runs forward in BACKFILL_STEP_MINUTES steps, watered below
        BACKFILL_WATER_BELOW_PCT, with a reading at every step stamped from
        `days` ago up to now, so the cloud gets a batch at real-time spacing.
        Live readings carry on from the pile it ends with. With no history
        (0 days) the pile just moves to the starting point, which needs no cloud.
        """
        with self.lock:
            start = dict(self.start_point)
            if days is not None:
                limit = self.max_backfill_days()
                if not 1 <= days <= limit:
                    raise BackfillError(f"Pick between 1 and {limit} days.")
                start["history_days"] = days
            if start["history_days"]:
                blocker = self._backfill_blocker()
                if blocker:
                    raise BackfillError(blocker, 409)
            self._run_batch(start)
        self.wake_uploader.set()

    # -------------------------------------------------------------- uplink ---

    def set_uploads_paused(self, paused):
        with self.lock:
            self.uploads_paused = bool(paused)
            self._log_event("uploads paused" if paused else "uploads resumed")
        self.wake_uploader.set()

    def retry_now(self):
        with self.lock:
            self.retry_at = 0.0
        self.wake_uploader.set()

    def _set_uplink(self, state, message):
        self.uplink["state"] = state
        self.uplink["message"] = message

    def _back_off(self, state, message):
        self.failures += 1
        delay = min(BACKOFF_MAX_SECONDS, BACKOFF_FIRST_SECONDS * 2 ** (self.failures - 1))
        self.retry_at = time.monotonic() + delay
        self._set_uplink(state, f"{message} Retrying in {delay} s.")

    def _uploader_loop(self):
        while not self.stop_event.is_set():
            # the timeout also lets a finished back-off be noticed
            self.wake_uploader.wait(timeout=1.0)
            self.wake_uploader.clear()
            if not self.stop_event.is_set():
                self._upload_once()

    def _upload_once(self):
        with self.lock:
            if self.uploads_paused or self._pairing_state() != "paired":
                return
            # the history goes once the cloud takes this device's readings; until
            # then an empty batch asks whether it does, and stores nothing either way
            probe = self._history_due()
            if not (probe or self.queue) or time.monotonic() < self.retry_at:
                return
            batch = [] if probe else list(itertools.islice(self.queue, self.settings.upload_batch_max))
            api_key = self.credentials.api_key
            generation = self.generation
            self.uplink["last_attempt_at"] = utc_now()

        try:
            self.cloud.send_records(api_key, [record for _, record in batch])
        except CloudUnreachable as error:
            with self.lock:
                if generation == self.generation:
                    self._back_off("offline", f"Can't reach {self.settings.cloud_api_url} ({error}).")
            return
        except CloudError as error:
            with self.lock:
                if generation == self.generation:
                    self._handle_rejection(error, batch)
            return

        with self.lock:
            if generation != self.generation:
                return
            if batch:
                last_sent = batch[-1][0]
                while self.queue and self.queue[0][0] <= last_sent:
                    self.queue.popleft()
            self.failures = 0
            self.retry_at = 0.0
            self.uplink["sent_total"] += len(batch)
            self.uplink["last_success_at"] = utc_now()
            if self.uplink["state"] == "awaiting_setup":
                self._log_event("setup finished in the dashboard; the cloud is taking readings")
            self._set_uplink("ok", f"Sent {len(batch)} reading{'s' if len(batch) != 1 else ''}." if batch
                             else "The cloud is taking this device's readings.")
            if self.store.history_pending:
                # the first time the cloud takes this pairing's readings: the history's moment.
                # After the state above, so the whole history is queued, not just the newest
                self.store.history_pending = False
                days = self.start_point["history_days"]
                if days:
                    self._run_batch(self.start_point)
                    self._set_uplink("ok", f"Sending {days} day{'s' if days != 1 else ''} of history "
                                           f"({len(self.queue)} readings).")
                self._save()
            more = bool(self.queue)
        if more:
            self.wake_uploader.set()

    def _handle_rejection(self, error, batch):
        if error.status in (401, 403):
            # the key was revoked, most likely by removing the device in the dashboard
            self._forget_credentials("the cloud rejected this device's key; pairing cleared")
            self._set_uplink("revoked", "The cloud no longer accepts this device's key "
                                        "(it was probably removed in the dashboard). Pair it again.")
        elif error.status == 409:
            # paired but not set up (or moved out of its bin): expected, not a
            # fault, so check back at a steady pace instead of backing off
            if self.uplink["state"] != "awaiting_setup":
                self._log_event("the cloud has no bin for this device; waiting for setup in the dashboard")
            while len(self.queue) > 1:
                self.queue.popleft()
            self.failures = 0
            self.retry_at = time.monotonic() + self.settings.setup_check_seconds
            self._set_uplink("awaiting_setup", AWAITING_SETUP)
        elif error.status in (400, 413, 422) and not batch:
            # the empty batch that asks whether the cloud takes readings was refused itself
            self._back_off("rejected", f"The cloud refused an empty batch ({error.status}: {error.detail}).")
        elif error.status in (400, 413, 422):
            # resending the same batch can never work, so drop it rather than wedge the queue
            last_sent = batch[-1][0]
            while self.queue and self.queue[0][0] <= last_sent:
                self.queue.popleft()
            self.uplink["dropped_total"] += len(batch)
            log.error("cloud rejected a batch of %d readings: %s", len(batch), error)
            self._set_uplink("rejected", f"The cloud rejected {len(batch)} readings ({error.status}: "
                                         f"{error.detail}); they were dropped.")
        else:
            self._back_off("error", f"The cloud returned {error.status}: {error.detail}.")

    # -------------------------------------------------------------- status ---

    def status(self):
        with self.lock:
            creds = self.credentials
            pairing = {"state": self._pairing_state()}
            if creds:
                pairing.update({
                    "device_id": creds.device_id,
                    "paired_at": creds.paired_at,
                    "cloud_api_url": creds.cloud_api_url,
                    "api_key_hint": "••••" + creds.api_key[-4:],
                })
            retry_in = max(0, round(self.retry_at - time.monotonic()))
            return {
                "device": {
                    "uid": self.store.device_uid,
                    "model": self.settings.device_model,
                    "firmware_version": self.settings.firmware_version,
                },
                "pairing": pairing,
                "cloud": {
                    "api_url": self.settings.cloud_api_url,
                    "pairing_url": self.settings.cloud_url(self.settings.pairing_path),
                    "records_url": self.settings.cloud_url(self.settings.records_path),
                    "paused": self.uploads_paused,
                    "queued": len(self.queue),
                    "retry_in_seconds": retry_in,
                    **self.uplink,
                },
                "sampling": {
                    "reading_interval_seconds": self.settings.reading_interval_seconds,
                    "time_scale": self.settings.time_scale,
                },
                "backfill": {
                    "max_days": self.max_backfill_days(),
                    "step_minutes": BACKFILL_STEP_MINUTES,
                    "blocked": self._backfill_blocker(),
                },
                "start": {
                    "history_days": self.start_point["history_days"],
                    "stage": self.start_point["stage"],
                    "progress": self.start_point["progress"],
                    "max_progress": MAX_START_PROGRESS,
                    "pending": self.store.history_pending,
                    "preview": self.start_preview,
                    "last_batch": self.last_batch,
                },
                "pile": self.model.summary(),
                "latest": self.latest,
                "history": list(self.history),
                "events": list(self.events),
            }
