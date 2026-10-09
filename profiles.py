"""Saved connection profiles per protocol (no passwords are stored)."""
import json
import os

FIELDS = {
    "serial": ("port", "baud", "data", "parity", "stop", "auto"),
    "telnet": ("host", "port", "ping", "interval"),
    "ssh": ("host", "port", "user"),
}


class ProfileStore:
    def __init__(self, path):
        self.path = path
        self.data = {k: [] for k in FIELDS}
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for proto, keys in FIELDS.items():
                for p in raw.get(proto, []):
                    if isinstance(p, dict) and p.get("name"):
                        self.data[proto].append({"name": str(p["name"]),
                                                 **{k: p.get(k) for k in keys if k in p}})
        except (OSError, ValueError, AttributeError):
            pass

    def names(self, proto):
        return [p["name"] for p in self.data[proto]]

    def get(self, proto, name):
        return next((dict(p) for p in self.data[proto] if p["name"] == name), None)

    def put(self, proto, name, values):
        entry = {"name": name, **{k: values[k] for k in FIELDS[proto] if k in values}}
        lst = self.data[proto]
        for i, p in enumerate(lst):
            if p["name"] == name:
                lst[i] = entry
                break
        else:
            lst.append(entry)
        return self.save()

    def delete(self, proto, name):
        self.data[proto] = [p for p in self.data[proto] if p["name"] != name]
        return self.save()

    def save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
            return ""
        except OSError as e:
            return str(e)
