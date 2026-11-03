"""A small HTTP client for the Aethera API, with the headers of the web app and the headers of a gateway"""

import http.client
import json
import time
import urllib.error
import urllib.request


class ApiError(Exception):
    """The API answered with a status that the caller did not expect"""

    def __init__(self, status, body, where=""):
        super().__init__(f"{where} answered {status} {body.get('code', '') if isinstance(body, dict) else ''}".strip())
        self.status = status
        self.body = body if isinstance(body, dict) else {}

    @property
    def code(self):
        return self.body.get("code", "")


class RateLimited(ApiError):
    def __init__(self, status, body, where=""):
        super().__init__(status, body, where)
        self.retry_after = int(self.body.get("retryAfterSeconds", 5))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    """Sends JSON requests. A network error or a 5xx answer is tried again a few times with a growing pause."""

    def __init__(self, base_url, origin, user_agent, timeout=20, tries=3, pause=2.0):
        self.base_url = base_url.rstrip("/")
        self.origin = origin
        self.user_agent = user_agent
        self.timeout = timeout
        self.tries = tries
        self.pause = pause
        self._opener = urllib.request.build_opener(_NoRedirect)

    def request(self, method, path, body=None, cookie="", bearer="", app=True, retry=None):
        """Returns the status, the headers and the JSON body. The body is an empty dict when the answer is not JSON.

        A request that is safe to send twice is tried again after a network error or a 5xx answer. That is a GET, and a request
        for which the caller sets retry to True, such as a batch of readings, which has a sequence number. Any other request is sent
        once, because a second try after a timeout could repeat a change that the server already made.
        """
        data = json.dumps(body).encode() if body is not None else None
        tries = self.tries if (method == "GET" if retry is None else retry) else 1
        for attempt in range(1, tries + 1):
            req = urllib.request.Request(self.base_url + path, data=data, method=method)
            req.add_header("Content-Type", "application/json")
            req.add_header("User-Agent", self.user_agent)
            if app:
                req.add_header("X-Requested-With", "aethera")
                req.add_header("Origin", self.origin)
            if cookie:
                req.add_header("Cookie", cookie)
            if bearer:
                req.add_header("Authorization", "Bearer " + bearer)
            try:
                with self._opener.open(req, timeout=self.timeout) as res:
                    status, headers, raw = res.status, res.headers, res.read()
            except urllib.error.HTTPError as err:
                status, headers, raw = err.code, err.headers, err.read()
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException):
                if attempt == tries:
                    raise
                time.sleep(self.pause * attempt)
                continue
            if status >= 500 and attempt < tries:
                time.sleep(self.pause * attempt)
                continue
            try:
                parsed = json.loads(raw) if raw else {}
            except ValueError:
                parsed = {}
            return status, headers, parsed
        raise AssertionError("unreachable")

    def call(self, method, path, expect, **kwargs):
        """Like request, but returns the body and raises ApiError when the status is not the expected one"""
        status, headers, body = self.request(method, path, **kwargs)
        if status == expect:
            return body
        if status == 429:
            raise RateLimited(status, body, f"{method} {path}")
        raise ApiError(status, body, f"{method} {path}")
