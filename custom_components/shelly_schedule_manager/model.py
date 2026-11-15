"""Schedule model, staging operations and field-level snapshot comparisons."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import time

from homeassistant.exceptions import HomeAssistantError


def validate_name(value):
    if not isinstance(value, str) or len(value) > 80:
        raise HomeAssistantError("Names must contain at most 80 characters")
    return value.strip()


def payload(raw):
    return {key: deepcopy(raw[key]) for key in ("timespec", "enable", "calls")}


@dataclass
class Job:
    id: int
    timespec: str
    enabled: bool
    calls: list
    deleted: bool = False
    uncertain: bool = False
    locked: bool = False
    baseline: dict | None = field(default=None)

    def __post_init__(self):
        if self.id >= 0 and self.baseline is None:
            self.baseline = self.raw()

    def raw(self):
        return {"id": self.id, "timespec": self.timespec, "enable": self.enabled, "calls": deepcopy(self.calls)}

    @property
    def operation(self):
        if self.deleted:
            return "delete"
        if self.baseline is None:
            return "create"
        return "update" if payload(self.raw()) != payload(self.baseline) else None

    @property
    def dirty(self):
        return self.operation is not None or self.uncertain

    @property
    def original_timespec(self):
        return self.baseline["timespec"] if self.baseline else ""

    @property
    def original_enabled(self):
        return self.baseline["enable"] if self.baseline else None

    def _refresh_dirty(self):
        """Compatibility with existing helpers; dirty is now derived from baseline."""

    def check_editable(self):
        if self.locked or self.uncertain or self.deleted:
            raise HomeAssistantError("Job is busy, deleted or unresolved; Load to inspect")

    @property
    def local_time(self):
        fields = self.timespec.split()
        try:
            if len(fields) != 6 or any(not f.isdecimal() for f in fields[:3]):
                return None
            return time(int(fields[2]), int(fields[1]), int(fields[0]))
        except ValueError:
            return None

    @property
    def weekday_values(self):
        fields = self.timespec.split()
        if len(fields) != 6:
            return None
        if fields[5] == "*":
            return set(range(7))
        aliases = dict(SUN=0, MON=1, TUE=2, WED=3, THU=4, FRI=5, SAT=6)
        days = set()
        for fragment in fields[5].upper().split(","):
            if fragment in aliases:
                days.add(aliases[fragment])
            elif fragment.isdecimal() and 0 <= int(fragment) <= 7:
                days.add(int(fragment) % 7)
            else:
                return None
        return days or None

    @property
    def weekday_text(self):
        values = self.weekday_values
        return ",".join(str(x) for x in sorted(values)) if values is not None else "advanced"

    def set_time(self, new):
        self.check_editable()
        if self.local_time is None:
            raise HomeAssistantError("Non-fixed time: edit this expression on Shelly")
        fields = self.timespec.split()
        fields[:3] = [str(new.second), str(new.minute), str(new.hour)]
        self.timespec = " ".join(fields)

    def set_weekdays(self, value):
        self.check_editable()
        if self.weekday_values is None:
            raise HomeAssistantError("Advanced weekday expression: edit on Shelly")
        tokens = value.split(",")
        if not tokens or any(not x.isdecimal() or not 0 <= int(x) <= 6 for x in tokens):
            raise HomeAssistantError("Choose at least one weekday (0=Sun through 6=Sat)")
        fields = self.timespec.split()
        fields[5] = ",".join(str(x) for x in sorted({int(x) for x in tokens}))
        self.timespec = " ".join(fields)

    def set_enabled(self, value):
        self.check_editable()
        if type(value) is not bool:
            raise HomeAssistantError("Enabled must be a boolean")
        self.enabled = value

    @property
    def action(self):
        if len(self.calls) == 1 and self.calls[0].get("method", "").lower() == "switch.set":
            params = self.calls[0].get("params", {})
            if type(params.get("on")) is bool:
                return f"Switch {params.get('id', 0)} {'ON' if params['on'] else 'OFF'}"
        return "Custom action"


def parse_job(raw):
    """Preserve arbitrary valid device cron and RPC calls, without simplifying them."""
    try:
        if type(raw["id"]) is not int or type(raw["enable"]) is not bool:
            raise ValueError
        if not isinstance(raw["timespec"], str) or not raw["timespec"].strip():
            raise ValueError
        calls = raw["calls"]
        if not isinstance(calls, list) or not 1 <= len(calls) <= 5:
            raise ValueError
        if any(not isinstance(c, dict) or not isinstance(c.get("method"), str)
               or not c["method"] or not isinstance(c.get("params", {}), dict) for c in calls):
            raise ValueError
        return Job(raw["id"], raw["timespec"], raw["enable"], deepcopy(calls))
    except (KeyError, TypeError, ValueError) as exc:
        raise HomeAssistantError("Invalid schedule data returned by device") from exc


def snapshot_diff(before, after):
    old = {str(j["id"]): j for j in before.get("jobs", [])}
    new = {str(j["id"]): j for j in after.get("jobs", [])}
    result = []
    for key in sorted(set(old) | set(new)):
        if key not in old or key not in new:
            result.append({"id": key, "operation": "create" if key not in old else "delete"})
            continue
        changes = {}
        for field_name in ("timespec", "enable", "calls"):
            if old[key].get(field_name) != new[key].get(field_name):
                changes[field_name] = {"before": old[key].get(field_name), "after": new[key].get(field_name)}
        a, b = old[key]["timespec"].split(), new[key]["timespec"].split()
        if len(a) == len(b) == 6:
            for name, left, right in (("time", a[:3], b[:3]), ("weekdays", a[5], b[5])):
                if left != right:
                    changes[name] = {"before": left, "after": right}
        left = before.get("names", {}).get(key, "")
        right = after.get("names", {}).get(key, "")
        if left != right:
            changes["name"] = {"before": left, "after": right}
        if changes:
            result.append({"id": key, "operation": "update", "changes": changes})
    return result
