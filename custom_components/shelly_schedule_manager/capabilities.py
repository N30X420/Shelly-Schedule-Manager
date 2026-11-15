"""Explicit capability discovery; never scheduled or inferred from device names."""
from __future__ import annotations

from dataclasses import dataclass, field
from homeassistant.exceptions import HomeAssistantError


@dataclass
class Capabilities:
    device_id: str | None = None
    methods: set = field(default_factory=set)
    switches: set = field(default_factory=set)
    capacity: int = 20  # Shelly Schedule API's documented limit, not a discovered field.

    def validate(self, jobs, creates=False, action_changes=False):
        if len(jobs) > self.capacity:
            raise HomeAssistantError(f"Schedule capacity exceeded ({self.capacity})")
        if creates and "Schedule.Create" not in self.methods:
            raise HomeAssistantError("Device does not support Schedule.Create")
        for raw in jobs:
            for call in raw["calls"]:
                method = call["method"]
                if method not in self.methods:
                    raise HomeAssistantError(f"Unsupported RPC method: {method}")
                params = call.get("params", {})
                if method.lower() == "switch.set":
                    if type(params.get("id")) is not int or params["id"] not in self.switches:
                        raise HomeAssistantError("Target switch component is not available; supply a channel mapping")
                    if type(params.get("on")) is not bool:
                        raise HomeAssistantError("Switch.Set requires a boolean on parameter")
                elif creates or action_changes:
                    # Method availability alone cannot validate component-specific parameters.
                    raise HomeAssistantError("Cloning/creating custom RPC actions is unsupported; existing actions are preserved")


async def discover(manager):
    info = await manager.rpc("Shelly.GetDeviceInfo")
    if info.get("gen") not in (2, 3) or not info.get("id"):
        raise HomeAssistantError("Unsupported device: requires Shelly Gen2/Gen3 identity")
    previous = manager.device_id
    if previous and previous != info["id"]:
        raise HomeAssistantError("Device identity changed. Reconfigure this device before writing")
    methods = (await manager.rpc("Shelly.ListMethods")).get("methods", [])
    if not isinstance(methods, list) or any(not isinstance(method, str) for method in methods):
        raise HomeAssistantError("Unsupported device: invalid method list")
    if "Schedule.List" not in methods:
        raise HomeAssistantError("Unsupported device: Schedule API unavailable")
    status = await manager.rpc("Shelly.GetStatus")
    switches = {int(key.split(":")[1]) for key in status if key.startswith("switch:") and key.split(":")[1].isdecimal()}
    caps = Capabilities(info["id"], set(methods), switches)
    manager.device_id = info["id"]
    manager.capabilities = caps
    await manager.persist_state()
    return info, status
