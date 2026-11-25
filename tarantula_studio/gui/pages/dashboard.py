"""Dashboard: connection state, quick DPI and live input."""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QProgressBar,
    QVBoxLayout, QWidget,
)

from ...core import device as devmod
from ...core import live
from ...core.transport import HidrawDevice
from ..labels import STICK_MODE_LABELS
from ..widgets import (
    Card, Page, SliderRow, StickPreview, info_label, make_button, muted,
    note, set_pill,
)


class DashboardPage(Page):
    TITLE = "Обзор"
    SUBTITLE = "Состояние контроллера, быстрый DPI и живой ввод"

    def __init__(self, app):
        super().__init__(app)
        self._live_timer = QTimer(self)
        self._live_timer.setInterval(50)
        self._live_timer.timeout.connect(self._poll_live)
        self._build()
        self.state.deviceChanged.connect(self.refresh)
        self.state.busyChanged.connect(self._busy_changed)

    def _build(self):
        top = QHBoxLayout()
        top.setSpacing(16)
        top.addWidget(self._connection_card(), 3)
        self.dpi_card = self._dpi_card()
        top.addWidget(self.dpi_card, 2)
        self.add_layout(top)
        self.add(self._live_card())
        self.actions_card = self._actions_card()
        self.add(self.actions_card)
        self.add_stretch()

    # -- cards ------------------------------------------------------------
    def _connection_card(self) -> Card:
        card = Card("Контроллер")
        card.setMinimumWidth(430)
        head = card.row()
        self.device_pill = QLabel()
        set_pill(self.device_pill, "Поиск…", "muted")
        head.addWidget(self.device_pill)
        head.addStretch(1)

        self.product_label = QLabel("GameSir Tarantula Pro")
        self.product_label.setObjectName("Big")
        card.add(self.product_label)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(5)
        self._info_labels = {}
        fields = [("path", "Интерфейс"), ("firmware", "Прошивка"),
                  ("battery", "Батарея"), ("mac", "MAC"), ("source", "Источник")]
        for row, (key, title) in enumerate(fields):
            label = QLabel(title)
            label.setObjectName("Muted")
            value = QLabel("—")
            value.setObjectName("Mono")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(label, row, 0)
            grid.addWidget(value, row, 1)
            self._info_labels[key] = value
        grid.setColumnStretch(1, 1)
        card.add_layout(grid)

        self.access_note = note(
            "Нет прав на /dev/hidraw. Откройте «Диагностику» и установите udev-правило."
        )
        self.access_note.hide()
        card.add(self.access_note)

        buttons = card.row()
        self.read_button = make_button("Считать с контроллера", primary=True)
        self.read_button.clicked.connect(lambda: self.app.read_controller())
        buttons.addWidget(self.read_button)
        diag = make_button("Диагностика")
        diag.clicked.connect(lambda: self.app.navigate("diagnostics"))
        buttons.addWidget(diag)
        buttons.addStretch(1)
        return card

    def _dpi_card(self) -> Card:
        card = Card("Быстрый DPI")
        side_row = card.row()
        side_row.addWidget(QLabel("Стик"))
        self.side_combo = QComboBox()
        self.side_combo.addItem("Правый (RS)", 1)
        self.side_combo.addItem("Левый (LS)", 0)
        self.side_combo.currentIndexChanged.connect(self._load_side)
        side_row.addWidget(self.side_combo, 1)
        self.mode_label = QLabel("—")
        self.mode_label.setObjectName("Muted")
        side_row.addWidget(self.mode_label)

        self.dpi = SliderRow("DPI по X и Y", 0, 255, 100, label_width=110)
        self.dpi.valueChanged.connect(self._dpi_note)
        card.add(self.dpi)

        self.dpi_note = note(
            "Выше 100 — экспериментальный режим. Официальное приложение ограничивает "
            "значение 100, но поле прошивки однобайтовое (0–255). После записи проверьте "
            "обратное чтение и движение мыши."
        )
        self.dpi_note.hide()
        card.add(self.dpi_note)
        card.add(muted("Кнопка сразу пишет в контроллер и переключает стик в режим мыши. "
                       "Остальные поля стика не меняются."))
        self.dpi_readback = muted("Обратное чтение: —")
        card.add(self.dpi_readback)

        row = card.row()
        self.write_dpi_button = make_button("Записать DPI", primary=True)
        self.write_dpi_button.clicked.connect(self._write_dpi)
        row.addWidget(self.write_dpi_button)
        mouse = make_button("Мышь и DPI")
        mouse.clicked.connect(lambda: self.app.navigate("mouse"))
        row.addWidget(mouse)
        row.addStretch(1)
        self._dpi_note()
        return card

    def _live_card(self) -> Card:
        card = Card("Живой ввод")
        head = card.row()
        self.live_check = QCheckBox("Опрашивать /dev/input/js*")
        self.live_check.toggled.connect(self._toggle_live)
        head.addWidget(self.live_check)
        self.live_status = muted("Остановлено")
        head.addWidget(self.live_status, 1)

        visuals = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("Левый стик"))
        self.left_preview = StickPreview()
        left.addWidget(self.left_preview)
        right = QVBoxLayout()
        right.addWidget(QLabel("Правый стик"))
        self.right_preview = StickPreview()
        right.addWidget(self.right_preview)
        visuals.addLayout(left, 1)
        visuals.addLayout(right, 1)

        triggers = QVBoxLayout()
        triggers.addWidget(QLabel("LT"))
        self.lt_bar = QProgressBar()
        self.lt_bar.setRange(0, 100)
        self.lt_bar.setValue(0)
        triggers.addWidget(self.lt_bar)
        triggers.addWidget(QLabel("RT"))
        self.rt_bar = QProgressBar()
        self.rt_bar.setRange(0, 100)
        self.rt_bar.setValue(0)
        triggers.addWidget(self.rt_bar)
        triggers.addStretch(1)
        visuals.addLayout(triggers, 2)
        card.add_layout(visuals)

        self.pressed_label = QLabel("Нажатые кнопки: —")
        self.pressed_label.setWordWrap(True)
        card.add(self.pressed_label)
        card.add(muted("Джойстик Linux видит стандартные кнопки XInput. "
                       "Дополнительные L4/R4/T1–T3/C1–C4 могут отображаться как "
                       "переназначенные им клавиши."))
        return card

    def _actions_card(self) -> Card:
        card = Card("Быстрые действия")
        row = card.row()
        backup = make_button("Создать резервную копию")
        backup.clicked.connect(lambda: self.app.backup_now())
        row.addWidget(backup)
        profiles = make_button("Профили и резервные копии")
        profiles.clicked.connect(lambda: self.app.navigate("profiles"))
        row.addWidget(profiles)
        reset = make_button("Отменить все изменения", danger=True)
        reset.clicked.connect(lambda: self.app.discard_changes())
        row.addWidget(reset)
        row.addStretch(1)
        return card

    # -- state ------------------------------------------------------------
    def refresh(self):
        state = self.state
        supernova = state.device_kind == "supernova"
        self.dpi_card.setVisible(not supernova)
        self.actions_card.setVisible(not supernova)
        if state.device_present:
            if state.access_error:
                set_pill(self.device_pill, "Нет доступа", "err")
            else:
                set_pill(self.device_pill, "Подключён", "ok")
        else:
            set_pill(self.device_pill, "Не найден", "muted")
        self.device_pill.setToolTip(state.device_summary())

        info = state.info or {}
        self.product_label.setText(info.get("product") or "GameSir Tarantula Pro")
        self._info_labels["path"].setText(state.device_path or info.get("path") or "—")
        firmware = info.get("firmware") or "—"
        ctrl = info.get("controller_version") or {}
        if ctrl.get("firmware"):
            firmware = f"{firmware}  ·  MCU {ctrl['firmware']}"
        self._info_labels["firmware"].setText(firmware)
        battery = info.get("battery")
        if info.get("charging"):
            battery_text = "заряжается"
        elif battery is None:
            battery_text = "—"
        else:
            battery_text = f"{battery}%"
        self._info_labels["battery"].setText(battery_text)
        self._info_labels["mac"].setText(info.get("mac") or "—")
        self._info_labels["source"].setText(state.config_source)
        self.access_note.setVisible(bool(state.access_error))
        self.read_button.setEnabled(not state.busy)
        self._busy_changed(state.busy)
        self._load_side()

    def _load_side(self):
        if self.state.device_kind == "supernova":
            self.mode_label.setText("Super Nova")
            return
        side = int(self.side_combo.currentData() or 1)
        stick = self.state.staged.get("stick_right" if side else "stick_left") or {}
        self.dpi.blockSignals(True)
        self.dpi.set_value(int(stick.get("mouse_dpi", 50)))
        self.dpi.blockSignals(False)
        mode = stick.get("mode", "native")
        self.mode_label.setText(STICK_MODE_LABELS.get(mode, mode))
        self._dpi_note()

    def _dpi_note(self, *_args):
        self.dpi_note.setVisible(self.dpi.value() > 100)

    def _busy_changed(self, busy: bool):
        self.read_button.setEnabled(not busy)
        self.write_dpi_button.setEnabled(not busy and self.state.device_present
                                          and not self.state.access_error)
        if busy:
            set_pill(self.device_pill, "Обмен…", "warn")

    def _write_dpi(self):
        if not self.state.device_present or self.state.device_kind == "supernova":
            return
        side = int(self.side_combo.currentData() or 1)
        value = self.dpi.value()

        def job(progress):
            progress(f"Запись DPI {value}…")
            with HidrawDevice() as dev:
                actual = devmod.quick_set_dpi(dev, side, value, enable_mouse=True)
                try:
                    info = devmod.read_device_info(dev)
                except Exception:
                    info = {}
                return actual, info

        def done(payload):
            actual, info = payload
            key = "stick_right" if side else "stick_left"
            self.state.baseline[key] = copy.deepcopy(actual)
            self.state.staged[key] = copy.deepcopy(actual)
            self.state.info.update(info)
            self.state.touch()
            self.state.deviceChanged.emit()
            got = actual.get("mouse_dpi")
            self.dpi_readback.setText(
                f"Обратное чтение: mode={STICK_MODE_LABELS.get(actual.get('mode'), actual.get('mode'))} · "
                f"DPI X={got} · Y={actual.get('mouse_dpi_y')}"
            )
            self.app.log(f"Быстрый DPI: записано {value}, прочитано X={got} Y={actual.get('mouse_dpi_y')}.")
            if got != value:
                self.app.show_warnings(
                    "Прошивка изменила значение DPI",
                    [f"Запрошено: {value}", f"Прочитано X: {got}",
                     f"Прочитано Y: {actual.get('mouse_dpi_y')}",
                     "Если значение больше 100 и прочиталось как 100 (или иное), "
                     "прошивка ограничивает DPI. Проверьте движение мыши на странице "
                     "«Мышь и DPI»."],
                )

        self.app.run_task("Быстрый DPI", job, done)

    # -- live input -------------------------------------------------------
    def _toggle_live(self, enabled: bool):
        if enabled and self.isVisible():
            self._live_timer.start()
            self.live_status.setText("Ожидание ввода…")
        else:
            self._live_timer.stop()
            self.live_status.setText("Остановлено")
            self._reset_live()

    def _reset_live(self):
        self.left_preview.set_position(0, 0)
        self.right_preview.set_position(0, 0)
        self.lt_bar.setValue(0)
        self.rt_bar.setValue(0)
        self.pressed_label.setText("Нажатые кнопки: —")

    def _poll_live(self):
        state = live.read_state()
        if not state.get("connected"):
            self.live_status.setText("Джойстик не найден")
            self._reset_live()
            return
        self.live_status.setText(f"{state.get('name')} · {state.get('path')}")
        self.left_preview.set_position(state["left"]["x"], state["left"]["y"])
        self.right_preview.set_position(state["right"]["x"], state["right"]["y"])
        self.lt_bar.setValue(round(state.get("lt", 0) * 100))
        self.rt_bar.setValue(round(state.get("rt", 0) * 100))
        pressed = state.get("pressed") or []
        self.pressed_label.setText("Нажатые кнопки: " +
                                   (", ".join(pressed) if pressed else "—"))

    def showEvent(self, event):
        super().showEvent(event)
        if self.live_check.isChecked():
            self._live_timer.start()

    def hideEvent(self, event):
        self._live_timer.stop()
        super().hideEvent(event)
