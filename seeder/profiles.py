"""The built-in profiles. A profile answers one question, how much power does this device draw at this moment.

To add a profile, write a class with a `sample(self, ctx)` method that returns a Reading, and register it with the decorator
`@profile("name")` in a file of the plugins folder. A device then names it in its `profile` setting and passes its own `params`.
"""

import datetime
import random
import zlib
from dataclasses import dataclass

from seeder.registry import profile

DAYS = {"mon-fri": range(0, 5), "mon-sat": range(0, 6), "daily": range(0, 7)}


@dataclass
class Reading:
    """What a device measures at one moment. Only the power is needed, and a field left as None is not sent."""

    power: float
    pf: float | None = None
    condition: int | None = None


@dataclass
class Context:
    """What a profile knows about the moment of the sample"""

    t: int
    local: datetime.datetime
    step: float
    rng: random.Random

    @property
    def hour(self):
        return self.local.hour + self.local.minute / 60 + self.local.second / 3600


class Profile:
    """The base class. A profile gets its params once and answers sample() for every moment."""

    def __init__(self, params, rng):
        self.params = params
        self.rng = rng

    def number(self, key, default):
        return float(self.params.get(key, default))

    def noisy(self, watts, noise):
        return max(0.0, watts * (1 + self.rng.gauss(0, noise)))

    def sample(self, ctx):
        raise NotImplementedError


def _clock(text):
    hours, minutes = text.split(":")
    return int(hours) + int(minutes) / 60


@profile("constant")
class Constant(Profile):
    """A device that draws about the same all day, such as a server or a light that stays on"""

    def sample(self, ctx):
        return Reading(self.noisy(self.number("watts", 100), self.number("noise", 0.03)), self.params.get("pf"))


@profile("scheduled")
class Scheduled(Profile):
    """A device that works in the work hours and idles at the standby power outside them.

    Params are on_watts, standby_watts, start, end, days (mon-fri, mon-sat or daily), noise, pf, and surge_probability and
    surge_factor for a short surge now and then. A device that never rests, such as a machine that is left on at night, can
    set standby_watts to a high number, and that is the waste that the tips find.
    """

    def _working(self, ctx):
        days = DAYS[self.params.get("days", "mon-sat")]
        start, end = _clock(self.params.get("start", "08:00")), _clock(self.params.get("end", "17:00"))
        return ctx.local.weekday() in days and start <= ctx.hour < end

    def sample(self, ctx):
        if not self._working(ctx):
            return Reading(self.noisy(self.number("standby_watts", 3), 0.1), None, 1)
        watts = self.noisy(self.number("on_watts", 200), self.number("noise", 0.06))
        if self.rng.random() < self.number("surge_probability", 0):
            watts *= self.number("surge_factor", 2.5)
        return Reading(watts, self.params.get("pf"))


@profile("cycling")
class Cycling(Profile):
    """A compressor, such as a refrigerator, that runs for a part of every period and rests for the rest"""

    def sample(self, ctx):
        period = self.number("period_seconds", 1800)
        # a phase from the name of the device, so two devices with the same period do not switch at the same second
        phase = zlib.crc32(str(self.params.get("phase_key", "")).encode()) % int(period)
        on = ((ctx.t + phase) % period) < period * self.number("duty", 0.4)
        watts = self.number("on_watts", 120) if on else self.number("off_watts", 2)
        return Reading(self.noisy(watts, 0.03), self.params.get("pf") if on else None)


@profile("motor")
class Motor(Scheduled):
    """A scheduled device with a power factor, which drops after a date to show a motor that wears out.

    Params are the ones of scheduled, and pf, pf_degraded and degrade_after as a date in the form 2026-11-30.
    """

    def sample(self, ctx):
        reading = super().sample(ctx)
        if reading.condition == 1:
            return reading
        after = self.params.get("degrade_after")
        worn = bool(after) and ctx.local.date() >= datetime.date.fromisoformat(after)
        pf = self.number("pf_degraded", 0.5) if worn else self.number("pf", 0.88)
        reading.pf = min(1.0, max(0.1, pf + self.rng.gauss(0, 0.02)))
        return reading
