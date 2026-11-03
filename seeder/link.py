"""The link of one simulated gateway to the device routes of the API"""

import time

from seeder.client import ApiError, RateLimited


class KeyRejected(Exception):
    """The API does not know the key of the gateway, so it has to enroll again"""


class BatchRejected(ApiError):
    """The API refuses the batch itself (400, 413, 415 or 422), so sending the same batch again can never work"""


class GatewayLink:
    """Builds numbered batches and sends them with the key of the gateway. The sequence number is kept in the state."""

    def __init__(self, client, state_gateway):
        self.client = client
        self.st = state_gateway

    def build(self, nodes, results=None, now=None):
        """Makes the next batch. It is sent again byte for byte until the API acknowledges it, as the firmware guide says."""
        payload = {"seq": self.st.get("seq", 0) + 1, "sentAt": int(now or time.time()), "nodes": nodes}
        if results:
            payload["results"] = results
        return payload

    def post(self, payload):
        """Sends one batch and returns the answer. A 409 with expectedSeq renumbers the batch and sends it again."""
        for _ in range(3):
            status, headers, body = self.client.request("POST", "/device/v1/readings", payload, bearer=self.st["key"], app=False, retry=True)
            if status == 200:
                self.st["seq"] = payload["seq"]
                return body
            if status == 409 and "expectedSeq" in body:
                payload["seq"] = int(body["expectedSeq"])
                self.st["seq"] = payload["seq"] - 1
                continue
            if status == 401:
                raise KeyRejected()
            if status == 429:
                raise RateLimited(status, body, "POST /device/v1/readings")
            if status in (400, 413, 415, 422):
                raise BatchRejected(status, body, "POST /device/v1/readings")
            raise ApiError(status, body, "POST /device/v1/readings")
        raise ApiError(409, {"code": "sequence_gap"}, "POST /device/v1/readings")

    def send(self, nodes, results=None, now=None):
        """Builds and sends a batch in one step, for a batch that is not kept when it fails, such as the first reading of a pairing"""
        return self.post(self.build(nodes, results, now))
