"""GameSir Super Nova / T4 Nova Pro page (verified feature subset)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout,
)

from ...core import supernova as snmod
from ...core.transport import HidrawDevice
from ..widgets import (
    Card, Page, SliderRow, info_label, make_button, muted, note, set_pill,
)


class SuperNovaPage(Page):
    TITLE = "T4 Nova Pro"
    SUBTITLE = "Super Nova: переназначения, вибрация и мёртвые зоны"

    def __init__(self, app):
        super().__init__(app)
        self._loading = False
        self._editor_cards: list[Card] = []
        self._build()
        self.state.deviceChanged.connect(self.refresh)
        self.state.configReplaced.connect(self.refresh)
        self.state.busyChanged.connect(self._busy_changed)

    def _build(self):
        self.add(note(
            "GameSir Super Nova / T4 Nova Pro подключается через донгл 2.4 ГГц "
            "в режиме PC. Протокол другой, чем у T3 Pro, поэтому приложение "
            "сначала проверяет тип устройства (3) и никогда не пишет T3-команды "
            "в Super Nova.\n\n"
            "Проверены на реальном железе только переназначения "
            "«кнопка → кнопка», сила вибрации и начальные мёртвые зоны стиков "
            "и курков. Кривые, антимёртвые зоны, подсветка, гироскоп, макросы "
            "и режим мыши/DPI у Super Nova не реализованы — их запись не "
            "подтверждена."
        ))

        card = Card("Подключение")
        row = card.row()
        self.connection_pill = QLabel()
        set_pill(self.connection_pill, "Не подключён", "muted")
        row.addWidget(self.connection_pill)
        row.addStretch(1)
        self.read_button = make_button("Прочитать Super Nova", primary=True)
        self.read_button.clicked.connect(lambda: self.app.read_controller())
        row.addWidget(self.read_button)
        self.info = info_label("Подключите T4 Nova Pro через донгл 2.4 ГГц.")
        card.add(self.info)
        self.battery = muted("")
        card.add(self.battery)
        self.add(card)

        remaps = Card("Переназначение кнопок")
        remaps.add(muted("Цель — другая кнопка геймпада. «Как есть» возвращает "
                        "заводское значение. L4/R4 можно переназначить, но "
                        "назначить их целью нельзя: такой записи нет в "
                        "проверенном протоколе."))
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(6)
        self.remap_combos: dict[str, QComboBox] = {}
        half = (len(snmod.REMAP_SOURCES) + 1) // 2
        for index, (name, _code) in enumerate(snmod.REMAP_SOURCES):
            column = 0 if index < half else 2
            row = index if index < half else index - half
            label = QLabel(name)
            combo = QComboBox()
            combo.addItem("Как есть", name)
            for target in snmod.TARGET_NAMES:
                combo.addItem(target, target)
            combo.currentIndexChanged.connect(
                lambda _idx, source=name: self._save_remap(source))
            grid.addWidget(label, row, column)
            grid.addWidget(combo, row, column + 1)
            self.remap_combos[name] = combo
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        remaps.add_layout(grid)
        self.add(remaps)
        self._editor_cards.append(remaps)

        deadzones = Card("Начальные мёртвые зоны")
        deadzones.add(muted(
            "Меняется только начало мёртвой зоны. Конец (100 для стиков, 95 "
            "для курков) и форма кривой не редактируются: эти поля не были "
            "проверены отдельно."))
        self.stick_left = SliderRow("Левый стик (LS)", 0, 99, 5)
        self.stick_right = SliderRow("Правый стик (RS)", 0, 99, 5)
        self.trigger_left = SliderRow("Левый курок (LT)", 0, 94, 5)
        self.trigger_right = SliderRow("Правый курок (RT)", 0, 94, 5)
        for widget in (self.stick_left, self.stick_right,
                       self.trigger_left, self.trigger_right):
            widget.valueChanged.connect(self._save_deadzones)
            deadzones.add(widget)
        self.add(deadzones)
        self._editor_cards.append(deadzones)

        vibration = Card("Сила вибрации")
        self.vib_left = SliderRow("Левый мотор", 0, 100, 75, "%")
        self.vib_right = SliderRow("Правый мотор", 0, 100, 75, "%")
        self.vib_left.valueChanged.connect(self._save_vibration)
        self.vib_right.valueChanged.connect(self._save_vibration)
        vibration.add(self.vib_left)
        vibration.add(self.vib_right)
        row = vibration.row()
        self.test_button = make_button("Тест вибрации")
        self.test_button.setToolTip("Один короткий импульс, настройки не сохраняются")
        self.test_button.clicked.connect(self._test_vibration)
        row.addWidget(self.test_button)
        row.addStretch(1)
        vibration.add(note("На Super Nova тестовый импульс может задействовать "
                           "оба мотора даже при ненулевом значении только одного "
                           "канала. Это проверка силы, а не раздельная настройка."))
        self.add(vibration)
        self._editor_cards.append(vibration)

        row = QHBoxLayout()
        self.apply_button = make_button("Применить изменения", primary=True)
        self.apply_button.clicked.connect(lambda: self.app.apply_changes())
        row.addWidget(self.apply_button)
        discard = make_button("Отменить изменения")
        discard.clicked.connect(self.app.discard_changes)
        row.addWidget(discard)
        row.addStretch(1)
        self.add_layout(row)
        self.add_stretch()

    # -- data -------------------------------------------------------------
    def _config(self) -> dict | None:
        return self.state.supernova

    def refresh(self):
        config = self._config()
        active = self.state.device_kind == "supernova" and config is not None
        if active:
            set_pill(self.connection_pill, "Super Nova", "ok")
            info = config.get("info") or self.state.info or {}
            battery = info.get("battery")
            battery_text = ("заряжается" if info.get("charging")
                            else (f"{battery}%" if battery is not None else "—"))
            self.info.setText(
                f"Прошивка: {info.get('firmware') or '—'} · "
                f"MAC: {info.get('mac') or '—'}")
            self.battery.setText(f"Батарея: {battery_text}")
        else:
            set_pill(self.connection_pill, "Не подключён", "muted")
            self.info.setText(
                "Сейчас T4 Nova Pro не выбран. Подключите Super Nova через "
                "донгл 2.4 ГГц и нажмите «Прочитать».")
            self.battery.setText("")

        self._loading = True
        try:
            if active:
                remaps = config.get("remaps") or {}
                for name, combo in self.remap_combos.items():
                    target = remaps.get(name, name)
                    index = combo.findData(target)
                    combo.setCurrentIndex(max(0, index))
                self.stick_left.set_value(
                    (config.get("stick_left") or {}).get("deadzone_min", 5))
                self.stick_right.set_value(
                    (config.get("stick_right") or {}).get("deadzone_min", 5))
                self.trigger_left.set_value(
                    (config.get("trigger_left") or {}).get("deadzone_min", 5))
                self.trigger_right.set_value(
                    (config.get("trigger_right") or {}).get("deadzone_min", 5))
                vib = config.get("vibration") or {}
                self.vib_left.set_value(vib.get("left", 75))
                self.vib_right.set_value(vib.get("right", 75))
        finally:
            self._loading = False
        for card in self._editor_cards:
            card.setEnabled(active)
        self._busy_changed(self.state.busy)

    # -- edits ------------------------------------------------------------
    def _save_remap(self, source: str):
        if self._loading or self.state.device_kind != "supernova":
            return
        config = self._config()
        if config is None:
            return
        combo = self.remap_combos[source]
        target = combo.currentData()
        remaps = config.setdefault("remaps", {})
        if target == source:
            remaps.pop(source, None)
        else:
            remaps[source] = target
        self.state.touch()

    def _save_deadzones(self, *_args):
        if self._loading or self.state.device_kind != "supernova":
            return
        config = self._config()
        if config is None:
            return
        config.setdefault("stick_left", {})["deadzone_min"] = self.stick_left.value()
        config.setdefault("stick_right", {})["deadzone_min"] = self.stick_right.value()
        config.setdefault("trigger_left", {})["deadzone_min"] = self.trigger_left.value()
        config.setdefault("trigger_right", {})["deadzone_min"] = self.trigger_right.value()
        self.state.touch()

    def _save_vibration(self, *_args):
        if self._loading or self.state.device_kind != "supernova":
            return
        config = self._config()
        if config is None:
            return
        config.setdefault("vibration", {})["left"] = self.vib_left.value()
        config.setdefault("vibration", {})["right"] = self.vib_right.value()
        self.state.touch()

    def _test_vibration(self):
        if not self.state.device_present or self.state.device_kind != "supernova":
            return
        left, right = self.vib_left.value(), self.vib_right.value()

        def job(progress):
            progress("Тест вибрации Super Nova…")
            with HidrawDevice() as dev:
                snmod.vibrate_test(dev, left, right)

        self.app.run_task("Тест вибрации", job,
                          lambda _result: self.app.log(
                              f"Super Nova: тест вибрации L={left} R={right}."))

    def _busy_changed(self, busy: bool):
        active = (self.state.device_kind == "supernova"
                  and self.state.device_present
                  and not self.state.access_error)
        self.read_button.setEnabled(not busy)
        self.test_button.setEnabled(active and not busy)
        self.apply_button.setEnabled(active and not busy
                                     and bool(self.state.dirty_supernova_sections()))
        for card in self._editor_cards:
            card.setEnabled(active and not busy)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
