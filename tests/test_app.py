"""End-to-end through the real main window (offscreen)."""
import socket
import threading
import time

import pytest


@pytest.fixture
def win(qapp, monkeypatch):
    import app as A
    import i18n
    store = {}
    monkeypatch.setattr(A, "QSettings", lambda *a, **k: type("S", (), {
        "value": lambda s, k, d=None: store.get(k, d), "setValue": lambda s, k, v: store.__setitem__(k, v)})())
    i18n.set_lang("en")
    w = A.MainWindow()
    w.show()
    yield w
    w.close()
    i18n.set_lang("en")


def test_language_switch_live(win):
    import i18n
    assert win.btn_connect.text().endswith("Connect")
    win.toggle_language()
    assert i18n.LANG == "th" and "เชื่อมต่อ" in win.btn_connect.text()
    assert win.lang_btn.text().endswith("TH")
    win.toggle_language()
    assert win.btn_connect.text().endswith("Connect")


def test_quick_groups_tests_and_hex_over_telnet(win, spin):
    from testrunner import Runner, make_step
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def serve():
        c, _ = srv.accept()
        c.settimeout(0.2)
        end = time.time() + 8
        while time.time() < end:
            try:
                d = c.recv(200)
                if not d:
                    break
                if b"mfg get_version" in d:
                    c.sendall(b"version v1.2.3 OK\r\n")
            except socket.timeout:
                pass
    threading.Thread(target=serve, daemon=True).start()

    win.seg_group.button(1).click()
    win.tn_host.setText("127.0.0.1")
    win.tn_port.setText(str(srv.getsockname()[1]))
    win.store.add_group("telnet", "MFG")
    win.store.add_tab("telnet", "Info")
    win.store.add_cmd("telnet", "Version", "mfg get_version")
    win.refresh_quick()
    assert [b.text() for b in win.quick_buttons] == ["Version"]
    win.connect_session()
    assert spin(5, until=lambda: win.opened)
    win.quick_buttons[0].click()
    assert spin(3, until=lambda: any("version v1.2.3" in l[0] for l in win.log_lines))
    spin(0.2)
    assert " TX " in win.hex.toPlainText() and " RX " in win.hex.toPlainText()

    win.open_tests()
    r = Runner([make_step("mfg get_version", "OK", 3)], win._send)
    win.test_win.runner = r
    win.test_win._reported = True
    assert spin(3, until=lambda: r.done) and r.passed
    win.disconnect_session()
    srv.close()


def test_edit_mode_opens_editor_instead_of_sending(win, spin, monkeypatch):
    import app as A
    opened = []
    monkeypatch.setattr(A.CmdDialog, "exec", lambda self: opened.append(self) or 0)
    win.store.add_cmd("serial", "SN", "mfg sn")
    win.seg_group.button(0).click()
    win.refresh_quick()
    win.btn_edit.setChecked(True)
    win.quick_buttons[0].click()
    assert opened and opened[0].label.text() == "SN"
