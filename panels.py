"""Extra windows: Settings, Test sequences, File transfer (XMODEM / YMODEM)."""
import os
import threading
import time

from PySide6.QtCore import Qt, Signal, QObject, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QWidget, QLabel, QPushButton, QComboBox, QLineEdit, QCheckBox, QFormLayout,
    QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QColorDialog, QInputDialog, QMessageBox, QProgressBar, QDoubleSpinBox, QFrame,
)

import testrunner
import xmodem
from i18n import T, LANGUAGES


def _section(text):
    lab = QLabel(T(text))
    lab.setObjectName("section")
    return lab


# ══════════════════════════════════════════════════════════════════════════════
class SettingsDialog(QDialog):
    """Logging · alerts / highlight words · updates. (Language is the 🌐 button.)"""

    def __init__(self, parent, values):
        super().__init__(parent)
        self.setWindowTitle(T("Settings"))
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(10)

        v.addWidget(_section("Logging"))
        self.chk_log = QCheckBox(T("Save every connection to a log file automatically"))
        self.chk_log.setChecked(values["log_auto"])
        v.addWidget(self.chk_log)
        row = QHBoxLayout()
        self.log_dir = QLineEdit(values["log_dir"])
        b = QPushButton(T("Browse…"))
        b.clicked.connect(self._browse)
        o = QPushButton(T("Open"))
        o.clicked.connect(lambda: (os.makedirs(self.log_dir.text(), exist_ok=True),
                                   QDesktopServices.openUrl(QUrl.fromLocalFile(self.log_dir.text()))))
        row.addWidget(QLabel(T("Log folder")))
        row.addWidget(self.log_dir, 1)
        row.addWidget(b)
        row.addWidget(o)
        v.addLayout(row)

        v.addSpacing(6)
        v.addWidget(_section("Alerts & highlight"))
        self.chk_beep = QCheckBox(T("Beep when a FAIL / error line arrives"))
        self.chk_beep.setChecked(values["beep"])
        v.addWidget(self.chk_beep)
        v.addWidget(QLabel(T("Extra highlight words (line gets this colour)")))
        self.rules = QTableWidget(0, 3)
        self.rules.setHorizontalHeaderLabels([T("Text"), T("Colour"), T("Regex")])
        self.rules.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.rules.verticalHeader().setVisible(False)
        self.rules.setMinimumHeight(120)
        self.rules.cellDoubleClicked.connect(self._pick_color)
        for r in values["rules"]:
            self._add_rule(r.get("text", ""), r.get("color", "#58a6ff"), r.get("regex", False))
        v.addWidget(self.rules)
        rb = QHBoxLayout()
        add = QPushButton(T("Add"))
        add.clicked.connect(lambda: self._add_rule("", "#58a6ff", False))
        rem = QPushButton(T("Remove"))
        rem.clicked.connect(lambda: self.rules.removeRow(self.rules.currentRow())
                            if self.rules.currentRow() >= 0 else None)
        rb.addWidget(add)
        rb.addWidget(rem)
        rb.addStretch(1)
        v.addLayout(rb)

        v.addSpacing(6)
        v.addWidget(_section("Updates"))
        f = QFormLayout()
        self.channel = QComboBox()
        self.channel.addItem(T("Stable"), "stable")
        self.channel.addItem(T("Beta (try new versions first)"), "beta")
        self.channel.setCurrentIndex(max(0, self.channel.findData(values["channel"])))
        f.addRow(T("Channel"), self.channel)
        v.addLayout(f)
        self.chk_auto_upd = QCheckBox(T("Check automatically when the program starts"))
        self.chk_auto_upd.setChecked(values["auto_update"])
        v.addWidget(self.chk_auto_upd)

        btns = QHBoxLayout()
        btns.addStretch(1)
        c = QPushButton(T("Cancel"))
        c.clicked.connect(self.reject)
        ok = QPushButton(T("OK"))
        ok.setObjectName("primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        btns.addWidget(c)
        btns.addWidget(ok)
        v.addLayout(btns)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, T("Log folder"), self.log_dir.text())
        if d:
            self.log_dir.setText(d)

    def _add_rule(self, text, color, regex):
        r = self.rules.rowCount()
        self.rules.insertRow(r)
        self.rules.setItem(r, 0, QTableWidgetItem(text))
        it = QTableWidgetItem(color)
        it.setBackground(QColor(color))
        it.setForeground(QColor("#000000") if QColor(color).lightness() > 128 else QColor("#ffffff"))
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        self.rules.setItem(r, 1, it)
        chk = QTableWidgetItem("")
        chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        chk.setCheckState(Qt.Checked if regex else Qt.Unchecked)
        self.rules.setItem(r, 2, chk)

    def _pick_color(self, row, col):
        if col != 1:
            return
        cur = QColor(self.rules.item(row, 1).text())
        c = QColorDialog.getColor(cur, self)
        if c.isValid():
            it = self.rules.item(row, 1)
            it.setText(c.name())
            it.setBackground(c)
            it.setForeground(QColor("#000000") if c.lightness() > 128 else QColor("#ffffff"))

    def values(self):
        rules = []
        for r in range(self.rules.rowCount()):
            text = (self.rules.item(r, 0).text() if self.rules.item(r, 0) else "").strip()
            if text:
                rules.append({"text": text, "color": self.rules.item(r, 1).text(),
                              "regex": self.rules.item(r, 2).checkState() == Qt.Checked})
        return {"log_auto": self.chk_log.isChecked(), "log_dir": self.log_dir.text().strip(),
                "beep": self.chk_beep.isChecked(), "rules": rules,
                "channel": self.channel.currentData(), "auto_update": self.chk_auto_upd.isChecked()}


# ══════════════════════════════════════════════════════════════════════════════
class TestRunnerWindow(QWidget):
    """Edit & run test sequences: send → expect text → PASS / FAIL, results to CSV."""

    COLORS = {"PASS": "#3fb950", "FAIL": "#f85149", "STOPPED": "#e3b341", "RUN": "#58a6ff"}

    def __init__(self, store, send, is_connected, connection_label, csv_dir):
        super().__init__()
        self.setObjectName("videoWin")
        self.setWindowTitle("SuperTerm — " + T("Test sequences"))
        self.resize(900, 640)
        self.store, self.send, self.is_connected = store, send, is_connected
        self.connection_label, self.csv_dir = connection_label, csv_dir
        self.runner = None
        self._loading = False

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)
        top = QHBoxLayout()
        top.addWidget(QLabel(T("Sequence")))
        self.seq_cb = QComboBox()
        self.seq_cb.setMinimumWidth(240)
        self.seq_cb.currentIndexChanged.connect(self._load_seq)
        top.addWidget(self.seq_cb)
        for text, fn in (("New", self._new), ("Rename", self._rename), ("Delete", self._delete)):
            b = QPushButton(T(text))
            b.clicked.connect(fn)
            top.addWidget(b)
        top.addStretch(1)
        v.addLayout(top)

        how = QLabel(T("Each step sends a command and waits for the expected text (e.g. OK) "
                       "within the timeout → PASS, otherwise FAIL. Press New to start."))
        how.setObjectName("hint")
        how.setWordWrap(True)
        v.addWidget(how)
        self.steps = QTableWidget(0, 4)
        self.steps.setHorizontalHeaderLabels([T("Send (command)"), T("Expect (text or re:regex)"),
                                              T("Timeout s"), T("If fail")])
        hh = self.steps.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        self.steps.verticalHeader().setDefaultSectionSize(30)
        self.steps.itemChanged.connect(lambda *_: self._save_seq())
        v.addWidget(self.steps, 2)
        sb = QHBoxLayout()
        for text, fn in (("＋ Step", self._add_step), ("Remove step", self._remove_step),
                         ("Up", lambda: self._move(-1)), ("Down", lambda: self._move(+1))):
            b = QPushButton(T(text))
            b.clicked.connect(fn)
            sb.addWidget(b)
        sb.addStretch(1)
        v.addLayout(sb)

        run = QHBoxLayout()
        run.addWidget(QLabel(T("Unit / SN")))
        self.unit = QLineEdit()
        self.unit.setMaximumWidth(220)
        run.addWidget(self.unit)
        self.chk_csv = QCheckBox(T("Save results to CSV automatically"))
        self.chk_csv.setChecked(True)
        run.addWidget(self.chk_csv)
        run.addStretch(1)
        self.btn_run = QPushButton(T("▶  Run"))
        self.btn_run.setObjectName("success")
        self.btn_run.clicked.connect(self.start)
        self.btn_stop = QPushButton(T("■  Stop"))
        self.btn_stop.setObjectName("danger")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop)
        run.addWidget(self.btn_run)
        run.addWidget(self.btn_stop)
        v.addLayout(run)

        self.verdict = QLabel("")
        self.verdict.setAlignment(Qt.AlignCenter)
        self.verdict.setStyleSheet("font-size: 22px; font-weight: 800; padding: 4px;")
        v.addWidget(self.verdict)
        self.results = QTableWidget(0, 4)
        self.results.setHorizontalHeaderLabels([T("Step"), T("Result"), T("Time s"), T("Matched line / reason")])
        self.results.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.results.verticalHeader().setVisible(False)
        self.results.setEditTriggers(QTableWidget.NoEditTriggers)
        v.addWidget(self.results, 2)
        self.csv_lbl = QLabel("")
        self.csv_lbl.setObjectName("hint")
        v.addWidget(self.csv_lbl)

        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._tick)
        self._refresh_seqs()

    # ── sequences ────────────────────────────────────────────────────────────
    def _refresh_seqs(self, select=0):
        self.seq_cb.blockSignals(True)
        self.seq_cb.clear()
        self.seq_cb.addItems(self.store.names())
        self.seq_cb.blockSignals(False)
        if self.store.items:
            self.seq_cb.setCurrentIndex(min(select, len(self.store.items) - 1))
        self._load_seq()

    def _load_seq(self, *_):
        self._loading = True
        self.steps.setRowCount(0)
        i = self.seq_cb.currentIndex()
        if i >= 0:
            for s in self.store.get(i)["steps"]:
                self._add_step(s, save=False)
        self._loading = False

    def _save_seq(self):
        if self._loading:
            return
        i = self.seq_cb.currentIndex()
        if i < 0:
            return
        self.store.put(i, {"name": self.seq_cb.currentText(), "steps": self._read_steps()})

    def _read_steps(self):
        out = []
        for r in range(self.steps.rowCount()):
            txt = lambda c: self.steps.item(r, c).text() if self.steps.item(r, c) else ""
            to = self.steps.cellWidget(r, 2)
            fail = self.steps.cellWidget(r, 3)
            out.append(testrunner.make_step(txt(0), txt(1), to.value() if to else 5,
                                            fail.currentData() if fail else "stop"))
        return out

    def _new(self):
        name, ok = QInputDialog.getText(self, T("New"), T("Sequence") + ":")
        if ok and name.strip():
            self.store.put(len(self.store.items), {"name": name.strip(),
                                                   "steps": [testrunner.make_step("", "OK", 5)]})
            self._refresh_seqs(len(self.store.items) - 1)

    def _rename(self):
        i = self.seq_cb.currentIndex()
        if i < 0:
            return
        name, ok = QInputDialog.getText(self, T("Rename"), T("Sequence") + ":", text=self.seq_cb.currentText())
        if ok and name.strip():
            seq = self.store.get(i)
            seq["name"] = name.strip()
            self.store.put(i, seq)
            self._refresh_seqs(i)

    def _delete(self):
        i = self.seq_cb.currentIndex()
        if i >= 0 and QMessageBox.question(self, T("Delete"), f"{T('Delete')} “{self.seq_cb.currentText()}”?") \
                == QMessageBox.Yes:
            self.store.delete(i)
            self._refresh_seqs(max(0, i - 1))

    # ── steps table ──────────────────────────────────────────────────────────
    def _add_step(self, step=None, save=True):
        if self.seq_cb.currentIndex() < 0 and save:
            self.store.put(0, {"name": "Sequence 1", "steps": []})
            self._refresh_seqs(0)
        step = step if isinstance(step, dict) else testrunner.make_step()
        r = self.steps.rowCount()
        self.steps.blockSignals(True)
        self.steps.insertRow(r)
        self.steps.setItem(r, 0, QTableWidgetItem(step["send"]))
        self.steps.setItem(r, 1, QTableWidgetItem(step["expect"]))
        to = QDoubleSpinBox()
        to.setRange(0, 600)
        to.setDecimals(1)
        to.setValue(float(step["timeout"]))
        to.valueChanged.connect(lambda *_: self._save_seq())
        self.steps.setCellWidget(r, 2, to)
        fail = QComboBox()
        fail.addItem(T("stop"), "stop")
        fail.addItem(T("continue"), "continue")
        fail.setCurrentIndex(0 if step["on_fail"] == "stop" else 1)
        fail.currentIndexChanged.connect(lambda *_: self._save_seq())
        self.steps.setCellWidget(r, 3, fail)
        self.steps.blockSignals(False)
        if save:
            self._save_seq()

    def _remove_step(self):
        r = self.steps.currentRow()
        if r >= 0:
            self.steps.removeRow(r)
            self._save_seq()

    def _move(self, delta):
        r = self.steps.currentRow()
        steps = self._read_steps()
        j = r + delta
        if 0 <= r < len(steps) and 0 <= j < len(steps):
            steps[r], steps[j] = steps[j], steps[r]
            self._loading = True
            self.steps.setRowCount(0)
            for s in steps:
                self._add_step(s, save=False)
            self._loading = False
            self._save_seq()
            self.steps.setCurrentCell(j, 0)

    # ── running ──────────────────────────────────────────────────────────────
    def start(self):
        steps = self._read_steps()
        if not steps:
            return
        if not self.is_connected():
            QMessageBox.information(self, T("Test sequences"), T("Connect first, then run the sequence."))
            return
        self.results.setRowCount(0)
        self.verdict.setText("…")
        self.verdict.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {self.COLORS['RUN']};")
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.runner = testrunner.Runner(steps, self.send)
        self._reported = False
        self.timer.start()
        self._show()

    def stop(self):
        if self.runner and not self.runner.done:
            self.runner.stop()
            self._show()

    def feed_line(self, line):
        """Called by the main window for every received line."""
        if self.runner and not self.runner.done:
            self.runner.feed_line(line)
            self._show()

    def _tick(self):
        if self.runner:
            self.runner.tick()
            self._show()

    def _show(self):
        r = self.runner
        self.results.setRowCount(len(r.results) + (0 if r.done else 1))
        for row, res in enumerate(r.results):
            self._set_row(row, res["step"], res["status"], res["seconds"], res["line"])
        if not r.done:
            self._set_row(len(r.results), r.current + 1, "RUN", "", r.steps[r.current].get("send", ""))
            return
        self.timer.stop()
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        s = r.summary()
        self.verdict.setText(f"{s['result']}   ·   {s['passed']}/{s['total']}")
        self.verdict.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {self.COLORS.get(s['result'])};")
        if self.chk_csv.isChecked() and not self._reported:
            self._reported = True
            path = os.path.join(self.csv_dir(), "test_results.csv")
            try:
                testrunner.append_csv(path, self.seq_cb.currentText(), self.unit.text().strip(), r,
                                      self.connection_label())
                self.csv_lbl.setText(f"CSV → {path}")
            except OSError as e:
                self.csv_lbl.setText(f"CSV error: {e}")
        self.runner = r                       # keep results on screen

    def _set_row(self, row, step, status, secs, line):
        vals = [str(step), status, str(secs), line]
        for c, val in enumerate(vals):
            it = QTableWidgetItem(val)
            if c == 1:
                it.setForeground(QColor(self.COLORS.get(status, "#8b949e")))
            self.results.setItem(row, c, it)


# ══════════════════════════════════════════════════════════════════════════════
class _XferSignals(QObject):
    progress = Signal(int, int)
    done = Signal(bool, str)


class TransferDialog(QDialog):
    """Send a file with YMODEM / XMODEM (e.g. U-Boot `loady`)."""

    def __init__(self, parent, session):
        super().__init__(parent)
        self.session = session
        self.sender = None
        self.setWindowTitle(T("Send file"))
        self.setMinimumWidth(520)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(10)
        f = QFormLayout()
        self.proto = QComboBox()
        self.proto.addItems(xmodem.PROTOCOLS)
        f.addRow(T("Protocol"), self.proto)
        row = QHBoxLayout()
        self.path = QLineEdit()
        b = QPushButton(T("Browse…"))
        b.clicked.connect(self._browse)
        row.addWidget(self.path, 1)
        row.addWidget(b)
        f.addRow(T("File"), row)
        v.addLayout(f)
        hint = QLabel(T("Start the receiver on the device first (U-Boot: loady / loadx), then press Start."))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        v.addWidget(hint)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        v.addWidget(self.bar)
        self.msg = QLabel("")
        self.msg.setWordWrap(True)
        v.addWidget(self.msg)
        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_close = QPushButton(T("Close"))
        self.btn_close.clicked.connect(self.reject)
        self.btn_go = QPushButton(T("Start"))
        self.btn_go.setObjectName("primary")
        self.btn_go.clicked.connect(self._start)
        btns.addWidget(self.btn_close)
        btns.addWidget(self.btn_go)
        v.addLayout(btns)
        self.sig = _XferSignals()
        self.sig.progress.connect(self._progress)
        self.sig.done.connect(self._done)

    def _browse(self):
        p, _ = QFileDialog.getOpenFileName(self, T("File"), self.path.text())
        if p:
            self.path.setText(p)

    def _start(self):
        p = self.path.text().strip()
        if not os.path.isfile(p):
            self.msg.setText("File not found.")
            return
        self.btn_go.setEnabled(False)
        self.msg.setText("…")
        self.sender = xmodem.Sender(self.session, p, self.proto.currentText(),
                                    progress=lambda d, t: self.sig.progress.emit(d, t),
                                    log=lambda m: None)

        def work():
            try:
                self.sig.done.emit(True, self.sender.run())
            except (xmodem.TransferError, OSError) as e:
                self.sig.done.emit(False, str(e))
        threading.Thread(target=work, daemon=True).start()

    def _progress(self, done, total):
        self.bar.setValue(int(done * 1000 / total) if total else 0)
        self.bar.setFormat(f"{done:,} / {total:,} bytes")

    def _done(self, ok, text):
        self.msg.setText(("✔ " if ok else "✖ ") + text)
        self.btn_go.setEnabled(True)
        self.sender = None

    def reject(self):
        if self.sender is not None:
            self.sender.cancel()
        super().reject()
