"""Runs the simulated gateways, which send a batch of samples to the API every interval"""

import datetime
import math
import random
import signal
import time
import zoneinfo

from seeder import profiles, scenarios
from seeder.client import ApiError, Client, RateLimitedError
from seeder.link import BatchRejectedError, GatewayLink, KeyRejectedError
from seeder.log import log
from seeder.provision import AccountError, ensure_devices, ensure_gateway, ensure_rooms, sign_in
from seeder.registry import PROFILES, load_plugins
from seeder.state import State

MAX_SAMPLES_PER_NODE = 1000
MAX_SAMPLES_PER_BATCH = 5000
MAX_BACKLOG_SECONDS = 23 * 3600
# the most that the API accepts for each field of a sample, and a value outside it is dropped by the API
LIMITS = {"p": (0, 60000), "v": (0, 500), "i": (0, 200), "f": (0, 100), "pf": (0, 1)}


class DeviceRuntime:
    """One simulated device, with its profile, its energy counter and the state of its relay"""

    def __init__(self, config, state_device, cfg):
        name = config.profile
        if name not in PROFILES:
            raise ValueError(f"device {config.node_id} names the profile {name}, which is not known. Known profiles are {sorted(PROFILES)}")
        seed = None if cfg.seed is None else f"{cfg.seed}:{config.node_id}"
        self.rng = random.Random(seed)
        self.config = config
        self.cfg = cfg
        self.profile = PROFILES[name]({"phase_key": config.node_id, **config.params}, self.rng)
        self.st = state_device
        self.st.setdefault("energy", 0.0)
        self.st.setdefault("relay_on", True)
        self.zone = zoneinfo.ZoneInfo(cfg.timezone) if cfg.timezone else None
        self.offset = datetime.timedelta(hours=cfg.utc_offset_hours)
        self.warned = set()

    def local(self, t):
        if self.zone:
            return datetime.datetime.fromtimestamp(t, tz=self.zone).replace(tzinfo=None)
        return datetime.datetime.fromtimestamp(t, tz=datetime.UTC).replace(tzinfo=None) + self.offset

    def _clamp(self, key, value):
        low, high = LIMITS[key]
        if low <= value <= high:
            return value
        if key not in self.warned:
            self.warned.add(key)
            log("value_clamped", device=self.config.node_id, field=key, value=round(value, 2), low=low, high=high)
        return min(high, max(low, value))

    def sample(self, t, step):
        """Returns the sample dict for the second t, and adds its energy to the counter"""
        local = self.local(t)
        reading = self.profile.sample(profiles.Context(t, local, step, self.rng))
        scenarios.apply(self.cfg.scenarios, self.config.node_id, local, reading)
        power = round(self._clamp("p", reading.power if self.st["relay_on"] or self.config.kind != "plug" else 0.0), 1)
        self.st["energy"] += power * step / 3_600_000
        volts = self._clamp("v", 220 + self.rng.gauss(0, 1.5))
        pf = None if reading.pf is None else self._clamp("pf", reading.pf)
        sample = {"t": t, "p": power, "v": round(volts, 1), "i": round(self._clamp("i", power / (volts * (pf or 0.95))), 2),
                  "e": round(self.st["energy"], 4), "f": round(self._clamp("f", 50 + self.rng.gauss(0, 0.04)), 2)}
        if pf is not None and power > 0:
            sample["pf"] = round(pf, 2)
        if reading.condition is not None:
            sample["a"] = reading.condition
        if self.config.kind == "plug":
            sample["r"] = 1 if self.st["relay_on"] else 0
        return sample

    def node(self, samples):
        return {"nodeId": self.config.node_id, "kind": self.config.kind, "samples": samples}


def validate(cfg):
    """Builds every device and takes one sample of it, so a wrong profile name or a wrong param stops the start and not a cycle"""
    load_plugins(cfg.plugins_dir)
    now = int(time.time())
    for account in cfg.accounts:
        for gateway in account.gateways:
            for device in gateway.devices:
                try:
                    runtime = DeviceRuntime(device, {}, cfg)
                    runtime.sample(now, cfg.sample_period)
                except Exception as err:  # noqa: BLE001  (any error of a profile is a wrong setting for the user to fix)
                    raise ValueError(f"device {device.node_id} of gateway {gateway.name} does not work with its profile {device.profile}, "
                                     f"{type(err).__name__}: {err}") from err


class GatewayRunner:
    """One simulated gateway. Each cycle sends the samples since the last batch."""

    def __init__(self, cfg, account, gateway, client, state):
        self.cfg, self.account, self.gateway, self.client = cfg, account, gateway, client
        self.st = state.gateway(account.name, gateway.hardware_id)
        self.devices = [DeviceRuntime(d, self.st["devices"].setdefault(d.node_id, {}), cfg) for d in gateway.devices]
        self.link = GatewayLink(client, self.st)
        self.results = []

    def first_sample(self, device):
        runtime = next(d for d in self.devices if d.config.node_id == device.node_id)
        return runtime.node([runtime.sample(int(time.time()), self.cfg.sample_period)])

    def cycle(self, now=None):
        """Sends the batch that waits for an acknowledgement, if there is one, and then the samples since the last batch.

        The batch is kept in the state until the API acknowledges it and is sent again as it is, so a lost answer never loses
        samples and never counts the energy twice. Returns the number of samples that were sent.
        """
        now = int(now or time.time())
        pending = self.st.get("pending")
        if pending:
            if not self._deliver(pending):
                return 0
        last = self.st.get("last_t") or now - self.cfg.interval
        if last > now:
            last = now - self.cfg.interval
        last = max(last, now - MAX_BACKLOG_SECONDS)
        span = now - last
        if span <= 0:
            return 0
        per_node = min(MAX_SAMPLES_PER_NODE, MAX_SAMPLES_PER_BATCH // len(self.devices))
        step = max(self.cfg.sample_period, math.ceil(span / per_node))
        times = list(range(last + step, now + 1, step))
        if not times:
            return 0
        nodes = [d.node([d.sample(t, step) for t in times]) for d in self.devices]
        payload = self.link.build(nodes, self.results, now)
        self.results = []
        self.st["pending"] = payload
        self.st["last_t"] = times[-1]
        return len(times) * len(nodes) if self._deliver(payload) else 0

    def _deliver(self, payload):
        """Sends a batch and keeps it in the state until it is acknowledged. A batch that the API refuses for good is dropped."""
        try:
            answer = self.link.post(payload)
        except BatchRejectedError as err:
            log("batch_dropped", gateway=self.gateway.name, error=str(err))
            self.st.pop("pending", None)
            return False
        self.st.pop("pending", None)
        self._apply(answer.get("commands", []), answer.get("serverTime"))
        return True

    def _apply(self, commands, server_time):
        """Switches the relay of a plug for each command, and reports the result in the next batch. A command comes again until then."""
        done = self.st.setdefault("done_ids", [])
        by_node = {d.config.node_id: d for d in self.devices}
        now = _parse(server_time) or datetime.datetime.now(datetime.UTC)
        for command in commands:
            device = by_node.get(command.get("nodeId"))
            ok = bool(device and device.config.kind == "plug")
            expired = (_parse(command.get("expiresAt")) or now) <= now
            if command["id"] not in done:
                if ok and not expired:
                    device.st["relay_on"] = command["action"] == "on"
                    log("relay_switched", device=device.config.name, action=command["action"])
                done.append(command["id"])
            self.results.append({"id": command["id"], "ok": ok and not expired})
        del done[:-100]


def _parse(text):
    if not text:
        return None
    try:
        return datetime.datetime.fromisoformat(text)
    except ValueError:
        return None


class Seeder:
    def __init__(self, cfg):
        self.cfg = cfg
        self.client = Client(cfg.base_url, cfg.origin, cfg.user_agent)
        self.state = State(cfg.state_file)
        self.runners = []
        self.stop = False

    def provision(self):
        """Signs in each account and makes what is missing, then builds the runner of every gateway"""
        validate(self.cfg)
        self.runners = []
        for account in self.cfg.accounts:
            cookie = sign_in(self.client, account)
            rooms = ensure_rooms(self.client, cookie, account.rooms)
            for gateway in account.gateways:
                stored = self.state.gateway(account.name, gateway.hardware_id)
                ensure_gateway(self.client, cookie, gateway, stored)
                self.state.save()
                runner = GatewayRunner(self.cfg, account, gateway, self.client, self.state)
                try:
                    ensure_devices(self.client, cookie, gateway, stored, rooms, runner.first_sample)
                except KeyRejectedError:
                    log("key_rejected", gateway=gateway.name)
                    stored.pop("key", None)
                    ensure_gateway(self.client, cookie, gateway, stored)
                    ensure_devices(self.client, cookie, gateway, stored, rooms, runner.first_sample)
                self.state.save()
                self.runners.append(runner)

    def provision_with_retry(self):
        """Provisions, and tries again with a growing pause when the API is down or limits the calls. A wrong account stops it."""
        pause = 5
        while not self.stop:
            try:
                return self.provision()
            except AccountError:
                raise
            except RateLimitedError as err:
                wait = min(900, max(err.retry_after, 1))
                log("provision_rate_limited", retry_after=wait)
            except (ApiError, OSError, KeyRejectedError) as err:
                wait = pause
                pause = min(300, pause * 2)
                log("provision_failed", error=str(err), retry_in=wait)
            self._sleep(wait)

    def once(self):
        """Runs one cycle of every gateway. A failure of one gateway is logged and does not stop the others."""
        for runner in self.runners:
            name = runner.gateway.name
            try:
                sent = runner.cycle()
                log("batch_sent", gateway=name, samples=sent, seq=runner.st.get("seq"))
            except KeyRejectedError:
                log("key_rejected", gateway=name)
                runner.st.pop("key", None)
                self.state.save()
                self.provision_with_retry()
                break
            except RateLimitedError as err:
                log("rate_limited", gateway=name, retry_after=err.retry_after)
            except (ApiError, OSError) as err:
                log("batch_failed", gateway=name, error=str(err))
            except Exception as err:  # noqa: BLE001  (one gateway must never stop the others, and the loop logs the type)
                log("cycle_error", gateway=name, error=f"{type(err).__name__}: {err}")
            self.state.save()
        self.state.heartbeat()

    def _sleep(self, seconds):
        end = time.monotonic() + seconds
        while not self.stop and time.monotonic() < end:
            time.sleep(min(1.0, end - time.monotonic()))

    def run(self):
        """Provisions and then sends a batch of every gateway each interval, until it is told to stop"""
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "stop", True))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "stop", True))
        self.provision_with_retry()
        log("started", gateways=len(self.runners), interval=self.cfg.interval)
        while not self.stop:
            began = time.monotonic()
            self.once()
            self._sleep(max(1.0, self.cfg.interval - (time.monotonic() - began)))
        self.state.save()
        log("stopped")
