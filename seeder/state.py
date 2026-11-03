"""The state that has to survive a restart, which is the key and the sequence number of every gateway"""

import fcntl
import json
import os
import tempfile

from seeder.log import log

VERSION = 1


class StateLockedError(Exception):
    """Another seeder holds the lock of this state file"""


class State:
    """A JSON file that is written whole and replaced in one step, so a stop in the middle never leaves half a file"""

    def __init__(self, path):
        self.path = path
        self.data = {"version": VERSION, "accounts": {}}
        self._lock = None
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as handle:
                    loaded = json.load(handle)
                if not isinstance(loaded, dict) or not isinstance(loaded.get("accounts", {}), dict):
                    raise ValueError("the file does not hold the state")
                self.data = loaded
                self.data.setdefault("version", VERSION)
            except (OSError, ValueError) as err:
                # provisioning is safe to repeat, so a state that cannot be read is moved aside and the seeder starts empty
                os.replace(path, path + ".corrupt")
                log("state_unreadable", path=path, moved_to=path + ".corrupt", error=str(err))

    def lock(self):
        """Takes an exclusive lock for as long as the process lives, so two seeders never change one state file"""
        folder = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(folder, exist_ok=True)
        self._lock = open(os.path.join(folder, ".seeder.lock"), "w", encoding="utf-8")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise StateLockedError(f"another seeder uses the state in {folder}") from None

    def gateway(self, account, hardware_id):
        """The dict of one gateway, which is made empty on first use and is changed in place"""
        accounts = self.data.setdefault("accounts", {})
        return accounts.setdefault(account, {}).setdefault(hardware_id, {"devices": {}})

    def heartbeat(self):
        """Touches a file after every cycle, so a health check can see that the loop still turns"""
        folder = os.path.dirname(os.path.abspath(self.path))
        with open(os.path.join(folder, "heartbeat"), "w", encoding="utf-8") as handle:
            handle.write("ok")

    def save(self):
        folder = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".state-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.data, handle, indent=1, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
