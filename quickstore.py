"""Quick-command storage: protocol → GROUP → TAB → commands. No GUI imports.

File (quick_commands_by_protocol.json in %APPDATA%\\SuperTerm), version 3:

    {"version": 3,
     "protocols": {"serial": {"groups": [{"name": "MFG test", "active": 0,
                                          "tabs": [{"name": "Audio", "cmds": [{"label": "...", "cmd": "..."}]}]}],
                              "active": 0},
                   "telnet": {...}, "ssh": {...}}}

Version-2 files (tabs directly under a protocol) are upgraded: their tabs go
into a group called "General". A fresh install starts completely empty.
"""
import copy
import json
import os
import shutil
import time

PROTOCOLS = ("serial", "telnet", "ssh")
DEFAULT_GROUP = "General"
DEFAULT_TAB = "General"


def _clean_tabs(tabs):
    out = []
    for p in tabs if isinstance(tabs, list) else []:
        if not isinstance(p, dict):
            continue
        cmds = [{"label": str(c["label"]), "cmd": str(c["cmd"])}
                for c in (p.get("cmds") if isinstance(p.get("cmds"), list) else [])
                if isinstance(c, dict) and "label" in c and "cmd" in c]
        out.append({"name": str(p.get("name", "Tab")), "cmds": cmds})
    return out


def _clean_groups(groups):
    out = []
    for g in groups if isinstance(groups, list) else []:
        if not isinstance(g, dict):
            continue
        tabs = _clean_tabs(g.get("tabs"))
        act = g.get("active", 0)
        out.append({"name": str(g.get("name", "Group")), "tabs": tabs,
                    "active": act if isinstance(act, int) and 0 <= act < len(tabs) else 0})
    return out


def _empty():
    return {"version": 3, "protocols": {p: {"groups": [], "active": 0} for p in PROTOCOLS}}


def detect_import(data):
    """Recognise an import file.
    ("v3", {protocol: groups})   – exported by SuperTerm ≥ 1.1
    ("v2", {protocol: tabs})     – exported by SuperTerm 1.0.x
    ("legacy", tabs)             – the old SuperSerial quick_commands.json (no protocols)"""
    if isinstance(data, dict) and isinstance(data.get("protocols"), dict):
        protos = data["protocols"]
        if any(isinstance((protos.get(p) or {}).get("groups"), list) for p in PROTOCOLS):
            out = {p: _clean_groups((protos.get(p) or {}).get("groups")) for p in PROTOCOLS}
            if any(out.values()):
                return "v3", out
        else:
            out = {p: _clean_tabs((protos.get(p) or {}).get("profiles")) for p in PROTOCOLS}
            if any(out.values()):
                return "v2", out
        raise ValueError("The file contains no quick commands.")
    raw = None
    if isinstance(data, dict) and "profiles" in data:
        raw = data["profiles"]
    elif isinstance(data, list):                       # very old flat list of commands
        raw = [{"name": "Default", "cmds": data}]
    tabs = _clean_tabs(raw)
    if tabs:
        return "legacy", tabs
    raise ValueError("This is not a quick-commands file.")


def _merge_tabs(mine, incoming):
    """Merge tab lists: same tab name → only the missing commands are added."""
    tabs = cmds = 0
    for tab in copy.deepcopy(incoming):
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


class QuickStore:
    def __init__(self, path):
        self.path = path
        self.data = _empty()
        self._mtime = None
        self._load()

    # ── file ─────────────────────────────────────────────────────────────────
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            protos = d["protocols"]
            for p in PROTOCOLS:
                src = protos.get(p) or {}
                if "groups" in src:
                    groups = _clean_groups(src.get("groups"))
                    act = src.get("active", 0)
                else:                                   # version 2 → one "General" group
                    tabs = _clean_tabs(src.get("profiles"))
                    tact = src.get("active", 0)
                    groups = [{"name": DEFAULT_GROUP, "tabs": tabs,
                               "active": tact if isinstance(tact, int) and 0 <= tact < len(tabs) else 0}] \
                        if tabs else []
                    act = 0
                self.data["protocols"][p] = {
                    "groups": groups,
                    "active": act if isinstance(act, int) and 0 <= act < len(groups) else 0}
            self._mtime = os.path.getmtime(self.path)
        except FileNotFoundError:
            pass
        except Exception:
            try:                                        # keep the unreadable file, start empty
                shutil.copy2(self.path, self.path + ".corrupt")
            except Exception:
                pass
            self.data = _empty()

    def reload_if_changed(self):
        """Another SuperTerm window may have saved meanwhile."""
        try:
            m = os.path.getmtime(self.path)
        except OSError:
            return False
        if m != self._mtime:
            self.data = _empty()
            self._load()
            return True
        return False

    def save(self):
        """Returns '' on success, or an error message."""
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
            self._mtime = os.path.getmtime(self.path)
            return ""
        except OSError as e:
            return str(e)

    # ── groups ───────────────────────────────────────────────────────────────
    def _p(self, proto):
        return self.data["protocols"][proto]

    def groups(self, proto):
        return self._p(proto)["groups"]

    def active_group(self, proto):
        return self._p(proto)["active"]

    def _group(self, proto):
        gs = self.groups(proto)
        return gs[self.active_group(proto)] if gs else None

    def set_active_group(self, proto, idx):
        if 0 <= idx < len(self.groups(proto)) and idx != self.active_group(proto):
            self._p(proto)["active"] = idx
            return self.save()
        return ""

    def add_group(self, proto, name):
        self.reload_if_changed()
        self.groups(proto).append({"name": name, "tabs": [], "active": 0})
        self._p(proto)["active"] = len(self.groups(proto)) - 1
        return self.save()

    def rename_group(self, proto, name):
        self.reload_if_changed()
        g = self._group(proto)
        if g is None:
            return ""
        g["name"] = name
        return self.save()

    def delete_group(self, proto):
        self.reload_if_changed()
        gs = self.groups(proto)
        if not gs:
            return ""
        gs.pop(self.active_group(proto))
        self._p(proto)["active"] = max(0, min(self.active_group(proto), len(gs) - 1))
        return self.save()

    def move_group(self, proto, delta):
        gs, i = self.groups(proto), self.active_group(proto)
        j = i + delta
        if gs and 0 <= j < len(gs):
            gs[i], gs[j] = gs[j], gs[i]
            self._p(proto)["active"] = j
            return self.save()
        return ""

    def delete_all(self, proto):
        self._p(proto)["groups"] = []
        self._p(proto)["active"] = 0
        return self.save()

    def _ensure_group(self, proto):
        if not self.groups(proto):
            self.groups(proto).append({"name": DEFAULT_GROUP, "tabs": [], "active": 0})
            self._p(proto)["active"] = 0
        return self._group(proto)

    # ── tabs (inside the active group) ───────────────────────────────────────
    def tabs(self, proto):
        g = self._group(proto)
        return g["tabs"] if g else []

    def has_tabs(self, proto):
        return bool(self.tabs(proto))

    def active_tab(self, proto):
        g = self._group(proto)
        return g["active"] if g else 0

    def _tab(self, proto):
        tabs = self.tabs(proto)
        return tabs[self.active_tab(proto)] if tabs else None

    def set_active_tab(self, proto, idx):
        g = self._group(proto)
        if g and 0 <= idx < len(g["tabs"]) and idx != g["active"]:
            g["active"] = idx
            return self.save()
        return ""

    def add_tab(self, proto, name):
        self.reload_if_changed()
        g = self._ensure_group(proto)
        g["tabs"].append({"name": name, "cmds": []})
        g["active"] = len(g["tabs"]) - 1
        return self.save()

    def rename_tab(self, proto, name):
        self.reload_if_changed()
        t = self._tab(proto)
        if t is None:
            return ""
        t["name"] = name
        return self.save()

    def delete_tab(self, proto):
        self.reload_if_changed()
        g = self._group(proto)
        if not g or not g["tabs"]:
            return ""
        g["tabs"].pop(g["active"])
        g["active"] = max(0, min(g["active"], len(g["tabs"]) - 1))
        return self.save()

    def move_tab(self, proto, delta):
        g = self._group(proto)
        if not g:
            return ""
        i, j = g["active"], g["active"] + delta
        if 0 <= j < len(g["tabs"]):
            g["tabs"][i], g["tabs"][j] = g["tabs"][j], g["tabs"][i]
            g["active"] = j
            return self.save()
        return ""

    # ── commands (inside the active tab) ─────────────────────────────────────
    def cmds(self, proto):
        t = self._tab(proto)
        return t["cmds"] if t else []

    def add_cmd(self, proto, label, cmd):
        """Adds to the active tab; creates 'General' group / tab when missing."""
        self.reload_if_changed()
        g = self._ensure_group(proto)
        if not g["tabs"]:
            g["tabs"].append({"name": DEFAULT_TAB, "cmds": []})
            g["active"] = 0
        self.cmds(proto).append({"label": label, "cmd": cmd})
        return self.save()

    def edit_cmd(self, proto, idx, label, cmd):
        self.reload_if_changed()
        lst = self.cmds(proto)
        if 0 <= idx < len(lst):
            lst[idx] = {"label": label, "cmd": cmd}
            return self.save()
        return ""

    def delete_cmd(self, proto, idx):
        self.reload_if_changed()
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

    # ── import / export ──────────────────────────────────────────────────────
    def export_data(self):
        d = copy.deepcopy(self.data)
        d["app"] = "SuperTerm"
        d["exported"] = time.strftime("%Y-%m-%d %H:%M:%S")
        return d

    def import_tabs(self, proto, tabs, replace=False, group_name=None):
        """Tabs from an old / v2 file → into `group_name` (default: the active
        group, created if needed). Returns (tabs_added, commands_added)."""
        self.reload_if_changed()
        gs = self.groups(proto)
        g = None
        if group_name:
            g = next((x for x in gs if x["name"] == group_name), None)
            if g is None:
                gs.append({"name": group_name, "tabs": [], "active": 0})
                g = gs[-1]
            self._p(proto)["active"] = gs.index(g)
        if g is None:
            g = self._ensure_group(proto)
        if replace:
            g["tabs"] = copy.deepcopy(tabs)
            g["active"] = 0
            return len(tabs), sum(len(t["cmds"]) for t in tabs)
        return _merge_tabs(g["tabs"], tabs)

    def import_groups(self, proto, groups, replace=False):
        """Groups from a v3 export. Same group name → tabs are merged."""
        self.reload_if_changed()
        if replace:
            self._p(proto)["groups"] = copy.deepcopy(groups)
            self._p(proto)["active"] = 0
            return len(groups), sum(len(t["cmds"]) for g in groups for t in g["tabs"])
        tabs = cmds = 0
        mine = self.groups(proto)
        for g in groups:
            same = next((m for m in mine if m["name"] == g["name"]), None)
            if same is None:
                mine.append(copy.deepcopy(g))
                tabs += len(g["tabs"])
                cmds += sum(len(t["cmds"]) for t in g["tabs"])
            else:
                a, b = _merge_tabs(same["tabs"], g["tabs"])
                tabs, cmds = tabs + a, cmds + b
        return tabs, cmds

    def counts(self):
        tabs = sum(len(g["tabs"]) for p in PROTOCOLS for g in self.groups(p))
        cmds = sum(len(t["cmds"]) for p in PROTOCOLS for g in self.groups(p) for t in g["tabs"])
        return tabs, cmds
