"""Nuke: submit Write nodes to PAAI Render Queue."""
from __future__ import annotations
import os

try:
    from PySide6 import QtWidgets, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtCore

import nuke
import pipeline_config as cfg

DEFAULT_START = cfg.START_FRAME_DEFAULT


def _show_root():
    """Show root from shared pipeline prefs (Render Browser / Write nodes). Queue data is separate."""
    try:
        for n in nuke.allNodes("Write", recurseGroups=True):
            if "pl_root" in n.knobs() and n["pl_root"].value():
                return cfg.norm_path(n["pl_root"].value())
    except Exception:
        pass
    try:
        return cfg.norm_path(cfg.start_root() or "")
    except Exception:
        return ""


def _queue_path(show_root):
    if show_root:
        try:
            return cfg.render_queue_path(show_root) or ""
        except Exception:
            return ""
    return ""


def _link():
    """Stdlib queue client bundled with this pack (no paai_render_queue import)."""
    import paai_queue_link as link
    return link


class SubmitDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(SubmitDialog, self).__init__(parent)
        self.setWindowTitle("PAAI Render Queue · Submit")
        self.resize(720, 420)
        self.writes = [n for n in nuke.allNodes("Write", recurseGroups=True)
                       if "pl_version" in n.knobs()]
        if not self.writes:
            self.writes = [n for n in nuke.selectedNodes() if n.Class() == "Write"]

        self.table = QtWidgets.QTableWidget(len(self.writes), 5)
        self.table.setHorizontalHeaderLabels(["", "Write", "File", "First", "Last"])
        self.table.horizontalHeader().setStretchLastSection(True)
        root = nuke.root()
        first = int(root.firstFrame()) if root else DEFAULT_START
        last = int(root.lastFrame()) if root else DEFAULT_START
        # prefer show start_frame when script still at 1-1
        show_root = _show_root()
        try:
            sf = cfg.start_frame(show_root) if show_root else DEFAULT_START
            if first == 1 and last == 1:
                first = last = sf
        except Exception:
            pass
        for r, n in enumerate(self.writes):
            cb = QtWidgets.QTableWidgetItem()
            cb.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
            cb.setCheckState(QtCore.Qt.Checked)
            self.table.setItem(r, 0, cb)
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(n.name()))
            try:
                f = n["file"].value()
            except Exception:
                f = ""
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(f))
            self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(first)))
            self.table.setItem(r, 4, QtWidgets.QTableWidgetItem(str(last)))

        self.step = QtWidgets.QSpinBox(); self.step.setRange(1, 100); self.step.setValue(1)
        self.cores = QtWidgets.QSpinBox(); self.cores.setRange(1, 256); self.cores.setValue(8)
        self.priority = QtWidgets.QSpinBox(); self.priority.setRange(0, 100); self.priority.setValue(50)
        self.queue_path = QtWidgets.QLineEdit(_queue_path(show_root))
        self.queue_path.setPlaceholderText("Optional folder (discovery) or URL — saved per show")

        form = QtWidgets.QFormLayout()
        form.addRow("Frame step", self.step)
        form.addRow("CPU cores / job", self.cores)
        form.addRow("Priority", self.priority)
        form.addRow("Render Queue path", self.queue_path)

        btns = QtWidgets.QDialogButtonBox()
        submit = btns.addButton("Submit", QtWidgets.QDialogButtonBox.AcceptRole)
        open_q = btns.addButton("Open Render Queue", QtWidgets.QDialogButtonBox.ActionRole)
        cancel = btns.addButton(QtWidgets.QDialogButtonBox.Cancel)
        submit.clicked.connect(self.submit)
        open_q.clicked.connect(self.open_queue)
        cancel.clicked.connect(self.reject)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(QtWidgets.QLabel("Select Write nodes to render (one queue job each):"))
        lay.addWidget(self.table, 1)
        lay.addLayout(form)
        lay.addWidget(btns)
        self.setStyleSheet("""
            QDialog { background: #2b2b2b; color: #e8e8e8; }
            QTableWidget { background: #1e1e1e; gridline-color: #333; }
            QHeaderView::section { background: #3a3a3a; color: #F28C28; padding: 4px; }
            QPushButton { background: #3a3a3a; border: 1px solid #111; padding: 6px 12px; border-radius: 4px; }
        """)

    def open_queue(self):
        show_root = _show_root()
        qp = self.queue_path.text().strip()
        if show_root and qp:
            try:
                cfg.set_show_setting(show_root, "render_queue_path", cfg.norm_path(qp))
            except Exception:
                pass
        link = _link()
        link.open_ui(queue_path=qp or _queue_path(show_root), show_root=show_root)

    def submit(self):
        show_root = _show_root()
        qp = self.queue_path.text().strip()
        if show_root and qp:
            try:
                cfg.set_show_setting(show_root, "render_queue_path", cfg.norm_path(qp))
            except Exception:
                pass
        link = _link()
        queue_path = qp or _queue_path(show_root)
        try:
            script_path = nuke.root().name()
        except Exception:
            script_path = ""
        if not script_path or script_path == "Root":
            tmp = os.path.join(os.path.expanduser("~"), ".nuke", "_paai_rq_submit.nk")
            nuke.scriptSaveAs(tmp)
            script_path = tmp
        else:
            nuke.scriptSave()

        jobs = []
        step = self.step.value()
        for r, n in enumerate(self.writes):
            if self.table.item(r, 0).checkState() != QtCore.Qt.Checked:
                continue
            first = int(self.table.item(r, 3).text())
            last = int(self.table.item(r, 4).text())
            try:
                out = n["file"].value()
            except Exception:
                out = ""
            jobs.append({
                "app": "nuke",
                "name": "%s · %s" % (os.path.basename(script_path), n.name()),
                "copy_from": script_path,
                "target": n.name(),
                "frames": {"start": first, "end": last, "step": step},
                "resources": {"cpu_cores": self.cores.value(), "gpu_index": None},
                "priority": self.priority.value(),
                "output_path": os.path.dirname(out) if out else "",
                "extra": {"write": n.name(), "show_root": show_root},
            })
        if not jobs:
            nuke.message("PAAI Pipeline\n\nTick at least one Write.")
            return
        res = link.submit(jobs, show_root=show_root, queue_path=queue_path)
        if not res.get("ok"):
            nuke.message("PAAI Pipeline\n\n%s" % (res.get("message") or "Queue not running"))
            return
        nuke.message("PAAI Pipeline\n\n%s\n(%d job(s))" % (res.get("message"), len(res.get("jobs") or [])))
        self.accept()


def show():
    dlg = SubmitDialog()
    dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()
    return dlg
