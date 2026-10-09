import json
import os
import time

from quickstore import QuickStore, detect_import


def test_upgrade_v2_file_into_general_group(tmp_path):
    p = tmp_path / "q.json"
    p.write_text(json.dumps({"version": 2, "protocols": {
        "serial": {"profiles": [{"name": "MFG", "cmds": [{"label": "SN", "cmd": "mfg sn"}]}], "active": 0}}}))
    s = QuickStore(str(p))
    assert [g["name"] for g in s.groups("serial")] == ["General"]
    assert s.tabs("serial")[0]["name"] == "MFG" and s.cmds("serial")[0]["cmd"] == "mfg sn"
    assert s.groups("ssh") == []


def test_groups_tabs_commands(tmp_path):
    s = QuickStore(str(tmp_path / "q.json"))
    assert s.cmds("serial") == []
    s.add_cmd("serial", "A", "a")                       # creates General / General
    assert s.groups("serial")[0]["name"] == "General" and s.tabs("serial")[0]["name"] == "General"
    s.add_group("serial", "WiFi")
    s.add_tab("serial", "2.4G")
    s.add_cmd("serial", "B", "b")
    assert s.active_group("serial") == 1 and [c["label"] for c in s.cmds("serial")] == ["B"]
    s.set_active_group("serial", 0)
    assert [c["label"] for c in s.cmds("serial")] == ["A"]
    s.move_group("serial", +1)
    assert [g["name"] for g in s.groups("serial")] == ["WiFi", "General"]
    s.rename_tab("serial", "Main")
    s.delete_group("serial")
    assert [g["name"] for g in s.groups("serial")] == ["WiFi"]
    s2 = QuickStore(str(tmp_path / "q.json"))           # persisted
    assert s2.cmds("serial")[0]["label"] == "B"


def test_import_old_program_into_own_group_without_duplicates(tmp_path):
    old = {"profiles": [{"name": "MFG", "cmds": [{"label": "SN", "cmd": "mfg sn"}, {"bad": 1}]}]}
    kind, tabs = detect_import(old)
    assert kind == "legacy" and len(tabs[0]["cmds"]) == 1
    s = QuickStore(str(tmp_path / "q.json"))
    assert s.import_tabs("serial", tabs, group_name="SuperSerial") == (1, 1)
    assert s.import_tabs("serial", tabs, group_name="SuperSerial") == (0, 0)     # merge = no duplicates
    assert [g["name"] for g in s.groups("serial")] == ["SuperSerial"]


def test_export_import_roundtrip_v3(tmp_path):
    a = QuickStore(str(tmp_path / "a.json"))
    a.add_group("ssh", "Linux")
    a.add_tab("ssh", "Info")
    a.add_cmd("ssh", "uptime", "uptime")
    kind, groups = detect_import(json.loads(json.dumps(a.export_data())))
    assert kind == "v3"
    b = QuickStore(str(tmp_path / "b.json"))
    b.import_groups("ssh", groups["ssh"])
    assert b.groups("ssh")[0]["tabs"][0]["cmds"][0]["cmd"] == "uptime"


def test_two_windows_see_each_others_changes(tmp_path):
    a = QuickStore(str(tmp_path / "q.json"))
    b = QuickStore(str(tmp_path / "q.json"))
    a.add_cmd("telnet", "X", "x")
    os.utime(tmp_path / "q.json", (time.time() + 5, time.time() + 5))   # visible on coarse clocks too
    assert b.reload_if_changed() and b.cmds("telnet")[0]["label"] == "X"
    b.add_cmd("telnet", "Y", "y")                       # b reloads before writing → keeps X
    assert [c["label"] for c in QuickStore(str(tmp_path / "q.json")).cmds("telnet")] == ["X", "Y"]
