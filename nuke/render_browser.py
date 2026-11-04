try:
    import branding
    PAAI_FULL_NAME = branding.PAAI_FULL_NAME
except Exception:
    PAAI_FULL_NAME = "Prasenjeet Anand Artist Interface"

"""Render Browser.

Left side:  Sequence tree (expand a sequence to see its shots) and a Type list, with checkboxes.
Right side: every render version that matches, with its note. Double-click to load as Read.
"""
import os
import subprocess
import sys
import nuke
import pipeline_config as cfg
import scan

try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui

Qt = QtCore.Qt

# ------------------------------------------------------------------ scanning (shared scan.py)
find_sequences = scan.find_sequences
scan_tree = scan.scan_tree
scan_renders = scan.scan_renders


# ------------------------------------------------------------------ pick panels
class PickPanel(QtWidgets.QGroupBox):
    """Checkable list/tree. Used for Sequence > Shot and for Type."""
    changed = QtCore.Signal()

    def __init__(self, title, collapsible=False, add_label=None, add_label2=None, parent=None):
        super(PickPanel, self).__init__(title, parent)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemChanged.connect(lambda *_: self.changed.emit())
        all_btn, none_btn = QtWidgets.QPushButton("All"), QtWidgets.QPushButton("None")
        all_btn.clicked.connect(lambda: self.set_all(True))
        none_btn.clicked.connect(lambda: self.set_all(False))
        bar = QtWidgets.QHBoxLayout()
        bar.addWidget(all_btn)
        bar.addWidget(none_btn)
        bar.addStretch()
        self.add_btn = self.add_btn2 = None
        if add_label:
            self.add_btn = QtWidgets.QPushButton(add_label)
            bar.addWidget(self.add_btn)
        if add_label2:
            self.add_btn2 = QtWidgets.QPushButton(add_label2)
            bar.addWidget(self.add_btn2)
        if collapsible:
            self.fold_btn = QtWidgets.QPushButton("Collapse All")
            self.fold_btn.clicked.connect(self.toggle_fold)
            bar.addWidget(self.fold_btn)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(bar)
        lay.addWidget(self.tree)

    def toggle_fold(self):
        if self.fold_btn.text() == "Collapse All":
            self.tree.collapseAll()
            self.fold_btn.setText("Expand All")
        else:
            self.tree.expandAll()
            self.fold_btn.setText("Collapse All")

    # build
    def set_data(self, data):
        """data: {parent: [children]} or a flat list."""
        keep = self.checked_keys()
        first = not self.tree.topLevelItemCount()
        self.tree.blockSignals(True)
        self.tree.clear()
        if isinstance(data, dict):
            for parent, kids in data.items():
                p = QtWidgets.QTreeWidgetItem(self.tree, [parent])
                p.setData(0, Qt.UserRole, (parent, None))
                p.setFlags(p.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
                for k in kids:
                    c = QtWidgets.QTreeWidgetItem(p, [k])
                    c.setData(0, Qt.UserRole, (parent, k))
                    c.setFlags(c.flags() | Qt.ItemIsUserCheckable)
                    c.setCheckState(0, Qt.Checked if first or (parent, k) in keep else Qt.Unchecked)
                if not kids:
                    p.setCheckState(0, Qt.Checked if first or (parent, None) in keep else Qt.Unchecked)
        else:
            for v in data:
                it = QtWidgets.QTreeWidgetItem(self.tree, [v])
                it.setData(0, Qt.UserRole, (v, None))
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(0, Qt.Checked if first or (v, None) in keep else Qt.Unchecked)
        folded = getattr(self, "fold_btn", None) and self.fold_btn.text() == "Expand All"
        self.tree.collapseAll() if folded else self.tree.expandAll()
        self.tree.blockSignals(False)

    def leaves(self):
        it = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value()
            if not item.childCount():
                yield item
            it += 1

    def checked_keys(self):
        return {i.data(0, Qt.UserRole) for i in self.leaves() if i.checkState(0) == Qt.Checked}

    def set_all(self, state):
        self.tree.blockSignals(True)
        for i in self.leaves():
            i.setCheckState(0, Qt.Checked if state else Qt.Unchecked)
        self.tree.blockSignals(False)
        self.changed.emit()


# ------------------------------------------------------------------ main window
class RenderBrowser(QtWidgets.QWidget):
    COLS = ["Sequence", "Shot", "Type", "Name", "Version", "Frames", "Note", "User", "Date", "Path"]

    def __init__(self, parent=None):
        super(RenderBrowser, self).__init__(parent)
        self.setWindowTitle("PAAI Pipeline · Render Browser")
        self.resize(1300, 620)
        self.items = []

        self.prefs = cfg.load_prefs()
        self.root_edit = QtWidgets.QLineEdit(cfg.start_root() or nuke.root()["project_directory"].value())
        browse = QtWidgets.QPushButton("...")
        browse.clicked.connect(self.pick_root)
        scan_btn = QtWidgets.QPushButton("Scan")
        scan_btn.clicked.connect(self.rescan)
        cfg_btn = QtWidgets.QPushButton("Show config")
        cfg_btn.setToolTip("Open <root>/showset/config")
        cfg_btn.clicked.connect(self.open_config)
        self.latest_only = QtWidgets.QCheckBox("Latest version only")
        self.latest_only.toggled.connect(self.populate)
        self.latest_only.toggled.connect(lambda *_: self.remember())
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search path or note...")
        self.search.textChanged.connect(self.populate)

        self.shot_panel = PickPanel("Sequence / Shot", collapsible=True, add_label="+ Shot")
        self.type_panel = PickPanel("Type / Name", collapsible=True, add_label="+ Type")
        self.shot_panel.add_btn.clicked.connect(self.add_shot_dialog)
        self.type_panel.add_btn.clicked.connect(self.add_type_dialog)
        for p in (self.shot_panel, self.type_panel):
            p.changed.connect(self.populate)
            p.changed.connect(self.remember)


        self.table = QtWidgets.QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideLeft)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._double_click)
        self.table.itemSelectionChanged.connect(self._show_note)

        self.note_view = QtWidgets.QPlainTextEdit()
        self.note_view.setPlaceholderText("Select a version to see or edit its note")
        self.note_view.setMaximumHeight(80)
        save_note = QtWidgets.QPushButton("Save note")
        save_note.clicked.connect(self.save_note)
        apply_btn = QtWidgets.QPushButton("Set selected Writes")
        apply_btn.setToolTip("Point the selected Write nodes at the selected sequence / shot")
        apply_btn.clicked.connect(self.apply_to_writes)
        load_btn = QtWidgets.QPushButton("Load as Read")
        load_btn.clicked.connect(self.load_selected)
        open_btn = QtWidgets.QPushButton("Open folder")
        open_btn.clicked.connect(self.open_folder)

        # layout
        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("Root"))
        top.addWidget(self.root_edit, 1)
        top.addWidget(browse)
        top.addWidget(scan_btn)
        top.addWidget(cfg_btn)

        left = QtWidgets.QSplitter(Qt.Vertical)
        left.addWidget(self.shot_panel)
        left.addWidget(self.type_panel)
        left.setSizes([380, 200])

        flt = QtWidgets.QHBoxLayout()
        flt.addWidget(self.latest_only)
        flt.addWidget(self.search, 1)
        note_row = QtWidgets.QHBoxLayout()
        note_row.addWidget(self.note_view, 1)
        btns = QtWidgets.QVBoxLayout()
        for b in (save_note, open_btn, apply_btn, load_btn):
            btns.addWidget(b)
        note_row.addLayout(btns)
        right = QtWidgets.QWidget()
        rl = QtWidgets.QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addLayout(flt)
        rl.addWidget(self.table, 1)
        rl.addWidget(QtWidgets.QLabel("Version note"))
        rl.addLayout(note_row)

        split = QtWidgets.QSplitter(Qt.Horizontal)
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([260, 1040])

        # Header: logo + title
        _hdr = QtWidgets.QHBoxLayout()
        _hdr.setContentsMargins(0, 0, 0, 4)
        _logo = QtWidgets.QLabel()
        _logo_path = os.path.join(os.path.dirname(__file__), "icons", "paai_logo_header.png")
        if os.path.isfile(_logo_path):
            _pm = QtGui.QPixmap(_logo_path)
            if not _pm.isNull():
                _logo.setPixmap(_pm)
        _logo.setFixedHeight(30)
        _title = QtWidgets.QLabel("PAAI Pipeline · Render Browser")
        _title.setStyleSheet("color: #f7931e; font-weight: 600; font-size: 13px;")
        _tag = QtWidgets.QLabel(PAAI_FULL_NAME)
        _tag.setStyleSheet("color: #a87840; font-size: 9px; letter-spacing: 1px;")
        _brand_col = QtWidgets.QVBoxLayout()
        _brand_col.setContentsMargins(0, 0, 0, 0)
        _brand_col.setSpacing(1)
        _brand_col.addWidget(_logo)
        _brand_col.addWidget(_tag)
        _hdr.addLayout(_brand_col)
        _hdr.addSpacing(8)
        _hdr.addWidget(_title)
        _hdr.addStretch(1)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(_hdr)
        lay.addLayout(top)
        lay.addWidget(split, 1)

        # restore last session (without saving while restoring)
        self._restoring = True
        self.latest_only.setChecked(bool(self.prefs.get("latest_only")))
        if self.root_edit.text():
            self.rescan()
        self._restoring = False

    # ---------------------------------------------------------------- data
    def pick_root(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Project root", self.root_edit.text())
        if d:
            self.root_edit.setText(d)
            self.rescan()

    def rescan(self):
        root = self.root_edit.text().strip()
        if not os.path.isdir(root):
            nuke.message("PAAI Pipeline\n\nProject root not found:\n%s" % root)
            return
        QtWidgets.QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            cfg.ensure_config(root)
            self.items = list(scan_renders(root))
            first = not self.shot_panel.tree.topLevelItemCount()
            self.shot_panel.set_data(scan_tree(root))
            self.type_panel.set_data(cfg.list_names(root, {(i["type"], i["name"]) for i in self.items}))
            if first:
                self._restore_checks()
            cfg.save_prefs(root=root)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self.populate()

    def _restore_checks(self):
        p = self.prefs
        if p.get("checked_shots") is not None:
            want = {tuple(k) for k in p["checked_shots"]}
            self.shot_panel.tree.blockSignals(True)
            for i in self.shot_panel.leaves():
                k = i.data(0, Qt.UserRole)
                i.setCheckState(0, Qt.Checked if [k[0], k[1]] in [list(w) for w in want] else Qt.Unchecked)
            self.shot_panel.tree.blockSignals(False)
        if p.get("checked_types") is not None:
            self.type_panel.tree.blockSignals(True)
            want = {tuple(k) if isinstance(k, list) else (k, None) for k in p["checked_types"]}
            want_types = {k[0] for k in want if k[1] is None}
            for i in self.type_panel.leaves():
                k = i.data(0, Qt.UserRole)
                i.setCheckState(0, Qt.Checked if (k in want or k[0] in want_types) else Qt.Unchecked)
            self.type_panel.tree.blockSignals(False)

    def current_shot(self):
        """First ticked (seq, shot), used for new Write nodes."""
        keys = sorted(k for k in self.shot_panel.checked_keys() if k[1])
        return keys[0] if keys else (None, None)

    def remember(self, *_):
        if getattr(self, "_restoring", False):
            return
        seq, shot = self.current_shot()
        tkeys = self.type_panel.checked_keys()
        types = sorted({k[0] for k in tkeys})
        cfg.save_prefs(root=self.root_edit.text().strip(), sequence=seq, shot=shot,
                       type=types[0] if len(types) == 1 else None,
                       checked_shots=sorted(list(k) for k in self.shot_panel.checked_keys()),
                       checked_types=sorted([k[0], k[1]] for k in tkeys),
                       latest_only=self.latest_only.isChecked())

    def apply_to_writes(self):
        sel = self.selected()
        seq, shot = (sel[0]["seq"], sel[0]["shot"]) if sel else self.current_shot()
        if not seq:
            nuke.message("PAAI Pipeline\n\nPick a shot in the list or the Sequence / Shot panel.")
            return
        import pipeline_write
        done = pipeline_write.set_writes_from_browser(seq, shot, root=self.root_edit.text().strip())
        if not done:
            nuke.message("PAAI Pipeline\n\nSelect one or more Write nodes in the Node Graph first.")
        else:
            cfg.save_prefs(sequence=seq, shot=shot)

    def closeEvent(self, event):
        self.remember()
        super(RenderBrowser, self).closeEvent(event)

    def filtered(self):
        shots = self.shot_panel.checked_keys()
        names = self.type_panel.checked_keys()
        text = self.search.text().lower()
        rows = [i for i in self.items
                if (i["seq"], i["shot"]) in shots
                and ((i["type"], i["name"]) in names or (i["type"], None) in names)
                and (not text or text in i["path"].lower() or text in i["note"].lower())]
        if self.latest_only.isChecked():
            best = {}
            for i in rows:
                k = (i["seq"], i["shot"], i["type"], i["name"])
                if k not in best or int(i["version"][1:]) > int(best[k]["version"][1:]):
                    best[k] = i
            rows = list(best.values())
        return sorted(rows, key=lambda i: (i["seq"], i["shot"], i["type"], i["name"], -int(i["version"][1:])))

    def populate(self, *_):
        rows = self.filtered()
        self.table.clearSelection()
        self.table.setRowCount(len(rows))
        for r, i in enumerate(rows):
            frames = ("%d-%d (%d)" % (i["first"], i["last"], i["count"])
                      if i["first"] is not None else "movie/still")
            vals = [i["seq"], i["shot"], i["type"], i["name"], i["version"], frames,
                    i["note"].replace("\n", " "), i["user"], i["date"], i["path"]]
            for c, v in enumerate(vals):
                cell = QtWidgets.QTableWidgetItem(v)
                cell.setData(Qt.UserRole, i)
                if c == 6:
                    cell.setToolTip(i["note"])
                self.table.setItem(r, c, cell)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(6, min(self.table.columnWidth(6), 260))
        self._show_note()

    def selected(self):
        rows = sorted({idx.row() for idx in self.table.selectionModel().selectedRows()})
        return [self.table.item(r, 0).data(Qt.UserRole) for r in rows]

    # ---------------------------------------------------------------- notes
    def _show_note(self):
        sel = self.selected()
        self.note_view.setPlainText(sel[0]["note"] if len(sel) == 1 else "")

    def save_note(self):
        sel = self.selected()
        if len(sel) != 1:
            nuke.message("PAAI Pipeline\n\nSelect one version to save its note.")
            return
        text = self.note_view.toPlainText()
        cfg.write_note(sel[0]["folder"], text)
        for i in self.items:
            if i["folder"] == sel[0]["folder"]:
                i.update(cfg.read_note(i["folder"]))
        self.populate()

    # ---------------------------------------------------------------- actions
    def _double_click(self, index):
        self.load_selected()

    def load_selected(self, *_):
        for i in self.selected():
            read = nuke.createNode("Read", inpanel=False)
            if i["first"] is not None:
                read["file"].fromUserText("%s %d-%d" % (i["path"], i["first"], i["last"]))
            else:
                read["file"].fromUserText(i["path"])
            label = "%s_%s\n%s %s %s" % (i["seq"], i["shot"], i["type"], i["name"], i["version"])
            if i["note"]:
                label += "\n" + i["note"].splitlines()[0][:40]
            read["label"].setValue(label)

    # ---------------------------------------------------------------- show config
    def _show_root(self):
        root = self.root_edit.text().strip()
        if not os.path.isdir(root):
            nuke.message("PAAI Pipeline\n\nSet a valid project root first.")
            return None
        return root

    def add_shot_dialog(self):
        root = self._show_root()
        if not root:
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Add Shot")
        seq_cb = QtWidgets.QComboBox()
        seq_cb.setEditable(True)
        seq_cb.addItems(list(cfg.list_shots(root)))
        cur = self.current_shot()[0]
        if cur:
            seq_cb.setCurrentText(cur)
        shots = QtWidgets.QLineEdit()
        shots.setPlaceholderText("SH0030  or several: SH0030, SH0040")
        mk = QtWidgets.QCheckBox("Create shot folders on disk")
        mk.setChecked(True)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        f = QtWidgets.QFormLayout(dlg)
        f.addRow("Sequence", seq_cb)
        f.addRow("Shot(s)", shots)
        f.addRow("", mk)
        f.addRow(bb)
        if dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec():
            seq = seq_cb.currentText().strip()
            names = [x.strip() for x in shots.text().replace(";", ",").split(",") if x.strip()]
            for sh in names:
                cfg.add_shot(root, seq, sh, make_folders=mk.isChecked())
            if names:
                self.rescan()
                self._tick(self.shot_panel, {(seq, sh) for sh in names})

    def add_type_dialog(self):
        root = self._show_root()
        if not root:
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Add Render Type")
        name = QtWidgets.QLineEdit()
        name.setPlaceholderText("e.g. denoise, cleanup, lighting")
        ext = QtWidgets.QComboBox()
        ext.setEditable(True)
        ext.addItems(["exr", "png", "jpg", "tif", "dpx", "mov"])
        named = QtWidgets.QCheckBox("Needs an element name (like element / comfyui)")
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        f = QtWidgets.QFormLayout(dlg)
        f.addRow("Type name", name)
        f.addRow("File type", ext)
        f.addRow("", named)
        f.addRow(bb)
        if dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec():
            n = name.text().strip().replace(" ", "_")
            if not cfg.add_type(root, n, ext.currentText(), named.isChecked()):
                nuke.message("PAAI Pipeline\n\nType '%s' is empty or already exists." % n)
                return
            cfg.add_name(root, n, "main")
            self.rescan()
            self._tick(self.type_panel, {(n, "main")})

    def _tick(self, panel, keys):
        panel.tree.blockSignals(True)
        for i in panel.leaves():
            if i.data(0, Qt.UserRole) in keys:
                i.setCheckState(0, Qt.Checked)
        panel.tree.blockSignals(False)
        panel.changed.emit()

    def open_config(self):
        root = self._show_root()
        if root:
            self._open(cfg.ensure_config(root))

    def _open(self, p):
        if sys.platform.startswith("win"):
            os.startfile(p)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p])

    def open_folder(self):
        for i in self.selected()[:1]:
            p = i["folder"]
            if sys.platform.startswith("win"):
                os.startfile(p)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", p])
            else:
                subprocess.Popen(["xdg-open", p])


_win = None


def show():
    global _win
    _win = RenderBrowser()
    _win.show()
    return _win


def register_panel():
    """Dockable from Windows > Custom > Render Browser."""
    try:
        from nukescripts import panels
        panels.registerWidgetAsPanel("render_browser.RenderBrowser", "PAAI Pipeline · Render Browser",
                                     "uk.pipeline.RenderBrowser")
    except Exception:
        pass
