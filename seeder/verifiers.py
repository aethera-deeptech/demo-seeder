"""Ways to get the token of a verification mail. A new account has to verify its email before it can sign in."""

import json
import shlex
import subprocess
import time
from urllib.parse import parse_qs, urlsplit

from seeder.registry import verifier


class VerifyError(Exception):
    pass


@verifier("none")
def none(account, options, client):
    """The account has to exist and be verified already, so there is nothing to read"""
    raise VerifyError(f"{account.email} is not verified and the verifier is none, so verify it by hand or choose another verifier")


@verifier("command")
def command(account, options, client):
    """Runs a command that prints the logs of an API that has no mail server, and finds the link of this account in them.

    The option `command` is the command, for example `docker compose logs --no-color --no-log-prefix api`. The API logs a line
    with the text "verification email" and the fields `to` and `link` when SMTP_HOST is empty, which is only a development stack.
    """
    argv = shlex.split(options.get("command", ""))
    if not argv:
        raise VerifyError("the verifier command needs the option command")
    for _ in range(int(options.get("tries", 20))):
        out = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=60).stdout
        for line in reversed(out.splitlines()):
            start = line.find("{")
            if start < 0 or "verification email" not in line:
                continue
            try:
                entry = json.loads(line[start:])
            except ValueError:
                continue
            if entry.get("to") == account.email:
                token = (parse_qs(urlsplit(entry.get("link", "")).query).get("token") or [""])[0]
                if token:
                    return token
        time.sleep(1)
    raise VerifyError("the verification link did not reach the log")
