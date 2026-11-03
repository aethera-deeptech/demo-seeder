"""Loads and checks the TOML configuration of the seeder"""

import datetime
import os
import re
import tomllib
import zoneinfo
from dataclasses import dataclass, field

NODE_ID = re.compile(r"^[A-Za-z0-9:_-]{6,32}$")
HARDWARE_ID = re.compile(r"^[A-Za-z0-9:_-]{6,64}$")
LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]", "host.docker.internal")
SCENARIO_MODES = ("off", "factor", "add")
KINDS = ("plug", "clamp")
MAX_NODES_PER_BATCH = 16
MAX_SAMPLES_PER_BATCH = 5000


class ConfigError(Exception):
    """The configuration is wrong, and the message says where"""


@dataclass
class Device:
    node_id: str
    kind: str
    name: str
    room: str
    profile: str
    params: dict = field(default_factory=dict)


@dataclass
class Gateway:
    name: str
    hardware_id: str
    firmware: str
    devices: list
    adopt: bool = False


@dataclass
class Scenario:
    """A change of the power of some devices for a time, such as a power cut or a day that the business is closed"""

    name: str
    mode: str
    factor: float
    watts: float
    devices: list
    start: str | None
    end: str | None
    days: str | None
    from_hour: float
    to_hour: float


@dataclass
class Account:
    name: str
    email: str
    password: str
    business_name: str
    verifier: str
    verifier_options: dict
    create: bool
    gateways: list

    @property
    def rooms(self):
        """The rooms that the devices need, in the order they are first used"""
        names = []
        for gateway in self.gateways:
            for device in gateway.devices:
                if device.room not in names:
                    names.append(device.room)
        return names


@dataclass
class Config:
    base_url: str
    origin: str
    user_agent: str
    interval: int
    sample_period: int
    state_file: str
    utc_offset_hours: float
    plugins_dir: str
    seed: int | None
    accounts: list
    timezone: str | None = None
    scenarios: list = field(default_factory=list)


def _text(table, key, where, default=None, limit=80):
    value = table.get(key, default)
    if not isinstance(value, str) or not value or len(value) > limit:
        raise ConfigError(f"{where}.{key} must be a text of 1 to {limit} characters")
    return value


def _device(raw, where):
    kind = _text(raw, "kind", where, "plug")
    if kind not in KINDS:
        raise ConfigError(f"{where}.kind must be plug or clamp")
    node_id = _text(raw, "node_id", where, limit=32)
    if not NODE_ID.match(node_id):
        raise ConfigError(f"{where}.node_id must be 6 to 32 characters from A-Z a-z 0-9 : _ -")
    params = raw.get("params", {})
    if not isinstance(params, dict):
        raise ConfigError(f"{where}.params must be a table")
    return Device(node_id, kind, _text(raw, "name", where, limit=40), _text(raw, "room", where, limit=40),
                  _text(raw, "profile", where, limit=40), params)


def _gateway(raw, where):
    hardware_id = _text(raw, "hardware_id", where, limit=64)
    if not HARDWARE_ID.match(hardware_id):
        raise ConfigError(f"{where}.hardware_id must be 6 to 64 characters from A-Z a-z 0-9 : _ -")
    devices = [_device(d, f"{where}.devices[{n}]") for n, d in enumerate(raw.get("devices", []))]
    if not devices:
        raise ConfigError(f"{where} needs at least one device")
    if len(devices) > MAX_NODES_PER_BATCH:
        raise ConfigError(f"{where} has more than {MAX_NODES_PER_BATCH} devices, so split them over two gateways")
    return Gateway(_text(raw, "name", where, limit=40), hardware_id, _text(raw, "firmware", where, "demo-seeder", 32), devices,
                   bool(raw.get("adopt", False)))


def _account(raw, where):
    password = raw.get("password")
    if raw.get("password_env"):
        password = os.environ.get(raw["password_env"])
        if not password:
            raise ConfigError(f"{where}.password_env names {raw['password_env']}, which is not set")
    if not isinstance(password, str) or len(password) < 8:
        raise ConfigError(f"{where} needs password_env or password, with at least 8 characters")
    gateways = [_gateway(g, f"{where}.gateways[{n}]") for n, g in enumerate(raw.get("gateways", []))]
    if not gateways:
        raise ConfigError(f"{where} needs at least one gateway")
    options = raw.get("verifier_options", {})
    return Account(_text(raw, "name", where, limit=40), _text(raw, "email", where, limit=254).lower(), password,
                   _text(raw, "business_name", where, "Demo", 80), _text(raw, "verifier", where, "none", 40), options,
                   bool(raw.get("create", True)), gateways)


def _scenario(raw, where):
    mode = _text(raw, "mode", where, "off", 10)
    if mode not in SCENARIO_MODES:
        raise ConfigError(f"{where}.mode must be one of {', '.join(SCENARIO_MODES)}")
    days = raw.get("days")
    if days is not None and days not in ("mon-fri", "mon-sat", "daily", "sat-sun"):
        raise ConfigError(f"{where}.days must be mon-fri, mon-sat, sat-sun or daily")
    devices = raw.get("devices", ["*"])
    if not isinstance(devices, list) or not all(isinstance(d, str) for d in devices):
        raise ConfigError(f"{where}.devices must be a list of node ids, or [\"*\"] for every device")
    for key in ("start", "end"):
        if raw.get(key) is not None:
            try:
                datetime.datetime.fromisoformat(raw[key])
            except (TypeError, ValueError):
                raise ConfigError(f"{where}.{key} must be a local time such as 2026-11-05T09:00") from None
    return Scenario(_text(raw, "name", where, "scenario", 40), mode, float(raw.get("factor", 0.0)), float(raw.get("watts", 0.0)),
                    devices, raw.get("start"), raw.get("end"), days, float(raw.get("from_hour", 0)), float(raw.get("to_hour", 24)))


def _coerce(text):
    """Reads a value of an environment variable or of --set as a TOML value, and as a plain text when it is none"""
    try:
        return tomllib.loads(f"v = {text}")["v"]
    except tomllib.TOMLDecodeError:
        return text


def apply_overrides(raw, env=None, sets=()):
    """Layers the settings of [api] and [run], from the lowest to the highest, which are the file, the environment and --set.

    The environment variable of api.base_url is SEEDER_API_BASE_URL, and --set takes api.base_url=https://example.com.
    """
    env = os.environ if env is None else env
    for table in ("api", "run"):
        section = raw.setdefault(table, {})
        prefix = f"SEEDER_{table.upper()}_"
        for name, value in env.items():
            if name.startswith(prefix) and value != "":
                section[name[len(prefix):].lower()] = _coerce(value)
    for item in sets:
        key, sep, value = item.partition("=")
        table, dot, setting = key.partition(".")
        if not sep or not dot or table not in ("api", "run") or not setting:
            raise ConfigError(f"--set needs the form api.setting=value or run.setting=value, not {item}")
        raw.setdefault(table, {})[setting] = _coerce(value)
    return raw


def _check_url(base, allow_insecure):
    host = base.split("://", 1)[1].split("/", 1)[0].rsplit("@", 1)[-1]
    host = host if host.startswith("[") else host.split(":", 1)[0]
    if base.startswith("http://") and not allow_insecure and host not in LOCAL_HOSTS:
        raise ConfigError("api.base_url uses http for a host that is not local, which would send the password and the keys in clear text. "
                          "Use https, or set api.allow_insecure = true if you accept that")


def load(path, env=None, sets=()):
    """Reads the file and returns a checked Config, or raises ConfigError"""
    with open(path, "rb") as handle:
        raw = tomllib.load(handle)
    apply_overrides(raw, env, sets)
    api = raw.get("api", {})
    run = raw.get("run", {})
    base = _text(api, "base_url", "api", limit=200).rstrip("/")
    if not base.startswith(("https://", "http://")):
        raise ConfigError("api.base_url must start with https:// or http://")
    _check_url(base, bool(api.get("allow_insecure", False)))
    interval = int(run.get("interval_seconds", 30))
    period = int(run.get("sample_period_seconds", 10))
    if not 10 <= interval <= 300:
        raise ConfigError("run.interval_seconds must be 10 to 300, because a gateway may send 600 batches in an hour")
    if not 1 <= period <= interval:
        raise ConfigError("run.sample_period_seconds must be 1 or more and not above the interval")
    accounts = [_account(a, f"accounts[{n}]") for n, a in enumerate(raw.get("accounts", []))]
    if not accounts:
        raise ConfigError("the file needs at least one [[accounts]] table")
    timezone = run.get("timezone")
    if timezone:
        try:
            zoneinfo.ZoneInfo(timezone)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            raise ConfigError(f"run.timezone {timezone} is not a time zone that this system knows") from None
    seen, names = set(), set()
    for account in accounts:
        for gateway in account.gateways:
            if len(gateway.devices) * (interval // period + 1) > MAX_SAMPLES_PER_BATCH:
                raise ConfigError(f"gateway {gateway.name} would send more than {MAX_SAMPLES_PER_BATCH} samples in a batch")
            for device in gateway.devices:
                key = (gateway.hardware_id, device.node_id)
                if key in seen:
                    raise ConfigError(f"node {device.node_id} of {gateway.hardware_id} is listed twice")
                seen.add(key)
                # a device is matched by its name when the seeder starts again, so a name has to be unique in an account
                if (account.name, device.name.lower()) in names:
                    raise ConfigError(f"the device name {device.name} is used twice in the account {account.name}")
                names.add((account.name, device.name.lower()))
    seed = run.get("seed")
    return Config(base, _text(api, "origin", "api", "http://localhost:5173", 200),
                  _text(api, "user_agent", "api", "aethera-demo-seeder", 100),
                  interval, period, _text(run, "state_file", "run", "state.json", 300), float(run.get("utc_offset_hours", 7)),
                  _text(run, "plugins_dir", "run", "plugins", 300), None if seed is None else int(seed), accounts, timezone or None,
                  [_scenario(sc, f"scenarios[{n}]") for n, sc in enumerate(raw.get("scenarios", []))])
