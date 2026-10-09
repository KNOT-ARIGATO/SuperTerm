"""Tera Term–style terminal widget.

* every key is sent immediately (no Enter needed); Enter / Backspace codes are
  configurable like Tera Term (CR · CR+LF · LF, BS · DEL)
* VT100 / xterm escape sequences are interpreted by `pyte` (colours, cursor
  movement, clear screen …) so shells, `top`, `vi`, U-Boot menus look right
* scrollback with mouse wheel / scrollbar / Shift+PgUp
* select = copy (like Tera Term), right-click / Shift+Insert / Alt+V = paste
"""
import re
from collections import deque

import pyte
from pyte import modes as _mo
from pyte.screens import Margins, wcwidth as _wcwidth
from PySide6.QtCore import Qt, Signal, QTimer, QRect, QEvent
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics
from PySide6.QtWidgets import QWidget, QScrollBar, QApplication, QMessageBox

ANSI_DARK = {
    "black": "#5c6370", "red": "#e06c75", "green": "#98c379", "brown": "#e5c07b",
    "blue": "#61afef", "magenta": "#c678dd", "cyan": "#56b6c2", "white": "#dcdfe4",
    "brightblack": "#7f848e", "brightred": "#ff7b86", "brightgreen": "#b5e890",
    "brightbrown": "#ffd88a", "brightblue": "#82c4ff", "brightmagenta": "#e09cf0",
    "brightcyan": "#7fd9e3", "brightwhite": "#ffffff",
}
ANSI_LIGHT = {
    "black": "#24292f", "red": "#cf222e", "green": "#116329", "brown": "#9a6700",
    "blue": "#0969da", "magenta": "#8250df", "cyan": "#1b7c83", "white": "#6e7781",
    "brightblack": "#57606a", "brightred": "#a40e26", "brightgreen": "#1a7f37",
    "brightbrown": "#633c01", "brightblue": "#218bff", "brightmagenta": "#a475f9",
    "brightcyan": "#3192aa", "brightwhite": "#8c959f",
}
_HEX = re.compile(r"^[0-9a-fA-F]{6}$")

ENTER_CODES = {"CR": b"\r", "CR+LF": b"\r\n", "LF": b"\n"}
BS_CODES = {"BS": b"\x08", "DEL": b"\x7f"}

# keys that send an escape sequence (xterm / Tera Term VT defaults)
_KEYMAP = {
    Qt.Key_Up: b"\x1b[A", Qt.Key_Down: b"\x1b[B", Qt.Key_Right: b"\x1b[C", Qt.Key_Left: b"\x1b[D",
    Qt.Key_Home: b"\x1b[1~", Qt.Key_End: b"\x1b[4~", Qt.Key_Insert: b"\x1b[2~",
    Qt.Key_Delete: b"\x1b[3~", Qt.Key_PageUp: b"\x1b[5~", Qt.Key_PageDown: b"\x1b[6~",
    Qt.Key_Escape: b"\x1b", Qt.Key_Tab: b"\t", Qt.Key_Backtab: b"\x1b[Z",
    Qt.Key_F1: b"\x1bOP", Qt.Key_F2: b"\x1bOQ", Qt.Key_F3: b"\x1bOR", Qt.Key_F4: b"\x1bOS",
    Qt.Key_F5: b"\x1b[15~", Qt.Key_F6: b"\x1b[17~", Qt.Key_F7: b"\x1b[18~", Qt.Key_F8: b"\x1b[19~",
    Qt.Key_F9: b"\x1b[20~", Qt.Key_F10: b"\x1b[21~", Qt.Key_F11: b"\x1b[23~", Qt.Key_F12: b"\x1b[24~",
}
_KEYMAP = {int(k): v for k, v in _KEYMAP.items()}
K = lambda k: int(k)      # Qt.Key enum → int (ev.key() is an int)


class _Screen(pyte.Screen):
    """pyte screen that keeps lines scrolled off the top (full-screen scroll only)."""

    def __init__(self, cols, rows, history):
        self.scrollback = deque(maxlen=history)
        super().__init__(cols, rows)

    def index(self):
        top, bottom = self.margins or Margins(0, self.lines - 1)
        if self.cursor.y == bottom and top == 0:
            self.scrollback.append(self.buffer[top])
        super().index()

    def draw(self, data):
        """Same as pyte's draw, with two fixes that matter for real devices:
        * an unprintable byte (noise at the wrong baud rate, stray control
          codes) is skipped — pyte would silently drop the REST of the text;
        * every zero-width character is attached to the previous cell — pyte
          drops Thai vowels/tone marks such as ั ิ ี ็ ์ and everything after them."""
        data = data.translate(self.g1_charset if self.charset else self.g0_charset)
        for char in data:
            w = _wcwidth(char)
            if w < 0:
                continue
            if w == 0:
                if self.cursor.x:
                    line = self.buffer[self.cursor.y]
                    last = line[self.cursor.x - 1]
                    line[self.cursor.x - 1] = last._replace(data=last.data + char)
                elif self.cursor.y:
                    prev = self.buffer[self.cursor.y - 1]
                    last = prev[self.columns - 1]
                    prev[self.columns - 1] = last._replace(data=last.data + char)
                continue
            if self.cursor.x == self.columns:
                if _mo.DECAWM in self.mode:
                    self.dirty.add(self.cursor.y)
                    self.carriage_return()
                    self.linefeed()
                else:
                    self.cursor.x -= w
            if _mo.IRM in self.mode:
                self.insert_characters(w)
            line = self.buffer[self.cursor.y]
            line[self.cursor.x] = self.cursor.attrs._replace(data=char)
            if w == 2 and self.cursor.x + 1 < self.columns:
                line[self.cursor.x + 1] = self.cursor.attrs._replace(data="")
            self.cursor.x = min(self.cursor.x + w, self.columns)
        self.dirty.add(self.cursor.y)

    def erase_in_display(self, how=0, *args, **kwargs):
        super().erase_in_display(how, *args, **kwargs)
        if how == 3:
            self.scrollback.clear()

    def reset(self):
        super().reset()
        self.scrollback.clear()


class TerminalWidget(QWidget):
    send_bytes = Signal(bytes)        # keystrokes / paste to transmit
    resized = Signal(int, int)        # columns, rows (for SSH pty size)
    status = Signal(str)              # short messages for the status bar

    PAD = 6

    def __init__(self, parent=None, history=10000):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.IBeamCursor)
        self.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.setMinimumSize(200, 120)

        self.screen = _Screen(80, 24, history)
        self.stream = pyte.ByteStream(self.screen)
        self.scroll = 0                     # lines scrolled back from the bottom
        self.sel_a = self.sel_b = None      # selection (abs_line, col)
        self._selecting = False
        self._pending = bytearray()
        self._last_cr = False
        self.online = False
        self.enter = b"\r"
        self.backspace = b"\x08"
        self.local_echo = False
        self.lf_to_crlf = True
        self._blink_on = True
        self.tagger = None                  # text -> "error" / "warn" / "success" / "info"
        self.tag_colors = {}                # tag -> QColor (same colours as the Log view)
        self._custom_colors = {}            # 'c:#rrggbb' -> QColor (user highlight words)

        self._feed_timer = QTimer(self)
        self._feed_timer.setInterval(25)
        self._feed_timer.timeout.connect(self._flush)
        self._blink = QTimer(self)
        self._blink.setInterval(550)
        self._blink.timeout.connect(self._toggle_blink)
        self._blink.start()
        self._paste_queue = []
        self._paste_timer = QTimer(self)
        self._paste_timer.setInterval(15)
        self._paste_timer.timeout.connect(self._paste_step)

        self.bar = QScrollBar(Qt.Vertical, self)
        self.bar.valueChanged.connect(self._bar_moved)
        self.set_font_size(9)
        self.set_colors("#0d1117", "#e6edf3", "#58a6ff", dark=True)

    # ── appearance ───────────────────────────────────────────────────────────
    def set_font_size(self, pt):
        f = QFont()
        # mono font first; Thai / CJK glyphs fall back to fonts that have them
        f.setFamilies(["Cascadia Mono", "Consolas", "JetBrains Mono", "Courier New",
                       "Leelawadee UI", "Tahoma", "Microsoft YaHei", "Segoe UI Symbol"])
        f.setStyleHint(QFont.Monospace)
        f.setFixedPitch(True)
        f.setPointSize(max(7, min(24, pt)))
        self.font_pt = f.pointSize()
        self.tfont = f
        self.bfont = QFont(f)
        self.bfont.setBold(True)
        fm = QFontMetrics(f)
        self.cw = max(1, fm.horizontalAdvance("M"))
        self.ch = max(1, fm.height())
        self.ascent = fm.ascent()
        self._relayout()

    def set_colors(self, bg, fg, accent, dark=True):
        self.c_bg, self.c_fg, self.c_accent = QColor(bg), QColor(fg), QColor(accent)
        sel = QColor(accent)
        sel.setAlpha(110)
        self.c_sel = sel
        self.ansi = {k: QColor(v) for k, v in (ANSI_DARK if dark else ANSI_LIGHT).items()}
        self.update()

    def set_highlight(self, tagger, colors):
        """Colour whole lines that contain pass / fail / error / warning words,
        like the Log view. Explicit ANSI colours from the device are kept."""
        self.tagger = tagger
        self.tag_colors = {k: QColor(v) for k, v in colors.items()}
        self.update()

    def _tag_qcolor(self, tag):
        c = self._custom_colors.get(tag)
        if c is None:
            c = self._custom_colors[tag] = QColor(tag[2:])
        return c

    def _color(self, name, default):
        if name == "default":
            return default
        c = self.ansi.get(name)
        if c is not None:
            return c
        if _HEX.match(name):
            return QColor("#" + name)
        return default

    # ── geometry ─────────────────────────────────────────────────────────────
    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._relayout()

    def _relayout(self):
        if not hasattr(self, "bar"):
            return
        sbw = self.bar.sizeHint().width()
        self.bar.setGeometry(self.width() - sbw, 0, sbw, self.height())
        cols = max(20, (self.width() - sbw - 2 * self.PAD) // self.cw)
        rows = max(4, (self.height() - 2 * self.PAD) // self.ch)
        if (cols, rows) != (self.screen.columns, self.screen.lines):
            self.screen.resize(rows, cols)
            self.resized.emit(cols, rows)
        self._update_bar()
        self.update()

    def size_chars(self):
        return self.screen.columns, self.screen.lines

    # ── incoming data ────────────────────────────────────────────────────────
    def feed(self, data):
        self._pending += data
        if not self._feed_timer.isActive():
            self._feed_timer.start()

    def _flush(self):
        if not self._pending:
            self._feed_timer.stop()
            return
        data, self._pending = bytes(self._pending), bytearray()
        if self.lf_to_crlf:
            data = self._lf_to_crlf(data)
        before = len(self.screen.scrollback)
        try:
            self.stream.feed(data)
        except Exception:                 # malformed sequences must never kill the view
            pass
        grown = len(self.screen.scrollback) - before
        if self.scroll and grown > 0:      # keep the view where the user scrolled to
            self.scroll = min(self.scroll + grown, len(self.screen.scrollback))
        self._update_bar()
        self.update()

    _BARE_LF = re.compile(rb"(?<!\r)\n")

    def _lf_to_crlf(self, data):
        """Insert CR before every LF that is not already preceded by CR
        (also across chunk boundaries)."""
        if not data:
            return data
        if self._last_cr and data[:1] == b"\n":
            out = b"\n" + self._BARE_LF.sub(b"\r\n", data[1:])
        else:
            out = self._BARE_LF.sub(b"\r\n", data)
        self._last_cr = data[-1:] == b"\r"
        return out

    def write_banner(self, text, color="brightblack"):
        """Status line inside the terminal (connect / disconnect)."""
        code = {"brightblack": "90", "green": "32", "red": "31", "brown": "33"}.get(color, "90")
        pre = "\r\n" if self.screen.cursor.x else ""
        self.feed(f"{pre}\x1b[{code}m── {text} ──\x1b[0m\r\n".encode("utf-8"))

    def clear(self):
        self._pending = bytearray()
        self.screen.reset()
        self.scroll = 0
        self.sel_a = self.sel_b = None
        self._update_bar()
        self.update()

    # ── view lines (scrollback + screen) ─────────────────────────────────────
    def _total(self):
        return len(self.screen.scrollback) + self.screen.lines

    def _line(self, abs_i):
        sb = self.screen.scrollback
        if abs_i < len(sb):
            return sb[abs_i]
        return self.screen.buffer[abs_i - len(sb)]

    def _first_visible(self):
        return self._total() - self.screen.lines - self.scroll

    def _update_bar(self):
        n = len(self.screen.scrollback)
        self.bar.blockSignals(True)
        self.bar.setRange(0, n)
        self.bar.setPageStep(self.screen.lines)
        self.bar.setValue(n - self.scroll)
        self.bar.blockSignals(False)

    def _bar_moved(self, v):
        self.scroll = len(self.screen.scrollback) - v
        self.update()

    def scroll_by(self, lines):
        self.scroll = max(0, min(len(self.screen.scrollback), self.scroll + lines))
        self._update_bar()
        self.update()

    def wheelEvent(self, ev):
        steps = ev.angleDelta().y() / 120
        if ev.modifiers() & Qt.ControlModifier:
            self.set_font_size(self.font_pt + (1 if steps > 0 else -1))
            return
        self.scroll_by(int(round(steps * 3)))

    # ── painting ─────────────────────────────────────────────────────────────
    def _toggle_blink(self):
        self._blink_on = not self._blink_on
        if self.hasFocus() and self.scroll == 0:
            cx, cy = self.screen.cursor.x, self.screen.cursor.y
            self.update(QRect(self.PAD + cx * self.cw, self.PAD + cy * self.ch, self.cw, self.ch))

    def _in_sel(self, ai, col):
        if self.sel_a is None or self.sel_b is None or self.sel_a == self.sel_b:
            return False
        a, b = sorted((self.sel_a, self.sel_b))
        return a <= (ai, col) < b

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), self.c_bg)
        cols, rows = self.screen.columns, self.screen.lines
        first = self._first_visible()
        dflt = self.screen.default_char
        for r in range(rows):
            ai = first + r
            if ai < 0:
                continue
            line = self._line(ai)
            y = self.PAD + r * self.ch
            line_fg = self.c_fg
            if self.tagger is not None:
                text = "".join((line[x] if x in line else dflt).data for x in range(cols))
                tag = self.tagger(text)
                line_fg = self.tag_colors.get(tag)
                if line_fg is None:
                    line_fg = self._tag_qcolor(tag) if tag.startswith("c:") else self.c_fg
            x = 0
            while x < cols:
                ch = line[x] if x in line else dflt
                fg = self._color(ch.fg, line_fg)
                bg = self._color(ch.bg, None)
                if ch.bold and ch.fg in self.ansi and not ch.fg.startswith("bright"):
                    fg = self.ansi.get("bright" + ch.fg, fg)
                if ch.reverse:
                    fg, bg = (bg or self.c_bg), fg
                sel = self._in_sel(ai, x)
                # gather a run of cells with identical attributes and draw it as one
                # string (keeps Thai vowels/tone marks and wide CJK glyphs natural);
                # every run starts on its own grid column, so nothing drifts.
                run = [ch.data]
                x2 = x + 1
                while x2 < cols:
                    c2 = line[x2] if x2 in line else dflt
                    if (c2.fg, c2.bg, c2.bold, c2.reverse, c2.underscore) != \
                       (ch.fg, ch.bg, ch.bold, ch.reverse, ch.underscore) \
                       or self._in_sel(ai, x2) != sel:
                        break
                    run.append(c2.data)           # "" for the 2nd half of a wide char
                    x2 += 1
                px = self.PAD + x * self.cw
                w = (x2 - x) * self.cw
                if sel:
                    p.fillRect(px, y, w, self.ch, self.c_sel)
                elif bg is not None:
                    p.fillRect(px, y, w, self.ch, bg)
                text = "".join(run)
                if text.strip():
                    p.setFont(self.bfont if ch.bold else self.tfont)
                    p.setPen(fg)
                    p.drawText(px, y + self.ascent, text)
                    if ch.underscore:
                        p.drawLine(px, y + self.ch - 2, px + w, y + self.ch - 2)
                x = x2
        # cursor
        cur = self.screen.cursor
        if self.scroll == 0 and not cur.hidden and cur.y < rows:
            cx = self.PAD + min(cur.x, cols - 1) * self.cw
            cy = self.PAD + cur.y * self.ch
            if self.hasFocus():
                if self._blink_on:
                    p.fillRect(cx, cy, self.cw, self.ch, self.c_accent)
                    ch = self.screen.buffer[cur.y][cur.x] if cur.x < cols else dflt
                    if ch.data.strip():
                        p.setPen(self.c_bg)
                        p.setFont(self.tfont)
                        p.drawText(cx, cy + self.ascent, ch.data)
            else:
                p.setPen(self.c_accent)
                p.drawRect(cx, cy, self.cw - 1, self.ch - 1)
        p.end()

    def focusInEvent(self, ev):
        self._blink_on = True
        self.update()
        super().focusInEvent(ev)

    def focusOutEvent(self, ev):
        self.update()
        super().focusOutEvent(ev)

    # ── selection / clipboard ────────────────────────────────────────────────
    def _cell_at(self, pos):
        col = max(0, min(self.screen.columns, (pos.x() - self.PAD + self.cw // 2) // self.cw))
        row = max(0, min(self.screen.lines - 1, (pos.y() - self.PAD) // self.ch))
        return self._first_visible() + row, col

    def mousePressEvent(self, ev):
        self.setFocus()
        if ev.button() == Qt.LeftButton:
            self.sel_a = self.sel_b = self._cell_at(ev.position().toPoint())
            self._selecting = True
            self.update()
        elif ev.button() in (Qt.RightButton, Qt.MiddleButton):
            self.paste()                  # Tera Term: right-click pastes

    def mouseMoveEvent(self, ev):
        if self._selecting:
            pos = ev.position().toPoint()
            if pos.y() < 0:
                self.scroll_by(1)
            elif pos.y() > self.height():
                self.scroll_by(-1)
            self.sel_b = self._cell_at(pos)
            self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self._selecting:
            self._selecting = False
            if self.selected_text():
                self.copy()               # Tera Term: copy on select

    def mouseDoubleClickEvent(self, ev):
        ai, col = self._cell_at(ev.position().toPoint())
        line = self._line(ai)
        text = "".join((line[x].data if x in line else " ") or " " for x in range(self.screen.columns))
        col = min(col, len(text) - 1)
        if col < 0 or not text[col].strip():
            return
        a = col
        while a > 0 and text[a - 1].strip():
            a -= 1
        b = col
        while b < len(text) and text[b].strip():
            b += 1
        self.sel_a, self.sel_b = (ai, a), (ai, b)
        self.copy()
        self.update()

    def selected_text(self):
        if self.sel_a is None or self.sel_b is None or self.sel_a == self.sel_b:
            return ""
        (a_line, a_col), (b_line, b_col) = sorted((self.sel_a, self.sel_b))
        out = []
        for ai in range(a_line, b_line + 1):
            if ai >= self._total():
                break
            line = self._line(ai)
            c0 = a_col if ai == a_line else 0
            c1 = b_col if ai == b_line else self.screen.columns
            out.append("".join((line[x].data if x in line else " ") for x in range(c0, c1)).rstrip())
        return "\n".join(out)

    def copy(self):
        t = self.selected_text()
        if t:
            QApplication.clipboard().setText(t)
            self.status.emit(f"Copied {len(t)} characters")

    def paste(self):
        text = QApplication.clipboard().text()
        if not text:
            return
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if len(lines) > 1 and lines[-1] == "":
            lines.pop()
            trailing = True
        else:
            trailing = False
        if len(lines) > 1:
            r = QMessageBox.question(self, "Paste",
                                     f"Paste {len(lines)} lines to the device?\n\n"
                                     + "\n".join(lines[:5]) + ("\n…" if len(lines) > 5 else ""))
            if r != QMessageBox.Yes:
                return
        # one line per tick so slow devices are not flooded (like Tera Term's paste delay)
        for i, ln in enumerate(lines):
            last = i == len(lines) - 1
            self._paste_queue.append(ln.encode("utf-8") + (self.enter if (not last or trailing) else b""))
        self._paste_timer.start()

    def _paste_step(self):
        if not self._paste_queue:
            self._paste_timer.stop()
            return
        self._transmit(self._paste_queue.pop(0))

    def select_all_text(self):
        return "\n".join(
            "".join((self._line(i)[x].data if x in self._line(i) else " ")
                    for x in range(self.screen.columns)).rstrip()
            for i in range(self._total())).rstrip("\n")

    # ── keyboard → device ────────────────────────────────────────────────────
    def event(self, ev):
        # keep Tab / Shift+Tab for the terminal instead of moving focus
        if ev.type() == QEvent.KeyPress and int(ev.key()) in (K(Qt.Key_Tab), K(Qt.Key_Backtab)):
            self.keyPressEvent(ev)
            return True
        return super().event(ev)

    def _transmit(self, data):
        if not data:
            return
        if not self.online:
            self.status.emit("Not connected — press Connect first")
            return
        if self.scroll:
            self.scroll = 0
            self._update_bar()
        if self.local_echo:
            self.feed(b"\r\n" if data in (b"\r", b"\r\n", b"\n") else data)
        self.send_bytes.emit(data)

    def keyPressEvent(self, ev):
        key, mods, text = int(ev.key()), ev.modifiers(), ev.text()
        ctrl = bool(mods & Qt.ControlModifier)
        shift = bool(mods & Qt.ShiftModifier)
        alt = bool(mods & Qt.AltModifier)

        # local shortcuts (Tera Term: Alt+C copy, Alt+V paste)
        if (ctrl and shift and key == K(Qt.Key_C)) or (alt and key == K(Qt.Key_C)) \
                or (ctrl and key == K(Qt.Key_Insert)):
            self.copy()
            return
        if (ctrl and shift and key == K(Qt.Key_V)) or (alt and key == K(Qt.Key_V)) \
                or (shift and key == K(Qt.Key_Insert)):
            self.paste()
            return
        if shift and key in (K(Qt.Key_PageUp), K(Qt.Key_PageDown)):
            page = self.screen.lines - 1
            self.scroll_by(page if key == K(Qt.Key_PageUp) else -page)
            return
        if ctrl and key in (K(Qt.Key_Plus), K(Qt.Key_Equal)):
            self.set_font_size(self.font_pt + 1)
            return
        if ctrl and key == K(Qt.Key_Minus):
            self.set_font_size(self.font_pt - 1)
            return

        if key in (K(Qt.Key_Return), K(Qt.Key_Enter)):
            self._transmit(self.enter)
            return
        if key == K(Qt.Key_Backspace):
            self._transmit(self.backspace)
            return
        if key in _KEYMAP:
            self._transmit(_KEYMAP[key])
            return
        if ctrl and K(Qt.Key_A) <= key <= K(Qt.Key_Z):
            self._transmit(bytes([key - K(Qt.Key_A) + 1]))      # Ctrl+C -> 0x03 …
            return
        if ctrl and key in (K(Qt.Key_Space), K(Qt.Key_At)):
            self._transmit(b"\x00")
            return
        if ctrl and key == K(Qt.Key_BracketLeft):
            self._transmit(b"\x1b")
            return
        if text:
            data = text.encode("utf-8")
            if alt:
                data = b"\x1b" + data                             # Meta prefix
            self._transmit(data)

    def inputMethodEvent(self, ev):
        if ev.commitString():
            self._transmit(ev.commitString().encode("utf-8"))
        ev.accept()
