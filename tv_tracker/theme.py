from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

BG        = "#1e2433"
SURFACE   = "#262d3d"
SURFACE2  = "#2f3748"
BORDER    = "#3a4357"
TEXT      = "#e4e9f4"
MUTED     = "#8b95b0"
HINT      = "#5a6480"
TEAL      = "#2dd4a0"
TEAL_DIM  = "#1a7d60"
TEAL_BG   = "#163d30"
BLUE      = "#5b9cf6"
BLUE_DIM  = "#2d5db5"
BLUE_BG   = "#162040"
AMBER     = "#f5a623"
AMBER_DIM = "#a06a10"
AMBER_BG  = "#3a2608"
RED       = "#f06d6d"
RED_DIM   = "#a03030"
RED_BG    = "#3a1515"
PURPLE    = "#a78bfa"
PURPLE_DIM = "#5b3db5"
PURPLE_BG  = "#1e1540"
ORANGE     = "#fb923c"
ORANGE_DIM = "#c2410c"
ORANGE_BG  = "#431407"
HORROR     = "#f87171"
HORROR_DIM = "#7f1d1d"
HORROR_BG  = "#1c0606"


def apply_dark_palette(app: QApplication):
    app.setStyle("Fusion")
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor(BG))
    p.setColor(QPalette.ColorRole.WindowText,      QColor(TEXT))
    p.setColor(QPalette.ColorRole.Base,            QColor(SURFACE2))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(SURFACE))
    p.setColor(QPalette.ColorRole.Text,            QColor(TEXT))
    p.setColor(QPalette.ColorRole.BrightText,      QColor(TEXT))
    p.setColor(QPalette.ColorRole.Button,          QColor(SURFACE))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor(TEXT))
    p.setColor(QPalette.ColorRole.Highlight,       QColor(TEAL))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#0a2018"))
    p.setColor(QPalette.ColorRole.ToolTipBase,     QColor(SURFACE2))
    p.setColor(QPalette.ColorRole.ToolTipText,     QColor(TEXT))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(HINT))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,       QColor(HINT))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(HINT))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base,       QColor(SURFACE))
    app.setPalette(p)


QSS = f"""
/* ── Scroll area ── */
QScrollArea {{ border: none; background: {BG}; }}
QScrollArea > QWidget > QWidget {{ background: {BG}; }}

QScrollBar:vertical {{
    background: {SURFACE}; width: 8px; border-radius: 4px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER}; border-radius: 4px; min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

/* ── Cards ── */
QFrame#series_card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame#series_card[completed="true"] {{
    background: {TEAL_BG};
    border: 1px solid {TEAL_DIM};
    border-radius: 12px;
}}
QFrame#p2w_card {{
    background: {PURPLE_BG};
    border: 1px solid {PURPLE_DIM};
    border-radius: 12px;
}}
QFrame#add_form {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame#edit_panel {{
    background: {SURFACE2};
    border-top: 1px solid {BORDER};
    border-bottom-left-radius: 12px;
    border-bottom-right-radius: 12px;
}}
QFrame#season_edit_block {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QFrame#new_season_block {{
    background: {PURPLE_BG};
    border: 1px solid {PURPLE_DIM};
    border-radius: 8px;
}}

/* ── Labels ── */
QLabel#section_label {{
    color: {MUTED};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#series_name {{
    font-size: 15px;
    font-weight: 500;
    color: {TEXT};
    background: transparent;
}}
QLabel#series_altname {{
    font-size: 11px;
    color: {HINT};
    background: transparent;
}}
QLabel#season_label    {{ color: {MUTED}; font-size: 12px; background: transparent; }}
QWidget#p2w_season_row {{
    border-left: 2px dashed {HINT};
    padding-left: 6px;
    background: transparent;
}}
QLabel#p2w_season_label {{ color: {HINT}; font-size: 12px; font-style: italic; background: transparent; }}
QLabel#season_sublabel {{ color: {HINT}; font-size: 10px; background: transparent; }}
QLabel#eps_label     {{ color: {MUTED}; font-size: 11px; background: transparent; }}
QLabel#field_label   {{ color: {MUTED}; font-size: 12px; background: transparent; }}
QLabel#edit_note     {{ color: {HINT}; font-size: 12px; background: transparent; }}
QLabel#edit_season_label {{ color: {TEAL}; font-size: 12px; font-weight: 500; background: transparent; }}
QLabel#new_season_label  {{ color: {PURPLE}; font-size: 12px; font-weight: 500; background: transparent; }}
QLabel#empty_label   {{ color: {HINT}; font-size: 14px; background: transparent; }}
QLabel#avg_badge {{
    color: {TEAL}; background: {TEAL_BG};
    border: 1px solid {TEAL_DIM}; border-radius: 6px;
    padding: 2px 7px; font-size: 11px;
}}
QLabel#p2w_col_header {{
    color: {PURPLE};
    font-size: 11px;
    font-weight: 600;
    padding: 4px 0 8px 0;
    background: transparent;
}}

QLabel#rating_badge {{
    color: {AMBER}; background: {AMBER_BG};
    border: 1px solid {AMBER_DIM}; border-radius: 6px;
    padding: 2px 7px; font-size: 11px;
}}
QLabel#unrated_badge {{
    color: {HINT}; background: transparent;
    border: 1px dashed {BORDER}; border-radius: 6px;
    padding: 2px 7px; font-size: 11px;
}}
QLabel#done_badge {{
    color: {TEAL}; background: {TEAL_BG};
    border: 1px solid {TEAL_DIM}; border-radius: 6px;
    padding: 2px 7px; font-size: 11px;
}}
QLabel#toast {{
    background: {SURFACE2};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 13px;
}}

/* ── Inputs ── */
QLineEdit {{
    background: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 10px;
    font-size: 13px;
    color: {TEXT};
    selection-background-color: {TEAL_DIM};
}}
QLineEdit:focus {{ border-color: {TEAL}; }}

QSpinBox {{
    background: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 10px;
    font-size: 13px;
    color: {TEXT};
}}
QSpinBox:focus {{ border-color: {TEAL}; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}

/* ── Rating combo ── */
QComboBox#rating_combo {{
    background: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 2px 2px 2px 5px;
    font-size: 11px;
    color: {TEXT};
}}
QComboBox#rating_combo:hover {{ border-color: {MUTED}; }}
QComboBox#rating_combo:focus {{ border-color: {TEAL}; }}
QComboBox#rating_combo::drop-down {{ border: none; width: 14px; }}
QComboBox#rating_combo QAbstractItemView {{
    background: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 6px;
    selection-background-color: {TEAL_DIM};
    selection-color: {TEXT};
    color: {TEXT};
    padding: 2px;
}}
QPushButton#rating_combo {{
    background: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 2px 5px;
    font-size: 11px;
    color: {TEXT};
    text-align: left;
}}
QPushButton#rating_combo:hover {{ border-color: {MUTED}; }}
QPushButton#rating_combo:pressed {{ border-color: {TEAL}; }}
QMenu#rating_menu {{
    background: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 2px;
}}
QMenu#rating_menu::item {{
    padding: 2px 10px;
    font-size: 11px;
    color: {TEXT};
    border-radius: 4px;
}}
QMenu#rating_menu::item:selected {{ background: {TEAL_DIM}; }}

/* ── Edit overlay ── */
QFrame#edit_dialog_panel {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QWidget#edit_dialog_titlebar {{
    background: {SURFACE2};
    border-bottom: 1px solid {BORDER};
}}
QLabel#edit_dialog_title_lbl {{
    font-size: 13px;
    font-weight: 600;
    color: {TEXT};
}}
QScrollArea#edit_dialog_scroll,
QScrollArea#edit_dialog_scroll > QWidget > QWidget {{
    background: transparent;
    border: none;
}}
QWidget#edit_dialog_content {{
    background: transparent;
}}

/* ── Progress bar ── */
QProgressBar {{
    background: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 3px;
    max-height: 5px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {TEAL_DIM}, stop:1 {TEAL});
    border-radius: 3px;
}}

/* ── Buttons ── */
QPushButton {{
    border-radius: 8px;
    padding: 7px 16px;
    font-size: 13px;
    font-weight: 500;
    border: none;
}}
QPushButton#btn_add  {{ background: {TEAL};  color: #0a2018; }}
QPushButton#btn_add:hover  {{ background: #25b88a; }}
QPushButton#btn_add:pressed {{ background: {TEAL_DIM}; }}

QPushButton#btn_save {{ background: {BLUE};  color: #06122e; }}
QPushButton#btn_save:hover {{ background: #4a8ae8; }}
QPushButton#btn_save:pressed {{ background: {BLUE_DIM}; }}

QPushButton#btn_cancel {{
    background: {SURFACE2}; color: {MUTED};
    border: 1px solid {BORDER};
}}
QPushButton#btn_cancel:hover {{ color: {TEXT}; border-color: {MUTED}; }}

QPushButton#btn_edit {{
    background: {BLUE_BG}; color: {BLUE};
    border: 1px solid {BLUE_DIM};
    border-radius: 8px; padding: 4px 8px;
}}
QPushButton#btn_edit:hover {{ background: #1e2e56; }}

QPushButton#btn_del {{
    background: {RED_BG}; color: {RED};
    border: 1px solid {RED_DIM};
    border-radius: 8px; padding: 4px 8px;
}}
QPushButton#btn_del:hover {{ background: #4a1a1a; }}

QPushButton#btn_watch {{
    background: {AMBER_BG}; color: {AMBER};
    border: 1px solid {AMBER_DIM};
    border-radius: 6px;
    padding: 3px 10px; font-size: 12px;
}}
QPushButton#btn_watch:hover {{ background: #4a3010; }}
QPushButton#btn_watch:pressed {{ background: {AMBER_DIM}; }}

QPushButton#btn_complete {{
    background: {TEAL_BG}; color: {TEAL};
    border: 1px solid {TEAL_DIM};
    border-radius: 6px;
    padding: 3px 10px; font-size: 12px;
}}
QPushButton#btn_complete:hover {{ background: #1a4a38; }}
QPushButton#btn_complete:pressed {{ background: {TEAL_DIM}; }}

QPushButton#btn_start {{
    background: {BLUE_BG}; color: {BLUE};
    border: 1px solid {BLUE_DIM};
    border-radius: 6px;
    padding: 3px 10px; font-size: 12px;
}}
QPushButton#btn_start:hover {{ background: #1e2e56; }}
QPushButton#btn_start:pressed {{ background: {BLUE_DIM}; }}

QPushButton#btn_p2w {{
    background: {PURPLE_BG}; color: {PURPLE};
    border: 1px solid {PURPLE_DIM};
    border-radius: 8px; padding: 7px 16px;
    font-size: 13px; font-weight: 500;
}}
QPushButton#btn_p2w:hover {{ background: #2a1a5a; }}
QPushButton#btn_p2w:pressed {{ background: {PURPLE_DIM}; }}

QPushButton#star_btn {{
    background: {SURFACE2}; color: {MUTED};
    border: 1px solid {BORDER};
    border-radius: 6px;
    min-width: 26px; max-width: 26px;
    min-height: 26px; max-height: 26px;
    padding: 0; font-size: 12px; font-weight: 500;
}}
QPushButton#star_btn:hover {{ border-color: #fbbf24; color: #fbbf24; }}
QPushButton#star_btn[active="true"] {{
    background: {AMBER_BG}; border-color: {AMBER_DIM}; color: {AMBER};
}}

QPushButton#kind_btn {{
    background: {SURFACE2}; color: {MUTED};
    border: 1px solid {BORDER};
    border-radius: 8px; padding: 5px 16px;
    font-size: 12px; font-weight: 500;
}}
QPushButton#kind_btn:hover {{ color: {TEXT}; border-color: {MUTED}; }}
QPushButton#kind_btn[active="true"][kind="tv"] {{
    background: {BLUE_BG}; color: {BLUE}; border-color: {BLUE_DIM};
}}
QPushButton#kind_btn[active="true"][kind="anime"] {{
    background: {PURPLE_BG}; color: {PURPLE}; border-color: {PURPLE_DIM};
}}
QPushButton#kind_btn[active="true"][kind="movie"] {{
    background: {ORANGE_BG}; color: {ORANGE}; border-color: {ORANGE_DIM};
}}
QPushButton#kind_btn[active="true"][kind="horror"] {{
    background: {HORROR_BG}; color: {HORROR}; border-color: {HORROR_DIM};
}}

/* ── Section headers in the series list ── */
QLabel#list_section_lbl {{
    color: {MUTED};
    font-size: 11px;
    font-weight: 600;
    padding-top: 8px;
}}

/* ── Status bar ── */
QStatusBar {{
    background: {BG};
    color: {HINT};
    font-size: 12px;
    border-top: 1px solid {BORDER};
}}
QStatusBar QLabel {{ background: transparent; color: {HINT}; font-size: 12px; }}

/* ── Spin column ── */
QLabel#spin_col_header {{
    color: {AMBER};
    font-size: 11px;
    font-weight: 600;
    padding: 4px 0 8px 0;
    background: transparent;
}}
QLabel#spin_result_lbl {{
    color: {TEAL}; background: {TEAL_BG};
    border: 1px solid {TEAL_DIM}; border-radius: 8px;
    padding: 8px 10px; font-size: 13px; font-weight: 600;
}}
QPushButton#btn_spin {{
    background: {AMBER_BG}; color: {AMBER};
    border: 1px solid {AMBER_DIM};
    border-radius: 8px; padding: 8px 16px;
    font-size: 13px; font-weight: 600;
}}
QPushButton#btn_spin:hover   {{ background: #4a3010; }}
QPushButton#btn_spin:pressed {{ background: {AMBER_DIM}; }}
QPushButton#btn_spin:disabled {{ color: {HINT}; border-color: {BORDER}; background: {SURFACE}; }}

/* ── Reorder arrows (small, neutral) ── */
QPushButton#btn_reorder {{
    background: {SURFACE2}; color: {MUTED};
    border: 1px solid {BORDER};
    border-radius: 4px; padding: 2px 3px;
    font-size: 10px; font-weight: 500;
}}
QPushButton#btn_reorder:hover {{ color: {TEXT}; border-color: {MUTED}; }}
QPushButton#btn_reorder:disabled {{ color: {SURFACE2}; border-color: {SURFACE2}; background: {SURFACE}; }}

/* ── Eject (extract season) button — small, amber-tinted ── */
QPushButton#btn_eject {{
    background: {AMBER_BG}; color: {AMBER};
    border: 1px solid {AMBER_DIM};
    border-radius: 4px; padding: 2px 6px;
    font-size: 11px; font-weight: 600;
}}
QPushButton#btn_eject:hover {{ background: #4a3010; }}
QPushButton#btn_eject:pressed {{ background: {AMBER_DIM}; }}

/* ── CheckBox ── */
QCheckBox {{ color: {PURPLE}; font-size: 12px; font-weight: 500; spacing: 6px; }}
QCheckBox::indicator {{
    width: 14px; height: 14px;
    border: 1px solid {BORDER}; border-radius: 3px;
    background: {SURFACE2};
}}
QCheckBox::indicator:checked {{
    background: {PURPLE_DIM}; border-color: {PURPLE};
}}
"""
