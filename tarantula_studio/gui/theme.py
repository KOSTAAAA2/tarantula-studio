"""Dark theme for Tarantula Studio."""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#ff6b35"
ACCENT_SOFT = "#ff8a5c"
BG = "#0f1318"
SURFACE = "#161c23"
SURFACE_ALT = "#121820"
BORDER = "#25303b"
TEXT = "#e6edf3"
MUTED = "#8b98a5"


def apply_theme(app: QApplication):
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor("#0d1116"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(SURFACE_ALT))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor("#222c36"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#14100d"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#5c6874"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#5c6874"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#5c6874"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#5c6874"))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)


STYLESHEET = f"""
* {{
    font-family: "Noto Sans", "Cantarell", "DejaVu Sans", "Segoe UI", sans-serif;
    font-size: 13px;
}}
QMainWindow, QWidget#Root {{
    background: {BG};
}}
QWidget#PageContent {{
    background: {BG};
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QFrame#Sidebar {{
    background: #0b0f13;
    border-right: 1px solid #1d262f;
}}
QLabel#Brand {{
    font-size: 17px;
    font-weight: 800;
    letter-spacing: 1px;
    color: {TEXT};
}}
QLabel#BrandAccent {{
    color: {ACCENT};
}}
QLabel#BrandSub {{
    color: {MUTED};
    font-size: 11px;
}}
QLabel#PageTitle {{
    font-size: 25px;
    font-weight: 700;
}}
QLabel#PageSubtitle {{
    color: {MUTED};
    font-size: 12px;
}}
QLabel#CardTitle {{
    font-size: 14px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#Muted {{
    color: {MUTED};
}}
QLabel#Mono {{
    font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace;
    font-size: 12px;
}}
QLabel#Big {{
    font-size: 19px;
    font-weight: 700;
}}
QLabel#SectionLabel {{
    color: {MUTED};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
}}
QLabel[pill="ok"] {{
    background: rgba(63, 185, 80, 0.14);
    color: #56d364;
    border: 1px solid rgba(63, 185, 80, 0.35);
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel[pill="warn"] {{
    background: rgba(210, 153, 34, 0.14);
    color: #e3b341;
    border: 1px solid rgba(210, 153, 34, 0.35);
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel[pill="err"] {{
    background: rgba(248, 81, 73, 0.14);
    color: #ff7b72;
    border: 1px solid rgba(248, 81, 73, 0.35);
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel[pill="muted"] {{
    background: rgba(139, 152, 165, 0.10);
    color: #9aa7b4;
    border: 1px solid rgba(139, 152, 165, 0.25);
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#Note {{
    color: #d9b06c;
    background: rgba(210, 153, 34, 0.08);
    border: 1px solid rgba(210, 153, 34, 0.22);
    border-radius: 8px;
    padding: 8px 10px;
}}
QLabel#Info {{
    color: #9fb6ca;
    background: rgba(88, 166, 255, 0.07);
    border: 1px solid rgba(88, 166, 255, 0.20);
    border-radius: 8px;
    padding: 8px 10px;
}}
QFrame#Card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame#ApplyBar {{
    background: {SURFACE_ALT};
    border-top: 1px solid {BORDER};
}}
QFrame#Header {{
    background: {BG};
    border-bottom: 1px solid #1d262f;
}}
QPushButton {{
    background: #222c36;
    border: 1px solid #33414f;
    border-radius: 8px;
    padding: 7px 14px;
    color: {TEXT};
}}
QPushButton:hover {{
    background: #2b3744;
    border-color: #405163;
}}
QPushButton:pressed {{
    background: #1b242d;
}}
QPushButton:disabled {{
    color: #5c6874;
    background: #171d24;
    border-color: #222b34;
}}
QPushButton#Primary {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: #17100c;
    font-weight: 700;
}}
QPushButton#Primary:hover {{
    background: {ACCENT_SOFT};
    border-color: {ACCENT_SOFT};
}}
QPushButton#Primary:disabled {{
    background: #4a3328;
    border-color: #4a3328;
    color: #8d756a;
}}
QPushButton#Danger {{
    color: #ff7b72;
    border-color: rgba(248, 81, 73, 0.35);
}}
QPushButton#Danger:hover {{
    background: rgba(248, 81, 73, 0.12);
}}
QPushButton#Ghost {{
    background: transparent;
    border: 1px solid transparent;
    color: {MUTED};
}}
QPushButton#Ghost:hover {{
    background: #1b232c;
    color: {TEXT};
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: #0f1419;
    border: 1px solid #2b3744;
    border-radius: 7px;
    padding: 5px 8px;
    color: {TEXT};
    selection-background-color: {ACCENT};
    selection-color: #17100c;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: #5b6b7c;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 1px solid #33414f;
    selection-background-color: #2b3744;
    selection-color: {TEXT};
    outline: none;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    width: 16px;
    background: #1a222b;
    border: none;
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: #2b3744;
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {TEXT};
    width: 14px;
    margin: -6px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background: #ffffff;
}}
QCheckBox {{
    spacing: 8px;
    color: {TEXT};
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid #3a4755;
    border-radius: 4px;
    background: #0f1419;
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QListWidget, QTableWidget, QTreeWidget {{
    background: {SURFACE_ALT};
    border: 1px solid {BORDER};
    border-radius: 9px;
    outline: none;
}}
QListWidget::item {{
    padding: 6px 8px;
    border-radius: 6px;
}}
QListWidget::item:selected, QTableWidget::item:selected {{
    background: #2a3542;
    color: {TEXT};
}}
QListWidget::item:hover {{
    background: #1a232c;
}}
QTableWidget {{
    gridline-color: #202a34;
    selection-background-color: #2a3542;
    alternate-background-color: #141b22;
}}
QTableWidget::item {{
    padding: 5px;
}}
QHeaderView::section {{
    background: #182029;
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 7px;
    font-weight: 700;
}}
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    background: {SURFACE_ALT};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    padding: 8px 18px;
    color: {MUTED};
    border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {ACCENT_SOFT};
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover {{
    color: {TEXT};
}}
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    margin-top: 14px;
    padding-top: 10px;
    font-weight: 700;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 5px;
    color: {MUTED};
}}
QToolTip {{
    background: #1d2731;
    color: {TEXT};
    border: 1px solid #33414f;
    padding: 5px;
}}
QStatusBar {{
    background: {SURFACE_ALT};
    border-top: 1px solid {BORDER};
    color: {MUTED};
}}
QStatusBar::item {{
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #2b3744;
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #3a4755;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #2b3744;
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
    width: 0;
}}
QProgressBar {{
    background: #10161c;
    border: 1px solid #2b3744;
    border-radius: 5px;
    text-align: center;
    color: {TEXT};
    max-height: 18px;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 4px;
}}
QListWidget#Nav {{
    background: transparent;
    border: none;
}}
QListWidget#Nav::item {{
    padding: 10px 14px;
    border-radius: 8px;
    color: #93a1af;
    margin: 2px 10px;
}}
QListWidget#Nav::item:selected {{
    background: #1d2731;
    color: {ACCENT_SOFT};
    font-weight: 700;
}}
QListWidget#Nav::item:hover {{
    background: #141b22;
    color: {TEXT};
}}
QSplitter::handle {{
    background: transparent;
}}
"""
