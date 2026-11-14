"""Digest-authenticated Shelly RPC transport; executed off the event loop."""
from __future__ import annotations

from typing import Any
import requests
from requests.auth import HTTPDigestAuth


class ShellyAPIError(Exception):
    """Remote RPC failed."""


class ShellyClient:
    def __init__(self, host: str, username: str, password: str) -> None:
        self.host = host.strip().removeprefix("http://").rstrip("/")
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
        except (requests.RequestException, ValueError) as exc:
            raise ShellyAPIError(f"RPC {method} failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise ShellyAPIError(f"Unexpected response to {method}")
        if payload.get("error"):
            raise ShellyAPIError(f"{method}: {payload['error']}")
        # Shelly /rpc uses a JSON-RPC envelope on some devices, but direct results on others.
        if "result" in payload and isinstance(payload["result"], dict):
            return payload["result"]
        return payload

    def list_jobs(self) -> dict[str, Any]:
        result = self.call("Schedule.List")
        if not isinstance(result.get("jobs"), list):
            raise ShellyAPIError("Schedule.List did not return jobs")
        return result
