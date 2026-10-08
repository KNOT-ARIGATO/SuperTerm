"""Quick-command storage, grouped by protocol (Serial / Telnet / SSH). No GUI imports.

File format (quick_commands_by_protocol.json in %APPDATA%\\SuperTerm):

    {"version": 2,
     "protocols": {"serial": {"profiles": [{"name": "MFG", "cmds": [{"label": "...", "cmd": "..."}]}],
                              "active": 0},
                   "telnet": {...}, "ssh": {...}}}

A protocol may have zero tabs; a fresh install starts completely empty.
"""
import copy
import json
import os
import shutil
import time

PROTOCOLS = ("serial", "telnet", "ssh")
DEFAULT_TAB = "General"


def _clean_profiles(profs):
    out = []
    for p in profs if isinstance(profs, list) else []:
        if not isinstance(p, dict):
            continue
        cmds = [{"label": str(c["label"]), "cmd": str(c["cmd"])}
                for c in (p.get("cmds") if isinstance(p.get("cmds"), list) else [])
                if isinstance(c, dict) and "label" in c and "cmd" in c]
        out.append({"name": str(p.get("name", "Tab")), "cmds": cmds})
    return out


def _empty():
    return {"version": 2, "protocols": {p: {"profiles": [], "active": 0} for p in PROTOCOLS}}


def detect_import(data):
    """Recognise an import file.

    Returns ("v2", {protocol: profiles}) for a file exported by this app, or
    ("legacy", profiles) for the old Tkinter program's quick_commands.json
    (no protocols there). Raises ValueError for anything else."""
    if isinstance(data, dict) and isinstance(data.get("protocols"), dict):
        out = {p: _clean_profiles((data["protocols"].get(p) or {}).get("profiles")) for p in PROTOCOLS}
        if any(out.values()):
            return "v2", out
        raise ValueError("The file contains no quick commands.")
    raw = None
    if isinstance(data, dict) and "profiles" in data:
        raw = data["profiles"]
    elif isinstance(data, list):                       # very old flat list of commands
        raw = [{"name": "Default", "cmds": data}]
    profs = _clean_profiles(raw)
    if profs:
        return "legacy", profs
    raise ValueError("This is not a quick-commands file.")


class QuickStore:
    def __init__(self, path):
        self.path = path
        self.data = _empty()
        self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            protos = d["protocols"]
            for p in PROTOCOLS:
                profs = _clean_profiles(protos.get(p, {}).get("profiles"))
                act = protos.get(p, {}).get("active", 0)
                self.data["protocols"][p] = {
                    "profiles": profs,
                    "active": act if isinstance(act, int) and 0 <= act < len(profs) else 0}
        except FileNotFoundError:
            pass
        except Exception:
            # unreadable file: keep a copy so it can be recovered, start empty
            try:
                shutil.copy2(self.path, self.path + ".corrupt")
            except Exception:
                pass
            self.data = _empty()

    def save(self):
        """Returns '' on success, or an error message."""
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
            return ""
        except OSError as e:
            return str(e)

    # -- access
    def _p(self, proto):
        return self.data["protocols"][proto]

    def profiles(self, proto):
        return self._p(proto)["profiles"]

    def has_tabs(self, proto):
        return bool(self.profiles(proto))

    def active(self, proto):
        return self._p(proto)["active"]

    def set_active(self, proto, idx):
        if 0 <= idx < len(self.profiles(proto)) and idx != self.active(proto):
            self._p(proto)["active"] = idx
            return self.save()
        return ""

    def cmds(self, proto):
        profs = self.profiles(proto)
        return profs[self.active(proto)]["cmds"] if profs else []

    # -- profiles (tabs)
    def add_profile(self, proto, name):
        self.profiles(proto).append({"name": name, "cmds": []})
        self._p(proto)["active"] = len(self.profiles(proto)) - 1
        return self.save()

    def rename_profile(self, proto, name):
        if not self.has_tabs(proto):
            return ""
        self.profiles(proto)[self.active(proto)]["name"] = name
        return self.save()

    def delete_profile(self, proto):
        """Deletes the active tab. The last tab may be deleted too."""
        profs = self.profiles(proto)
        if not profs:
            return ""
        profs.pop(self.active(proto))
        self._p(proto)["active"] = max(0, min(self.active(proto), len(profs) - 1))
        return self.save()

    def delete_all_profiles(self, proto):
        self._p(proto)["profiles"] = []
        self._p(proto)["active"] = 0
        return self.save()

    def move_profile(self, proto, delta):
        profs, i = self.profiles(proto), self.active(proto)
        j = i + delta
        if profs and 0 <= j < len(profs):
            profs[i], profs[j] = profs[j], profs[i]
            self._p(proto)["active"] = j
            return self.save()
        return ""

    # -- import / export
    def export_data(self):
        d = copy.deepcopy(self.data)
        d["app"] = "SuperTerm"
        d["exported"] = time.strftime("%Y-%m-%d %H:%M:%S")
        return d

    def import_profiles(self, proto, profiles, replace=False):
        """Add tabs to `proto` (does not save). Merge mode keeps everything the
        user already has: a tab with the same name gets only the commands it
        does not contain yet. Returns (tabs_added, commands_added)."""
        incoming = copy.deepcopy(profiles)
        if replace:
            self._p(proto)["profiles"] = incoming
            self._p(proto)["active"] = 0
            return len(incoming), sum(len(p["cmds"]) for p in incoming)
        tabs = cmds = 0
        mine = self.profiles(proto)
        for tab in incoming:
            same = next((m for m in mine if m["name"] == tab["name"]), None)
            if same is None:
                mine.append(tab)
                tabs += 1
                cmds += len(tab["cmds"])
                continue
            have = {(c["label"], c["cmd"]) for c in same["cmds"]}
            for c in tab["cmds"]:
                if (c["label"], c["cmd"]) not in have:
                    same["cmds"].append(c)
                    have.add((c["label"], c["cmd"]))
                    cmds += 1
        return tabs, cmds

    # -- commands
    def add_cmd(self, proto, label, cmd):
        """Adds to the active tab; creates a 'General' tab if there is none."""
        if not self.has_tabs(proto):
            self.profiles(proto).append({"name": DEFAULT_TAB, "cmds": []})
            self._p(proto)["active"] = 0
        self.cmds(proto).append({"label": label, "cmd": cmd})
        return self.save()

    def edit_cmd(self, proto, idx, label, cmd):
        lst = self.cmds(proto)
        if 0 <= idx < len(lst):
            lst[idx] = {"label": label, "cmd": cmd}
            return self.save()
        return ""

    def delete_cmd(self, proto, idx):
        lst = self.cmds(proto)
        if 0 <= idx < len(lst):
            lst.pop(idx)
            return self.save()
        return ""

    def move_cmd(self, proto, idx, delta):
        lst, j = self.cmds(proto), idx + delta
        if 0 <= idx < len(lst) and 0 <= j < len(lst):
            lst[idx], lst[j] = lst[j], lst[idx]
            return self.save()
        return ""
