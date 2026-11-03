"""A small fake of the Aethera API with just the routes that the seeder calls, for the tests"""

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeApi:
    def __init__(self, password="demo-password-1"):
        self.password = password
        self.users = {}
        self.rooms = {}
        self.gateways = {}
        self.enrollments = {}
        self.devices = {}
        self.pairings = {}
        self.batches = []
        self.commands = []
        self.next_id = 1
        self.reject_key = False
        self.fail_next = []
        self.lose_answer = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def new_id(self):
        self.next_id += 1
        return f"id-{self.next_id}"

    def _handler(self):
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send(self, status, body=None, headers=None):
                raw = json.dumps(body if body is not None else {}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(raw)

            def body(self):
                size = int(self.headers.get("Content-Length", 0))
                return json.loads(self.rfile.read(size)) if size else {}

            def signed_in(self):
                return "session=ok" in self.headers.get("Cookie", "")

            def do_GET(self):
                path = self.path
                if path.startswith("/v1/") and not self.signed_in():
                    return self.send(401, {"code": "unauthorized"})
                if path == "/v1/rooms":
                    return self.send(200, {"items": [{"id": i, "name": n} for n, i in api.rooms.items()]})
                if path == "/v1/gateways":
                    return self.send(200, {"items": [{"id": "g", "name": g["name"]} for g in api.gateways.values()]})
                if path == "/v1/devices":
                    return self.send(200, {"items": [{"id": i, "name": d["name"]} for i, d in api.devices.items()]})
                if path.startswith("/v1/pairings/"):
                    pairing = api.pairings[path.rsplit("/", 1)[1]]
                    return self.send(200, {"status": pairing["status"], "deviceId": pairing.get("deviceId")})
                return self.send(404, {"code": "not_found"})

            def do_POST(self):
                data, path = self.body(), self.path
                if path == "/v1/auth/login":
                    user = api.users.get(data.get("email"))
                    if not user or user["password"] != data.get("password"):
                        return self.send(401, {"code": "invalid_credentials"})
                    if not user["verified"]:
                        return self.send(403, {"code": "email_not_verified"})
                    return self.send(200, {}, {"Set-Cookie": "session=ok; Path=/"})
                if path == "/v1/auth/register":
                    if data["email"] in api.users:
                        return self.send(409, {"code": "email_taken"})
                    api.users[data["email"]] = {"password": data["password"], "verified": False}
                    return self.send(201, {})
                if path == "/v1/auth/verify-email":
                    for user in api.users.values():
                        user["verified"] = True
                    return self.send(200, {}, {"Set-Cookie": "session=ok; Path=/"})
                if path == "/v1/auth/resend-verification":
                    return self.send(202, {})
                if path == "/device/v1/enroll":
                    code = api.new_id()
                    api.enrollments[code] = data
                    return self.send(201, {"claimCode": code, "pollId": api.new_id()})
                if path == "/v1/rooms":
                    if not self.signed_in():
                        return self.send(401, {"code": "unauthorized"})
                    api.rooms[data["name"]] = api.new_id()
                    return self.send(201, {"id": api.rooms[data["name"]], "name": data["name"]})
                if path == "/v1/gateways":
                    enrolled = api.enrollments.pop(data["claimCode"], None)
                    if not enrolled:
                        return self.send(404, {"code": "claim_code_unknown"})
                    api.gateways[enrolled["keyHash"]] = {"seq": 0, "name": data["name"]}
                    return self.send(201, {"id": api.new_id()})
                if path == "/v1/pairings":
                    pid = api.new_id()
                    api.pairings[pid] = {"status": "searching", "kind": data["kind"], "name": data["name"]}
                    return self.send(201, {"id": pid})
                if path == "/device/v1/readings":
                    return self.readings(data)
                return self.send(404, {"code": "not_found"})

            def readings(self, data):
                key = self.headers.get("Authorization", "").removeprefix("Bearer ")
                gateway = api.gateways.get(hashlib.sha256(key.encode()).hexdigest())
                if gateway is None or api.reject_key:
                    return self.send(401, {"code": "invalid_gateway_key"})
                if api.fail_next:
                    status = api.fail_next.pop(0)
                    return self.send(status, {"code": "injected"}, {"Retry-After": "1"} if status == 429 else None)
                if sum(len(n["samples"]) for n in data["nodes"]) > 5000:
                    return self.send(413, {"code": "payload_too_large"})
                if data["seq"] == gateway["seq"]:
                    return self.send(200, {"ackSeq": data["seq"], "accepted": 0, "rejected": 0, "commands": []})
                if data["seq"] != gateway["seq"] + 1:
                    return self.send(409, {"code": "sequence_gap", "expectedSeq": gateway["seq"] + 1})
                gateway["seq"] = data["seq"]
                api.batches.append(data)
                if api.lose_answer:
                    api.lose_answer = False
                    return self.send(500, {"code": "internal"})
                for node in data["nodes"]:
                    for pairing in api.pairings.values():
                        if pairing["status"] == "searching" and pairing["kind"] == node["kind"]:
                            device = api.new_id()
                            api.devices[device] = {"name": pairing["name"], "node": node["nodeId"]}
                            pairing.update(status="connected", deviceId=device)
                commands, api.commands = api.commands, []
                return self.send(200, {"ackSeq": data["seq"], "accepted": len(data["nodes"]), "rejected": 0, "commands": commands})

        return Handler
