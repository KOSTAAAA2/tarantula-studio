"""Reusable widgets for Tarantula Studio."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QColorDialog, QComboBox,
    QDialog, QDialogButtonBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from ..core import keys
from .labels import (
    CURVE_LABELS, MOUSE_TARGET_LABELS, MEDIA_TARGET_LABELS, SOURCE_ORDER,
    TARGET_KIND_LABELS, pretty_key, source_label,
)


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------
class Page(QWidget):
    TITLE = ""
    SUBTITLE = ""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.state = app.state
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("PageContent")
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(28, 22, 28, 28)
        self.body.setSpacing(16)
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def add(self, widget, stretch=0):
        self.body.addWidget(widget, stretch)

    def add_layout(self, layout):
        self.body.addLayout(layout)

    def add_stretch(self):
        self.body.addStretch(1)

    def refresh(self):
        pass


class Card(QFrame):
    def __init__(self, title: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 16, 18, 16)
        self.body.setSpacing(10)
        if title:
            label = QLabel(title)
            label.setObjectName("CardTitle")
            self.body.addWidget(label)

    def add(self, widget):
        self.body.addWidget(widget)
        return widget

    def add_layout(self, layout):
        self.body.addLayout(layout)
        return layout

    def row(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(10)
        self.body.addLayout(layout)
        return layout


def muted(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("Muted")
    label.setWordWrap(True)
    return label


def note(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Note")
    label.setWordWrap(True)
    return label


def info_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("Info")
    label.setWordWrap(True)
    return label


def hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("background: #25303b; max-height: 1px; border: none;")
    return line


def make_button(text: str, *, primary=False, danger=False, ghost=False) -> QPushButton:
    button = QPushButton(text)
    if primary:
        button.setObjectName("Primary")
    elif danger:
        button.setObjectName("Danger")
    elif ghost:
        button.setObjectName("Ghost")
    return button


def set_pill(label: QLabel, text: str, level: str = "muted"):
    label.setText(text)
    label.setProperty("pill", level)
    label.style().unpolish(label)
    label.style().polish(label)


def fill_combo(combo: QComboBox, labels: dict[str, str] | None, values=None):
    combo.clear()
    for value in (values if values is not None else list((labels or {}).keys())):
        combo.addItem((labels or {}).get(value, value), value)


def select_combo(combo: QComboBox, value):
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)


def combo_value(combo: QComboBox, default=None):
    value = combo.currentData()
    return default if value is None else value


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------
class SliderRow(QWidget):
    valueChanged = Signal(int)

    def __init__(self, label: str, minimum=0, maximum=100, value=0,
                 suffix: str = "", label_width=180, parent=None):
        super().__init__(parent)
        self._guard = False
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.label = QLabel(label)
        self.label.setMinimumWidth(label_width)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.spin = QSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setFixedWidth(76)
        if suffix:
            self.spin.setSuffix(suffix)
        row.addWidget(self.label)
        row.addWidget(self.slider, 1)
        row.addWidget(self.spin)
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)
        self.set_value(value)

    def _from_slider(self, value):
        if self._guard:
            return
        self._guard = True
        self.spin.setValue(value)
        self._guard = False
        self.valueChanged.emit(value)

    def _from_spin(self, value):
        if self._guard:
            return
        self._guard = True
        self.slider.setValue(value)
        self._guard = False
        self.valueChanged.emit(value)

    def set_value(self, value: int):
        self._guard = True
        self.slider.setValue(int(value))
        self.spin.setValue(int(value))
        self._guard = False

    def value(self) -> int:
        return self.spin.value()

    def set_suffix(self, suffix: str):
        self.spin.setSuffix(suffix)

    def set_label_width(self, width: int):
        self.label.setMinimumWidth(width)


class CurveEditor(QWidget):
    """Draggable three-point stick/trigger response curve."""

    pointsChanged = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points = [[30, 30], [50, 50], [70, 70]]
        self._drag = None
        self.setMinimumHeight(185)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip("Потяните точки, чтобы изменить кривую")

    def set_points(self, points):
        cleaned = []
        for point in (points or [])[:3]:
            try:
                cleaned.append([max(0, min(100, int(point[0]))),
                                max(0, min(100, int(point[1])))])
            except (TypeError, ValueError, IndexError):
                continue
        while len(cleaned) < 3:
            cleaned.append([30 + len(cleaned) * 20, 30 + len(cleaned) * 20])
        self._points = cleaned
        self.update()

    def points(self):
        return [list(point) for point in self._points]

    def _rect(self) -> QRectF:
        return QRectF(30, 12, max(10, self.width() - 48), max(10, self.height() - 44))

    def _to_px(self, point) -> QPointF:
        rect = self._rect()
        return QPointF(rect.left() + point[0] / 100 * rect.width(),
                       rect.bottom() - point[1] / 100 * rect.height())

    def _from_px(self, position: QPointF):
        rect = self._rect()
        x = (position.x() - rect.left()) / rect.width() * 100
        y = (rect.bottom() - position.y()) / rect.height() * 100
        return [max(0, min(100, round(x))), max(0, min(100, round(y)))]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self._rect()
        painter.fillRect(self.rect(), QColor("#10161c"))
        painter.setPen(QPen(QColor("#25303b"), 1))
        for i in range(0, 11):
            x = rect.left() + rect.width() * i / 10
            y = rect.top() + rect.height() * i / 10
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        painter.setPen(QPen(QColor("#44515f"), 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(rect.left(), rect.bottom()), QPointF(rect.right(), rect.top()))
        path = [QPointF(rect.left(), rect.bottom())]
        path += [self._to_px(point) for point in self._points]
        path.append(QPointF(rect.right(), rect.top()))
        painter.setPen(QPen(QColor("#ff6b35"), 2.2))
        for index in range(len(path) - 1):
            painter.drawLine(path[index], path[index + 1])
        for index, point in enumerate(self._points):
            centre = self._to_px(point)
            colour = QColor("#ffd7c8") if index == self._drag else QColor("#ff6b35")
            painter.setBrush(colour)
            painter.setPen(QPen(QColor("#17100c"), 1.5))
            painter.drawEllipse(centre, 6.0, 6.0)
        painter.setPen(QPen(QColor("#8b98a5"), 1))
        painter.drawText(QPointF(rect.left(), rect.bottom() + 17), "0")
        painter.drawText(QPointF(rect.right() - 12, rect.bottom() + 17), "100")
        painter.drawText(QPointF(rect.left() - 24, rect.top() + 6), "100")
        painter.setPen(QPen(QColor("#5c6874"), 1))
        painter.drawText(QPointF(rect.right() - 74, rect.bottom() + 17), "вход →")
        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        position = event.position()
        best, best_dist = None, 18.0
        for index, point in enumerate(self._points):
            centre = self._to_px(point)
            dist = ((centre.x() - position.x()) ** 2 + (centre.y() - position.y()) ** 2) ** 0.5
            if dist < best_dist:
                best, best_dist = index, dist
        if best is not None:
            self._drag = best
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag is None:
            return
        self._points[self._drag] = self._from_px(event.position())
        self.update()
        self.pointsChanged.emit(self.points())

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._drag is not None:
            self._drag = None
            self.update()
            self.pointsChanged.emit(self.points())


class CurveGroup(QGroupBox):
    changed = Signal()

    def __init__(self, title="Кривая отклика", *, circle=False, axis_ratio=True,
                 parent=None):
        super().__init__(title, parent)
        self._guard = False
        self._circle = circle
        self._axis_ratio = axis_ratio
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(8)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Тип кривой"))
        self.preset = QComboBox()
        fill_combo(self.preset, CURVE_LABELS)
        preset_row.addWidget(self.preset, 1)
        layout.addLayout(preset_row)

        self.intensity = SliderRow("Интенсивность", 0, 100, 100, "%", 150)
        layout.addWidget(self.intensity)

        self.deadzone_min = SliderRow("Мёртвая зона (начало)", 0, 100, 5, "%", 200)
        self.deadzone_max = SliderRow("Мёртвая зона (конец)", 0, 100, 100, "%", 200)
        self.antideadzone_min = SliderRow("Анти-мёртвая зона (начало)", 0, 100, 0, "%", 200)
        self.antideadzone_max = SliderRow("Анти-мёртвая зона (конец)", 0, 100, 100, "%", 200)
        layout.addWidget(self.deadzone_min)
        layout.addWidget(self.deadzone_max)
        layout.addWidget(self.antideadzone_min)
        layout.addWidget(self.antideadzone_max)

        options = QHBoxLayout()
        if self._circle:
            self.circle = QCheckBox("Круглая зона стика")
            self.circle.setToolTip("Ограничение хода стика кругом, а не квадратом")
            options.addWidget(self.circle)
        else:
            self.circle = None
        if self._axis_ratio:
            self.axis_label = QLabel("Соотношение осей X/Y")
            options.addWidget(self.axis_label)
            self.axis = QSpinBox()
            self.axis.setRange(0, 100)
            self.axis.setSuffix("%")
            self.axis.setFixedWidth(80)
            options.addWidget(self.axis)
        else:
            self.axis = None
        options.addStretch(1)
        layout.addLayout(options)

        self.editor = CurveEditor()
        layout.addWidget(self.editor)
        layout.addWidget(muted("Точки задают форму кривой для типа «Своя». "
                               "Потяните их мышью."))

        self.preset.currentIndexChanged.connect(self._emit)
        for row in (self.intensity, self.deadzone_min, self.deadzone_max,
                    self.antideadzone_min, self.antideadzone_max):
            row.valueChanged.connect(self._emit)
        if self.circle:
            self.circle.toggled.connect(self._emit)
        if self.axis:
            self.axis.valueChanged.connect(self._emit)
        self.editor.pointsChanged.connect(self._emit)

    def _emit(self, *_args):
        if not self._guard:
            self.changed.emit()

    def set_config(self, data: dict):
        self._guard = True
        select_combo(self.preset, data.get("curve_preset", "linear"))
        self.intensity.set_value(data.get("curve_intensity", 100))
        self.deadzone_min.set_value(data.get("deadzone_min", 5))
        self.deadzone_max.set_value(data.get("deadzone_max", 100))
        self.antideadzone_min.set_value(data.get("antideadzone_min", 0))
        self.antideadzone_max.set_value(data.get("antideadzone_max", 100))
        if self.circle:
            self.circle.setChecked(bool(data.get("is_circle", True)))
        if self.axis:
            self.axis.setValue(int(data.get("axis_ratio", 50)))
        self.editor.set_points(data.get("curve_points"))
        self._guard = False

    def update_config(self, data: dict):
        data["curve_preset"] = combo_value(self.preset, "linear")
        data["curve_intensity"] = self.intensity.value()
        data["deadzone_min"] = self.deadzone_min.value()
        data["deadzone_max"] = self.deadzone_max.value()
        data["antideadzone_min"] = self.antideadzone_min.value()
        data["antideadzone_max"] = self.antideadzone_max.value()
        data["curve_points"] = self.editor.points()
        if self.circle:
            data["is_circle"] = self.circle.isChecked()
        if self.axis:
            data["axis_ratio"] = self.axis.value()


class StickPreview(QWidget):
    """Small live stick visualisation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._x = 0.0
        self._y = 0.0
        self._active = False
        self.setMinimumSize(130, 130)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_position(self, x: float, y: float):
        self._x = max(-1.0, min(1.0, float(x)))
        self._y = max(-1.0, min(1.0, float(y)))
        self._active = abs(self._x) > 0.03 or abs(self._y) > 0.03
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        side = min(self.width(), self.height()) - 14
        rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        painter.setBrush(QColor("#10161c"))
        painter.setPen(QPen(QColor("#33414f"), 2))
        painter.drawEllipse(rect)
        painter.setPen(QPen(QColor("#25303b"), 1))
        centre = rect.center()
        painter.drawLine(QPointF(rect.left() + 8, centre.y()), QPointF(rect.right() - 8, centre.y()))
        painter.drawLine(QPointF(centre.x(), rect.top() + 8), QPointF(centre.x(), rect.bottom() - 8))
        dot = QPointF(centre.x() + self._x * (side / 2 - 14),
                      centre.y() + self._y * (side / 2 - 14))
        painter.setBrush(QColor("#ff6b35") if self._active else QColor("#8b98a5"))
        painter.setPen(QPen(QColor("#17100c"), 1.5))
        painter.drawEllipse(dot, 8.0, 8.0)
        painter.end()


class ColorButton(QPushButton):
    changed = Signal(list)

    def __init__(self, hsv=None, parent=None):
        super().__init__(parent)
        self._hsv = list(hsv or [0, 0, 100])
        self.setFixedSize(74, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._pick)
        self._update_style()

    def set_hsv(self, hsv):
        self._hsv = list(hsv or [0, 0, 100])
        self._update_style()

    def hsv(self):
        return list(self._hsv)

    def _qcolor(self) -> QColor:
        h, s, v = self._hsv
        return QColor.fromHsv(max(0, min(359, int(h))),
                              max(0, min(255, round(s * 255 / 100))),
                              max(0, min(255, round(v * 255 / 100))))

    def _update_style(self):
        colour = self._qcolor()
        text = "#101010" if colour.lightness() > 140 else "#f0f0f0"
        self.setStyleSheet(
            f"QPushButton {{ background: {colour.name()}; border: 1px solid #3a4755; "
            f"border-radius: 7px; color: {text}; font-size: 10px; font-weight: 700; }}"
            f"QPushButton:hover {{ border: 2px solid #ff6b35; }}"
        )
        self.setText(colour.name().upper())
        self.setToolTip(f"H {self._hsv[0]}° · S {self._hsv[1]}% · V {self._hsv[2]}%")

    def _pick(self):
        start = self._qcolor()
        colour = QColorDialog.getColor(start, self, "Выберите цвет")
        if not colour.isValid():
            return
        hue = colour.hue()
        if hue < 0:
            hue = int(self._hsv[0])
        self._hsv = [int(hue), round(colour.saturation() * 100 / 255),
                     round(colour.value() * 100 / 255)]
        self._update_style()
        self.changed.emit(self.hsv())


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------
class TargetEditorDialog(QDialog):
    """Build a mapping target: controller button, keyboard, mouse or media."""

    def __init__(self, target: str | None, parent=None, title="Назначение кнопки"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(620, 640)
        self._loading = False
        self._controller_items: dict[str, QListWidgetItem] = {}
        self._key_items: dict[str, QListWidgetItem] = {}
        self._mouse_checks: dict[str, QCheckBox] = {}
        self._media_checks: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        kind_row = QHBoxLayout()
        kind_row.addWidget(QLabel("Тип назначения"))
        self.kind = QComboBox()
        for value in ("factory", "controller", "key", "mouse", "media", "unbind"):
            self.kind.addItem(TARGET_KIND_LABELS[value], value)
        kind_row.addWidget(self.kind, 1)
        layout.addLayout(kind_row)

        from PySide6.QtWidgets import QStackedWidget
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.stack.addWidget(self._build_factory_page())
        self.stack.addWidget(self._build_controller_page())
        self.stack.addWidget(self._build_key_page())
        self.stack.addWidget(self._build_mouse_page())
        self.stack.addWidget(self._build_media_page())
        self.stack.addWidget(self._build_unbind_page())

        self.preview = QLabel()
        self.preview.setObjectName("Mono")
        self.preview.setWordWrap(True)
        layout.addWidget(self.preview)
        self.error = QLabel()
        self.error.setStyleSheet("color: #ff7b72;")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        self._ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.kind.currentIndexChanged.connect(self._kind_changed)
        self._load(target or None)

    # -- pages ------------------------------------------------------------
    def _build_factory_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(info_label(
            "Кнопка возвращается к заводскому назначению контроллера. "
            "Перед записью макрос и турбо для неё будут удалены."
        ))
        layout.addStretch(1)
        return page

    def _build_unbind_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(note("Кнопка будет отключена и не будет отправлять никаких событий."))
        layout.addStretch(1)
        return page

    def _build_controller_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.controller_search = QLineEdit()
        self.controller_search.setPlaceholderText("Поиск кнопки…")
        self.controller_search.textChanged.connect(self._filter_controller)
        layout.addWidget(self.controller_search)
        self.controller_list = QListWidget()
        self.controller_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        names = [name for name in SOURCE_ORDER if name in keys.CONTROLLER_SOURCE]
        extra = [name for name in keys.CONTROLLER_SOURCE if name not in names]
        names += sorted(extra)
        for name in names:
            item = QListWidgetItem(source_label(name))
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.controller_list.addItem(item)
            self._controller_items[name] = item
        for name in keys.STICK_DIRECTION:
            if name.startswith(("lstick", "rstick")):
                continue
            if name in self._controller_items:
                continue
            item = QListWidgetItem(source_label(name))
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.controller_list.addItem(item)
            self._controller_items[name] = item
        self.controller_list.itemSelectionChanged.connect(self._update_preview)
        layout.addWidget(self.controller_list)
        layout.addWidget(muted("Можно выбрать до трёх кнопок — они нажмутся одновременно."))
        return page

    def _build_key_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        mods = QLabel("Модификаторы")
        mods.setObjectName("SectionLabel")
        layout.addWidget(mods)
        grid = QGridLayout()
        grid.setSpacing(6)
        self._mod_checks = {}
        for index, name in enumerate(keys.CANONICAL_MODIFIER):
            check = QCheckBox(pretty_key(name))
            check.toggled.connect(self._update_preview)
            grid.addWidget(check, index // 4, index % 4)
            self._mod_checks[name] = check
        layout.addLayout(grid)
        self.key_search = QLineEdit()
        self.key_search.setPlaceholderText("Поиск клавиши…")
        self.key_search.textChanged.connect(self._filter_keys)
        layout.addWidget(self.key_search)
        self.key_list = QListWidget()
        self.key_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        names = [name for name, usage in keys.KEYBOARD_USAGE.items()
                 if usage > 0x03 and not 0xE0 <= usage <= 0xE7]
        for name in sorted(names, key=lambda item: pretty_key(item).lower()):
            item = QListWidgetItem(pretty_key(name))
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.key_list.addItem(item)
            self._key_items[name] = item
        self.key_list.itemSelectionChanged.connect(self._update_preview)
        layout.addWidget(self.key_list)
        layout.addWidget(muted("До трёх клавиш плюс модификаторы."))
        return page

    def _build_mouse_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        for name, label in MOUSE_TARGET_LABELS.items():
            check = QCheckBox(label)
            check.toggled.connect(self._update_preview)
            layout.addWidget(check)
            self._mouse_checks[name] = check
        layout.addStretch(1)
        return page

    def _build_media_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        for name, label in MEDIA_TARGET_LABELS.items():
            check = QCheckBox(label)
            check.toggled.connect(self._update_preview)
            layout.addWidget(check)
            self._media_checks[name] = check
        layout.addStretch(1)
        return page

    # -- filtering --------------------------------------------------------
    def _filter_controller(self, text: str):
        text = text.strip().lower()
        for name, item in self._controller_items.items():
            item.setHidden(bool(text) and text not in name.lower()
                           and text not in item.text().lower())

    def _filter_keys(self, text: str):
        text = text.strip().lower()
        for name, item in self._key_items.items():
            item.setHidden(bool(text) and text not in name.lower()
                           and text not in item.text().lower())

    # -- loading ----------------------------------------------------------
    def _load(self, target: str | None):
        self._loading = True
        kind = "factory"
        tokens: list[str] = []
        text = (target or "").strip().lower()
        try:
            if text in ("none", "unbind", "nc", "disabled"):
                kind = "unbind"
            elif text:
                parsed = keys.parse_target(text)
                if parsed is None:
                    for candidate, table in (
                        ("mouse", keys.MOUSE_BUTTON), ("mouse", keys.MOUSE_SCROLL),
                        ("key", keys.KEYBOARD_USAGE),
                        ("controller", keys.CONTROLLER_SOURCE),
                        ("controller", keys.STICK_DIRECTION),
                    ):
                        if text in table:
                            kind, tokens = candidate, [text]
                            break
                else:
                    kind, tokens = parsed
            if kind not in TARGET_KIND_LABELS:
                kind = "factory"
                tokens = []

            if kind == "controller":
                for token in tokens:
                    name = keys.normalize_source(token)
                    item = self._controller_items.get(name)
                    if item:
                        item.setSelected(True)
            elif kind == "key":
                for token in tokens:
                    name = keys.normalize_source(token)
                    if name in keys.MODIFIER_BITS:
                        canonical = keys.CANONICAL_MODIFIER[keys.MODIFIER_BITS[name]]
                        self._mod_checks[canonical].setChecked(True)
                    elif name in self._key_items:
                        self._key_items[name].setSelected(True)
            elif kind == "mouse":
                for token in tokens:
                    if token in self._mouse_checks:
                        self._mouse_checks[token].setChecked(True)
            elif kind == "media":
                for token in tokens:
                    if token in self._media_checks:
                        self._media_checks[token].setChecked(True)
        finally:
            self._loading = False
        index = self.kind.findData(kind)
        self.kind.setCurrentIndex(max(0, index))
        self._update_preview()

    # -- preview ----------------------------------------------------------
    def _kind_changed(self, _index):
        self.stack.setCurrentIndex(self.kind.currentIndex())
        self._update_preview()

    def _build_target(self) -> str | None:
        kind = combo_value(self.kind, "factory")
        if kind == "factory":
            return None
        if kind == "unbind":
            return "none"
        if kind == "controller":
            names = [item.data(Qt.ItemDataRole.UserRole)
                     for item in self.controller_list.selectedItems()]
            return "controller:" + "+".join(names) if names else ""
        if kind == "key":
            mods = [name for name, check in self._mod_checks.items() if check.isChecked()]
            chosen = [item.data(Qt.ItemDataRole.UserRole)
                      for item in self.key_list.selectedItems()]
            tokens = mods + chosen
            return "key:" + "+".join(tokens) if tokens else ""
        if kind == "mouse":
            tokens = [name for name, check in self._mouse_checks.items() if check.isChecked()]
            return "mouse:" + "+".join(tokens) if tokens else ""
        if kind == "media":
            tokens = [name for name, check in self._media_checks.items() if check.isChecked()]
            return "media:" + "+".join(tokens) if tokens else ""
        return None

    def _update_preview(self):
        if self._loading:
            return
        kind = combo_value(self.kind, "factory")
        target = self._build_target()
        valid = True
        message = ""
        if kind == "factory":
            self.preview.setText("Заводское назначение — кнопка работает как в прошивке.")
        elif kind == "unbind":
            self.preview.setText("none — кнопка отключена")
        elif not target:
            self.preview.setText("Ничего не выбрано")
            valid = False
        else:
            try:
                report, code = keys.encode_target(target)
                self.preview.setText(f"{target}\nтип {report[0]:02x}/{report[1]:02x} · "
                                     f"код {code.hex(' ')}")
            except ValueError as exc:
                valid = False
                message = str(exc)
                self.preview.setText(target)
        count_error = ""
        if kind == "controller":
            selected = len(self.controller_list.selectedItems())
            if selected > 3:
                valid = False
                count_error = "Можно выбрать не более трёх кнопок контроллера."
        if kind == "key":
            if len(self.key_list.selectedItems()) > 3:
                valid = False
                count_error = "Можно выбрать не более трёх клавиш."
        self.error.setText(message or count_error)
        self._ok.setEnabled(valid)

    def target(self) -> str | None:
        return self._build_target()

    def accept(self):
        self._update_preview()
        if not self._ok.isEnabled():
            return
        super().accept()


class TurboDialog(QDialog):
    def __init__(self, turbo: dict | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Турбо для кнопки")
        self.resize(430, 240)
        layout = QVBoxLayout(self)
        self.enabled = QCheckBox("Включить турбо")
        self.enabled.setChecked(bool(turbo))
        layout.addWidget(self.enabled)
        self.rate = SliderRow("Частота, Гц", 2, 50, int((turbo or {}).get("rate", 10)))
        layout.addWidget(self.rate)
        self.continuous = QCheckBox("Режим переключателя (toggle)")
        self.continuous.setChecked(bool((turbo or {}).get("continuous", False)))
        self.continuous.setToolTip("Нажатие включает удержание, повторное нажатие выключает")
        layout.addWidget(self.continuous)
        layout.addWidget(muted(
            "Прошивка хранит частоту как режим A/B/C: ≥20 Гц — C, ≥12 Гц — B, "
            "иначе A. Фактическая частота может немного отличаться."
        ))
        layout.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.enabled.toggled.connect(self.rate.setEnabled)

    def result_settings(self):
        if not self.enabled.isChecked():
            return None
        return {"rate": self.rate.value(), "continuous": self.continuous.isChecked()}


class MacroStepDialog(QDialog):
    def __init__(self, step: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Шаг макроса")
        self.resize(520, 300)
        step = step or {}
        self._target = step.get("target") or "controller:a"
        layout = QVBoxLayout(self)
        form = QGridLayout()
        form.addWidget(QLabel("Действие"), 0, 0)
        self.target_button = QPushButton()
        self.target_button.clicked.connect(self._choose_target)
        form.addWidget(self.target_button, 0, 1)
        form.addWidget(QLabel("Нажатие"), 1, 0)
        self.press = QSpinBox()
        self.press.setRange(0, 65535)
        self.press.setSuffix(" мс")
        self.press.setValue(int(step.get("press_ms", 50)))
        form.addWidget(self.press, 1, 1)
        form.addWidget(QLabel("Отпускание / пауза"), 2, 0)
        self.release = QSpinBox()
        self.release.setRange(0, 65535)
        self.release.setSuffix(" мс")
        self.release.setValue(int(step.get("release_ms", 50)))
        form.addWidget(self.release, 2, 1)
        layout.addLayout(form)
        layout.addWidget(muted(
            "Для кнопок контроллера время нажатия и отпускания задаёт длительность "
            "импульса. Для клавиш и мыши это также пауза между событиями."
        ))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh_target()

    def _refresh_target(self):
        from .labels import target_label
        self.target_button.setText(target_label(self._target))

    def _choose_target(self):
        dialog = TargetEditorDialog(self._target, self, "Действие шага макроса")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            target = dialog.target()
            if target and target != "none":
                self._target = target
                self._refresh_target()

    def accept(self):
        try:
            keys.encode_target(self._target)
        except ValueError as exc:
            QMessageBox.warning(self, "Некорректное действие", str(exc))
            return
        super().accept()

    def step(self):
        return {"target": self._target,
                "press_ms": self.press.value(),
                "release_ms": self.release.value()}


def show_text_dialog(parent, title: str, text: str,
                     icon=QMessageBox.Icon.Warning):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.resize(660, 420)
    layout = QVBoxLayout(dialog)
    heading = QLabel(title)
    heading.setObjectName("Big")
    heading.setWordWrap(True)
    layout.addWidget(heading)
    edit = QPlainTextEdit()
    edit.setReadOnly(True)
    edit.setPlainText(text)
    layout.addWidget(edit, 1)
    buttons = QHBoxLayout()
    copy = make_button("Копировать")
    close = make_button("Закрыть", primary=True)
    buttons.addStretch(1)
    buttons.addWidget(copy)
    buttons.addWidget(close)
    layout.addLayout(buttons)

    def do_copy():
        QApplication.clipboard().setText(text)

    copy.clicked.connect(do_copy)
    close.clicked.connect(dialog.accept)
    dialog.exec()


# Need this import at module scope for show_text_dialog.
from PySide6.QtWidgets import QPlainTextEdit  # noqa: E402
