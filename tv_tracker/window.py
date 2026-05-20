import threading
import time
from datetime import datetime
from PyQt6.QtCore import Qt, QTimer, QMetaObject, pyqtSlot
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QScrollArea,
    QLabel, QLineEdit, QPushButton, QStatusBar, QSizePolicy, QMessageBox,
)
from models import Season, Series, Tracker
from widgets import AddForm, SeriesCard, SeriesEditDialog, P2WCard, SpinWheel, Toast, MALImportDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._tracker = Tracker()
        self._toast: Toast = None
        self._cards: dict[int, SeriesCard] = {}
        self._p2w_cards: dict[int, P2WCard] = {}
        self._section_headers: dict[str, QLabel] = {}
        self._kind_filter: str | None = None
        self._filter_btns: dict[str, QPushButton] = {}
        self._spin_result_name: str | None = None
        self._load_result: tuple | None = None
        self._edit_dialogs: dict[int, SeriesEditDialog] = {}

        # Lazy loader:
        #   _left_pending    — raw data items not yet turned into widgets
        #   _prebuilt_queue  — widgets built off-layout, shown only on scroll
        self._left_pending: list = []
        self._prebuilt_queue: list = []
        self._scroll_connected = False

        # interval=0 fires when the event loop is idle (after all input/paint events)
        self._bg_build_timer = QTimer(self)
        self._bg_build_timer.setInterval(0)
        self._bg_build_timer.timeout.connect(self._bg_build_tick)

        # Deferred save: mutations mark dirty; timer batches the actual disk write
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(2000)   # 2 s debounce
        self._save_timer.timeout.connect(self._on_debounce)

        self._setup_ui()
        self._load()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_vbox = QVBoxLayout(central)
        root_vbox.setContentsMargins(0, 0, 0, 0)
        root_vbox.setSpacing(0)

        # ── Top row: AddForm (stretch 3) | Gamba (stretch 2) ────
        top_row = QWidget()
        top_row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        top_hbox = QHBoxLayout(top_row)
        top_hbox.setContentsMargins(20, 20, 20, 8)
        top_hbox.setSpacing(16)

        # Left top: AddForm + search + filter
        left_top = QWidget()
        left_top.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        lt = QVBoxLayout(left_top)
        lt.setContentsMargins(0, 0, 0, 0)
        lt.setSpacing(8)

        self._add_form = AddForm()
        self._add_form.add_requested.connect(self._on_add)
        lt.addWidget(self._add_form)

        self._import_mal_btn = QPushButton("⬆  Import MAL")
        self._import_mal_btn.setObjectName("kind_btn")
        self._import_mal_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._import_mal_btn.clicked.connect(self._on_import_mal)
        lt.addWidget(self._import_mal_btn)

        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Search by name…")
        self._search.setVisible(False)
        self._search.textChanged.connect(self._apply_filter)
        lt.addWidget(self._search)

        filter_row = QWidget()
        filter_row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._filter_row = filter_row
        fr = QHBoxLayout(filter_row)
        fr.setContentsMargins(0, 0, 0, 0)
        fr.setSpacing(6)
        for kind, label in [("tv", "📺  TV"), ("anime", "🎌  Anime"),
                             ("movie", "🎬  Movie"), ("horror", "👻  Horror")]:
            btn = QPushButton(label)
            btn.setObjectName("kind_btn")
            btn.setProperty("kind", kind)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _, k=kind: self._toggle_kind_filter(k))
            self._filter_btns[kind] = btn
            fr.addWidget(btn)
        sort_btn = QPushButton("⇅  A – Z")
        sort_btn.setObjectName("kind_btn")
        sort_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        sort_btn.clicked.connect(self._on_sort)
        fr.addWidget(sort_btn)
        fr.addStretch()
        filter_row.setVisible(False)
        lt.addWidget(filter_row)

        top_hbox.addWidget(left_top, 3)

        # Right top: Gamba spin panel
        gamba_widget = QWidget()
        gamba_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        gw = QVBoxLayout(gamba_widget)
        gw.setContentsMargins(0, 0, 0, 0)
        gw.setSpacing(8)

        spin_hdr = QLabel("🎲  GAMBA")
        spin_hdr.setObjectName("spin_col_header")
        spin_hdr.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        gw.addWidget(spin_hdr)

        self._spin_wheel = SpinWheel()
        self._spin_wheel.spun.connect(self._on_spin_result)
        gw.addWidget(self._spin_wheel, 1)

        self._spin_btn = QPushButton("🎰  Spin!")
        self._spin_btn.setObjectName("btn_spin")
        self._spin_btn.clicked.connect(self._on_spin)
        gw.addWidget(self._spin_btn)

        self._spin_result_lbl = QLabel("")
        self._spin_result_lbl.setObjectName("spin_result_lbl")
        self._spin_result_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._spin_result_lbl.setWordWrap(True)
        self._spin_result_lbl.setVisible(False)
        gw.addWidget(self._spin_result_lbl)

        self._spin_start_btn = QPushButton("▶  Start")
        self._spin_start_btn.setObjectName("btn_start")
        self._spin_start_btn.setVisible(False)
        self._spin_start_btn.clicked.connect(self._on_spin_start)
        gw.addWidget(self._spin_start_btn)

        top_hbox.addWidget(gamba_widget, 2)

        root_vbox.addWidget(top_row)

        # ── Body row: watching list (stretch 3) | P2W (stretch 2) ─
        body = QWidget()
        body.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        body_hbox = QHBoxLayout(body)
        body_hbox.setContentsMargins(20, 0, 20, 20)
        body_hbox.setSpacing(16)

        # Left: active watching list
        self._left_scroll = QScrollArea()
        self._left_scroll.setWidgetResizable(True)
        self._left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._left_content = QWidget()
        left_outer = QVBoxLayout(self._left_content)
        left_outer.setContentsMargins(0, 0, 4, 0)
        left_outer.setSpacing(0)
        left_outer.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._list_container = QWidget()
        self._list_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(10)
        left_outer.addWidget(self._list_container)

        self._empty_label = QLabel("📺\n\nNo series yet — add one above!")
        self._empty_label.setObjectName("empty_label")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_outer.addWidget(self._empty_label)

        self._left_scroll.setWidget(self._left_content)
        body_hbox.addWidget(self._left_scroll, 3)

        # Right: plan to watch
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._right_content = QWidget()
        right_outer = QVBoxLayout(self._right_content)
        right_outer.setContentsMargins(0, 0, 0, 0)
        right_outer.setSpacing(0)
        right_outer.setAlignment(Qt.AlignmentFlag.AlignTop)

        p2w_hdr = QLabel("📋  PLAN TO WATCH")
        p2w_hdr.setObjectName("p2w_col_header")
        p2w_hdr.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        right_outer.addWidget(p2w_hdr)

        self._p2w_container = QWidget()
        self._p2w_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._p2w_layout = QVBoxLayout(self._p2w_container)
        self._p2w_layout.setContentsMargins(0, 0, 0, 0)
        self._p2w_layout.setSpacing(10)
        right_outer.addWidget(self._p2w_container)

        self._p2w_empty_label = QLabel("Nothing planned yet.\n\nUse \"Plan to Watch\"\nwhen adding a series.")
        self._p2w_empty_label.setObjectName("empty_label")
        self._p2w_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._p2w_empty_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right_outer.addWidget(self._p2w_empty_label)

        right_scroll.setWidget(self._right_content)
        body_hbox.addWidget(right_scroll, 2)

        root_vbox.addWidget(body, 1)

        self._toast = Toast(central)

        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self._status_lbl = QLabel("—")
        status_bar.addWidget(self._status_lbl)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._toast:
            self._toast._reposition()

    def closeEvent(self, event):
        """Flush any pending writes before the window closes."""
        self._save_timer.stop()
        self._tracker.flush_now()
        super().closeEvent(event)

    # ── Deferred save ────────────────────────────────────────────

    def _schedule_save(self):
        """Restart the 2-second debounce timer and show pending-save status."""
        self._set_status("Unsaved changes…")
        self._save_timer.start()   # start() restarts if already running

    def _on_debounce(self):
        """Timer fired — flush to disk in a background thread to avoid blocking the UI."""
        self._set_status("Saving…")
        t = threading.Thread(target=self._bg_flush, daemon=True)
        t.start()

    def _bg_flush(self):
        """Runs on the background thread."""
        self._tracker.flush_now()
        # Qt UI must only be updated from the main thread; invokeMethod queues the call safely
        QMetaObject.invokeMethod(self, "_on_flush_done", Qt.ConnectionType.QueuedConnection)

    @pyqtSlot()
    def _on_flush_done(self):
        self._set_status(self._saved_msg())

    def _on_save_btn(self):
        """Manual save: synchronous, immediate."""
        self._save_timer.stop()
        self._tracker.flush_now()
        self._set_status(self._saved_msg())

    def _load(self):
        """Start loading saved data on a background thread; the window appears immediately."""
        self._set_status("Loading…")
        t = threading.Thread(target=self._bg_load, daemon=True)
        t.start()

    def _bg_load(self):
        result = self._tracker.load()
        self._load_result = (result, len(self._tracker.series))
        QMetaObject.invokeMethod(self, "_on_load_ready", Qt.ConnectionType.QueuedConnection)

    @pyqtSlot()
    def _on_load_ready(self):
        result, n = self._load_result
        if result == "ok":
            self._set_status(f"Loading {n} series…")
        elif result == "empty":
            self._set_status("No saved data yet — add your first series below")
        else:
            self._set_status("Storage error — data added this session won't be saved")

        self._clear_both_columns()

        # Right (P2W) column — usually small; build it all at once
        self._right_content.setUpdatesEnabled(False)
        try:
            for s in self._tracker.series:
                if any(v.p2w for v in s.seasons.values()):
                    card = self._make_p2w_card(s)
                    self._p2w_layout.addWidget(card)
                    self._p2w_cards[s.id] = card
        finally:
            self._right_content.setUpdatesEnabled(True)

        # Populate the data queue for the left column
        for kind, label_text in self._KIND_LABELS:
            group = [s for s in self._tracker.series
                     if s.kind == kind and any(not v.p2w for v in s.seasons.values())]
            if group:
                self._left_pending.append(('header', kind, label_text))
                for s in group:
                    self._left_pending.append(('left', s))

        # Flush the first batch straight to the layout — user sees content immediately
        self._flush_pending_to_layout(20)
        self._apply_filter()

        n_total = len(self._tracker.series)
        self.setWindowTitle(f"My Series Tracker{'  —  ' + str(n_total) + ' series' if n_total else ''}")
        self._update_spin_wheel()

        if self._left_pending:
            self._bg_build_timer.start()
            self._left_scroll.verticalScrollBar().valueChanged.connect(self._on_left_scroll)
            self._scroll_connected = True
        elif result == "ok":
            self._set_status(f"Auto-loaded {n} record{'s' if n != 1 else ''} from storage")

    # ── Two-queue lazy loader ────────────────────────────────────

    def _flush_pending_to_layout(self, count=None):
        """Build items from _left_pending directly into the layout (used for the initial batch)."""
        added = 0
        while self._left_pending:
            if count is not None and added >= count:
                break
            item = self._left_pending.pop(0)
            if item[0] == 'header':
                _, kind, label_text = item
                hdr = QLabel(label_text)
                hdr.setObjectName("list_section_lbl")
                self._list_layout.addWidget(hdr)
                self._section_headers[kind] = hdr
            else:
                _, s = item
                card = self._make_left_card(s)
                self._list_layout.addWidget(card)
                self._cards[s.id] = card
                added += 1

    def _bg_build_tick(self):
        """Build exactly one item per idle tick — maximum blocking is one cheap card (~0.5 ms)."""
        if not self._left_pending:
            self._bg_build_timer.stop()
            return
        item = self._left_pending.pop(0)
        if item[0] == 'header':
            _, kind, label_text = item
            hdr = QLabel(label_text)
            hdr.setObjectName("list_section_lbl")
            self._prebuilt_queue.append(('header', kind, hdr))
        else:
            _, s = item
            card = self._make_left_card(s)
            self._prebuilt_queue.append(('left', s.id, card))

    def _on_left_scroll(self, value: int):
        """Flush pre-built cards into the layout as the user scrolls toward the bottom."""
        if not self._prebuilt_queue:
            return
        sb = self._left_scroll.verticalScrollBar()
        if sb.maximum() > 0 and value >= sb.maximum() - 400:
            self._flush_prebuilt_to_layout(10)

    def _flush_prebuilt_to_layout(self, count=None):
        """Move pre-built widgets from the queue into the layout, applying current filter."""
        flushed = 0
        query = self._search.text().strip().lower()
        while self._prebuilt_queue:
            if count is not None and flushed >= count:
                break
            item = self._prebuilt_queue.pop(0)
            if item[0] == 'header':
                _, kind, hdr = item
                if any(s.kind == kind and any(not v.p2w for v in s.seasons.values())
                       for s in self._tracker.series):
                    self._list_layout.addWidget(hdr)
                    self._section_headers[kind] = hdr
                else:
                    hdr.setParent(None)
            else:
                _, sid, card = item
                s = self._tracker._find(sid)
                if s and any(not v.p2w for v in s.seasons.values()):
                    self._list_layout.addWidget(card)
                    self._cards[sid] = card
                    kind_ok = self._kind_filter is None or s.kind == self._kind_filter
                    name_ok = not query or query in s.name.lower() or any(query in a.lower() for a in s.alt_names)
                    card.setVisible(kind_ok and name_ok)
                    flushed += 1
                else:
                    card.setParent(None)

        if not self._prebuilt_queue and not self._left_pending and self._load_result:
            result, n = self._load_result
            if result == "ok":
                self._set_status(f"Auto-loaded {n} record{'s' if n != 1 else ''} from storage")

    def _make_left_card(self, s) -> SeriesCard:
        card = SeriesCard(s)
        card.watch_requested.connect(self._on_watch)
        card.delete_requested.connect(self._on_delete)
        card.complete_requested.connect(self._on_complete)
        card.rate_requested.connect(self._on_rate)
        card.dirty_requested.connect(self._on_season_dirty)
        card.edit_requested.connect(self._on_edit_requested)
        return card

    def _make_p2w_card(self, s) -> P2WCard:
        card = P2WCard(s)
        card.p2w_remove_requested.connect(self._on_p2w_remove)
        card.delete_requested.connect(self._on_delete)
        card.season_delete_requested.connect(self._on_delete_season)
        card.auto_save_requested.connect(self._on_p2w_auto_save)
        return card

    _KIND_LABELS = [("tv", "📺  TV SERIES"), ("anime", "🎌  ANIME"),
                    ("movie", "🎬  MOVIES"), ("horror", "👻  HORROR")]

    def _rebuild(self):
        self._left_content.setUpdatesEnabled(False)
        self._right_content.setUpdatesEnabled(False)
        try:
            self._rebuild_inner()
        finally:
            self._left_content.setUpdatesEnabled(True)
            self._right_content.setUpdatesEnabled(True)

    def _clear_both_columns(self):
        self._left_pending.clear()
        self._bg_build_timer.stop()
        for item in self._prebuilt_queue:
            item[-1].setParent(None)
        self._prebuilt_queue.clear()
        if self._scroll_connected:
            self._left_scroll.verticalScrollBar().valueChanged.disconnect(self._on_left_scroll)
            self._scroll_connected = False
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                w = item.widget()
                w.hide()
                w.setParent(None)
        while self._p2w_layout.count():
            item = self._p2w_layout.takeAt(0)
            if item.widget():
                w = item.widget()
                w.hide()
                w.setParent(None)
        self._cards = {}
        self._p2w_cards = {}
        self._section_headers = {}

    def _rebuild_inner(self):
        self._clear_both_columns()

        by_kind = {k: [s for s in self._tracker.series if s.kind == k]
                   for k, _ in self._KIND_LABELS}

        # Left: series with ≥1 non-P2W season
        for kind, label_text in self._KIND_LABELS:
            group = [s for s in by_kind[kind]
                     if any(not v.p2w for v in s.seasons.values())]
            if not group:
                continue
            hdr = QLabel(label_text)
            hdr.setObjectName("list_section_lbl")
            self._list_layout.addWidget(hdr)
            self._section_headers[kind] = hdr

            for s in group:
                card = self._make_left_card(s)
                self._list_layout.addWidget(card)
                self._cards[s.id] = card

        # Right: series with ≥1 P2W season
        for s in self._tracker.series:
            if any(v.p2w for v in s.seasons.values()):
                p2w_card = self._make_p2w_card(s)
                self._p2w_layout.addWidget(p2w_card)
                self._p2w_cards[s.id] = p2w_card

        n = len(self._tracker.series)
        self.setWindowTitle(f"My Series Tracker{'  —  ' + str(n) + ' series' if n else ''}")
        self._update_spin_wheel()
        self._apply_filter()

    def _scroll_to_card(self, series_id: int):
        """Scroll the left watching list to make the given series card visible."""
        card = self._cards.get(series_id)
        if card and self._left_scroll:
            QTimer.singleShot(0, lambda: self._left_scroll.ensureWidgetVisible(card))

    def _toggle_kind_filter(self, kind: str):
        self._kind_filter = None if self._kind_filter == kind else kind
        for k, btn in self._filter_btns.items():
            btn.setProperty("active", k == self._kind_filter)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._apply_filter()
        self._update_spin_wheel()

    def _update_spin_wheel(self):
        items = [
            s.name for s in self._tracker.series
            if any(v.p2w for v in s.seasons.values())
            and (self._kind_filter is None or s.kind == self._kind_filter)
        ]
        self._spin_wheel.set_items(items)
        self._spin_result_lbl.setVisible(False)
        self._spin_start_btn.setVisible(False)
        self._spin_btn.setEnabled(bool(items))

    def _apply_filter(self):
        query = self._search.text().strip().lower()
        if query:
            if self._left_pending:
                self._flush_pending_to_layout(count=None)
                self._bg_build_timer.stop()
            if self._prebuilt_queue:
                self._flush_prebuilt_to_layout(count=None)
        has_series = bool(self._tracker.series)
        self._search.setVisible(has_series)
        self._filter_row.setVisible(has_series)

        # Left column
        visible_kinds: set[str] = set()
        any_left = False
        for sid, card in self._cards.items():
            s = self._tracker._find(sid)
            name_ok = not query or (s and (
                query in s.name.lower() or
                any(query in a.lower() for a in s.alt_names)
            ))
            kind_ok = self._kind_filter is None or (s and s.kind == self._kind_filter)
            visible = name_ok and kind_ok
            card.setVisible(visible)
            if visible and s:
                any_left = True
                visible_kinds.add(s.kind)

        for kind, hdr in self._section_headers.items():
            hdr.setVisible(kind in visible_kinds)

        self._list_container.setVisible(any_left)
        if not has_series:
            self._empty_label.setText("📺\n\nNo series yet — add one above!")
            self._empty_label.setVisible(True)
        elif not any_left:
            txt = (f"No results for \"{self._search.text().strip()}\""
                   if query else "All series are in plan to watch.")
            self._empty_label.setText(txt)
            self._empty_label.setVisible(True)
        else:
            self._empty_label.setVisible(False)

        # Right column (P2W)
        any_p2w = False
        for sid, card in self._p2w_cards.items():
            s = self._tracker._find(sid)
            name_ok = not query or (s and (
                query in s.name.lower() or
                any(query in a.lower() for a in s.alt_names)
            ))
            kind_ok = self._kind_filter is None or (s and s.kind == self._kind_filter)
            visible = name_ok and kind_ok
            card.setVisible(visible)
            if visible:
                any_p2w = True

        self._p2w_container.setVisible(any_p2w)
        self._p2w_empty_label.setVisible(not any_p2w)

    # ── Spin handlers ────────────────────────────────────────────

    def _on_spin(self):
        self._spin_result_lbl.setVisible(False)
        self._spin_start_btn.setVisible(False)
        self._spin_btn.setEnabled(False)
        self._spin_wheel.spin()

    def _on_spin_result(self, name: str):
        self._spin_result_name = name
        self._spin_result_lbl.setText(f"🎉  {name}")
        self._spin_result_lbl.setVisible(True)
        self._spin_start_btn.setVisible(True)
        self._spin_btn.setEnabled(True)

    def _on_spin_start(self):
        name = self._spin_result_name
        if not name:
            return
        series = next((s for s in self._tracker.series if s.name == name), None)
        if not series:
            return
        # Move the first P2W season (lowest number) to watching
        p2w_seasons = sorted(
            [(int(k), v) for k, v in series.seasons.items() if v.p2w],
            key=lambda x: x[0],
        )
        if not p2w_seasons:
            return
        season_num = p2w_seasons[0][0]
        self._tracker.set_season_p2w(series.id, season_num, False)
        self._schedule_save()
        self._rebuild()
        self._scroll_to_card(series.id)
        self._spin_result_lbl.setVisible(False)
        self._spin_start_btn.setVisible(False)
        self._spin_result_name = None
        self._toast.show_message(f"Started \"{name}\"!")

    # ── Series handlers ──────────────────────────────────────────

    def _on_sort(self):
        self._tracker.sort_alphabetically()
        self._rebuild()
        self._on_save_btn()   # sort is explicit — flush immediately
        self._toast.show_message("Series sorted A – Z!")

    def _on_add(self, name: str, season: int, episodes: int, label: str, kind: str, p2w: bool):
        # Smart add: binary search when sorted, linear fallback otherwise
        existing = self._tracker.find_by_name(name)
        if existing:
            key = str(season)
            if key in existing.seasons:
                self._toast.show_message(
                    f"Season {season} already exists in \"{existing.name}\"!"
                )
                return  # leave form untouched so user can fix the season number
            existing.seasons[key] = Season(episodes=episodes, watched=0, rating=0, label=label, p2w=p2w)
            self._tracker._mark_dirty()
            self._schedule_save()
            self._insert_or_replace_card(existing)
            self._scroll_to_card(existing.id)
            self._add_form.reset()
            msg = "Season added to Plan to Watch!" if p2w else "Season added!"
            self._toast.show_message(msg)
            return

        # New series
        s = self._tracker.add_series(name, season, episodes, 0, kind, p2w, label=label)
        self._schedule_save()
        self._insert_or_replace_card(s)
        self._scroll_to_card(s.id)
        self._add_form.reset()
        msg = "Added to Plan to Watch!" if p2w else "Series added!"
        self._toast.show_message(msg)

    def _insert_or_replace_card(self, s):
        """Insert or replace cards for series s without a full rebuild."""
        self._left_content.setUpdatesEnabled(False)
        self._right_content.setUpdatesEnabled(False)
        try:
            self._do_insert_or_replace_card(s)
        finally:
            self._left_content.setUpdatesEnabled(True)
            self._right_content.setUpdatesEnabled(True)
        n = len(self._tracker.series)
        self.setWindowTitle(f"My Series Tracker{'  —  ' + str(n) + ' series' if n else ''}")
        self._update_spin_wheel()
        self._apply_filter()

    def _do_insert_or_replace_card(self, s):
        has_active = any(not v.p2w for v in s.seasons.values())
        has_p2w    = any(v.p2w    for v in s.seasons.values())

        # ── Left column ──────────────────────────────────────────
        old_card = self._cards.pop(s.id, None)
        if old_card:
            idx = self._list_layout.indexOf(old_card)
            self._list_layout.removeWidget(old_card)
            old_card.setParent(None)
        else:
            idx = -1

        if has_active:
            card = self._make_left_card(s)
            self._cards[s.id] = card

            if idx >= 0:
                # Replace in-place at the same position
                self._list_layout.insertWidget(idx, card)
            else:
                # Insert at end of the kind group, creating header if needed
                insert_idx = self._kind_group_end_index(s.kind)
                self._list_layout.insertWidget(insert_idx, card)

        # ── Right column (P2W) ───────────────────────────────────
        old_p2w = self._p2w_cards.pop(s.id, None)
        if old_p2w:
            self._p2w_layout.removeWidget(old_p2w)
            old_p2w.setParent(None)

        if has_p2w:
            p2w_card = self._make_p2w_card(s)
            self._p2w_layout.addWidget(p2w_card)
            self._p2w_cards[s.id] = p2w_card

    def _kind_group_end_index(self, kind: str) -> int:
        """Return the layout index just after the last card of `kind`, creating the section header if absent."""
        kind_order = [k for k, _ in self._KIND_LABELS]
        label_map  = {k: lbl for k, lbl in self._KIND_LABELS}

        # Collect cards per kind from current layout state
        cards_by_kind: dict[str, list[int]] = {k: [] for k in kind_order}
        for i in range(self._list_layout.count()):
            w = self._list_layout.itemAt(i).widget()
            if isinstance(w, SeriesCard):
                cards_by_kind.get(w._series.kind, []).append(i)

        if cards_by_kind[kind]:
            # Kind group already exists — insert after its last card
            return cards_by_kind[kind][-1] + 1

        # Kind group doesn't exist yet — find where it should go based on kind order
        insert_before = self._list_layout.count()
        for k in kind_order:
            if k == kind:
                break
            # skip kinds that come before ours
        for k in kind_order[kind_order.index(kind) + 1:]:
            if cards_by_kind[k]:
                # Find the header for this kind and insert before it
                for i in range(self._list_layout.count()):
                    w = self._list_layout.itemAt(i).widget()
                    if w is self._section_headers.get(k):
                        insert_before = i
                        break
                break

        # Create and insert the section header
        hdr = QLabel(label_map[kind])
        hdr.setObjectName("list_section_lbl")
        self._list_layout.insertWidget(insert_before, hdr)
        self._section_headers[kind] = hdr
        return insert_before + 1  # card goes right after the new header

    def _on_watch(self, series_id: int, season_num: int):
        finished = self._tracker.watch_one(series_id, season_num)
        self._schedule_save()

        s = self._tracker._find(series_id)
        card = self._cards.get(series_id)
        if s and card:
            card.apply_watch(season_num, s.seasons[str(season_num)])

        dlg = self._edit_dialogs.get(series_id)
        if dlg and s:
            dlg.sync_season_watched(season_num, s.seasons[str(season_num)].watched)

        if finished and s:
            self._toast.show_message(f"🎉  Finished season {season_num} of \"{s.name}\"!")

    def _on_delete(self, series_id: int):
        self._tracker.delete_series(series_id)
        self._schedule_save()

        dlg = self._edit_dialogs.pop(series_id, None)
        if dlg:
            dlg.close()

        keep = []
        for item in self._prebuilt_queue:
            if item[0] == 'left' and item[1] == series_id:
                item[2].setParent(None)
            else:
                keep.append(item)
        self._prebuilt_queue = keep

        # Remove card from left column directly — no full rebuild needed
        card = self._cards.pop(series_id, None)
        if card:
            self._list_layout.removeWidget(card)
            card.setParent(None)

        # Remove P2W card from right column directly
        p2w_card = self._p2w_cards.pop(series_id, None)
        if p2w_card:
            self._p2w_layout.removeWidget(p2w_card)
            p2w_card.setParent(None)

        n = len(self._tracker.series)
        self.setWindowTitle(f"My Series Tracker{'  —  ' + str(n) + ' series' if n else ''}")
        self._update_spin_wheel()
        self._apply_filter()   # hides section headers whose group is now empty
        self._toast.show_message("Removed.")

    def _on_auto_save(self, series_id: int, name: str, kind: str, alt_names: list, season_edits: dict):
        old_kind = getattr(self._tracker._find(series_id), "kind", None)
        self._tracker.apply_edit(series_id, name, kind, alt_names, season_edits)
        self._schedule_save()

        s = self._tracker._find(series_id)
        if not s:
            return

        if kind != old_kind:
            self._insert_or_replace_card(s)
            return

        card = self._cards.get(series_id)
        if card:
            card.update_name(s.name, s.alt_names)
            for sn_str in season_edits:
                card.apply_watch(int(sn_str), s.seasons[sn_str])
        dlg = self._edit_dialogs.get(series_id)
        if dlg and season_edits:
            for sn_str in season_edits:
                dlg.sync_season_watched(int(sn_str), s.seasons[sn_str].watched)

    def _on_p2w_auto_save(self, series_id: int, name: str, season_edits: dict):
        """Handle name/label/episode edits from the P2W card edit panel."""
        s = self._tracker._find(series_id)
        if not s:
            return
        # Build full edit dict preserving watched/rating for each P2W season
        full_edits = {}
        for sn_str, data in season_edits.items():
            if sn_str in s.seasons:
                existing = s.seasons[sn_str]
                full_edits[sn_str] = {
                    "episodes": data["episodes"],
                    "watched":  existing.watched,
                    "rating":   existing.rating,
                    "label":    data["label"],
                }
        self._tracker.apply_edit(series_id, name, s.kind, s.alt_names, full_edits)
        self._schedule_save()
        p2w_card = self._p2w_cards.get(series_id)
        if p2w_card:
            p2w_card.update_name(name)

    def _on_rate(self, series_id: int, season_num: int, rating: int):
        self._tracker.rate_season(series_id, season_num, rating)
        self._schedule_save()
        card = self._cards.get(series_id)
        if card:
            card.update_season_rating(season_num, rating)

    def _on_complete(self, series_id: int, season_num: int):
        self._tracker.complete_season(series_id, season_num)
        self._schedule_save()
        s = self._tracker._find(series_id)
        card = self._cards.get(series_id)
        if s and card:
            card.apply_watch(season_num, s.seasons[str(season_num)])
        dlg = self._edit_dialogs.get(series_id)
        if dlg and s:
            dlg.sync_season_watched(season_num, s.seasons[str(season_num)].watched)
        if s:
            self._toast.show_message(f"🎉  Season {season_num} of \"{s.name}\" marked complete!")

    def _on_add_season(self, series_id: int, season_num: int, episodes: int, p2w: bool):
        self._tracker._mark_dirty()
        self._schedule_save()
        s = self._tracker._find(series_id)
        if s:
            self._insert_or_replace_card(s)
            self._scroll_to_card(series_id)
        msg = f"Season {season_num} added to Plan to Watch!" if p2w else f"Season {season_num} added!"
        self._toast.show_message(msg)

    def _on_delete_season(self, series_id: int, season_num: int):
        s = self._tracker._find(series_id)
        name = s.name if s else "?"
        self._tracker.delete_season(series_id, season_num)
        self._schedule_save()
        s = self._tracker._find(series_id)
        if s:
            self._insert_or_replace_card(s)
        self._toast.show_message(f"Season {season_num} of \"{name}\" removed.")

    def _on_p2w_remove(self, series_id: int, season_num: int):
        self._tracker.set_season_p2w(series_id, season_num, False)
        self._schedule_save()
        self._rebuild()
        self._scroll_to_card(series_id)
        s = self._tracker._find(series_id)
        if s:
            self._toast.show_message(
                f"Season {season_num} of \"{s.name}\" moved to watching list!")

    def _on_edit_requested(self, series_id: int):
        if series_id in self._edit_dialogs:
            self._edit_dialogs[series_id].raise_()
            return
        s = self._tracker._find(series_id)
        if not s:
            return
        dlg = SeriesEditDialog(s, self.centralWidget())
        dlg.auto_save_requested.connect(self._on_auto_save)
        dlg.add_season_requested.connect(self._on_add_season)
        dlg.season_delete_requested.connect(self._on_delete_season)
        dlg.eject_season_requested.connect(self._on_eject_season)
        dlg.absorb_requested.connect(self._on_absorb)
        dlg.closed.connect(lambda sid: self._edit_dialogs.pop(sid, None))
        self._edit_dialogs[series_id] = dlg
        dlg.show()

    def _on_season_dirty(self, series_id: int):
        self._tracker._mark_dirty()
        self._schedule_save()

    def _on_eject_season(self, series_id: int, season_key: str, new_name: str):
        s = self._tracker._find(series_id)
        if not s:
            return
        original_kind = s.kind
        season = s.seasons.pop(season_key, None)
        if season is None:
            return
        sorted_remaining = sorted(s.seasons.keys(), key=int)
        s.seasons = {str(i + 1): s.seasons[k] for i, k in enumerate(sorted_remaining)}

        new_series = Series(
            id=int(time.time() * 1000),
            name=new_name,
            kind=original_kind,
            seasons={"1": Season(
                episodes=season.episodes, watched=season.watched,
                rating=season.rating, label=season.label, p2w=season.p2w,
            )},
        )
        self._tracker._id_index[new_series.id] = new_series
        self._tracker.series.append(new_series)
        self._tracker._is_sorted = False
        self._tracker._mark_dirty()

        if s.seasons:
            self._insert_or_replace_card(s)
        else:
            self._tracker.delete_series(series_id)
            for cards, layout in ((self._cards, self._list_layout),
                                  (self._p2w_cards, self._p2w_layout)):
                card = cards.pop(series_id, None)
                if card:
                    layout.removeWidget(card)
                    card.setParent(None)

        self._insert_or_replace_card(new_series)
        self._schedule_save()
        self._toast.show_message(f'"{new_name}" created!')

    def _on_absorb(self, series_id: int, target_name: str, new_label: str):
        src = self._tracker._find(series_id)
        if not src or len(src.seasons) != 1:
            return
        season_data = next(iter(src.seasons.values()))

        target = self._tracker.find_by_name(target_name)
        if target:
            next_key = str(max(int(k) for k in target.seasons) + 1) if target.seasons else "1"
            target.seasons[next_key] = Season(
                episodes=season_data.episodes, watched=season_data.watched,
                rating=season_data.rating, label=new_label, p2w=season_data.p2w,
            )
        else:
            target = Series(
                id=int(time.time() * 1000),
                name=target_name,
                kind=src.kind,
                seasons={"1": Season(
                    episodes=season_data.episodes, watched=season_data.watched,
                    rating=season_data.rating, label=new_label, p2w=season_data.p2w,
                )},
            )
            self._tracker._id_index[target.id] = target
            self._tracker.series.append(target)
            self._tracker._is_sorted = False

        self._tracker.delete_series(series_id)
        for cards, layout in ((self._cards, self._list_layout),
                              (self._p2w_cards, self._p2w_layout)):
            card = cards.pop(series_id, None)
            if card:
                layout.removeWidget(card)
                card.setParent(None)

        self._tracker._mark_dirty()
        self._insert_or_replace_card(target)
        self._schedule_save()
        self._toast.show_message(f'Merged into "{target_name}"!')

    def _on_import_mal(self):
        dlg = MALImportDialog(self)
        dlg.import_requested.connect(self._run_mal_import)
        dlg.exec()

    def _run_mal_import(self, path: str, group: bool):
        from mal_import import parse_mal_xml, build_series_grouped, build_series_ungrouped
        try:
            entries = parse_mal_xml(path)
        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to parse XML:\n{e}")
            return

        series_list = build_series_grouped(entries) if group else build_series_ungrouped(entries)

        skipped: list[str] = []
        added = 0
        base_id = int(time.time() * 1000)
        for i, (name, seasons) in enumerate(series_list):
            if self._tracker.find_by_name(name):
                skipped.append(name)
                continue
            s = Series(id=base_id + i, name=name, kind="anime", seasons=seasons)
            self._tracker._id_index[s.id] = s
            self._tracker.series.append(s)
            added += 1

        if added:
            self._tracker._is_sorted = False
            self._tracker._mark_dirty()
            self._tracker.flush_now()
            self._rebuild()
            self._set_status(self._saved_msg())

        if skipped:
            names = ", ".join(skipped[:10])
            if len(skipped) > 10:
                names += f"  (+{len(skipped) - 10} more)"
            QMessageBox.information(
                self, "Import Complete",
                f"Imported {added} series.\n"
                f"Skipped {len(skipped)} duplicate{'s' if len(skipped) != 1 else ''}: {names}",
            )
        elif added:
            self._toast.show_message(f"Imported {added} series!")
        else:
            self._toast.show_message("Nothing imported — all entries already exist.")

    def _saved_msg(self) -> str:
        n = len(self._tracker.series)
        ts = datetime.now().strftime("%H:%M:%S")
        return f"Saved · {n} record{'s' if n != 1 else ''} · {ts}"

    def _set_status(self, msg: str):
        self._status_lbl.setText(msg)
