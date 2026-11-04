"""Nuke UI for PAAI show create / check."""
import os
import nuke
import paai_show

try:
    from PySide6 import QtWidgets, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtCore


class ShowDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(ShowDialog, self).__init__(parent)
        self.setWindowTitle("PAAI Pipeline · Create / Check Show")
        self.resize(640, 480)
        self.root = QtWidgets.QLineEdit()
        try:
            import pipeline_config as cfg
            self.root.setText(cfg.start_root() or "")
        except Exception:
            pass
        browse = QtWidgets.QPushButton("…")
        browse.clicked.connect(self._browse)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.root, 1)
        row.addWidget(browse)

        self.seq = QtWidgets.QLineEdit("SQ010")
        self.shots = QtWidgets.QLineEdit("SH010,SH020")
        self.out = QtWidgets.QPlainTextEdit()
        self.out.setReadOnly(True)

        form = QtWidgets.QFormLayout()
        form.addRow("Show root", row)
        form.addRow("Sequence", self.seq)
        form.addRow("Shots", self.shots)

        btns = QtWidgets.QDialogButtonBox()
        create = btns.addButton("Create", QtWidgets.QDialogButtonBox.ActionRole)
        check = btns.addButton("Check", QtWidgets.QDialogButtonBox.ActionRole)
        close = btns.addButton(QtWidgets.QDialogButtonBox.Close)
        create.clicked.connect(self._create)
        check.clicked.connect(self._check)
        close.clicked.connect(self.reject)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.out, 1)
        lay.addWidget(btns)

    def _browse(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Show root", self.root.text())
        if d:
            self.root.setText(d)

    def _create(self):
        root = self.root.text().strip()
        pairs = paai_show._parse_shots_arg(self.seq.text(), self.shots.text())
        if not root or not pairs:
            self.out.setPlainText("Need a show root and at least one shot.")
            return
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            paai_show.create_show(root, pairs)
            paai_show.check_show(root)
        self.out.setPlainText(buf.getvalue())
        try:
            import pipeline_config as cfg
            cfg.save_prefs(root=cfg.norm_path(root))
        except Exception:
            pass

    def _check(self):
        root = self.root.text().strip()
        if not root:
            self.out.setPlainText("Need a show root.")
            return
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            paai_show.check_show(root)
        self.out.setPlainText(buf.getvalue())


def show():
    dlg = ShowDialog()
    dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()
    return dlg
