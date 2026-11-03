"""The command line, `python -m seeder <command>`"""

import argparse
import sys

from seeder import __version__, config
from seeder.log import log
from seeder.provision import AccountError
from seeder.registry import PROFILES, VERIFIERS, load_plugins
from seeder.runner import Seeder, validate
from seeder.state import StateLockedError


def main(argv=None):
    parser = argparse.ArgumentParser(prog="seeder", description="Keeps demo accounts of the Aethera backend alive")
    parser.add_argument("command", choices=["run", "once", "provision", "check", "plugins"],
                        help="run sends batches until stopped, once sends one cycle, provision only makes the accounts, "
                             "check reads the file")
    parser.add_argument("-c", "--config", default="config/demo.toml", help="the TOML file")
    parser.add_argument("--set", action="append", default=[], metavar="TABLE.KEY=VALUE",
                        help="overrides a setting of [api] or [run] for this run, such as --set run.interval_seconds=60. "
                             "The environment variable SEEDER_<TABLE>_<KEY> does the same, and --set wins")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        cfg = config.load(args.config, sets=args.set)
    except (OSError, config.ConfigError) as err:
        print(f"configuration error, {err}", file=sys.stderr)
        return 2
    if args.command == "check":
        try:
            validate(cfg)
        except ValueError as err:
            print(f"configuration error, {err}", file=sys.stderr)
            return 2
        print(f"the file is valid, with {sum(len(a.gateways) for a in cfg.accounts)} gateways in {len(cfg.accounts)} accounts")
        return 0
    if args.command == "plugins":
        load_plugins(cfg.plugins_dir)
        print("profiles", ", ".join(sorted(PROFILES)))
        print("verifiers", ", ".join(sorted(VERIFIERS)))
        return 0
    seeder = Seeder(cfg)
    try:
        seeder.state.lock()
        if args.command == "run":
            seeder.run()
            return 0
        seeder.provision()
        if args.command == "once":
            seeder.once()
    except (StateLockedError, AccountError, ValueError) as err:
        print(f"stopped, {err}", file=sys.stderr)
        return 1
    log("done", command=args.command)
    return 0


if __name__ == "__main__":
    sys.exit(main())
