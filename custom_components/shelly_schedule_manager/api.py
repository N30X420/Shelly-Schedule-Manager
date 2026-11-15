"""Digest-authenticated Shelly RPC transport; executed off the event loop."""
from __future__ import annotations

from typing import Any
import requests
from requests.auth import HTTPDigestAuth


class ShellyAPIError(Exception):
    """Remote RPC failed."""

    def __init__(self, message, kind="rpc_error"):
        super().__init__(message)
        self.kind = kind


class ShellyClient:
    def __init__(self, host: str, username: str, password: str) -> None:
        self.host = host.strip().rstrip("/")
        if self.host.startswith("http://"):
            self.host = self.host[7:]
        self.auth = HTTPDigestAuth(username, password)

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"http://{self.host}/rpc"
        try:
            # Explicitly disable environmental proxies for private LAN devices.
            with requests.Session() as session:
                session.trust_env = False
                response = session.post(
                    url,
                    json={"id": 1, "method": method, **({"params": params} if params is not None else {})},
                    auth=self.auth,
                    timeout=(5, 12),
                )
                response.raise_for_status()
                payload = response.json()
        except requests.Timeout as exc:
            raise ShellyAPIError(f"{method}: request timed out", "timeout") from exc
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            kind = "authentication_failed" if status in (401, 403) else "network_error"
            raise ShellyAPIError(f"{method}: HTTP {status}", kind) from exc
        except (requests.RequestException, ValueError) as exc:
            # Never echo URLs, headers, response bodies or third-party exception text.
            raise ShellyAPIError(f"{method}: network or response error", "network_error") from exc
        if not isinstance(payload, dict):
            raise ShellyAPIError(f"Unexpected response to {method}")
        if payload.get("error"):
            code = payload['error'].get('code') if isinstance(payload['error'], dict) else None
            kind = "authentication_failed" if code in (401, 403) else "rpc_error"
            raise ShellyAPIError(f"{method}: RPC error {code}", kind)
        # Shelly /rpc uses a JSON-RPC envelope on some devices, but direct results on others.
        if "result" in payload and isinstance(payload["result"], dict):
            return payload["result"]
        return payload

    def list_jobs(self) -> dict[str, Any]:
        result = self.call("Schedule.List")
        if not isinstance(result.get("jobs"), list):
            raise ShellyAPIError("Schedule.List did not return jobs")
        return result
