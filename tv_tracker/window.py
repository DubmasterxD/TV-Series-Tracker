import bisect
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
        self._cards: dict[int, SeriesCard] = {}   # series_id → pool card (currently visible)
        self._p2w_cards: dict[int, P2WCard] = {}
        self._kind_filter: str | None = None
        self._filter_btns: dict[str, QPushButton] = {}
        self._spin_result_name: str | None = None
        self._load_result: tuple | None = None
        self._edit_dialogs: dict[int, SeriesEditDialog] = {}

        # ── Virtual recycling list ──────────────────────────────────
        # Exactly POOL_SIZE SeriesCard widgets are kept alive at all times.
        # _virt_items  — the currently-filtered ordered list of Series objects.
        # _virt_start  — index into _virt_items of the first pool card.
        # _virt_prefix — prefix-sum of card heights: _virt_prefix[i] is the
        #                total pixel height of items 0 … i-1.  Used to position
        #                the top/bottom spacers so the scrollbar reflects the
        #                true total content height without rendering every card.
        self._POOL_SIZE        = 16
        self._virt_items: list = []
        self._virt_start: int  = 0
        self._virt_prefix: list[int] = []
        self._pool: list[SeriesCard] = []
        self._top_spacer: QWidget | None = None
        self._bot_spacer: QWidget | None = None
        self._scroll_connected = False

        # Deferred save: mutations mark dirty; timer batches the actual disk write
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(2000)   # 2 s debounce
        self._save_timer.timeout.connect(self._on_debounce)

        # Debounce search input: rebuild the list only after the user pauses typing
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._apply_filter)

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
        self._search.textChanged.connect(lambda _: self._search_timer.start())
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

        # Left column — virtual recycling list
        self._apply_filter()

        n_total = len(self._tracker.series)
        self.setWindowTitle(f"My Series Tracker{'  —  ' + str(n_total) + ' series' if n_total else ''}")
        self._update_spin_wheel()

        # Connect scroll handler (kept connected permanently; handler is a no-op
        # when fewer than POOL_SIZE items are loaded)
        if not self._scroll_connected:
            self._left_scroll.verticalScrollBar().valueChanged.connect(self._on_left_scroll)
            self._scroll_connected = True

        if result == "ok":
            self._set_status(f"Auto-loaded {n} record{'s' if n != 1 else ''} from storage")

    # ── Virtual recycling list ───────────────────────────────────

    def _card_height(self, series) -> int:
        """Estimated pixel height of a SeriesCard (includes the 10 px layout spacing)."""
        active = sum(1 for v in series.seasons.values() if not v.p2w)
        # Header ≈ 50 px; each season row (with hline) ≈ 48 px; body bottom ≈ 12 px
        return max(80, 50 + active * 48 + 12) + 10

    def _build_virt_items(self):
        """Rebuild the ordered, filtered list of Series for the left column."""
        query      = self._search.text().strip().lower()
        kind_order = {k: i for i, (k, _) in enumerate(self._KIND_LABELS)}
        items      = []
        for s in self._tracker.series:
            if not any(not v.p2w for v in s.seasons.values()):
                continue
            if self._kind_filter and s.kind != self._kind_filter:
                continue
            if query and not (query in s.name.lower() or
                              any(query in a.lower() for a in s.alt_names)):
                continue
            items.append(s)
        # Stable sort keeps tracker ordering within each kind group.
        items.sort(key=lambda s: kind_order.get(s.kind, 999))
        self._virt_items = items

    def _build_virt_prefix(self):
        """Build the prefix-sum table from _virt_items heights."""
        prefix = [0]
        for s in self._virt_items:
            prefix.append(prefix[-1] + self._card_height(s))
        self._virt_prefix = prefix

    def _update_spacers(self):
        """Resize top/bottom spacers so the scrollbar reflects total content height."""
        N = len(self._virt_items)
        pool_size = len(self._pool)
        top_h = self._virt_prefix[self._virt_start] if self._virt_prefix else 0
        end_idx = min(self._virt_start + pool_size, N)
        bot_h = (self._virt_prefix[N] - self._virt_prefix[end_idx]) if self._virt_prefix else 0
        if self._top_spacer:
            self._top_spacer.setFixedHeight(max(0, top_h))
        if self._bot_spacer:
            self._bot_spacer.setFixedHeight(max(0, bot_h))

    def _clear_pool_from_layout(self):
        """Remove the pool cards and spacers from _list_layout (does not destroy them)."""
        if self._top_spacer:
            self._list_layout.removeWidget(self._top_spacer)
            self._top_spacer.hide()
        for card in self._pool:
            self._list_layout.removeWidget(card)
            card.hide()
        if self._bot_spacer:
            self._list_layout.removeWidget(self._bot_spacer)
            self._bot_spacer.hide()
        self._cards = {}

    def _setup_virt_list(self):
        """(Re)populate the layout from _virt_items at the current _virt_start.

        Reuses existing pool cards by calling refresh() on them; creates new
        ones only when the pool needs to grow.  Excess cards are destroyed.
        """
        N = len(self._virt_items)
        target = min(self._POOL_SIZE, N)

        # Remove everything from layout (hide, don't destroy)
        self._clear_pool_from_layout()

        # Clamp virt_start so it never goes out of bounds
        self._virt_start = max(0, min(self._virt_start, max(0, N - target)))

        if N == 0:
            # Shrink pool completely; empty label will be shown by caller
            while self._pool:
                self._pool.pop().setParent(None)
            return

        # Ensure spacer widgets exist (created once, never destroyed)
        if self._top_spacer is None:
            self._top_spacer = QWidget()
            self._top_spacer.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        if self._bot_spacer is None:
            self._bot_spacer = QWidget()
            self._bot_spacer.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Shrink pool if needed
        while len(self._pool) > target:
            self._pool.pop().setParent(None)

        # Refresh existing cards / create new ones
        for i in range(target):
            s = self._virt_items[self._virt_start + i]
            if i < len(self._pool):
                self._pool[i].refresh(s)
            else:
                self._pool.append(self._make_left_card(s))
            self._cards[s.id] = self._pool[i]

        # Re-add to layout: top_spacer → cards → bot_spacer
        self._list_container.setUpdatesEnabled(False)
        try:
            self._list_layout.addWidget(self._top_spacer)
            self._top_spacer.show()
            for card in self._pool:
                self._list_layout.addWidget(card)
                card.show()
            self._list_layout.addWidget(self._bot_spacer)
            self._bot_spacer.show()
            self._update_spacers()
        finally:
            self._list_container.setUpdatesEnabled(True)

    def _recycle_forward(self):
        """Move the topmost pool card to the bottom, advancing the visible window."""
        N = len(self._virt_items)
        pool_size = len(self._pool)
        next_idx = self._virt_start + pool_size
        if next_idx >= N:
            return

        self._list_container.setUpdatesEnabled(False)
        try:
            # Unmap old series
            old_s = self._virt_items[self._virt_start]
            self._cards.pop(old_s.id, None)

            card = self._pool[0]

            # Remove from layout (top card is always at layout index 1, right after top_spacer)
            self._list_layout.removeWidget(card)

            # Refresh with the next series below the current window
            new_s = self._virt_items[next_idx]
            card.refresh(new_s)
            self._cards[new_s.id] = card

            # Re-insert just before bot_spacer (last item in layout)
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)

            # Rotate pool list so pool[0] is now the new bottom card
            self._pool.append(self._pool.pop(0))

            self._virt_start += 1
            self._update_spacers()
        finally:
            self._list_container.setUpdatesEnabled(True)

    def _recycle_backward(self):
        """Move the bottommost pool card to the top, retreating the visible window."""
        if self._virt_start <= 0:
            return

        self._list_container.setUpdatesEnabled(False)
        try:
            pool_size = len(self._pool)

            # Unmap old series
            old_s = self._virt_items[self._virt_start + pool_size - 1]
            self._cards.pop(old_s.id, None)

            card = self._pool[-1]

            # Remove from layout
            self._list_layout.removeWidget(card)

            # Refresh with the series just above the current window
            new_s = self._virt_items[self._virt_start - 1]
            card.refresh(new_s)
            self._cards[new_s.id] = card

            # Re-insert just after top_spacer (layout index 1)
            self._list_layout.insertWidget(1, card)

            # Rotate pool list so the recycled card is pool[0]
            self._pool.insert(0, self._pool.pop(-1))

            self._virt_start -= 1
            self._update_spacers()
        finally:
            self._list_container.setUpdatesEnabled(True)

    def _on_left_scroll(self, value: int):
        """Recycle pool cards as the user scrolls through the virtual list.

        Uses binary search on the prefix-sum table (O(log N)) then measures
        how many items the viewport actually shows so the pool window covers
        the entire visible area with equal buffer cards above and below.
        """
        N = len(self._virt_items)
        pool_size = len(self._pool)
        if pool_size < 2 or N <= pool_size:
            return   # not enough items to need recycling

        viewport_h = self._left_scroll.viewport().height()

        # Binary search: which items sit at the top and bottom of the viewport?
        top_idx = max(0, bisect.bisect_right(self._virt_prefix, value) - 1)
        bot_idx = max(0, bisect.bisect_right(self._virt_prefix, value + viewport_h) - 1)

        # Distribute spare pool slots as equal buffers above and below visible area.
        visible   = bot_idx - top_idx + 1
        spare     = max(0, pool_size - visible)
        buf_above = spare // 2
        target    = max(0, min(top_idx - buf_above, N - pool_size))
        delta     = target - self._virt_start

        if delta == 0:
            return

        if abs(delta) >= pool_size:
            # Large jump (e.g. dragging scrollbar to end): jump straight to the
            # target position and rebuild the entire pool in one batched shot.
            self._virt_start = target
            self._setup_virt_list()
        else:
            # Small incremental move: recycle one card at a time.
            for _ in range(abs(delta)):
                if delta > 0:
                    self._recycle_forward()
                else:
                    self._recycle_backward()

    def _make_left_card(self, s) -> SeriesCard:
        card = SeriesCard(s)
        card.watch_requested.connect(self._on_watch)
        card.delete_requested.connect(self._on_delete)
        card.complete_requested.connect(self._on_complete)
        card.rate_requested.connect(self._on_rate)
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
        self._clear_both_columns()
        self._right_content.setUpdatesEnabled(False)
        try:
            for s in self._tracker.series:
                if any(v.p2w for v in s.seasons.values()):
                    card = self._make_p2w_card(s)
                    self._p2w_layout.addWidget(card)
                    self._p2w_cards[s.id] = card
        finally:
            self._right_content.setUpdatesEnabled(True)
        self._apply_filter()
        n = len(self._tracker.series)
        self.setWindowTitle(f"My Series Tracker{'  —  ' + str(n) + ' series' if n else ''}")
        self._update_spin_wheel()

    def _clear_both_columns(self):
        # Destroy all pool cards (and spacers)
        self._clear_pool_from_layout()
        while self._pool:
            self._pool.pop().setParent(None)
        for spc in (self._top_spacer, self._bot_spacer):
            if spc:
                spc.setParent(None)
        self._top_spacer = None
        self._bot_spacer = None

        # Clear any leftover layout items (e.g. from an old rebuild)
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        while self._p2w_layout.count():
            item = self._p2w_layout.takeAt(0)
            if item.widget():
                w = item.widget()
                w.hide()
                w.setParent(None)

        self._cards = {}
        self._p2w_cards = {}
        self._virt_items = []
        self._virt_start = 0
        self._virt_prefix = []

    def _scroll_to_card(self, series_id: int):
        """Scroll to the position of the given series in the virtual list."""
        for i, s in enumerate(self._virt_items):
            if s.id == series_id:
                y = self._virt_prefix[i] if i < len(self._virt_prefix) else 0
                QTimer.singleShot(0, lambda y=y:
                    self._left_scroll.verticalScrollBar().setValue(y))
                return

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

    def _apply_filter(self, reset_scroll: bool = True):
        """Rebuild the virtual left-column list for the current filter/search state.

        reset_scroll=True  — resets to the top (used for filter/search changes).
        reset_scroll=False — preserves virt_start (used for in-place data mutations).
        """
        has_series = bool(self._tracker.series)
        self._search.setVisible(has_series)
        self._filter_row.setVisible(has_series)

        # ── Left column: virtual recycling list ─────────────────────
        if reset_scroll:
            self._virt_start = 0

        self._build_virt_items()
        self._build_virt_prefix()
        self._setup_virt_list()

        N = len(self._virt_items)
        self._list_container.setVisible(N > 0)

        if not has_series:
            self._empty_label.setText("📺\n\nNo series yet — add one above!")
            self._empty_label.setVisible(True)
        elif N == 0:
            query = self._search.text().strip()
            txt = (f"No results for \"{query}\""
                   if query else "All series are in plan to watch.")
            self._empty_label.setText(txt)
            self._empty_label.setVisible(True)
        else:
            self._empty_label.setVisible(False)

        # ── Right column (P2W) ───────────────────────────────────────
        query = self._search.text().strip().lower()
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
        """Update both columns for series s after a data mutation.

        If the card for s is currently in the pool we refresh it in-place
        (preserving scroll position).  Either way we also rebuild the prefix
        sums so scrollbar height stays accurate, then rebuild the P2W column.
        """
        has_p2w = any(v.p2w for v in s.seasons.values())

        # ── Right column (P2W) ───────────────────────────────────────
        self._right_content.setUpdatesEnabled(False)
        try:
            old_p2w = self._p2w_cards.pop(s.id, None)
            if old_p2w:
                self._p2w_layout.removeWidget(old_p2w)
                old_p2w.setParent(None)
            if has_p2w:
                p2w_card = self._make_p2w_card(s)
                self._p2w_layout.addWidget(p2w_card)
                self._p2w_cards[s.id] = p2w_card
        finally:
            self._right_content.setUpdatesEnabled(True)

        n = len(self._tracker.series)
        self.setWindowTitle(f"My Series Tracker{'  —  ' + str(n) + ' series' if n else ''}")
        self._update_spin_wheel()
        # Rebuild left column in-place (preserves scroll position)
        self._apply_filter(reset_scroll=False)

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

        # Remove P2W card immediately (right column)
        p2w_card = self._p2w_cards.pop(series_id, None)
        if p2w_card:
            self._p2w_layout.removeWidget(p2w_card)
            p2w_card.setParent(None)

        n = len(self._tracker.series)
        self.setWindowTitle(f"My Series Tracker{'  —  ' + str(n) + ' series' if n else ''}")
        self._update_spin_wheel()
        # Rebuild virtual list (the deleted item is gone from tracker, so it
        # won't appear in the new virt_items); preserve scroll position.
        self._apply_filter(reset_scroll=False)
        self._toast.show_message("Removed.")

    def _on_auto_save(self, series_id: int, name: str, kind: str, alt_names: list, season_edits: dict):
        self._tracker.apply_edit(series_id, name, kind, alt_names, season_edits)
        self._schedule_save()

        s = self._tracker._find(series_id)
        if not s:
            return

        # Refresh the card if it's currently visible in the pool
        card = self._cards.get(series_id)
        if card:
            card.refresh(s)

        dlg = self._edit_dialogs.get(series_id)
        if dlg and season_edits:
            for sn_str in season_edits:
                dlg.sync_season_watched(int(sn_str), s.seasons[sn_str].watched)

        # Kind change moves the series to a different position in the grouped list
        # → full filter rebuild so the ordering stays correct
        self._insert_or_replace_card(s)

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
