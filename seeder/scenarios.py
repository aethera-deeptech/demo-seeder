"""Scenarios change the power of some devices for a time, so one rule covers a power cut or a closed day for many devices.

A scenario is a `[[scenarios]]` table in the configuration. It applies when the local time is inside its window, which is either
the pair `start` and `end` (a local date and time) or a recurring window with `days`, `from_hour` and `to_hour`. Its mode is
`off` (no power), `factor` (the power times `factor`) or `add` (`watts` more). `devices` names node ids, and `["*"]` means all.
"""

import datetime

DAYS = {"mon-fri": range(0, 5), "mon-sat": range(0, 6), "sat-sun": range(5, 7), "daily": range(0, 7)}


def _active(scenario, local):
    if scenario.start and local < datetime.datetime.fromisoformat(scenario.start):
        return False
    if scenario.end and local >= datetime.datetime.fromisoformat(scenario.end):
        return False
    if scenario.days and local.weekday() not in DAYS[scenario.days]:
        return False
    hour = local.hour + local.minute / 60
    return scenario.from_hour <= hour < scenario.to_hour


def apply(scenarios, node_id, local, reading):
    """Changes the reading of a device in place when a scenario applies, and returns it"""
    for scenario in scenarios:
        if ("*" not in scenario.devices and node_id not in scenario.devices) or not _active(scenario, local):
            continue
        if scenario.mode == "off":
            reading.power, reading.pf, reading.condition = 0.0, None, 1
        elif scenario.mode == "factor":
            reading.power *= scenario.factor
        else:
            reading.power += scenario.watts
    return reading
