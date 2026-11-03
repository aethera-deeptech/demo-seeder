"""Gets an account, its rooms, its gateways and its devices to the state that the configuration describes.

Every step looks at what exists first, so running it again changes nothing. A restart of the seeder is therefore safe.
"""

import hashlib
import secrets
import time

from seeder.client import ApiError
from seeder.link import GatewayLink
from seeder.log import log
from seeder import verifiers  # noqa: F401  (registers the built-in verifiers)
from seeder.registry import VERIFIERS


class AccountError(Exception):
    """A problem that waiting does not fix, such as a wrong password, which the person who runs the seeder has to correct"""


def _cookie(headers):
    return headers.get("Set-Cookie", "").split(";", 1)[0]


def sign_in(client, account):
    """Signs in and returns the session cookie. A missing account is made, and an unverified one is verified, when it is allowed."""
    body = {"email": account.email, "password": account.password}
    status, headers, answer = client.request("POST", "/v1/auth/login", body)
    if status == 200:
        return _cookie(headers)
    code = answer.get("code", "")
    if status == 401 and account.create:
        status, headers, answer = client.request("POST", "/v1/auth/register",
                                                 {"businessName": account.business_name, "email": account.email, "password": account.password})
        if status == 409:
            raise AccountError(f"the account {account.email} exists and the password in the configuration is not its password")
        if status != 201:
            raise ApiError(status, answer, "POST /v1/auth/register")
        log("account_registered", account=account.name)
    elif status == 401:
        raise AccountError(f"the login of {account.email} failed and create is false, so check the email and the password")
    elif status == 403 and code == "email_not_verified":
        client.request("POST", "/v1/auth/resend-verification", {"email": account.email})
    else:
        raise ApiError(status, answer, "POST /v1/auth/login")
    token = VERIFIERS[account.verifier](account, account.verifier_options, client)
    status, headers, answer = client.request("POST", "/v1/auth/verify-email", {"token": token})
    if status != 200:
        raise ApiError(status, answer, "POST /v1/auth/verify-email")
    log("account_verified", account=account.name)
    return _cookie(headers)


def ensure_rooms(client, cookie, names):
    """Returns the id of each room by name and makes the rooms that are missing"""
    items = client.call("GET", "/v1/rooms", 200, cookie=cookie)["items"]
    rooms = {room["name"].lower(): room["id"] for room in items}
    for name in names:
        if name.lower() not in rooms:
            rooms[name.lower()] = client.call("POST", "/v1/rooms", 201, cookie=cookie, body={"name": name})["id"]
            log("room_made", room=name)
    return rooms


def ensure_gateway(client, cookie, gateway, state_gateway):
    """Enrolls the gateway with a new key and claims it, unless the state already holds a key for it.

    A gateway of the same business that is claimed again keeps its readings and gets the new key, so the hardware id of a gateway
    that exists already can be named here to take it over.
    """
    if state_gateway.get("key"):
        return
    if not gateway.adopt:
        names = {g["name"].lower() for g in client.call("GET", "/v1/gateways", 200, cookie=cookie)["items"]}
        if gateway.name.lower() in names:
            raise AccountError(f"the account has a gateway named {gateway.name} already, and the seeder has no key for it. "
                               "Set adopt = true on this gateway if it is a demo gateway that the seeder may take over, "
                               "which replaces its key, or give it another name")
    key = secrets.token_urlsafe(32)
    enrolled = client.call("POST", "/device/v1/enroll", 201, app=False, body={
        "hardwareId": gateway.hardware_id, "firmware": gateway.firmware, "keyHash": hashlib.sha256(key.encode()).hexdigest()})
    client.call("POST", "/v1/gateways", 201, cookie=cookie, body={"claimCode": enrolled["claimCode"], "name": gateway.name})
    state_gateway.update({"key": key, "seq": 0})
    log("gateway_claimed", gateway=gateway.name, hardware_id=gateway.hardware_id)


def ensure_devices(client, cookie, gateway, state_gateway, rooms, first_sample, wait=3.0, tries=8):
    """Pairs every device that is not paired yet. A device with the name of an existing one counts as paired.

    first_sample(device) returns the node dict of a first reading, which a pairing needs from the node before it connects.
    """
    link = GatewayLink(client, state_gateway)
    existing = {item["name"].lower() for item in client.call("GET", "/v1/devices", 200, cookie=cookie)["items"]}
    for device in gateway.devices:
        mine = state_gateway["devices"].setdefault(device.node_id, {})
        if mine.get("paired"):
            continue
        if device.name.lower() in existing:
            mine["paired"] = True
            continue
        pairing = client.call("POST", "/v1/pairings", 201, cookie=cookie,
                              body={"kind": device.kind, "name": device.name, "roomId": rooms[device.room.lower()]})["id"]
        for _ in range(tries):
            link.send([first_sample(device)])
            status = client.call("GET", f"/v1/pairings/{pairing}", 200, cookie=cookie)
            if status.get("status") == "connected":
                mine["paired"] = True
                log("device_paired", device=device.name, node_id=device.node_id)
                break
            time.sleep(wait)
        else:
            # a search that is left running blocks the next pairing of the business for minutes, so it is ended
            client.request("DELETE", f"/v1/pairings/{pairing}", cookie=cookie)
            raise ApiError(0, {"code": "pairing_not_connected"}, f"pairing of {device.name}")
