import pyte

import terminal
from sessions import TelnetFilter, LineBuffer, list_ports


def test_telnet_negotiation():
    f = TelnetFilter()
    data, rep = f.feed(bytes([255, 251, 1, 255, 251, 3, 255, 253, 24]) + b"lo" + bytes([255, 255]) + b"gin")
    assert data == b"lo\xffgin"
    assert rep == bytes([255, 253, 1, 255, 253, 3, 255, 252, 24])
    assert f.feed(bytes([255, 250, 24, 1, 255, 240]) + b"ok") == (b"ok", b"")


def test_linebuffer_cleans_lines():
    b = LineBuffer()
    lines = b.feed(b"roo\x08ot\x1b[1;32mOK\x1b[0m\r\nprogress 10%\rprogress 100%\r\n\x01junk\r\npro")
    assert lines == ["rootOK", "progress 100%", "junk"]
    assert b.flush() == "pro"


def test_list_ports_shape():
    for dev, desc in list_ports():
        assert isinstance(dev, str) and isinstance(desc, str)


def _screen_text(s):
    return "\n".join("".join(s.buffer[y][x].data for x in range(s.columns)).rstrip() for y in range(s.lines))


def test_thai_marks_and_noise_bytes_are_kept():
    s = terminal._Screen(80, 5, 100)
    pyte.ByteStream(s).feed("ok\x01ที่นี่ สวัสดีครับ ไฟล์ end".encode())
    assert "okที่นี่ สวัสดีครับ ไฟล์ end" in _screen_text(s)


def test_scrollback_and_lf(qapp):
    t = terminal.TerminalWidget()
    t.resize(600, 300)
    t.feed(b"".join(b"line %d\n" % i for i in range(200)))
    t._flush()
    assert len(t.screen.scrollback) > 100
    text = t.select_all_text()
    assert "line 199" in text and "line 0\nline 1" in text       # LF -> CR+LF, no staircase


def test_keys_are_sent(qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    t = terminal.TerminalWidget()
    t.online = True
    sent = []
    t.send_bytes.connect(sent.append)
    QTest.keyClicks(t, "ls")
    QTest.keyClick(t, Qt.Key_Return)
    QTest.keyClick(t, Qt.Key_C, Qt.ControlModifier)
    QTest.keyClick(t, Qt.Key_Up)
    assert sent == [b"l", b"s", b"\r", b"\x03", b"\x1b[A"]
