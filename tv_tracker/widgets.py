import math
import random
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRectF, QPointF, QSize, QEvent
from PyQt6.QtGui import QValidator, QPainter, QColor, QPen, QBrush, QFont, QPolygonF
from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QLineEdit, QSpinBox, QComboBox,
    QAbstractSpinBox, QProgressBar, QHBoxLayout, QVBoxLayout, QSizePolicy,
)
from models import Series, Season


class ClampSpinBox(QSpinBox):
    """Accepts any integer while typing; clamps to [min, max] on commit.

    Qt's default valueFromText uses locale.toInt() which returns minimum on
    failure — that's the source of the "clamps to 0" bug.  Overriding both
    validate and valueFromText bypasses that path entirely.
    """
    def validate(self, text: str, pos: int):
        t = text.strip()
        if not t or t == '-':
            return (QValidator.State.Intermediate, text, pos)
        try:
            int(t)
            return (QValidator.State.Acceptable, text, pos)
        except ValueError:
            return (QValidator.State.Invalid, text, pos)

    def valueFromText(self, text: str) -> int:
        try:
            v = int(text.strip())
            return max(self.minimum(), min(v, self.maximum()))
        except ValueError:
            return self.value()

    def textFromValue(self, value: int) -> str:
        return str(value)


_KIND_ICON: dict[str, str] = {
    "tv":     "📺",
    "anime":  "🎌",
    "movie":  "🎬",
    "horror": "👻",
}


def _lbl(text: str, name: str = "", parent: QWidget = None) -> QLabel:
    w = QLabel(text, parent)
    if name:
        w.setObjectName(name)
    w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    return w


def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    line.setStyleSheet("background: #3a4357; border: none;")
    return line


def _transparent() -> QWidget:
    w = QWidget()
    w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    return w


class KindSelector(QWidget):
    changed = pyqtSignal(str)

    _KINDS = [("tv", "📺  TV"), ("anime", "🎌  Anime"), ("movie", "🎬  Movie"), ("horror", "👻  Horror")]

    def __init__(self, value: str = "tv", parent: QWidget = None):
        super().__init__(parent)
        self._value = value
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._btns: dict[str, QPushButton] = {}
        for k, label in self._KINDS:
            btn = QPushButton(label)
            btn.setObjectName("kind_btn")
            btn.setProperty("kind", k)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _, v=k: self._set(v))
            self._btns[k] = btn
            layout.addWidget(btn)
        layout.addStretch()
        self._refresh()

    def _set(self, v: str):
        self._value = v
        self._refresh()
        self.changed.emit(v)

    def _refresh(self):
        for k, btn in self._btns.items():
            btn.setProperty("active", k == self._value)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    @property
    def value(self) -> str:
        return self._value

    def set_value(self, v: str):
        self._value = v
        self._refresh()


class StarRating(QWidget):
    """Kept for backwards-compatibility but not used in the current UI."""
    changed = pyqtSignal(int)

    def __init__(self, value: int = 0, parent: QWidget = None):
        super().__init__(parent)
        self._value = value

    @property
    def value(self) -> int:
        return self._value

    def set_value(self, v: int):
        self._value = v


class SeasonRow(QWidget):
    watch_requested    = pyqtSignal('qlonglong', int)
    complete_requested = pyqtSignal('qlonglong', int)
    rate_requested     = pyqtSignal('qlonglong', int, int)  # series_id, season_num, rating

    def __init__(self, series_id: int, season_num: int, season: Season, parent: QWidget = None):
        super().__init__(parent)
        self._series_id = series_id
        self._season_num = season_num

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(10)

        sn_col = _transparent()
        sc = QVBoxLayout(sn_col)
        sc.setContentsMargins(0, 0, 0, 0)
        sc.setSpacing(0)
        if season.label:
            lbl = _lbl(season.label, "season_label")
            lbl.setWordWrap(True)
            sc.addWidget(lbl)
        else:
            sn_lbl = _lbl(f"Season {season_num}", "season_label")
            sn_lbl.setWordWrap(True)
            sc.addWidget(sn_lbl)
        sn_col.setFixedWidth(100)
        layout.addWidget(sn_col)

        prog_col = _transparent()
        pc = QVBoxLayout(prog_col)
        pc.setContentsMargins(0, 0, 0, 0)
        pc.setSpacing(3)

        bar = QProgressBar()
        bar.setRange(0, max(season.episodes, 1))
        bar.setValue(season.watched)
        bar.setFixedHeight(5)
        bar.setTextVisible(False)
        pc.addWidget(bar)

        pct = round((season.watched / season.episodes) * 100) if season.episodes > 0 else 0
        pc.addWidget(_lbl(f"{season.watched} / {season.episodes} eps ({pct}%)", "eps_label"))
        layout.addWidget(prog_col, 1)

        rating_combo = QComboBox()
        rating_combo.setObjectName("rating_combo")
        rating_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        rating_combo.setMinimumContentsLength(2)
        rating_combo.addItem("Rate")
        for i in range(1, 11):
            rating_combo.addItem(f"★ {i}")
        rating_combo.setCurrentIndex(season.rating)
        rating_combo.currentIndexChanged.connect(
            lambda idx: self.rate_requested.emit(self._series_id, self._season_num, idx)
        )
        layout.addWidget(rating_combo)

        if season.watched >= season.episodes:
            layout.addWidget(_lbl("✓ done", "done_badge"))
        else:
            btn = QPushButton("+1")
            btn.setObjectName("btn_watch")
            btn.setFixedSize(42, 26)
            btn.clicked.connect(lambda: self.watch_requested.emit(self._series_id, self._season_num))
            layout.addWidget(btn)

            done_btn = QPushButton("✓ All")
            done_btn.setObjectName("btn_complete")
            done_btn.setFixedSize(52, 26)
            done_btn.setToolTip("Mark season as fully watched")
            done_btn.clicked.connect(lambda: self.complete_requested.emit(self._series_id, self._season_num))
            layout.addWidget(done_btn)


class SeriesCard(QFrame):
    watch_requested          = pyqtSignal('qlonglong', int)
    delete_requested         = pyqtSignal('qlonglong')
    auto_save_requested      = pyqtSignal('qlonglong', str, str, object, dict)
    add_season_requested     = pyqtSignal('qlonglong', int, int, bool)   # id, season_num, eps, p2w
    complete_requested       = pyqtSignal('qlonglong', int)
    rate_requested           = pyqtSignal('qlonglong', int, int)
    season_delete_requested  = pyqtSignal('qlonglong', int)
    edit_closed              = pyqtSignal('qlonglong')

    def __init__(self, series: Series, parent: QWidget = None):
        super().__init__(parent)
        self._series = series
        self._season_rows: dict[str, SeasonRow] = {}
        self._season_inputs: dict[str, dict] = {}   # populated lazily on first edit-panel open
        self._edit_panel = None                      # built lazily on first edit-panel open
        self.setObjectName("series_card")

        active_seasons = {k: v for k, v in series.seasons.items() if not v.p2w}
        _rated = [v.rating for v in active_seasons.values() if v.rating > 0]
        _avg = round(sum(_rated) / len(_rated)) if _rated else None
        _has_p2w = any(v.p2w for v in series.seasons.values())
        _completed = (
            bool(active_seasons)
            and not _has_p2w
            and all(v.watched >= v.episodes for v in active_seasons.values())
        )
        self.setProperty("completed", "true" if _completed else "false")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._outer = outer   # kept for lazy edit-panel insertion

        # ── Header ──────────────────────────────────────────────
        header = _transparent()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 12, 16, 8)
        hl.setSpacing(10)

        hl.addWidget(_lbl(_KIND_ICON.get(series.kind, "📺")))
        name_col = _transparent()
        nc = QVBoxLayout(name_col)
        nc.setContentsMargins(0, 0, 0, 0)
        nc.setSpacing(1)
        self._name_lbl = _lbl(series.name, "series_name")
        self._name_lbl.setWordWrap(True)
        nc.addWidget(self._name_lbl)
        self._altname_lbl = _lbl("", "series_altname")
        self._altname_lbl.setWordWrap(True)
        self._altname_lbl.setVisible(bool(series.alt_names))
        if series.alt_names:
            self._altname_lbl.setText("  /  ".join(series.alt_names))
        nc.addWidget(self._altname_lbl)
        name_col.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        hl.addWidget(name_col, 1)

        self._avg_lbl = _lbl("", "avg_badge")
        self._avg_lbl.setVisible(_avg is not None)
        if _avg is not None:
            self._avg_lbl.setText(f"⭐ {_avg}")
        hl.addWidget(self._avg_lbl)

        edit_btn = QPushButton("✏")
        edit_btn.setObjectName("btn_edit")
        edit_btn.setFixedSize(30, 28)
        edit_btn.setToolTip("Edit")
        edit_btn.clicked.connect(self._toggle_edit)
        hl.addWidget(edit_btn)

        del_btn = QPushButton("🗑")
        del_btn.setObjectName("btn_del")
        del_btn.setFixedSize(30, 28)
        del_btn.setToolTip("Delete")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(series.id))
        hl.addWidget(del_btn)
        outer.addWidget(header)

        # ── Season rows ─────────────────────────────────────────
        seasons_body = _transparent()
        self._seasons_layout = QVBoxLayout(seasons_body)
        self._seasons_layout.setContentsMargins(16, 0, 16, 12)
        self._seasons_layout.setSpacing(0)

        for i, sn_str in enumerate(sorted(active_seasons.keys(), key=int)):
            if i > 0:
                self._seasons_layout.addWidget(_hline())
            row = SeasonRow(series.id, int(sn_str), active_seasons[sn_str])
            row.watch_requested.connect(self.watch_requested)
            row.complete_requested.connect(self.complete_requested)
            row.rate_requested.connect(self.rate_requested)
            self._seasons_layout.addWidget(row)
            self._season_rows[sn_str] = row

        outer.addWidget(seasons_body)
        # Edit panel is built lazily on first open — see _toggle_edit()

    # ── Edit panel construction ──────────────────────────────────

    def _build_edit_panel(self, series: Series) -> QFrame:
        panel = QFrame()
        panel.setObjectName("edit_panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(10)

        note = _lbl("ℹ  Edit episodes or ratings, or add seasons below.", "edit_note")
        note.setWordWrap(True)
        layout.addWidget(note)

        layout.addWidget(_lbl("Series name", "field_label"))
        self._name_input = QLineEdit(series.name)
        self._name_input.editingFinished.connect(self._auto_save_name)
        layout.addWidget(self._name_input)

        layout.addWidget(_lbl("Type", "field_label"))
        self._kind_selector = KindSelector(series.kind)
        self._kind_selector.changed.connect(lambda _: self._auto_save_name())
        layout.addWidget(self._kind_selector)

        layout.addWidget(_lbl("Alternative names", "field_label"))
        self._alt_names_input = QLineEdit(", ".join(series.alt_names))
        self._alt_names_input.setPlaceholderText("e.g. ワンピース, One Piece, OP")
        self._alt_names_input.editingFinished.connect(self._auto_save_name)
        layout.addWidget(self._alt_names_input)
        layout.addWidget(_hline())

        self._season_inputs: dict[str, dict] = {}
        blocks_container = _transparent()
        self._edit_blocks_layout = QVBoxLayout(blocks_container)
        self._edit_blocks_layout.setContentsMargins(0, 0, 0, 0)
        self._edit_blocks_layout.setSpacing(8)

        for sn_str in sorted(series.seasons.keys(), key=int):
            block = self._make_season_block(sn_str, series.seasons[sn_str])
            self._edit_blocks_layout.addWidget(block)

        layout.addWidget(blocks_container)

        # ── Add new season block ─────────────────────────────────
        new_block = QFrame()
        new_block.setObjectName("new_season_block")
        nb = QVBoxLayout(new_block)
        nb.setContentsMargins(10, 8, 10, 8)
        nb.setSpacing(8)
        nb.addWidget(_lbl("Add new season", "new_season_label"))

        pair_row = QHBoxLayout()
        pair_row.setSpacing(8)

        sn_col = _transparent()
        sc = QVBoxLayout(sn_col)
        sc.setContentsMargins(0, 0, 0, 0)
        sc.setSpacing(4)
        sc.addWidget(_lbl("Season #", "field_label"))
        self._new_sn = QSpinBox()
        self._new_sn.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._new_sn.setMinimum(1)
        self._new_sn.setMaximum(999)
        self._new_sn.setValue(len(series.seasons) + 1)
        sc.addWidget(self._new_sn)
        pair_row.addWidget(sn_col)

        ep_col = _transparent()
        epc = QVBoxLayout(ep_col)
        epc.setContentsMargins(0, 0, 0, 0)
        epc.setSpacing(4)
        epc.addWidget(_lbl("Episodes", "field_label"))
        self._new_eps = QSpinBox()
        self._new_eps.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._new_eps.setMinimum(1)
        self._new_eps.setMaximum(9999)
        self._new_eps.setValue(10)
        epc.addWidget(self._new_eps)
        pair_row.addWidget(ep_col)
        nb.addLayout(pair_row)

        nb.addWidget(_lbl("Label (optional)", "field_label"))
        self._new_label = QLineEdit()
        self._new_label.setPlaceholderText("e.g. Part 1, OVA, Arc name…")
        nb.addWidget(self._new_label)

        # Two buttons in same row: Add to watching + Add to P2W
        add_btn_row = QHBoxLayout()
        add_btn_row.setSpacing(8)

        add_season_btn = QPushButton("＋  Add season")
        add_season_btn.setObjectName("btn_add")
        add_season_btn.clicked.connect(lambda: self._on_add_season(False))
        add_btn_row.addWidget(add_season_btn)

        add_p2w_btn = QPushButton("＋  Add to Plan to Watch")
        add_p2w_btn.setObjectName("btn_p2w")
        add_p2w_btn.clicked.connect(lambda: self._on_add_season(True))
        add_btn_row.addWidget(add_p2w_btn)

        nb.addLayout(add_btn_row)
        layout.addWidget(new_block)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setObjectName("btn_cancel")
        close_btn.clicked.connect(self._close_edit)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        panel.installEventFilter(self)
        return panel

    def _make_season_block(self, sn_str: str, season: Season) -> QFrame:
        block = QFrame()
        block.setObjectName("season_edit_block")
        bl = QVBoxLayout(block)
        bl.setContentsMargins(10, 8, 10, 8)
        bl.setSpacing(8)
        header_row = QHBoxLayout()
        header_row.addWidget(_lbl(f"📅  Season {sn_str}", "edit_season_label"))
        header_row.addStretch()
        del_season_btn = QPushButton("✕")
        del_season_btn.setObjectName("btn_del")
        del_season_btn.setFixedSize(24, 22)
        del_season_btn.setToolTip(f"Remove Season {sn_str}")
        del_season_btn.clicked.connect(
            lambda _, sn=int(sn_str): self.season_delete_requested.emit(self._series.id, sn)
        )
        header_row.addWidget(del_season_btn)
        bl.addLayout(header_row)

        bl.addWidget(_lbl("Label (optional)", "field_label"))
        label_input = QLineEdit(season.label)
        label_input.setPlaceholderText("e.g. Part 1, OVA, Shippuden Arc…")
        bl.addWidget(label_input)

        fields_row = QHBoxLayout()
        fields_row.setSpacing(8)

        eps_col = _transparent()
        ec = QVBoxLayout(eps_col)
        ec.setContentsMargins(0, 0, 0, 0)
        ec.setSpacing(4)
        ec.addWidget(_lbl("Total episodes", "field_label"))
        eps_spin = QSpinBox()
        eps_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        eps_spin.setMinimum(1)
        eps_spin.setMaximum(9999)
        eps_spin.setValue(season.episodes)
        ec.addWidget(eps_spin)
        fields_row.addWidget(eps_col)

        w_col = _transparent()
        wc = QVBoxLayout(w_col)
        wc.setContentsMargins(0, 0, 0, 0)
        wc.setSpacing(4)
        wc.addWidget(_lbl("Episodes watched", "field_label"))
        w_spin = ClampSpinBox()
        w_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        w_spin.setMinimum(0)
        w_spin.setMaximum(season.episodes)
        w_spin.setValue(season.watched)
        wc.addWidget(w_spin)
        fields_row.addWidget(w_col)

        eps_spin.editingFinished.connect(lambda e=eps_spin, ws=w_spin: ws.setMaximum(e.value()))

        bl.addLayout(fields_row)

        def _save(sn=sn_str, e=eps_spin, w=w_spin, li=label_input):
            rating = self._series.seasons[sn].rating if sn in self._series.seasons else 0
            name = self._name_input.text().strip() or self._series.name
            self.auto_save_requested.emit(
                self._series.id, name, self._kind_selector.value, self._alt_names_parsed(),
                {sn: {"episodes": e.value(), "watched": w.value(),
                      "rating": rating, "label": li.text().strip()}},
            )

        eps_spin.editingFinished.connect(_save)
        w_spin.editingFinished.connect(_save)
        label_input.editingFinished.connect(_save)

        self._season_inputs[sn_str] = {"eps": eps_spin, "watched": w_spin, "label": label_input}
        return block

    # ── Actions ──────────────────────────────────────────────────

    def _toggle_edit(self):
        if self._edit_panel is None:
            self._edit_panel = self._build_edit_panel(self._series)
            self._edit_panel.setVisible(False)
            self._outer.addWidget(self._edit_panel)
        self._edit_panel.setVisible(not self._edit_panel.isVisible())

    def _close_edit(self):
        if self._edit_panel is not None:
            self._edit_panel.setVisible(False)
        self.edit_closed.emit(self._series.id)

    def eventFilter(self, obj, event):
        """Close the edit panel when clicking on its background (not on child widgets)."""
        if (self._edit_panel is not None
                and obj is self._edit_panel
                and event.type() == QEvent.Type.MouseButtonPress):
            if self._edit_panel.childAt(event.pos()) is None:
                self._close_edit()
                return True
        return super().eventFilter(obj, event)

    def _on_add_season(self, p2w: bool = False):
        sn_val  = self._new_sn.value()
        eps_val = self._new_eps.value()
        key     = str(sn_val)

        if key in self._series.seasons:
            return

        lbl_val    = self._new_label.text().strip()
        new_season = Season(episodes=eps_val, watched=0, rating=0, label=lbl_val, p2w=p2w)
        self._series.seasons[key] = new_season

        if not p2w:
            if self._season_rows:
                self._seasons_layout.addWidget(_hline())
            row = SeasonRow(self._series.id, sn_val, new_season)
            row.watch_requested.connect(self.watch_requested)
            row.complete_requested.connect(self.complete_requested)
            row.rate_requested.connect(self.rate_requested)
            self._seasons_layout.addWidget(row)
            self._season_rows[key] = row

        block = self._make_season_block(key, new_season)
        self._edit_blocks_layout.addWidget(block)

        self.add_season_requested.emit(self._series.id, sn_val, eps_val, p2w)

        next_sn = max(int(k) for k in self._series.seasons) + 1
        self._new_sn.setValue(next_sn)
        self._new_eps.setValue(10)
        self._new_label.clear()

    def update_season_rating(self, season_num: int, rating: int):
        """Refresh the avg badge (rating is persisted via SeasonRow combo)."""
        self._refresh_avg_badge()

    def _recheck_completed(self):
        active = {k: v for k, v in self._series.seasons.items() if not v.p2w}
        has_p2w = any(v.p2w for v in self._series.seasons.values())
        completed = (
            bool(active)
            and not has_p2w
            and all(v.watched >= v.episodes for v in active.values())
        )
        self.setProperty("completed", "true" if completed else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def _refresh_avg_badge(self):
        active = {k: v for k, v in self._series.seasons.items() if not v.p2w}
        rated = [v.rating for v in active.values() if v.rating > 0]
        avg = round(sum(rated) / len(rated)) if rated else None
        if avg is not None:
            self._avg_lbl.setText(f"⭐ {avg}")
            self._avg_lbl.setVisible(True)
        else:
            self._avg_lbl.setVisible(False)

    def update_name(self, name: str, alt_names: list[str] = None):
        self._name_lbl.setText(name)
        if alt_names is not None:
            self._altname_lbl.setText("  /  ".join(alt_names))
            self._altname_lbl.setVisible(bool(alt_names))

    def _alt_names_parsed(self) -> list[str]:
        return [n.strip() for n in self._alt_names_input.text().split(",") if n.strip()]

    def _auto_save_name(self):
        name = self._name_input.text().strip() or self._series.name
        self.auto_save_requested.emit(
            self._series.id, name, self._kind_selector.value, self._alt_names_parsed(), {}
        )

    def apply_watch(self, season_num: int, updated_season: Season):
        """Replace a SeasonRow in-place and sync the edit panel spinbox."""
        key = str(season_num)
        old_row = self._season_rows.get(key)
        if old_row:
            idx = self._seasons_layout.indexOf(old_row)
            self._seasons_layout.removeWidget(old_row)
            old_row.setParent(None)
            new_row = SeasonRow(self._series.id, season_num, updated_season)
            new_row.watch_requested.connect(self.watch_requested)
            new_row.complete_requested.connect(self.complete_requested)
            new_row.rate_requested.connect(self.rate_requested)
            self._seasons_layout.insertWidget(idx, new_row)
            self._season_rows[key] = new_row
        self._series.seasons[key] = updated_season
        inp = self._season_inputs.get(key)
        if inp:
            inp['watched'].setValue(updated_season.watched)

        self._recheck_completed()

    def update_kind_icon(self, kind: str):
        """Refresh the kind icon label if kind changed without a full rebuild."""
        pass  # icon label not stored as instance var; full rebuild handles kind changes


class P2WCard(QFrame):
    """Right-column card showing only the plan-to-watch seasons of a series."""
    p2w_remove_requested    = pyqtSignal('qlonglong', int)   # series_id, season_num (start watching)
    delete_requested        = pyqtSignal('qlonglong')         # delete entire series
    season_delete_requested = pyqtSignal('qlonglong', int)    # delete a P2W season
    auto_save_requested     = pyqtSignal('qlonglong', str, object)  # id, name, season_edits dict

    def __init__(self, series: Series, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("p2w_card")
        self._series = series
        self._p2w_season_inputs: dict[str, dict] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header
        header = _transparent()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(14, 10, 14, 6)
        hl.setSpacing(8)
        hl.addWidget(_lbl(_KIND_ICON.get(series.kind, "📋")))
        self._name_lbl = _lbl(series.name, "series_name")
        self._name_lbl.setWordWrap(True)
        hl.addWidget(self._name_lbl, 1)

        edit_btn = QPushButton("✏")
        edit_btn.setObjectName("btn_edit")
        edit_btn.setFixedSize(30, 28)
        edit_btn.setToolTip("Edit")
        edit_btn.clicked.connect(self._toggle_edit)
        hl.addWidget(edit_btn)

        del_btn = QPushButton("🗑")
        del_btn.setObjectName("btn_del")
        del_btn.setFixedSize(30, 28)
        del_btn.setToolTip("Delete series")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(series.id))
        hl.addWidget(del_btn)
        outer.addWidget(header)

        # P2W season rows
        body = _transparent()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(14, 0, 14, 10)
        body_layout.setSpacing(0)

        p2w_seasons = [
            (k, v) for k, v in sorted(series.seasons.items(), key=lambda x: int(x[0]))
            if v.p2w
        ]
        for i, (sn_str, season) in enumerate(p2w_seasons):
            if i > 0:
                body_layout.addWidget(_hline())
            body_layout.addWidget(self._make_row(series.id, int(sn_str), season))

        outer.addWidget(body)

        self._edit_panel = None  # built lazily on first open
        self._outer_layout = outer

    def _build_edit_panel(self, series: Series) -> QFrame:
        panel = QFrame()
        panel.setObjectName("edit_panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)

        layout.addWidget(_lbl("Series name", "field_label"))
        self._name_input = QLineEdit(series.name)
        self._name_input.editingFinished.connect(self._auto_save)
        layout.addWidget(self._name_input)

        layout.addWidget(_hline())

        p2w_seasons = [
            (k, v) for k, v in sorted(series.seasons.items(), key=lambda x: int(x[0]))
            if v.p2w
        ]
        for sn_str, season in p2w_seasons:
            layout.addWidget(self._make_season_edit_block(sn_str, season))

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setObjectName("btn_cancel")
        close_btn.clicked.connect(lambda: self._edit_panel.setVisible(False))
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        return panel

    def _make_season_edit_block(self, sn_str: str, season: Season) -> QFrame:
        block = QFrame()
        block.setObjectName("season_edit_block")
        bl = QVBoxLayout(block)
        bl.setContentsMargins(8, 6, 8, 6)
        bl.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.addWidget(_lbl(f"📅  Season {sn_str}", "edit_season_label"))
        header_row.addStretch()
        del_btn = QPushButton("✕")
        del_btn.setObjectName("btn_del")
        del_btn.setFixedSize(24, 22)
        del_btn.setToolTip(f"Remove Season {sn_str}")
        del_btn.clicked.connect(
            lambda _, sn=int(sn_str): self.season_delete_requested.emit(self._series.id, sn)
        )
        header_row.addWidget(del_btn)
        bl.addLayout(header_row)

        bl.addWidget(_lbl("Label", "field_label"))
        label_input = QLineEdit(season.label)
        label_input.setPlaceholderText("e.g. Part 1, OVA…")
        bl.addWidget(label_input)

        eps_col = _transparent()
        ec = QVBoxLayout(eps_col)
        ec.setContentsMargins(0, 0, 0, 0)
        ec.setSpacing(4)
        ec.addWidget(_lbl("Total episodes", "field_label"))
        eps_spin = QSpinBox()
        eps_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        eps_spin.setMinimum(1)
        eps_spin.setMaximum(9999)
        eps_spin.setValue(season.episodes)
        ec.addWidget(eps_spin)
        bl.addWidget(eps_col)

        eps_spin.editingFinished.connect(self._auto_save)
        label_input.editingFinished.connect(self._auto_save)

        self._p2w_season_inputs[sn_str] = {"eps": eps_spin, "label": label_input}
        return block

    def _make_row(self, series_id: int, season_num: int, season: Season) -> QWidget:
        row = _transparent()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 5, 0, 5)
        rl.setSpacing(10)

        label_text = season.label if season.label else f"Season {season_num}"
        lbl = _lbl(label_text, "season_label")
        lbl.setWordWrap(True)
        rl.addWidget(lbl, 1)

        rl.addWidget(_lbl(f"{season.episodes} ep{'s' if season.episodes != 1 else ''}", "eps_label"))

        start_btn = QPushButton("▶  Start")
        start_btn.setObjectName("btn_start")
        start_btn.setFixedHeight(26)
        start_btn.setToolTip("Move to watching list")
        start_btn.clicked.connect(
            lambda: self.p2w_remove_requested.emit(series_id, season_num)
        )
        rl.addWidget(start_btn)
        return row

    def _toggle_edit(self):
        if self._edit_panel is None:
            self._edit_panel = self._build_edit_panel(self._series)
            self._edit_panel.setVisible(False)
            self._outer_layout.addWidget(self._edit_panel)
        self._edit_panel.setVisible(not self._edit_panel.isVisible())

    def _auto_save(self):
        name = self._name_input.text().strip() or self._series.name
        season_edits = {
            sn_str: {"episodes": inp["eps"].value(), "label": inp["label"].text().strip()}
            for sn_str, inp in self._p2w_season_inputs.items()
        }
        self.auto_save_requested.emit(self._series.id, name, season_edits)

    def update_name(self, name: str):
        self._name_lbl.setText(name)


class SpinWheel(QWidget):
    """Animated spinning wheel — picks a random entry from a list."""
    spun = pyqtSignal(str)

    _COLORS = [
        "#2dd4a0", "#5b9cf6", "#f5a623", "#a78bfa",
        "#fb923c", "#f87171", "#34d399", "#60a5fa",
        "#fbbf24", "#c084fc", "#4ade80", "#f472b6",
    ]

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self._items: list[str] = []
        self._angle       = 0.0
        self._velocity    = 0.0
        self._decay       = 0.982
        self._target_item: str | None = None
        self._target_angle = 0.0
        self._result: str | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self)  -> QSize: return QSize(260, 260)
    def minimumSizeHint(self) -> QSize: return QSize(160, 160)

    def set_items(self, items: list[str]):
        self._items = list(items)
        self._result = None
        self.update()

    def is_spinning(self) -> bool:
        return self._timer.isActive()

    def spin(self):
        if not self._items or self._timer.isActive():
            return
        self._result = None
        n         = len(self._items)
        angle_per = 360.0 / n

        target_idx = random.randint(0, n - 1)
        self._target_item = self._items[target_idx]

        self._target_angle = (-(target_idx * angle_per + angle_per / 2)) % 360

        current          = self._angle % 360
        travel_to_target = (self._target_angle - current) % 360
        extra            = random.randint(5, 9) * 360
        total            = extra + travel_to_target

        self._velocity = total * (1.0 - self._decay)
        self._timer.start()

    def _tick(self):
        self._angle = (self._angle + self._velocity) % 360
        self._velocity *= self._decay
        self.update()
        if self._velocity < 0.25:
            self._timer.stop()
            self._angle  = self._target_angle
            self._result = self._target_item
            self.update()
            if self._result:
                self.spun.emit(self._result)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h  = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        r      = min(w, h) / 2.0 - 24

        if not self._items:
            painter.setPen(QColor("#5a6480"))
            f = QFont("Segoe UI", 10)
            painter.setFont(f)
            painter.drawText(
                QRectF(0, 0, w, h),
                Qt.AlignmentFlag.AlignCenter,
                "No plan-to-watch\nseries for this type",
            )
            return

        n         = len(self._items)
        angle_per = 360.0 / n
        colors    = [QColor(c) for c in self._COLORS]
        rim_rect  = QRectF(cx - r, cy - r, r * 2, r * 2)

        for i in range(n):
            my_start = self._angle + i * angle_per
            qt_start = int((90.0 - my_start) * 16)
            qt_span  = int(-angle_per * 16)

            painter.setBrush(QBrush(colors[i % len(colors)]))
            painter.setPen(QPen(QColor("#1e2433"), 1))
            painter.drawPie(rim_rect, qt_start, qt_span)

        # ── Radial text sizing ────────────────────────────────────
        # Text centre at mid-radius; rect spans hub → near-rim along the spoke.
        text_r      = r * 0.50
        radial_span = r * 0.70

        # Perpendicular gap between neighbouring segment boundaries at text_r
        arc_width = text_r * math.radians(angle_per)

        # Find the largest font size that fits the longest name, trying 1-4 lines.
        # Two constraints per attempt:
        #   width  → font_size ≤ radial_span / (chars_per_line × avg_char_width)
        #   height → font_size ≤ arc_width   / (n_lines × line_height_ratio)
        longest   = max(self._items, key=len) if self._items else ""
        font_size = 5
        n_lines   = 1
        for nl in range(1, 5):
            cpl = math.ceil(len(longest) / nl) if longest else 1
            fs  = int(min(
                radial_span / max(1.0, cpl * 0.70),   # width constraint (avg char ≈ 0.70×pt)
                arc_width   / max(1.0, nl  * 1.35),   # height constraint (line ≈ 1.35×pt)
                16,                                     # absolute cap
            ))
            if fs > font_size:
                font_size, n_lines = fs, nl

        font_size = max(5, font_size)
        lbl_font  = QFont("Segoe UI", font_size, QFont.Weight.Bold)
        half_span = radial_span / 2
        fh        = font_size * 1.35 * n_lines   # total rect height in px

        # AlignCenter | TextWordWrap — Qt wraps on spaces automatically
        txt_flags = int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap)

        for i, name in enumerate(self._items):
            my_mid   = self._angle + i * angle_per + angle_per / 2
            math_rad = math.radians(90.0 - my_mid)
            tx = cx + text_r * math.cos(math_rad)
            ty = cy - text_r * math.sin(math_rad)

            # Radial rotation: painter X-axis aligned with the outward spoke direction
            rot = (my_mid - 90) % 360
            if 90 < rot < 270:
                rot -= 180   # flip left-half spokes so text reads naturally from outside

            painter.save()
            painter.translate(tx, ty)
            painter.rotate(rot)
            painter.setFont(lbl_font)
            painter.setPen(QColor("#0a120e"))
            painter.drawText(QRectF(-half_span, -fh / 2, radial_span, fh), txt_flags, name)
            painter.restore()

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#3a4357"), 2))
        painter.drawEllipse(rim_rect)

        hub_r = max(10.0, r * 0.11)
        painter.setBrush(QBrush(QColor("#1e2433")))
        painter.setPen(QPen(QColor("#3a4357"), 2))
        painter.drawEllipse(QPointF(cx, cy), hub_r, hub_r)

        ptr_tip_y = cy - r - 4
        ptr_h, ptr_w = 14, 9
        triangle = QPolygonF([
            QPointF(cx,           ptr_tip_y + ptr_h),
            QPointF(cx - ptr_w,  ptr_tip_y),
            QPointF(cx + ptr_w,  ptr_tip_y),
        ])
        painter.setBrush(QBrush(QColor("#f5a623")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(triangle)

        if self._result and not self._timer.isActive():
            flash_r = r * 0.38
            painter.setBrush(QBrush(QColor(30, 36, 51, 210)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(cx, cy), flash_r, flash_r)
            painter.setPen(QColor("#2dd4a0"))
            f2 = QFont("Segoe UI", max(8, font_size + 1), QFont.Weight.Bold)
            painter.setFont(f2)
            painter.drawText(
                QRectF(cx - flash_r, cy - flash_r, flash_r * 2, flash_r * 2),
                Qt.AlignmentFlag.AlignCenter,
                "✓",
            )


class AddForm(QFrame):
    add_requested = pyqtSignal(str, int, int, str, str, bool)  # name, season, eps, label, kind, p2w

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("add_form")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(_lbl("ADD NEW SERIES", "section_label"))

        # Series name — full width
        layout.addWidget(_lbl("Series name", "field_label"))
        self._name = QLineEdit()
        self._name.setPlaceholderText("e.g. Breaking Bad")
        layout.addWidget(self._name)

        # Season + Episodes — narrower, side by side
        season_eps_row = QHBoxLayout()
        season_eps_row.setSpacing(10)

        sn_col = _transparent()
        sc = QVBoxLayout(sn_col)
        sc.setContentsMargins(0, 0, 0, 0)
        sc.setSpacing(4)
        sc.addWidget(_lbl("Season", "field_label"))
        self._season = QSpinBox()
        self._season.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._season.setMinimum(1)
        self._season.setMaximum(999)
        self._season.setValue(1)
        self._season.setFixedWidth(80)
        sc.addWidget(self._season)
        season_eps_row.addWidget(sn_col)

        eps_col = _transparent()
        ec = QVBoxLayout(eps_col)
        ec.setContentsMargins(0, 0, 0, 0)
        ec.setSpacing(4)
        ec.addWidget(_lbl("Total episodes", "field_label"))
        self._episodes = QSpinBox()
        self._episodes.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._episodes.setMinimum(1)
        self._episodes.setMaximum(9999)
        self._episodes.setValue(10)
        self._episodes.setFixedWidth(90)
        ec.addWidget(self._episodes)
        season_eps_row.addWidget(eps_col)

        lbl_col = _transparent()
        lc = QVBoxLayout(lbl_col)
        lc.setContentsMargins(0, 0, 0, 0)
        lc.setSpacing(4)
        lc.addWidget(_lbl("Season label (optional)", "field_label"))
        self._label = QLineEdit()
        self._label.setPlaceholderText("e.g. Part 1, OVA…")
        lc.addWidget(self._label)
        season_eps_row.addWidget(lbl_col, 1)

        layout.addLayout(season_eps_row)

        layout.addWidget(_lbl("Type", "field_label"))
        self._kind = KindSelector("tv")
        layout.addWidget(self._kind)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        p2w_btn = QPushButton("📋  Plan to Watch")
        p2w_btn.setObjectName("btn_p2w")
        btn_row.addWidget(p2w_btn)
        add_btn = QPushButton("＋  Add to list")
        add_btn.setObjectName("btn_add")
        btn_row.addWidget(add_btn)
        layout.addLayout(btn_row)

        add_btn.clicked.connect(self._on_add)
        p2w_btn.clicked.connect(self._on_add_p2w)
        self._name.returnPressed.connect(lambda: self._season.setFocus())

    def _on_add(self):
        self._emit_add(p2w=False)

    def _on_add_p2w(self):
        self._emit_add(p2w=True)

    def _emit_add(self, p2w: bool):
        name = self._name.text().strip()
        if not name:
            return
        self.add_requested.emit(
            name, self._season.value(), self._episodes.value(),
            self._label.text().strip(), self._kind.value, p2w,
        )

    def reset(self):
        """Clear input fields after a successful add. Kind is intentionally kept."""
        self._name.clear()
        self._season.setValue(1)
        self._episodes.setValue(10)
        self._label.clear()
        self._name.setFocus()


class Toast(QLabel):
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setVisible(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str):
        self.setText(f"  {text}  ")
        self.adjustSize()
        self._reposition()
        self.setVisible(True)
        self.raise_()
        self._timer.start(2400)

    def _reposition(self):
        if self.parent():
            pw = self.parent().width()
            ph = self.parent().height()
            self.move(pw - self.width() - 20, ph - self.height() - 24)
