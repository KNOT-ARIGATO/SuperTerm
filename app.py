"""SuperTerm — Serial / Telnet / SSH log viewer with RTSP video test.

One connection at a time (see sessions.py). Settings live in
%APPDATA%\\SuperTerm. Quick commands start empty; the old app's
ssh_passwords.json is only READ (saved-password picker).
"""
import sys
import threading
import traceback
import os
import re
import json
import time
from collections import deque
from string import Template

import serial
import serial.tools.list_ports
from sessions import SerialSession, TelnetSession, SshSession
from quickstore import QuickStore, PROTOCOLS, detect_import
from nature import NATURE
from terminal import TerminalWidget, ENTER_CODES, BS_CODES
import updater
from PySide6.QtCore import Qt, Signal, QTimer, QSettings, QUrl, QRect, QSize, QPoint, QObject
from PySide6.QtGui import QFont, QTextCharFormat, QColor, QTextCursor, QIcon, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QComboBox,
    QLineEdit, QPlainTextEdit, QCheckBox, QStackedWidget, QButtonGroup,
    QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QFileDialog, QScrollArea, QTabBar,
    QSizePolicy, QDialog, QMenu, QInputDialog, QMessageBox, QRadioButton, QLayout, QProgressBar,
)

MAX_LOG_LINES = 50000
FLUSH_MS = 40            # log output is batched: one UI update per 40 ms ...
FLUSH_MAX = 1500         # ... of at most this many lines
APP_NAME = "SuperTerm"
APP_VERSION = "1.0.2"
OLD_NAMES = ("SuperTeam", "UartLogViewer")   # earlier names of this app (settings migration)


def resource_path(rel):
    """Bundled read-only file (works from source and from the PyInstaller build)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def user_data_dir():
    """Writable per-user settings folder: %APPDATA%\\SuperTerm.
    Settings of earlier builds (SuperTeam / UartLogViewer) are copied over once."""
    root = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(root, "SuperTerm")
    try:
        if not os.path.isdir(d):
            for old_name in OLD_NAMES:
                old = os.path.join(root, old_name)
                if os.path.isdir(old):
                    import shutil
                    shutil.copytree(old, d)
                    break
        os.makedirs(d, exist_ok=True)
    except OSError:
        d = os.path.expanduser("~")
    return d


def legacy_dirs():
    """Places the old Tkinter app may have left its settings files."""
    here = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    home = os.path.expanduser("~")
    return [os.getcwd(), here, os.path.join(here, ".."),
            os.path.join(home, "Desktop", "UART"), os.path.join(home, "Desktop")]


def install_crash_handler():
    """Never die silently: write the traceback to crash.log and tell the user."""
    log = os.path.join(user_data_dir(), "crash.log")

    def record(text):
        try:
            with open(log, "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n" + text + "\n")
        except OSError:
            pass

    def hook(et, ev, tb):
        record("".join(traceback.format_exception(et, ev, tb)))
        try:
            QMessageBox.critical(None, APP_NAME,
                                 f"Unexpected error:\n{ev}\n\nDetails were saved to:\n{log}")
        except Exception:
            pass

    sys.excepthook = hook
    threading.excepthook = lambda a: record("".join(
        traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback)))

# ─────────────────────────────────────────────────────────────
#  Themes (same palette tokens as the Tkinter version)
# ─────────────────────────────────────────────────────────────
THEMES = {
    # same colours as the original SuperSerial program — the calm default
    "Classic Dark": dict(
        BG="#0d1117", PANEL="#161b22", INPUT="#21262d", BORDER="#30363d",
        ACCENT="#58a6ff", ACCENT2="#3fb950", WARN="#f85149", TEXT="#e6edf3",
        DIM="#8b949e", MAUVE="#bc8cff", SKY="#79c0ff", PEACH="#ffa657",
        YELLOW="#e3b341", ON_ACCENT="#0d1117"),
    "Classic Light": dict(
        BG="#f6f8fa", PANEL="#ffffff", INPUT="#f6f8fa", BORDER="#d0d7de",
        ACCENT="#0969da", ACCENT2="#1a7f37", WARN="#cf222e", TEXT="#1f2328",
        DIM="#656d76", MAUVE="#8250df", SKY="#218bff", PEACH="#bc4c00",
        YELLOW="#9a6700", ON_ACCENT="#ffffff"),
    "Sakura Night": dict(
        BG="#1e1e2e", PANEL="#27273b", INPUT="#34344d", BORDER="#4a4a68",
        ACCENT="#f5c2e7", ACCENT2="#a6e3a1", WARN="#f38ba8", TEXT="#cdd6f4",
        DIM="#9399b2", MAUVE="#cba6f7", SKY="#89dceb", PEACH="#fab387",
        YELLOW="#f9e2af", ON_ACCENT="#1e1e2e"),
    "Ocean Breeze": dict(
        BG="#0f1b2d", PANEL="#172a43", INPUT="#223a5a", BORDER="#36557f",
        ACCENT="#7cc4ff", ACCENT2="#7ee8c0", WARN="#ff8fa3", TEXT="#dbe9ff",
        DIM="#8aa3c4", MAUVE="#b9a5ff", SKY="#8be9fd", PEACH="#ffb88c",
        YELLOW="#ffe08a", ON_ACCENT="#0f1b2d"),
    "Matcha Forest": dict(
        BG="#1a2320", PANEL="#232f2b", INPUT="#2f3e39", BORDER="#466057",
        ACCENT="#b5e48c", ACCENT2="#76e0a8", WARN="#ff8a80", TEXT="#e4f1e6",
        DIM="#94ab9d", MAUVE="#cdb4db", SKY="#9bf6ff", PEACH="#ffc09f",
        YELLOW="#fdf0a6", ON_ACCENT="#1a2320"),
    "Sunset Peach": dict(
        BG="#2a1f2d", PANEL="#35293a", INPUT="#43344a", BORDER="#5d4a66",
        ACCENT="#ffb386", ACCENT2="#b8e986", WARN="#ff6b81", TEXT="#fbeee6",
        DIM="#b5a0b8", MAUVE="#d6a5ff", SKY="#8edcff", PEACH="#ffa07a",
        YELLOW="#ffe08a", ON_ACCENT="#2a1f2d"),
    "Cream Light": dict(
        BG="#f6f1ea", PANEL="#fffaf3", INPUT="#ebe3d8", BORDER="#d4c8b8",
        ACCENT="#d6336c", ACCENT2="#2f9e6b", WARN="#e03131", TEXT="#3b3340",
        DIM="#857a8a", MAUVE="#7048e8", SKY="#1c7ed6", PEACH="#e8590c",
        YELLOW="#b8860b", ON_ACCENT="#fffaf3"),
}
DEFAULT_THEME = "Classic Dark"
LIGHT_THEMES = {"Classic Light", "Cream Light"}


def _mix(a, b, t):
    """Blend hex colour a toward b by t (0..1)."""
    x = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    y = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(u + (v - u) * t) for u, v in zip(x, y))


def derive(p):
    """Extra shades used by the stylesheet (soft tints, hover stops)."""
    return dict(
        HOVER=_mix(p["INPUT"], p["TEXT"], .08),
        ACCENT_SOFT=_mix(p["ACCENT"], p["PANEL"], .86),
        ACCENT_H=_mix(p["ACCENT"], "#ffffff", .15),
        OK_H=_mix(p["ACCENT2"], "#ffffff", .15),
        WARN_SOFT=_mix(p["WARN"], p["PANEL"], .86),
    )


QSS = Template("""
* { font-family: "Segoe UI", "Leelawadee UI", sans-serif; font-size: 12px; }
QMainWindow, QWidget#root { background: $BG; }
QWidget { color: $TEXT; }
QLabel { background: transparent; }
QLabel#title { font-size: 15px; font-weight: 700; color: $TEXT; }
QLabel#subtitle, QLabel#hint, QLabel#field, QLabel#empty { color: $DIM; }
QLabel#hint { font-size: 10px; }
QLabel#section { font-weight: 700; color: $DIM; font-size: 10px; letter-spacing: 1px; }
QLabel#mono { font-family: Consolas, monospace; color: $DIM; font-size: 10px; }
QLabel#badge { background: $INPUT; color: $DIM; border: 1px solid $BORDER; border-radius: 6px;
               padding: 1px 7px; font-size: 9px; font-weight: 700; }

QFrame#card { background: $PANEL; border: 1px solid $BORDER; border-radius: 10px; }
QFrame#header { background: $PANEL; border-bottom: 1px solid $BORDER; }

QLabel#pill { padding: 4px 10px; border-radius: 11px; background: $INPUT; color: $DIM;
              border: 1px solid $BORDER; font-weight: 600; }
QLabel#pill[state="on"]   { color: $ACCENT2; border: 1px solid $ACCENT2; }
QLabel#pill[state="busy"] { color: $YELLOW; border: 1px solid $YELLOW; }
QLabel#pill[state="err"]  { color: $WARN; border: 1px solid $WARN; }
QWidget#videoWin { background: $BG; }
QFrame#videoSurface { background: #000000; border: 1px solid $BORDER; border-radius: 8px; }

QPushButton { background: $INPUT; color: $TEXT; border: 1px solid $BORDER; border-radius: 7px;
              padding: 4px 12px; font-weight: 600; min-height: 18px; }
QPushButton:hover { background: $HOVER; }
QPushButton:pressed { background: $PANEL; }
QPushButton:disabled { color: $DIM; background: $PANEL; border: 1px solid $BORDER; }
QPushButton#primary { background: $ACCENT; color: $ON_ACCENT; border: 1px solid $ACCENT; }
QPushButton#primary:hover { background: $ACCENT_H; }
QPushButton#primary:disabled { background: $PANEL; color: $DIM; border: 1px solid $BORDER; }
QPushButton#success { background: $ACCENT2; color: $ON_ACCENT; border: 1px solid $ACCENT2; }
QPushButton#success:hover { background: $OK_H; }
QPushButton#success:disabled { background: $PANEL; color: $DIM; border: 1px solid $BORDER; }
QPushButton#danger { background: $INPUT; color: $WARN; border: 1px solid $WARN; }
QPushButton#danger:hover { background: $WARN_SOFT; }
QPushButton#danger:disabled { background: $PANEL; color: $DIM; border: 1px solid $BORDER; }
QPushButton#quick { background: $INPUT; color: $TEXT; padding: 3px 10px; min-height: 18px; }
QPushButton#quick:hover { color: $ACCENT; border: 1px solid $ACCENT; }
QPushButton#quick[offline="true"] { color: $DIM; }
QPushButton#icon { padding: 0; min-height: 26px; }
QPushButton#tool[hasMenu="true"] { padding-right: 28px; }
QPushButton#tool::menu-indicator { image: url($ARROW_URL); subcontrol-origin: padding;
                                   subcontrol-position: center right; right: 9px; width: 10px; height: 10px; }

QFrame#segbar { background: $BG; border-radius: 8px; border: 1px solid $BORDER; }
QPushButton[seg="true"] { background: transparent; color: $DIM; border: none; border-radius: 6px; padding: 4px 14px; }
QPushButton[seg="true"]:hover { color: $TEXT; background: $INPUT; }
QPushButton[seg="true"]:checked { background: $ACCENT; color: $ON_ACCENT; }
QPushButton[seg="true"]:disabled { background: transparent; color: $BORDER; }
QPushButton[seg="true"]:checked:disabled { background: $ACCENT; color: $ON_ACCENT; }

QTabBar { background: transparent; }
QTabBar::tab { background: transparent; color: $DIM; padding: 3px 10px; margin-right: 2px;
               border: 1px solid transparent; border-radius: 6px; font-weight: 600; }
QTabBar::tab:hover { color: $TEXT; background: $INPUT; }
QTabBar::tab:selected { color: $ACCENT; background: $ACCENT_SOFT; border: 1px solid $ACCENT; }
QTabBar QToolButton { background: $INPUT; border: 1px solid $BORDER; border-radius: 6px; }

QDialog, QMessageBox, QInputDialog { background: $PANEL; }
QMenu { background: $PANEL; border: 1px solid $BORDER; border-radius: 8px; padding: 5px; }
QMenu::item { padding: 6px 18px; border-radius: 5px; }
QMenu::item:selected { background: $ACCENT; color: $ON_ACCENT; }
QMenu::separator { height: 1px; background: $BORDER; margin: 5px 8px; }

QLineEdit, QComboBox { background: $INPUT; border: 1px solid $BORDER; border-radius: 7px;
                       padding: 3px 8px; min-height: 18px; selection-background-color: $ACCENT; selection-color: $ON_ACCENT; }
QLineEdit:focus, QComboBox:focus { border: 1px solid $ACCENT; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow { image: url($ARROW_URL); width: 11px; height: 11px; margin-right: 7px; }
QComboBox QAbstractItemView { background: $INPUT; border: 1px solid $BORDER; border-radius: 6px;
                              selection-background-color: $ACCENT; selection-color: $ON_ACCENT; outline: 0; padding: 3px; }

QFrame#termframe { background: $BG; border: 1px solid $BORDER; border-radius: 8px; }
QPlainTextEdit#log { background: $BG; border: 1px solid $BORDER; border-radius: 8px; padding: 6px;
                     selection-background-color: $ACCENT; selection-color: $ON_ACCENT; }

QCheckBox, QRadioButton { spacing: 8px; color: $DIM; padding: 3px 0; }
QRadioButton { color: $TEXT; }
QCheckBox::indicator { width: 15px; height: 15px; border-radius: 4px; border: 1px solid $BORDER; background: $INPUT; }
QCheckBox::indicator:checked { background: $ACCENT; border: 1px solid $ACCENT; image: url($CHECK_URL); }
QRadioButton::indicator { width: 15px; height: 15px; border-radius: 8px; border: 1px solid $BORDER; background: $INPUT; }
QRadioButton::indicator:checked { border: 1px solid $ACCENT; background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
                                  fx:0.5, fy:0.5, stop:0 $ACCENT, stop:0.5 $ACCENT, stop:0.6 $INPUT, stop:1 $INPUT); }

QScrollArea { border: none; background: transparent; }
QWidget#qcont { background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $BORDER; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: $DIM; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: $BORDER; border-radius: 4px; min-width: 30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QToolTip { background: $INPUT; color: $TEXT; border: 1px solid $BORDER; }
QProgressBar { background: $INPUT; border: 1px solid $BORDER; border-radius: 6px; text-align: center;
               color: $TEXT; min-height: 18px; }
QProgressBar::chunk { background: $ACCENT; border-radius: 5px; }
""")

def load_saved_passwords_readonly():
    """Read the old app's ssh_passwords.json (never writes it)."""
    for d in legacy_dirs():
        try:
            with open(os.path.join(d, "ssh_passwords.json"), "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [e for e in data if isinstance(e, dict) and "label" in e and "password" in e]
        except Exception:
            continue
    return []


def auto_tag(text):
    lo = text.lower()
    if re.search(r"\b(err|fail|fatal|exception)", lo):
        return "error"
    if re.search(r"\b(warn|caution)", lo):
        return "warn"
    if re.search(r"\b(ok|pass|passed|success|successful|done|connected)\b", lo):
        return "success"
    return "info"


# ─────────────────────────────────────────────────────────────
#  Main window
# ─────────────────────────────────────────────────────────────
class FlowLayout(QLayout):
    """Lays widgets out left-to-right and wraps to the next line when full."""

    def __init__(self, parent=None, spacing=8):
        super().__init__(parent)
        self._items = []
        self._sp = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._arrange(QRect(0, 0, w, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        return s

    def _arrange(self, rect, test):
        x, y, line_h = rect.x(), rect.y(), 0
        for it in self._items:
            hint = it.sizeHint()
            if x > rect.x() and x + hint.width() > rect.right() + 1:
                x, y, line_h = rect.x(), y + line_h + self._sp, 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._sp
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y()


class CmdDialog(QDialog):
    def __init__(self, parent, title, label="", cmd=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 22)
        v.setSpacing(14)
        f = QFormLayout()
        f.setHorizontalSpacing(16)
        f.setVerticalSpacing(14)
        self.label = QLineEdit(label)
        self.cmd = QLineEdit(cmd)
        self.cmd.setFont(MainWindow._mono(10))
        f.addRow("Button label", self.label)
        f.addRow("Command", self.cmd)
        v.addLayout(f)
        hint = QLabel("Use  |  to send several commands in sequence.")
        hint.setObjectName("hint")
        v.addWidget(hint)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.setDefault(True)
        save.clicked.connect(self._accept)
        row.addWidget(cancel)
        row.addWidget(save)
        v.addLayout(row)

    def _accept(self):
        if self.label.text().strip() and self.cmd.text().strip():
            self.accept()
        else:
            QMessageBox.warning(self, "Missing", "Both label and command are required.")

    def values(self):
        return self.label.text().strip(), self.cmd.text().strip()


class ImportDialog(QDialog):
    """Shows what an import file contains and asks where / how to import it."""
    BROWSE = 2

    LABELS = {"serial": "Serial", "telnet": "Telnet", "ssh": "SSH"}

    def __init__(self, parent, path, kind, payload, current_proto):
        super().__init__(parent)
        self.kind, self.payload = kind, payload
        self.setWindowTitle("Import quick commands")
        self.setMinimumWidth(520)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 22)
        v.setSpacing(14)

        head = QLabel("📥  Import quick commands")
        head.setObjectName("section")
        v.addWidget(head)
        name = QLabel(f"📄  <b>{os.path.basename(path)}</b>")
        v.addWidget(name)
        src = QLabel()
        src.setObjectName("mono")
        src.setText(src.fontMetrics().elidedText(os.path.dirname(path), Qt.ElideMiddle, 470))
        src.setToolTip(path)
        v.addWidget(src)

        if kind == "legacy":
            fmt = "Old program — SuperSerial (quick_commands.json)"
            lines = [f"• {p['name']}  —  {len(p['cmds'])} command(s)" for p in payload]
        else:
            fmt = "SuperTerm export"
            lines = [f"• {self.LABELS[k]}:  {len(v_)} tab(s), {sum(len(x['cmds']) for x in v_)} command(s)"
                     for k, v_ in payload.items() if v_]
        info = QLabel(f"<b>{fmt}</b><br>" + "<br>".join(lines))
        info.setWordWrap(True)
        v.addWidget(info)

        f = QFormLayout()
        f.setHorizontalSpacing(16)
        f.setVerticalSpacing(12)
        self.target = None
        if kind == "legacy":
            # the old program had no protocols: let the user choose
            self.target = QComboBox()
            for key, lab in self.LABELS.items():
                self.target.addItem(lab, [key])
            self.target.addItem("All three (Serial + Telnet + SSH)", list(PROTOCOLS))
            self.target.setCurrentIndex(PROTOCOLS.index(current_proto))
            f.addRow("Import into", self.target)
        v.addLayout(f)

        self.merge = QRadioButton("Merge — keep my commands, add the new ones (no duplicates)")
        self.replace = QRadioButton("Replace — remove my tabs first, then import")
        self.merge.setChecked(True)
        v.addWidget(self.merge)
        v.addWidget(self.replace)

        row = QHBoxLayout()
        row.setSpacing(10)
        browse = QPushButton("📂  Choose another file…")
        browse.clicked.connect(lambda: self.done(self.BROWSE))
        row.addWidget(browse)
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Import")
        ok.setObjectName("primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        v.addLayout(row)

    def targets(self):
        if self.kind == "legacy":
            return self.target.currentData()
        return [k for k, v in self.payload.items() if v]

    def profiles_for(self, proto):
        return self.payload if self.kind == "legacy" else self.payload[proto]

    def replace_mode(self):
        return self.replace.isChecked()


class _UpdateSignals(QObject):
    progress = Signal(int, int)
    done = Signal(str)
    failed = Signal(str)


class UpdateDialog(QDialog):
    """Shows what is new and installs the update (download → verify → swap)."""

    def __init__(self, parent, info, before_install):
        super().__init__(parent)
        self.info = info
        self.before_install = before_install
        self.installed = False
        self._cancel = False
        self.setWindowTitle("Update SuperTerm")
        self.setMinimumWidth(520)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 22)
        v.setSpacing(12)
        head = QLabel(f"<b>SuperTerm {info['version']}</b> is available "
                      f"&nbsp;·&nbsp; you have v{APP_VERSION}")
        v.addWidget(head)
        notes = QPlainTextEdit(info.get("notes") or "(no release notes)")
        notes.setReadOnly(True)
        notes.setMinimumHeight(160)
        v.addWidget(notes)
        hint = QLabel("Your quick commands and settings are kept. SuperTerm restarts after the update.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        v.addWidget(hint)
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        v.addWidget(self.bar)
        self.msg = QLabel("")
        self.msg.setObjectName("hint")
        self.msg.setWordWrap(True)
        v.addWidget(self.msg)
        row = QHBoxLayout()
        row.setSpacing(10)
        page = QPushButton("Release page")
        page.setEnabled(bool(info.get("page")))
        page.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(info["page"])))
        row.addWidget(page)
        row.addStretch(1)
        self.btn_later = QPushButton("Later")
        self.btn_later.clicked.connect(self.reject)
        self.btn_go = QPushButton("Install now")
        self.btn_go.setObjectName("primary")
        self.btn_go.setDefault(True)
        self.btn_go.clicked.connect(self._start)
        row.addWidget(self.btn_later)
        row.addWidget(self.btn_go)
        v.addLayout(row)
        self.sig = _UpdateSignals()
        self.sig.progress.connect(self._progress)
        self.sig.done.connect(self._downloaded)
        self.sig.failed.connect(self._failed)

    def _start(self):
        if updater.running_exe() is None:
            self.msg.setText("Running from source code — download the new SuperTerm.exe from the release page.")
            return
        self.btn_go.setEnabled(False)
        self.bar.setVisible(True)
        self.bar.setRange(0, 0)
        self.msg.setText("Downloading…")

        def work():
            try:
                path = updater.fetch(self.info, lambda d, t_: self.sig.progress.emit(d, t_),
                                     lambda: self._cancel)
                self.sig.done.emit(path)
            except updater.UpdateError as e:
                self.sig.failed.emit(str(e))
            except Exception as e:                    # never leave the dialog hanging
                self.sig.failed.emit(f"Unexpected error: {e}")
        threading.Thread(target=work, daemon=True).start()

    def _progress(self, done, total):
        if total > 0:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(done * 1000 / total))
            self.bar.setFormat(f"{done / 1e6:.1f} / {total / 1e6:.1f} MB")

    def _downloaded(self, path):
        self.msg.setText("Installing…")
        try:
            self.before_install()                       # e.g. close the COM port first
            updater.install(path)
        except updater.UpdateError as e:
            self._failed(str(e))
            return
        self.installed = True
        self.accept()

    def _failed(self, err):
        self.bar.setVisible(False)
        self.btn_go.setEnabled(True)
        self.msg.setText(f"Update failed: {err}")

    def reject(self):
        self._cancel = True
        super().reject()


class VideoWindow(QWidget):
    """RTSP camera test — its own window, independent of the log connection."""

    def __init__(self, default_host=""):
        super().__init__()
        self.setObjectName("videoWin")
        self.setWindowTitle("🎥 RTSP video test")
        self.resize(820, 560)
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(12)

        row = QHBoxLayout()
        row.addWidget(QLabel("IP"))
        self.host = QLineEdit(default_host or "192.168.1.1")
        self.host.setFixedWidth(170)
        row.addWidget(self.host)
        row.addWidget(QLabel("Path"))
        self.path = QLineEdit("/profile1")
        self.path.setFixedWidth(140)
        row.addWidget(self.path)
        self.btn_play = QPushButton("▶  Open video")
        self.btn_play.setObjectName("primary")
        self.btn_stop = QPushButton("■  Close")
        self.btn_stop.setObjectName("danger")
        self.btn_stop.setEnabled(False)
        row.addWidget(self.btn_play)
        row.addWidget(self.btn_stop)
        row.addStretch(1)
        self.status = QLabel("●  Not connected")
        self.status.setObjectName("pill")
        self.status.setProperty("state", "off")
        row.addWidget(self.status)
        v.addLayout(row)

        surface = QFrame()
        surface.setObjectName("videoSurface")
        sl = QVBoxLayout(surface)
        sl.setContentsMargins(2, 2, 2, 2)
        self.player = None
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtMultimediaWidgets import QVideoWidget
            self.video = QVideoWidget()
            sl.addWidget(self.video)
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.player.setAudioOutput(self.audio)
            self.player.setVideoOutput(self.video)
            self.player.errorOccurred.connect(self._on_error)
            self.player.playbackStateChanged.connect(self._on_state)
            self.player.mediaStatusChanged.connect(self._on_media_status)
        except ImportError:
            msg = QLabel("QtMultimedia is not available in this PySide6 install.")
            msg.setAlignment(Qt.AlignCenter)
            sl.addWidget(msg)
            self.btn_play.setEnabled(False)
        v.addWidget(surface, 1)

        self.btn_play.clicked.connect(self.play)
        self.btn_stop.clicked.connect(self.stop)
        self.host.returnPressed.connect(self.play)

    def _pill(self, text, state):
        self.status.setText(text)
        self.status.setProperty("state", state)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def url(self):
        path = self.path.text().strip() or "/profile1"
        if not path.startswith("/"):
            path = "/" + path
        return f"rtsp://{self.host.text().strip()}{path}"

    def play(self):
        if self.player is None or not self.host.text().strip():
            return
        self.player.stop()
        self.player.setSource(QUrl(self.url()))
        self.player.play()
        self.btn_play.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._pill("●  Connecting…", "busy")

    def stop(self):
        if self.player is None:
            return
        self.player.stop()
        self.player.setSource(QUrl())
        self.btn_play.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._pill("●  Not connected", "off")

    def _on_state(self, state):
        from PySide6.QtMultimedia import QMediaPlayer
        if state == QMediaPlayer.PlayingState:
            self._pill("●  Playing", "on")

    def _on_media_status(self, st):
        from PySide6.QtMultimedia import QMediaPlayer
        if st in (QMediaPlayer.InvalidMedia, QMediaPlayer.EndOfMedia):
            self._pill("●  Stopped", "err")
            self.btn_play.setEnabled(True)
            self.btn_stop.setEnabled(False)

    def _on_error(self, _err, text):
        self._pill("●  Failed", "err")
        self.status.setToolTip(text)
        self.btn_play.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def closeEvent(self, ev):
        self.stop()
        super().closeEvent(ev)


class MainWindow(QMainWindow):
    # worker threads emit these; Qt delivers them on the GUI thread
    sig_line = Signal(object, str)
    sig_info = Signal(object, str, str)
    sig_opened = Signal(object)
    sig_closed = Signal(object, str, bool)
    sig_data = Signal(object, bytes)
    sig_update = Signal(object, str, bool)     # info, error, manual

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 860)
        self.setMinimumSize(1000, 640)

        self.settings = QSettings("SuperTerm", "SuperTerm")
        if self.settings.value("theme") is None:          # carry over theme / window size once
            for old_name in OLD_NAMES:
                old = QSettings(old_name, old_name)
                if old.value("theme") is not None:
                    for k in ("theme", "geometry"):
                        if old.value(k) is not None:
                            self.settings.setValue(k, old.value(k))
                    break
        self._pending = []                     # log lines waiting for the next batched flush
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(FLUSH_MS)
        self._flush_timer.timeout.connect(self._flush)
        self.theme_name = self.settings.value("theme", DEFAULT_THEME)
        if self.theme_name not in THEMES:
            self.theme_name = DEFAULT_THEME

        self.session = None          # the ONE active connection (or None)
        self.token = None            # identifies the current session; stale signals are dropped
        self.opened = False
        self.video_win = None
        self.sig_line.connect(self._on_line)
        self.sig_info.connect(self._on_info)
        self.sig_opened.connect(self._on_opened)
        self.sig_closed.connect(self._on_closed)
        self.sig_data.connect(self._on_data)
        self.sig_update.connect(self._on_update_checked)
        self._update_info = None
        self.t0 = time.monotonic()
        self.log_lines = deque(maxlen=MAX_LOG_LINES)   # (text, tag, is_sys)
        self.history = []
        self.hist_idx = -1
        self.store = QuickStore(os.path.join(user_data_dir(), "quick_commands_by_protocol.json"))
        self.quick_buttons = []

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())

        body = QVBoxLayout()
        body.setContentsMargins(14, 12, 14, 6)
        body.setSpacing(10)
        body.addWidget(self._build_connection())
        body.addWidget(self._build_quick())
        body.addWidget(self._build_send())
        body.addWidget(self._build_log_area(), 1)
        outer.addLayout(body, 1)

        self.status_lines = QLabel("Lines: 0")
        self.status_lines.setObjectName("hint")
        self.status_port = QLabel("")
        self.status_port.setObjectName("hint")
        bar = QHBoxLayout()
        bar.setContentsMargins(18, 0, 18, 8)
        bar.addWidget(self.status_lines)
        bar.addSpacing(24)
        self.status_msg = QLabel("")
        self.status_msg.setObjectName("hint")
        bar.addWidget(self.status_msg)
        bar.addStretch(1)
        bar.addWidget(self.status_port)
        outer.addLayout(bar)

        geo = self.settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)
        self.apply_theme(self.theme_name)
        self.refresh_ports()
        self.refresh_quick()
        self._set_ui_state("idle")
        self.log_sys("Ready — pick ONE protocol (Serial / Telnet / SSH) and press Connect.", "info")
        updater.cleanup_old()                       # leftovers of the previous update
        QTimer.singleShot(4000, self._auto_check_update)

    # ── building blocks ──────────────────────────────────────────────────────
    def _card(self):
        f = QFrame()
        f.setObjectName("card")
        return f

    def _section(self, text, width=None):
        lab = QLabel(text)
        lab.setObjectName("section")
        if width:
            lab.setFixedWidth(width)
        return lab

    def _field(self, text):
        lab = QLabel(text)
        lab.setObjectName("field")
        return lab

    def _row(self):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        return w, h

    def _build_header(self):
        h = QFrame()
        h.setObjectName("header")
        lay = QHBoxLayout(h)
        lay.setContentsMargins(18, 8, 18, 8)
        lay.setSpacing(10)
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        self.title_lbl = title
        sub = QLabel(f"Serial · Telnet · SSH · RTSP   ·   v{APP_VERSION}")
        sub.setObjectName("subtitle")
        lay.addWidget(title)
        lay.addWidget(sub, 0, Qt.AlignVCenter)
        lay.addStretch(1)

        self.btn_update = QPushButton("Check updates")
        self.btn_update.setToolTip("Look for a newer SuperTerm on GitHub")
        self.btn_update.clicked.connect(self.update_clicked)
        lay.addWidget(self.btn_update)
        video_btn = QPushButton("RTSP Video")
        video_btn.setToolTip("Separate camera test window — independent of the log connection")
        video_btn.clicked.connect(self.open_video)
        lay.addWidget(video_btn)
        lay.addSpacing(6)
        lay.addWidget(self._field("Theme"))
        self.theme_cb = QComboBox()
        for n in THEMES:
            self.theme_cb.addItem(f"{NATURE[n]['logo']}  {n}", n)
        self.theme_cb.setCurrentIndex(max(0, self.theme_cb.findData(self.theme_name)))
        self.theme_cb.currentIndexChanged.connect(
            lambda i: self.apply_theme(self.theme_cb.itemData(i)))
        self.theme_cb.setMinimumWidth(160)
        lay.addWidget(self.theme_cb)
        lay.addSpacing(6)
        self.pill = QLabel("●  Disconnected")
        self.pill.setObjectName("pill")
        self.pill.setProperty("state", "off")
        lay.addWidget(self.pill)
        return h

    SECTION_W = 120      # left label column, keeps the three bars aligned

    def _build_connection(self):
        card = self._card()
        v = QVBoxLayout(card)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(10)
        self.sec_conn = self._section("CONNECTION", self.SECTION_W)
        top.addWidget(self.sec_conn)
        seg = QFrame()
        seg.setObjectName("segbar")
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(3, 3, 3, 3)
        sl.setSpacing(2)
        self.seg_group = QButtonGroup(self)
        self.stack = QStackedWidget()
        for i, name in enumerate(("Serial", "Telnet", "SSH")):
            b = QPushButton(name)
            b.setCheckable(True)
            b.setProperty("seg", True)
            b.setCursor(Qt.PointingHandCursor)
            self.seg_group.addButton(b, i)
            sl.addWidget(b)
            if i == 0:
                b.setChecked(True)
        self.seg_group.idClicked.connect(self.stack.setCurrentIndex)
        self.seg_group.idClicked.connect(lambda _: self.refresh_quick())
        top.addWidget(seg)
        hint = self._field("one connection at a time")
        hint.setObjectName("hint")
        top.addWidget(hint)
        top.addStretch(1)
        self.btn_connect = QPushButton("▶  Connect")
        self.btn_connect.setObjectName("success")
        self.btn_connect.setMinimumWidth(120)
        self.btn_connect.clicked.connect(self.connect_session)
        self.btn_disconnect = QPushButton("■  Disconnect")
        self.btn_disconnect.setObjectName("danger")
        self.btn_disconnect.setMinimumWidth(120)
        self.btn_disconnect.clicked.connect(self.disconnect_session)
        top.addWidget(self.btn_connect)
        top.addWidget(self.btn_disconnect)
        v.addLayout(top)

        fields = QHBoxLayout()
        fields.setSpacing(10)
        fields.addSpacing(self.SECTION_W + 10)
        self.stack.addWidget(self._page_serial())
        self.stack.addWidget(self._page_telnet())
        self.stack.addWidget(self._page_ssh())
        fields.addWidget(self.stack, 1)
        v.addLayout(fields)
        return card

    def _page_serial(self):
        w, h = self._row()
        self.port_cb = QComboBox()
        self.port_cb.setMinimumWidth(110)
        refresh = QPushButton("⟳")
        refresh.setObjectName("icon")
        refresh.setFixedWidth(34)
        refresh.setToolTip("Refresh ports")
        refresh.clicked.connect(self.refresh_ports)
        self.baud_cb = QComboBox()
        self.baud_cb.addItems(["9600", "19200", "38400", "57600", "115200",
                               "230400", "460800", "921600"])
        self.baud_cb.setCurrentText("115200")
        self.data_cb = QComboBox(); self.data_cb.addItems(["5", "6", "7", "8"]); self.data_cb.setCurrentText("8")
        self.parity_cb = QComboBox(); self.parity_cb.addItems(["None", "Even", "Odd", "Mark", "Space"])
        self.stop_cb = QComboBox(); self.stop_cb.addItems(["1", "1.5", "2"])
        h.addWidget(self._field("COM Port"))
        h.addWidget(self.port_cb)
        h.addWidget(refresh)
        for lbl, cb in (("Baud", self.baud_cb), ("Data", self.data_cb),
                        ("Parity", self.parity_cb), ("Stop", self.stop_cb)):
            h.addSpacing(8)
            h.addWidget(self._field(lbl))
            h.addWidget(cb)
        h.addStretch(1)
        return w

    def _page_telnet(self):
        w, h = self._row()
        self.tn_host = QLineEdit("192.168.1.1")
        self.tn_host.setFixedWidth(150)
        self.tn_port = QLineEdit("23")
        self.tn_port.setFixedWidth(64)
        self.tn_ping = QCheckBox("Ping first · auto-reconnect")
        self.tn_ping.setToolTip("Waits until the host answers ping, then connects.\n"
                                "If the host goes away it reconnects by itself.")
        self.tn_interval = QComboBox()
        self.tn_interval.addItems(["1", "2", "3", "5", "10"])
        self.tn_interval.setCurrentText("2")
        h.addWidget(self._field("IP"))
        h.addWidget(self.tn_host)
        h.addSpacing(8)
        h.addWidget(self._field("Port"))
        h.addWidget(self.tn_port)
        h.addSpacing(16)
        h.addWidget(self.tn_ping)
        h.addWidget(self._field("every"))
        h.addWidget(self.tn_interval)
        h.addWidget(self._field("s"))
        h.addStretch(1)
        return w

    def _page_ssh(self):
        w, h = self._row()
        self.ssh_host = QLineEdit("192.168.1.1")
        self.ssh_host.setFixedWidth(150)
        self.ssh_port = QLineEdit("22")
        self.ssh_port.setFixedWidth(64)
        self.ssh_user = QLineEdit("root")
        self.ssh_user.setFixedWidth(110)
        self.ssh_pass = QLineEdit()
        self.ssh_pass.setEchoMode(QLineEdit.Password)
        self.ssh_pass.setFixedWidth(140)
        for lbl, wid in (("IP", self.ssh_host), ("Port", self.ssh_port),
                         ("User", self.ssh_user), ("Password", self.ssh_pass)):
            h.addWidget(self._field(lbl))
            h.addWidget(wid)
            h.addSpacing(8)
        saved = load_saved_passwords_readonly()
        if saved:
            self.saved_cb = QComboBox()
            self.saved_cb.addItem("Saved passwords…")
            for e in saved:
                self.saved_cb.addItem(e["label"], e["password"])
            self.saved_cb.activated.connect(
                lambda i: self.ssh_pass.setText(self.saved_cb.itemData(i) or ""))
            h.addWidget(self.saved_cb)
        h.addStretch(1)
        return w

    def _build_quick(self):
        """Quick commands bar — shows ONLY the commands of the selected protocol."""
        card = self._card()
        v = QVBoxLayout(card)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(8)
        sec = QWidget()
        sec.setFixedWidth(self.SECTION_W)
        sh = QHBoxLayout(sec)
        sh.setContentsMargins(0, 0, 0, 0)
        sh.setSpacing(6)
        self.sec_quick = self._section("QUICK CMD")
        sh.addWidget(self.sec_quick)
        self.proto_badge = QLabel("SERIAL")
        self.proto_badge.setObjectName("badge")
        sh.addWidget(self.proto_badge, 0, Qt.AlignVCenter)
        sh.addStretch(1)
        top.addWidget(sec)
        top.addSpacing(2)

        self.qtabs = QTabBar()
        self.qtabs.setObjectName("qtabs")
        self.qtabs.setExpanding(False)
        self.qtabs.setDrawBase(False)
        self.qtabs.setUsesScrollButtons(True)
        self.qtabs.setElideMode(Qt.ElideNone)
        self.qtabs.setCursor(Qt.PointingHandCursor)
        self.qtabs.setContextMenuPolicy(Qt.CustomContextMenu)
        self.qtabs.customContextMenuRequested.connect(self._tab_menu)
        self.qtabs.currentChanged.connect(self._profile_changed)
        self.qtabs.tabBarDoubleClicked.connect(lambda i: self.qc_rename_tab())
        self.qtabs.setToolTip("Right-click a tab: rename / delete / move")
        top.addWidget(self.qtabs)
        new_tab = QPushButton("＋ Tab")
        new_tab.setToolTip("New tab")
        new_tab.clicked.connect(self.qc_new_tab)
        top.addWidget(new_tab)
        top.addStretch(1)
        add_btn = QPushButton("＋ Command")
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self.qc_add)
        top.addWidget(add_btn)
        imp = QPushButton("Import")
        imp.setObjectName("tool")
        imp.setProperty("hasMenu", True)
        imp.setToolTip("Bring quick commands in from the old program or from an exported file")
        im = QMenu(imp)
        im.addAction("From the old program (quick_commands.json)…", self.qc_import_old)
        im.addAction("From an exported file…", self.qc_import_file)
        imp.setMenu(im)
        top.addWidget(imp)
        exp = QPushButton("Export")
        exp.setObjectName("tool")
        exp.setToolTip("Save ALL quick commands (every protocol) to a file — e.g. to copy to another PC")
        exp.clicked.connect(self.qc_export)
        top.addWidget(exp)
        v.addLayout(top)

        body = QHBoxLayout()
        body.setSpacing(10)
        body.addSpacing(self.SECTION_W + 10)
        cont = QWidget()
        cont.setObjectName("qcont")
        self.quick_flow = FlowLayout(cont, spacing=6)
        self.quick_scroll = QScrollArea()
        self.quick_scroll.setWidgetResizable(True)
        self.quick_scroll.setWidget(cont)
        self.quick_scroll.setFrameShape(QFrame.NoFrame)
        self.quick_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.quick_scroll.viewport().setAutoFillBackground(False)
        cont.setAutoFillBackground(False)
        body.addWidget(self.quick_scroll, 1)
        self.quick_empty = QLabel()
        self.quick_empty.setObjectName("empty")
        body.addWidget(self.quick_empty, 1)
        v.addLayout(body)
        return card

    def _fit_quick(self):
        """Grow the button area with its content, up to ~3 rows, then scroll."""
        if not hasattr(self, "quick_scroll"):
            return
        w = max(200, self.quick_scroll.viewport().width())
        need = self.quick_flow.heightForWidth(w) if self.quick_buttons else 0
        self.quick_scroll.setFixedHeight(min(max(need, 34), 112) + 2)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        QTimer.singleShot(0, self._fit_quick)

    def _build_send(self):
        card = self._card()
        h = QHBoxLayout(card)
        h.setContentsMargins(14, 8, 14, 8)
        h.setSpacing(10)
        h.addWidget(self._section("SEND", self.SECTION_W))
        self.send_edit = QLineEdit()
        self.send_edit.setPlaceholderText("Type a command and press Enter  (↑ / ↓ = history)")
        self.send_edit.setFont(self._mono(9))
        self.send_edit.returnPressed.connect(self.send_custom)
        self.send_edit.installEventFilter(self)
        self.ending_cb = QComboBox(); self.ending_cb.addItems(["CR+LF", "CR", "LF", "None"])
        self.btn_send = QPushButton("▶  Send")
        self.btn_send.setObjectName("primary")
        self.btn_send.setMinimumWidth(100)
        self.btn_send.setEnabled(False)
        self.btn_send.clicked.connect(self.send_custom)
        h.addWidget(self.send_edit, 1)
        h.addWidget(self.ending_cb)
        h.addWidget(self.btn_send)
        return card

    def _build_log_area(self):
        card = self._card()
        v = QVBoxLayout(card)
        v.setContentsMargins(14, 10, 14, 12)
        v.setSpacing(8)
        tools = QHBoxLayout()
        tools.setSpacing(10)
        self.sec_log = self._section("OUTPUT", self.SECTION_W)
        tools.addWidget(self.sec_log)

        vseg = QFrame()
        vseg.setObjectName("segbar")
        vl = QHBoxLayout(vseg)
        vl.setContentsMargins(3, 3, 3, 3)
        vl.setSpacing(2)
        self.view_group = QButtonGroup(self)
        for i, (name, tip) in enumerate((
                ("Terminal", "Type directly like Tera Term — every key goes to the device"),
                ("Log", "Line log with filter and colours"))):
            b = QPushButton(name)
            b.setCheckable(True)
            b.setProperty("seg", True)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(tip)
            self.view_group.addButton(b, i)
            vl.addWidget(b)
        self.view_group.idClicked.connect(self._set_view)
        tools.addWidget(vseg)
        tools.addSpacing(8)

        self.tool_stack = QStackedWidget()
        tw, th = self._row()                       # terminal options (Tera Term names)
        th.addWidget(self._field("Enter sends"))
        self.enter_cb = QComboBox()
        self.enter_cb.addItems(list(ENTER_CODES))
        th.addWidget(self.enter_cb)
        th.addSpacing(6)
        th.addWidget(self._field("Backspace"))
        self.bs_cb = QComboBox()
        self.bs_cb.addItems(list(BS_CODES))
        th.addWidget(self.bs_cb)
        th.addSpacing(6)
        self.chk_echo = QCheckBox("Local echo")
        self.chk_echo.setToolTip("Show what you type yourself (only if the device does not echo)")
        th.addWidget(self.chk_echo)
        self.chk_lf = QCheckBox("LF → CR+LF")
        self.chk_lf.setToolTip("Treat a received LF as new line (fixes 'staircase' text)")
        th.addWidget(self.chk_lf)
        self.btn_break = QPushButton("Break")
        self.btn_break.setToolTip("Send serial BREAK (Tera Term: Alt+B)")
        self.btn_break.setEnabled(False)
        self.btn_break.clicked.connect(self.send_break)
        th.addWidget(self.btn_break)
        hint = QLabel("select = copy · right-click = paste")
        hint.setObjectName("hint")
        th.addSpacing(6)
        th.addWidget(hint)
        th.addStretch(1)
        lw, lh = self._row()                       # log options
        lh.addWidget(self._field("Filter"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("show only lines containing…")
        self.filter_edit.setFixedWidth(240)
        self.filter_edit.textChanged.connect(self.rerender)
        lh.addWidget(self.filter_edit)
        lh.addSpacing(10)
        self.chk_scroll = QCheckBox("Auto Scroll"); self.chk_scroll.setChecked(True)
        lh.addWidget(self.chk_scroll)
        lh.addStretch(1)
        self.tool_stack.addWidget(tw)
        self.tool_stack.addWidget(lw)
        tools.addWidget(self.tool_stack, 1)
        save = QPushButton("Save"); save.clicked.connect(self.save_output)
        clear = QPushButton("Clear"); clear.clicked.connect(self.clear_output)
        tools.addWidget(save)
        tools.addWidget(clear)
        v.addLayout(tools)

        self.view_stack = QStackedWidget()
        frame = QFrame()
        frame.setObjectName("termframe")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(1, 1, 1, 1)
        self.term = TerminalWidget()
        self.term.send_bytes.connect(self._term_send)
        self.term.resized.connect(self._term_resized)
        self.term.status.connect(self._status)
        fl.addWidget(self.term)
        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)            # selecting + Ctrl+C work natively
        self.log.setMaximumBlockCount(MAX_LOG_LINES)
        self.log.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.log.setFont(self._mono(9))
        self.view_stack.addWidget(frame)
        self.view_stack.addWidget(self.log)
        v.addWidget(self.view_stack, 1)

        # restore terminal options (defaults = Tera Term defaults)
        st = self.settings
        on = lambda k, d: str(st.value(k, d)).lower() == "true"
        self.enter_cb.setCurrentText(str(st.value("term_enter", "CR")))
        self.bs_cb.setCurrentText(str(st.value("term_bs", "BS")))
        self.chk_echo.setChecked(on("term_echo", "false"))
        self.chk_lf.setChecked(on("term_lf", "true"))
        try:
            self.term.set_font_size(int(st.value("term_font_pt", 9)))
        except (TypeError, ValueError):
            pass
        for w_ in (self.enter_cb, self.bs_cb):
            w_.currentIndexChanged.connect(self._term_opts)
        for w_ in (self.chk_echo, self.chk_lf):
            w_.toggled.connect(self._term_opts)
        self._term_opts()
        self._set_view(self.VIEW_LOG)          # the program always opens in the Log view
        return card

    # ── terminal view ────────────────────────────────────────────────────────
    VIEW_TERMINAL, VIEW_LOG = 0, 1

    def _set_view(self, i):
        if self.view_group.checkedId() != i:
            self.view_group.button(i).setChecked(True)
        self.view_stack.setCurrentIndex(i)
        self.tool_stack.setCurrentIndex(i)
        if i == self.VIEW_TERMINAL:
            QTimer.singleShot(0, self.term.setFocus)

    def _term_opts(self, *_):
        self.term.enter = ENTER_CODES[self.enter_cb.currentText()]
        self.term.backspace = BS_CODES[self.bs_cb.currentText()]
        self.term.local_echo = self.chk_echo.isChecked()
        self.term.lf_to_crlf = self.chk_lf.isChecked()
        st = self.settings
        st.setValue("term_enter", self.enter_cb.currentText())
        st.setValue("term_bs", self.bs_cb.currentText())
        st.setValue("term_echo", "true" if self.chk_echo.isChecked() else "false")
        st.setValue("term_lf", "true" if self.chk_lf.isChecked() else "false")

    def _term_send(self, data):
        if self.session is None or not self.opened:
            self._status("Not connected — press Connect first")
            return
        ok, err = self.session.send(data)
        if not ok:
            self._status(f"Send error: {err}")

    def _term_resized(self, cols, rows):
        if self.session is not None:
            self.session.resize(cols, rows)

    def _on_data(self, token, data):
        if token is self.token:
            self.term.feed(data)

    def _status(self, msg):
        self.status_msg.setText(msg)
        QTimer.singleShot(8000, lambda m=msg: self.status_msg.text() == m and self.status_msg.setText(""))

    def send_break(self):
        if isinstance(self.session, SerialSession) and self.opened:
            self.session.send_break()
            self._status("BREAK sent")

    def _in_terminal(self):
        return self.view_stack.currentIndex() == self.VIEW_TERMINAL

    def clear_output(self):
        if self._in_terminal():
            self.term.clear()
        else:
            self.clear_log()

    def save_output(self):
        if not self._in_terminal():
            self.save_log()
            return
        default = os.path.join(os.path.expanduser("~"), "Documents",
                               time.strftime("terminal_%Y%m%d_%H%M%S.txt"))
        path, _ = QFileDialog.getSaveFileName(self, "Save terminal", default, "Text (*.txt);;All (*.*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.term.select_all_text() + "\n")
            self._status(f"Saved terminal → {os.path.basename(path)}")
        except OSError as e:
            self._status(f"Save failed: {e}")

    @staticmethod
    def _mono(size):
        f = QFont()
        f.setFamilies(["JetBrains Mono", "Cascadia Code", "Fira Code", "Cascadia Mono", "Consolas"])
        f.setPointSize(size)
        f.setStyleHint(QFont.Monospace)
        return f

    def eventFilter(self, obj, ev):          # ↑ / ↓ command history
        from PySide6.QtCore import QEvent
        if obj is self.send_edit and ev.type() == QEvent.KeyPress and self.history:
            if ev.key() == Qt.Key_Up:
                self.hist_idx = len(self.history) - 1 if self.hist_idx == -1 else max(0, self.hist_idx - 1)
                self.send_edit.setText(self.history[self.hist_idx]); return True
            if ev.key() == Qt.Key_Down and self.hist_idx != -1:
                if self.hist_idx < len(self.history) - 1:
                    self.hist_idx += 1; self.send_edit.setText(self.history[self.hist_idx])
                else:
                    self.hist_idx = -1; self.send_edit.clear()
                return True
        return super().eventFilter(obj, ev)

    # ── theme ────────────────────────────────────────────────────────────────
    @staticmethod
    def _icons(pal):
        """Small SVGs (combo arrow / check mark) tinted for the current theme."""
        import tempfile
        d = os.path.join(tempfile.gettempdir(), "uart_viewer_icons")
        os.makedirs(d, exist_ok=True)
        arrow = os.path.join(d, f"arrow_{pal['DIM'][1:]}.svg")
        check = os.path.join(d, f"check_{pal['ON_ACCENT'][1:]}.svg")
        with open(arrow, "w") as f:
            f.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
                    f'<path d="M2 4l4 4 4-4" fill="none" stroke="{pal["DIM"]}" stroke-width="1.8" '
                    f'stroke-linecap="round" stroke-linejoin="round"/></svg>')
        with open(check, "w") as f:
            f.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
                    f'<path d="M2.5 6.5l2.5 2.5 4.5-5" fill="none" stroke="{pal["ON_ACCENT"]}" '
                    f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>')
        return {"ARROW_URL": arrow.replace("\\", "/"), "CHECK_URL": check.replace("\\", "/")}

    def apply_theme(self, name):
        if name not in THEMES:
            return
        self.theme_name = name
        self.pal = THEMES[name]
        tokens = dict(self.pal)
        tokens.update(derive(self.pal))
        tokens.update(self._icons(self.pal))
        QApplication.instance().setStyleSheet(QSS.substitute(tokens))
        self.settings.setValue("theme", name)
        ic = NATURE[name]
        if hasattr(self, "title_lbl"):
            self.title_lbl.setText(f"{ic['logo']}  {APP_NAME}")
        if hasattr(self, "theme_cb"):
            i = self.theme_cb.findData(name)
            if i >= 0 and i != self.theme_cb.currentIndex():
                self.theme_cb.blockSignals(True)
                self.theme_cb.setCurrentIndex(i)
                self.theme_cb.blockSignals(False)
        if hasattr(self, "term"):
            self.term.set_colors(self.pal["BG"], self.pal["TEXT"], self.pal["ACCENT"],
                                 dark=name not in LIGHT_THEMES)
            # pass / fail / error / warning lines get the same colours as in the Log view
            self.term.set_highlight(auto_tag, {"error": self.pal["WARN"], "warn": self.pal["YELLOW"],
                                               "success": self.pal["ACCENT2"]})
        if hasattr(self, "log"):
            self.rerender()
        if hasattr(self, "quick_empty"):
            self.render_quick()

    # ── log ──────────────────────────────────────────────────────────────────
    def _fmt(self, tag):
        f = QTextCharFormat()
        key = {"info": "TEXT", "warn": "YELLOW", "error": "WARN", "success": "ACCENT2"}[tag]
        f.setForeground(QColor(self.pal[key]))
        return f

    def _insert(self, items):
        # a private cursor: the visible cursor/selection (copy!) must not be replaced
        cur = QTextCursor(self.log.document())
        cur.movePosition(QTextCursor.End)
        cur.beginEditBlock()
        for text, tag, is_sys in items:
            cur.insertText(("● " + text if is_sys else text) + "\n", self._fmt(tag))
        cur.endEditBlock()

    def _passes(self, text):
        flt = self.filter_edit.text().lower()
        return not flt or flt in text.lower()

    def _after_add(self):
        shown = self.log.blockCount() - 1
        self.status_lines.setText(f"Lines: {shown}")
        if self.chk_scroll.isChecked():
            self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def _enqueue(self, text, tag, is_sys):
        self.log_lines.append((text, tag, is_sys))
        if self._passes(text):
            self._pending.append((text, tag, is_sys))
            if not self._flush_timer.isActive():
                self._flush_timer.start()

    def _flush(self):
        if not self._pending:
            self._flush_timer.stop()
            return
        batch, self._pending = self._pending[:FLUSH_MAX], self._pending[FLUSH_MAX:]
        self._insert(batch)
        self._after_add()
        if not self._pending:
            self._flush_timer.stop()

    def log_sys(self, msg, tag="info"):
        self._enqueue(msg, tag, True)
        if hasattr(self, "status_msg"):
            self._status(msg)

    def add_line(self, text):
        self._enqueue(text, auto_tag(text), False)

    def rerender(self, *_):
        self._pending = []
        self.log.clear()
        self.log.setUpdatesEnabled(False)
        self._insert([(t_, g, s) for t_, g, s in self.log_lines if self._passes(t_)])
        self.log.setUpdatesEnabled(True)
        self._after_add()

    def clear_log(self):
        self._pending = []
        self.log_lines.clear()
        self.log.clear()
        self.status_lines.setText("Lines: 0")

    def save_log(self):
        default = os.path.join(os.path.expanduser("~"), "Documents",
                               time.strftime("uart_log_%Y%m%d_%H%M%S.txt"))
        path, _ = QFileDialog.getSaveFileName(self, "Save log", default, "Text (*.txt);;All (*.*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                for text, *_ in self.log_lines:
                    f.write(f"{text}\n")
            self.log_sys(f"Saved {len(self.log_lines)} lines → {os.path.basename(path)}", "success")
        except OSError as e:
            self.log_sys(f"Save failed: {e}", "error")

    # ── serial ───────────────────────────────────────────────────────────────
    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        keep = self.port_cb.currentText()
        self.port_cb.clear()
        self.port_cb.addItems(ports)
        if keep in ports:
            self.port_cb.setCurrentText(keep)
        if hasattr(self, "log"):
            self.log_sys(f"Found {len(ports)} port(s): {', '.join(ports) if ports else 'none'}")

    def _set_pill(self, text, state):
        self.pill.setText(text)
        self.pill.setProperty("state", state)
        self.pill.style().unpolish(self.pill)
        self.pill.style().polish(self.pill)

    # ── one protocol at a time ───────────────────────────────────────────────
    def _make_session(self, kind):
        """Build the session for the selected protocol, or return (None, error)."""
        token = self.token

        def cbs():
            return dict(
                on_line=lambda t: self.sig_line.emit(token, t),
                on_info=lambda t, g: self.sig_info.emit(token, t, g),
                on_opened=lambda: self.sig_opened.emit(token),
                on_closed=lambda r, e: self.sig_closed.emit(token, r, e),
                on_data=lambda b: self.sig_data.emit(token, b))
        try:
            if kind == 0:
                port = self.port_cb.currentText()
                if not port:
                    return None, "Select a COM port first."
                parity = {"None": serial.PARITY_NONE, "Even": serial.PARITY_EVEN,
                          "Odd": serial.PARITY_ODD, "Mark": serial.PARITY_MARK,
                          "Space": serial.PARITY_SPACE}[self.parity_cb.currentText()]
                return SerialSession(port, int(self.baud_cb.currentText()),
                                     int(self.data_cb.currentText()), parity,
                                     float(self.stop_cb.currentText()), **cbs()), ""
            if kind == 1:
                host = self.tn_host.text().strip()
                if not host:
                    return None, "Enter an IP address."
                return TelnetSession(host, int(self.tn_port.text() or 23),
                                     self.tn_ping.isChecked(),
                                     int(self.tn_interval.currentText()), **cbs()), ""
            host = self.ssh_host.text().strip()
            if not host:
                return None, "Enter an IP address."
            cols, rows = self.term.size_chars()
            return SshSession(host, int(self.ssh_port.text() or 22), self.ssh_user.text().strip(),
                              self.ssh_pass.text(), cols=cols, rows=rows, **cbs()), ""
        except ValueError:
            return None, "Port / number fields must be numeric."

    def connect_session(self):
        if self.session is not None:
            return
        self.token = object()
        sess, err = self._make_session(self.seg_group.checkedId())
        if sess is None:
            self.token = None
            self.log_sys(err, "warn")
            return
        self.session = sess
        self.opened = False
        self._set_ui_state("connecting")
        self._set_pill(f"●  Connecting… {sess.label}", "busy")
        self.log_sys(f"Connecting → {sess.label}")
        self.term.write_banner(f"Connecting  {sess.label}")
        sess.start()

    def disconnect_session(self):
        sess, self.session, self.token = self.session, None, None
        if sess is not None:
            sess.stop()
            self.log_sys(f"Disconnected ({sess.kind})", "warn")
            self.term.write_banner(f"Disconnected  {sess.label}")
        self.opened = False
        self._set_ui_state("idle")
        self._set_pill("●  Disconnected", "off")
        self.status_port.setText("")

    # signals arrive on the GUI thread; `token` filters out stale sessions
    def _on_opened(self, token):
        if token is not self.token or self.session is None:
            return
        self.opened = True
        self._set_ui_state("connected")
        self._set_pill(f"●  {self.session.label}", "on")
        self.status_port.setText(self.session.label)
        self.log_sys(f"Connected → {self.session.label}", "success")
        self.term.write_banner(f"Connected  {self.session.label}", "green")
        if self._in_terminal():
            self.term.setFocus()

    def _on_closed(self, token, reason, error):
        if token is not self.token or self.session is None:
            return                      # user already disconnected / replaced
        kind = self.session.kind
        self.session, self.token, self.opened = None, None, False
        self._set_ui_state("idle")
        self._set_pill("●  Disconnected", "err" if error else "off")
        self.status_port.setText("")
        self.log_sys(reason or f"{kind} session ended", "error" if error else "warn")
        self.term.write_banner(reason or f"{kind} session ended", "red" if error else "brightblack")

    def _on_info(self, token, text, tag):
        if token is self.token:
            self.log_sys(text, tag)
            self.term.write_banner(text, {"success": "green", "error": "red", "warn": "brown"}.get(tag, "brightblack"))

    def _on_line(self, token, text):
        if token is self.token:
            self.add_line(text)

    def _set_ui_state(self, state):
        idle = state == "idle"
        up = state == "connected"
        self.btn_connect.setEnabled(idle)
        self.btn_disconnect.setEnabled(not idle)
        self.btn_send.setEnabled(up)
        self.term.online = up
        self.btn_break.setEnabled(up and isinstance(self.session, SerialSession))
        for b in self.seg_group.buttons():          # protocol is locked while a session exists
            b.setEnabled(idle or b is self.seg_group.checkedButton())
        for b in self.quick_buttons:
            b.setProperty("offline", not up)
            b.style().unpolish(b)
            b.style().polish(b)

    # ── send / quick commands ────────────────────────────────────────────────
    def _ending(self):
        return {"CR+LF": b"\r\n", "CR": b"\r", "LF": b"\n", "None": b""}[self.ending_cb.currentText()]

    def _send(self, text):
        if self.session is None or not self.opened:
            self.log_sys("Not connected.", "warn")
            return False
        ok, err = self.session.send(text.encode("utf-8") + self._ending())
        self.log_sys(f"TX → {text}" if ok else f"Send error: {err}", "info" if ok else "error")
        return ok

    def send_custom(self):
        text = self.send_edit.text().strip()
        if text and self._send(text):
            if not self.history or self.history[-1] != text:
                self.history.append(text)
            self.hist_idx = -1
            self.send_edit.clear()

    def run_quick(self, cmd, idx=0, parts=None):
        if idx == 0 and self._in_terminal():
            QTimer.singleShot(0, self.term.setFocus)
        parts = parts if parts is not None else [p.strip() for p in cmd.split("|") if p.strip()]
        if idx >= len(parts):
            return
        if not self._send(parts[idx]):
            return
        if idx + 1 < len(parts):
            QTimer.singleShot(300, lambda: self.run_quick(cmd, idx + 1, parts))

    # ── quick commands (per protocol) ────────────────────────────────────────
    def qproto(self):
        return PROTOCOLS[max(0, self.seg_group.checkedId())]

    def _qc_error(self, err):
        if err:
            self.log_sys(f"Could not save quick commands: {err}", "error")

    def _fill_profiles(self):
        proto = self.qproto()
        self.qtabs.blockSignals(True)
        while self.qtabs.count():
            self.qtabs.removeTab(0)
        for p in self.store.profiles(proto):
            self.qtabs.addTab(p["name"])
        if self.qtabs.count():
            self.qtabs.setCurrentIndex(self.store.active(proto))
        self.qtabs.setVisible(self.qtabs.count() > 0)
        self.qtabs.blockSignals(False)

    def _profile_changed(self, idx):
        if idx >= 0:
            self._qc_error(self.store.set_active(self.qproto(), idx))
            self.render_quick()

    def _tab_menu(self, pos):
        i = self.qtabs.tabAt(pos)
        if i < 0:
            return
        self.qtabs.setCurrentIndex(i)
        m = QMenu(self)
        m.addAction("✎  Rename…", self.qc_rename_tab)
        m.addAction("🗑  Delete tab", self.qc_delete_tab)
        m.addSeparator()
        m.addAction("◀  Move left", lambda: self.qc_move_tab(-1))
        m.addAction("▶  Move right", lambda: self.qc_move_tab(+1))
        m.addSeparator()
        m.addAction("🧹  Delete ALL tabs of this protocol", self.qc_delete_all_tabs)
        m.exec(self.qtabs.mapToGlobal(pos))

    def qc_move_tab(self, delta):
        self._qc_error(self.store.move_profile(self.qproto(), delta))
        self.refresh_quick()

    def refresh_quick(self):
        """Protocol (or its data) changed: rebuild tab list + buttons."""
        self.proto_badge.setText(self.qproto().upper())
        self._fill_profiles()
        self.render_quick()

    def render_quick(self):
        while self.quick_flow.count():
            w = self.quick_flow.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)       # gone from the layout immediately
                w.deleteLater()
        self.quick_buttons = []
        proto = self.qproto()
        cmds = self.store.cmds(proto)
        if not self.store.has_tabs(proto):
            msg = "No quick commands yet — press ＋ Command, or Import from the old program."
        else:
            msg = "This tab is empty — press ＋ Command to add one."
        self.quick_empty.setText(msg)
        self.quick_empty.setVisible(not cmds)
        self.quick_scroll.setVisible(bool(cmds))
        for i, c in enumerate(cmds):
            b = QPushButton(c["label"])
            b.setObjectName("quick")
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(c["cmd"] + "\n\nRight-click: edit / delete / move")
            b.setProperty("offline", not self.opened)
            b.clicked.connect(lambda _=False, cmd=c["cmd"]: self.run_quick(cmd))
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.customContextMenuRequested.connect(
                lambda pos, idx=i, btn=b: self._quick_menu(idx, btn.mapToGlobal(pos)))
            self.quick_flow.addWidget(b)
            self.quick_buttons.append(b)
        self._fit_quick()

    def _quick_menu(self, idx, global_pos):
        m = QMenu(self)
        m.addAction("✎  Edit…", lambda: self.qc_edit(idx))
        m.addAction("🗑  Delete", lambda: self.qc_delete(idx))
        m.addSeparator()
        m.addAction("◀  Move earlier", lambda: self.qc_move(idx, -1))
        m.addAction("▶  Move later", lambda: self.qc_move(idx, +1))
        m.exec(global_pos)

    def qc_add(self):
        dlg = CmdDialog(self, "Add command")
        if dlg.exec():
            self._qc_error(self.store.add_cmd(self.qproto(), *dlg.values()))
            self.refresh_quick()          # a "General" tab may have been created

    def qc_edit(self, idx):
        c = self.store.cmds(self.qproto())[idx]
        dlg = CmdDialog(self, "Edit command", c["label"], c["cmd"])
        if dlg.exec():
            self._qc_error(self.store.edit_cmd(self.qproto(), idx, *dlg.values()))
            self.render_quick()

    def qc_delete(self, idx):
        c = self.store.cmds(self.qproto())[idx]
        if QMessageBox.question(self, "Delete command", f"Delete “{c['label']}”?") == QMessageBox.Yes:
            self._qc_error(self.store.delete_cmd(self.qproto(), idx))
            self.render_quick()

    def qc_move(self, idx, delta):
        self._qc_error(self.store.move_cmd(self.qproto(), idx, delta))
        self.render_quick()

    def qc_new_tab(self):
        name, ok = QInputDialog.getText(self, "New tab", "Tab name:")
        if ok and name.strip():
            self._qc_error(self.store.add_profile(self.qproto(), name.strip()))
            self.refresh_quick()

    def qc_rename_tab(self):
        if not self.store.has_tabs(self.qproto()):
            return
        cur = self.qtabs.tabText(self.qtabs.currentIndex())
        name, ok = QInputDialog.getText(self, "Rename tab", "Tab name:", text=cur)
        if ok and name.strip():
            self._qc_error(self.store.rename_profile(self.qproto(), name.strip()))
            self.refresh_quick()

    def qc_delete_tab(self):
        if not self.store.has_tabs(self.qproto()):
            return
        name = self.qtabs.tabText(self.qtabs.currentIndex())
        if QMessageBox.question(self, "Delete tab",
                                f"Delete tab “{name}” and all its commands?") != QMessageBox.Yes:
            return
        self._qc_error(self.store.delete_profile(self.qproto()))
        self.refresh_quick()

    def _docs_dir(self):
        d = os.path.join(os.path.expanduser("~"), "Documents")
        return d if os.path.isdir(d) else os.path.expanduser("~")

    def qc_export(self):
        n_tabs = sum(len(self.store.profiles(p)) for p in PROTOCOLS)
        n_cmds = sum(len(t_["cmds"]) for p in PROTOCOLS for t_ in self.store.profiles(p))
        if not n_tabs:
            QMessageBox.information(self, "Export", "There are no quick commands to export yet.")
            return
        default = os.path.join(self._docs_dir(), time.strftime("quick_commands_%Y%m%d.json"))
        path, _ = QFileDialog.getSaveFileName(self, "Export quick commands", default,
                                              "Quick commands (*.json);;All files (*.*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.store.export_data(), f, ensure_ascii=False, indent=2)
        except OSError as e:
            QMessageBox.warning(self, "Export", f"Could not write the file:\n{e}")
            return
        self.log_sys(f"Exported {n_tabs} tab(s), {n_cmds} command(s) → {path}", "success")

    def qc_import_file(self, start_dir=None):
        path, _ = QFileDialog.getOpenFileName(self, "Import quick commands", start_dir or self._docs_dir(),
                                              "Quick commands (*.json);;All files (*.*)")
        if path:
            self._import_from(path)

    def qc_import_old(self):
        """Find the old Tkinter program's quick_commands.json automatically."""
        for d in legacy_dirs():
            cand = os.path.normpath(os.path.join(d, "quick_commands.json"))
            if os.path.isfile(cand):
                self._import_from(cand)
                return
        QMessageBox.information(
            self, "Import from the old program",
            "quick_commands.json of the old program was not found automatically.\n\n"
            "It is normally in the same folder as SuperSerial.py. Please choose it.")
        self.qc_import_file(os.path.join(os.path.expanduser("~"), "Desktop"))

    def _import_from(self, path):
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                kind, payload = detect_import(json.load(f))
        except (OSError, ValueError) as e:      # JSONDecodeError is a ValueError
            QMessageBox.warning(self, "Import", f"Cannot import this file:\n{path}\n\n{e}")
            return
        dlg = ImportDialog(self, path, kind, payload, self.qproto())
        res = dlg.exec()
        if res == ImportDialog.BROWSE:
            self.qc_import_file(os.path.dirname(path))
            return
        if res != QDialog.Accepted:
            return
        targets, replace = dlg.targets(), dlg.replace_mode()
        if replace:
            names = ", ".join(ImportDialog.LABELS[p] for p in targets)
            if QMessageBox.question(self, "Replace",
                                    f"Remove all current tabs of {names} and import?") != QMessageBox.Yes:
                return
        tabs = cmds = 0
        for proto in targets:
            a, b = self.store.import_profiles(proto, dlg.profiles_for(proto), replace)
            tabs, cmds = tabs + a, cmds + b
        self._qc_error(self.store.save())
        where = ", ".join(ImportDialog.LABELS[p] for p in targets)
        self.log_sys(f"Imported {tabs} new tab(s), {cmds} command(s) into {where} ← {os.path.basename(path)}",
                     "success")
        self.refresh_quick()

    def qc_delete_all_tabs(self):
        proto = self.qproto()
        if not self.store.has_tabs(proto):
            return
        if QMessageBox.question(self, "Delete all tabs",
                                f"Delete ALL {proto.upper()} tabs and their commands?") != QMessageBox.Yes:
            return
        self._qc_error(self.store.delete_all_profiles(proto))
        self.refresh_quick()

    # ── updates ──────────────────────────────────────────────────────────────
    UPDATE_EVERY_S = 12 * 3600       # automatic check at most twice a day (GitHub rate limits)

    def _auto_check_update(self):
        if not updater.configured():
            return
        try:
            last = float(self.settings.value("update_last_check", 0) or 0)
        except (TypeError, ValueError):
            last = 0
        if time.time() - last >= self.UPDATE_EVERY_S:
            self._check_update(manual=False)

    def _check_update(self, manual):
        def work():
            try:
                self.sig_update.emit(updater.check_latest(), "", manual)
            except updater.UpdateError as e:
                self.sig_update.emit(None, str(e), manual)
        if manual:
            self.btn_update.setEnabled(False)
            self.btn_update.setText("Checking…")
        threading.Thread(target=work, daemon=True).start()

    def _on_update_checked(self, info, err, manual):
        self.btn_update.setEnabled(True)
        if err:
            self._mark_update(None)
            if manual:
                QMessageBox.information(self, "Updates", err)
            return
        self.settings.setValue("update_last_check", time.time())
        if updater.is_newer(info["version"], APP_VERSION):
            self._mark_update(info)
            self._status(f"SuperTerm {info['version']} is available — click “Update”.")
            if manual:
                self._show_update()
        else:
            self._mark_update(None)
            if manual:
                QMessageBox.information(self, "Updates", f"You have the latest version (v{APP_VERSION}).")

    def _mark_update(self, info):
        self._update_info = info
        if info:
            self.btn_update.setText(f"⬆ Update {info['version']}")
            self.btn_update.setObjectName("primary")
        else:
            self.btn_update.setText("Check updates")
            self.btn_update.setObjectName("")
        self.btn_update.style().unpolish(self.btn_update)
        self.btn_update.style().polish(self.btn_update)

    def update_clicked(self):
        if not updater.configured():
            QMessageBox.information(
                self, "Updates",
                "Automatic updates are not switched on in this build yet.\n\n"
                "(Set GITHUB_REPO in updater.py to the GitHub repository and rebuild.)")
            return
        if self._update_info:
            self._show_update()
        else:
            self._check_update(manual=True)

    def _show_update(self):
        def before_install():
            if self.session is not None:
                self.disconnect_session()
        dlg = UpdateDialog(self, self._update_info, before_install)
        dlg.exec()
        if dlg.installed:
            QMessageBox.information(self, "Updated",
                                    f"SuperTerm {self._update_info['version']} is installed and starting now.")
            self.close()

    def closeEvent(self, ev):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("term_font_pt", self.term.font_pt)
        if self.session is not None:
            self.disconnect_session()
        if self.video_win is not None:
            self.video_win.close()
        super().closeEvent(ev)

    def open_video(self):
        if self.video_win is None:
            host = ""
            if self.session is not None:     # reuse the host of the current connection
                host = getattr(self.session, "host", "")
            self.video_win = VideoWindow(host)
            self.video_win.destroyed.connect(lambda *_: setattr(self, "video_win", None))
        self.video_win.show()
        self.video_win.raise_()
        self.video_win.activateWindow()


def selftest():
    """`SuperTerm.exe --selftest`: verify every bundled dependency loads
    (used to validate a build). Result goes to selftest.txt in the data folder."""
    lines, ok = [], True
    for label, stmt in (("pyserial ports", "import serial.tools.list_ports as lp; lp.comports()"),
                        ("paramiko", "import paramiko"),
                        ("terminal (pyte, Thai)",
                         "import pyte, terminal; s = terminal._Screen(80, 24, 10); "
                         "pyte.ByteStream(s).feed('ok\\x01ที่'.encode()); "
                         "assert s.buffer[0][2].data == 'ที่', s.buffer[0][2]"),
                        ("QtMultimedia", "from PySide6.QtMultimedia import QMediaPlayer"),
                        ("QtMultimediaWidgets", "from PySide6.QtMultimediaWidgets import QVideoWidget"),
                        ("CA bundle (updates)", "import certifi, os; assert os.path.getsize(certifi.where()) > 100000; "
                                                "import updater; updater._ssl_context()"),
                        ("icon asset", "assert __import__('os').path.exists(resource_path('assets/icon.png'))")):
        try:
            exec(stmt, globals())
            lines.append(f"OK    {label}")
        except Exception as e:
            ok = False
            lines.append(f"FAIL  {label}: {e!r}")
    lines.append(f"version {APP_VERSION}  frozen={getattr(sys, 'frozen', False)}")
    with open(os.path.join(user_data_dir(), "selftest.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 0 if ok else 1


def apply_update_cli(path):
    """`SuperTerm.exe --apply-update NEW.exe`: replace this exe with NEW.exe and
    start it (for IT scripts that roll out a version without clicking)."""
    try:
        updater.install(os.path.abspath(path))
        return 0
    except updater.UpdateError as e:
        with open(os.path.join(user_data_dir(), "update_error.txt"), "w", encoding="utf-8") as f:
            f.write(str(e) + "\n")
        return 1


def main():
    if "--selftest" in sys.argv:
        QApplication(sys.argv)
        sys.exit(selftest())
    if "--apply-update" in sys.argv:
        i = sys.argv.index("--apply-update")
        sys.exit(apply_update_cli(sys.argv[i + 1]) if i + 1 < len(sys.argv) else 2)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("SuperTerm")
    icon = resource_path(os.path.join("assets", "icon.png"))
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    install_crash_handler()
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
