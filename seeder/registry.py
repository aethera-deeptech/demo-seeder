"""Finds the plugins. A profile makes the power of a device, a verifier reads the link of a verification mail."""

import importlib.util
import os

PROFILES = {}
VERIFIERS = {}


def profile(name):
    """Registers a class under a name that a device names in its `profile` setting"""

    def wrap(cls):
        PROFILES[name] = cls
        return cls

    return wrap


def verifier(name):
    """Registers a function that gets the account and its options and returns the token of the verification link"""

    def wrap(func):
        VERIFIERS[name] = func
        return func

    return wrap


def load_plugins(folder):
    """Imports every .py file of the folder, so a file that uses the decorators above adds its profiles and verifiers"""
    if not folder or not os.path.isdir(folder):
        return []
    loaded = []
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".py") or name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"seeder_plugin_{name[:-3]}", os.path.join(folder, name))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded.append(name)
    return loaded
