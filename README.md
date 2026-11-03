# Aethera demo seeder

A small service that keeps the demo accounts of the [Aethera backend](https://github.com/aethera-deeptech/backend) alive. It acts like the gateways of a real business. Every interval it sends a batch of simulated readings to the API, so the devices of a demo account stay online and the dashboard always shows live numbers.

It uses only the standard library of Python 3.12 or newer, and it runs in a small Docker container.

## What it does

1. Signs in to each account in the configuration. A missing account is made, and an unverified one is verified, when the configuration allows it.
2. Makes the rooms, claims the gateways and pairs the devices that are missing. Every step looks at what exists first, so a restart changes nothing.
3. Sends a batch of samples for every gateway each interval, with a sequence number that survives a restart.
4. Switches the relay of a plug when the owner sends a command in the app, and reports the result like the firmware does.

## Quick start

```sh
cp config/demo.example.toml config/demo.toml
cp .env.example .env
# edit both files, then check the configuration
python3 -m seeder check -c config/demo.toml
docker compose up -d --build
docker compose logs -f seeder
```

The seeder writes one JSON object for each line of its log.

## The configuration

The file is TOML. [config/demo.example.toml](config/demo.example.toml) has every setting with a comment.

| Table | What it sets |
|:---|:---|
| `[api]` | The address of the API, the origin of the web app, the user agent and `allow_insecure` for http to a host that is not local |
| `[run]` | The interval, the time between two samples, the state file, the time zone (`timezone`, or `utc_offset_hours`), the plugins folder and an optional seed |
| `[[accounts]]` | The email, the password variable, the business name, the verifier and whether to make the account |
| `[[accounts.gateways]]` | The name and the hardware id of a simulated gateway, and `adopt` to take over a gateway that exists |
| `[[scenarios]]` | A power cut or a closed day for some devices, see below |
| `[[accounts.gateways.devices]]` | The node id, the kind (`plug` or `clamp`), the name, the room, the profile and its `params` |

Every setting of `[api]` and `[run]` can also be set without editing the file. The environment variable `SEEDER_<TABLE>_<KEY>` sets it, such as `SEEDER_RUN_INTERVAL_SECONDS=60`, and `--set run.interval_seconds=60` on the command line wins over both. The order from lowest to highest is the default, the file, the environment and `--set`.

Add an account, a gateway or a device by adding a table. A gateway can hold up to 16 devices, and a second gateway takes the rest.

To take over a gateway that already exists in a demo business, give it the hardware id and set `adopt = true`. A gateway that the same business claims again keeps its readings and gets a new key, which the seeder keeps in its state file. Without `adopt` the seeder refuses when the account already has a gateway with that name, so it never replaces the key of a real gateway by accident.

## Profiles

A profile answers one question, how much power does this device draw now.

| Profile | What it simulates | Main params |
|:---|:---|:---|
| `constant` | A device that draws about the same all day | `watts`, `noise`, `pf` |
| `scheduled` | A device that works in the work hours and idles outside them. A high `standby_watts` shows the waste that the tips find | `on_watts`, `standby_watts`, `start`, `end`, `days`, `noise`, `pf`, `surge_probability`, `surge_factor` |
| `cycling` | A compressor that runs for a part of every period | `on_watts`, `off_watts`, `period_seconds`, `duty` |
| `motor` | A scheduled device with a power factor that falls after a date, which makes the service raise a motor degradation | The params of `scheduled`, and `pf`, `pf_degraded`, `degrade_after` |

## Scenarios

A `[[scenarios]]` table changes the power of some devices for a time, so one rule covers many devices.

```toml
[[scenarios]]
name = "power cut"
mode = "off"                        # off, factor or add
devices = ["PLUG-DEMO-0001"]        # node ids, or ["*"] for all
start = "2026-11-05T09:00"          # local time, and a window may also use days, from_hour and to_hour
end = "2026-11-05T12:00"
```

The mode `factor` multiplies the power by `factor`, and `add` adds `watts`. A recurring window such as a closed Sunday uses `days = "sat-sun"` with no start and end.

## Extending it

Every `.py` file in the plugins folder is loaded when the seeder starts, so you add behavior without changing the code of the seeder.

- **A profile.** Write a class with a `sample(self, ctx)` method that returns a `Reading`, and register it with `@profile("name")`. The context has the time `t`, the local time `ctx.local`, the hour of the day `ctx.hour`, the step and a random generator. [plugins/example.py](plugins/example.py) is a complete example.
- **A verifier.** A function registered with `@verifier("name")` that gets the account, its `verifier_options` and the client, and returns the token of the verification link. The built-in `command` reads the link from the log of an API with no mail server, and `none` expects a verified account. A verifier that reads a mailbox or a mail provider fits here.

`python3 -m seeder plugins -c config/demo.toml` lists the profiles and the verifiers that are loaded.

## Running notes

- **Safe to repeat.** Provisioning looks at what exists first, and a batch stays in the state until the API acknowledges it, so a restart or a lost answer never loses samples and never counts the energy twice. A second seeder on the same state folder is refused by a lock.
- **State.** The file in `state_file` holds the key and the sequence number of every gateway, the energy counter of every device and the state of its relay. Keep it on a volume. If the file is lost, the seeder claims the gateways again and the API gives them new keys.
- **After an outage.** The seeder sends what it missed in one batch, up to 23 hours back, because the API takes no sample older than a day. Longer gaps are left empty.
- **Limits.** A gateway may send 600 batches in an hour, so the interval is 10 seconds or more. A 429 answer is logged and the seeder tries again at the next interval.
- **A rejected key.** When the API does not know the key of a gateway, the seeder drops it and enrolls the gateway again.
- **Health.** The loop touches `heartbeat` in the folder of the state file after every cycle, and the image health check fails when it is older than ten minutes.
- **Commands.** `run` sends batches until it is stopped. `once` sends one cycle, `provision` only makes the accounts and the devices, `check` reads the configuration, and `plugins` lists the plugins.

## Safety

The seeder writes data to the API that it is pointed at. Use it only on demo accounts, never on the account of a real business. It refuses plain http to a host that is not local, because the password and the gateway keys would travel in clear text. Keep the password in an environment variable and never in the configuration file. The state file holds gateway keys, so it is created with mode 600.

## Development

```sh
python3 -m unittest discover -s . -t .
```

The tests start a small fake of the API in the process, so they need no network and no database. CI runs the same tests, ruff and a build of the image.
