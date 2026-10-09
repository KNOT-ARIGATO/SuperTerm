"""Auto-reconnect: the USB-UART disappears, comes back, and the session carries on."""
import threading
import time

import serial

import sessions


class FlakyPort:
    """Pretends to be a serial port; the first instance 'unplugs' after one read."""
    opened = 0

    def __init__(self, **kw):
        FlakyPort.opened += 1
        self.gen = FlakyPort.opened
        self.reads = 0

    @property
    def in_waiting(self):
        self.reads += 1
        if self.gen == 1 and self.reads > 1:
            raise serial.SerialException("device disconnected")
        return 6

    def read(self, n):
        time.sleep(0.01)
        return f"gen{self.gen}\n".encode()[:n]

    def close(self):
        pass


def test_auto_reconnect(monkeypatch):
    monkeypatch.setattr(sessions.serial, "Serial", FlakyPort)
    monkeypatch.setattr(sessions, "list_ports", lambda: [("COM9", "USB-SERIAL CH340")])
    FlakyPort.opened = 0
    lines, infos, closed = [], [], []
    s = sessions.SerialSession("COM9", 115200, 8, "N", 1, auto_reconnect=True,
                               on_line=lines.append, on_info=lambda t, g: infos.append(t),
                               on_opened=lambda: None, on_closed=lambda r, e: closed.append((r, e)))
    s.start()
    end = time.time() + 5
    while time.time() < end and "gen2" not in lines:
        time.sleep(0.02)
    s.stop()
    s._thread.join(3)
    assert "gen1" in lines and "gen2" in lines
    assert any("lost" in i for i in infos) and any("Reconnected" in i for i in infos)
    assert closed == [("", False)]                 # ended only because we stopped it


def test_without_auto_reconnect_the_session_ends(monkeypatch):
    monkeypatch.setattr(sessions.serial, "Serial", FlakyPort)
    FlakyPort.opened = 0
    closed = threading.Event()
    result = []
    s = sessions.SerialSession("COM9", 115200, 8, "N", 1, auto_reconnect=False,
                               on_line=lambda t: None, on_info=lambda t, g: None, on_opened=lambda: None,
                               on_closed=lambda r, e: (result.append((r, e)), closed.set()))
    s.start()
    assert closed.wait(3)
    assert result[0][1] is True and "disconnected" in result[0][0]
