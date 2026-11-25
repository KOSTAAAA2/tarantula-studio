"""Mouse & DPI page: experimental DPI range and motion measurement."""
from __future__ import annotations

import copy
import math
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
    QVBoxLayout,
)

from ...core import boost
from ...core import device as devmod
from ...core import mouse
from ...core.transport import HidrawDevice
from ..labels import STICK_MODE_LABELS
from ..widgets import (
    Card, Page, SliderRow, info_label, make_button, muted, note, set_pill,
)


class MouseDPIPage(Page):
    TITLE = "Мышь и DPI"
    SUBTITLE = "Режим мыши, чувствительность 0–255 и проверка движения"

    def __init__(self, app):
        super().__init__(app)
        self._loading = False
        self._syncing = False
        self._monitor = None
        self._measure_started = 0.0
        self._measure_timer = QTimer(self)
        self._measure_timer.setInterval(120)
        self._measure_timer.timeout.connect(self._measure_tick)
        self._boost_timer = QTimer(self)
        self._boost_timer.setInterval(500)
        self._boost_timer.timeout.connect(self._poll_boost)
        self._build()
        self.state.configReplaced.connect(self.refresh)
        self.state.deviceChanged.connect(self._scan_nodes)
        self.state.busyChanged.connect(self._busy_changed)

    def _build(self):
        self.add(note(
            "Экспериментально: поле DPI в прошивке однобайтовое, поэтому приложение "
            "разрешает 0–255. Официальная утилита ограничивает значение 100. После "
            "записи обязательно проверьте обратное чтение: если контроллер вернул 100, "
            "прошивка ограничивает DPI."
        ))

        cols = QHBoxLayout()
        cols.setSpacing(16)
        cols.addWidget(self._config_card(), 2)
        cols.addWidget(self._measure_card(), 3)
        self.add_layout(cols)
        self.add(self._boost_card())

        card = Card("Как проверить, что DPI выше 100 работает")
        card.add(info_label(
            "1. Выберите стик и включите режим «Мышь (HID)».\n"
            "2. Запишите DPI 50, подвиньте стик и запомните счётчики dx/dy.\n"
            "3. Запишите 100, 150 и 255, повторяя движение с той же амплитудой.\n"
            "4. Если счётчики растут пропорционально, значение действует. Если после "
            "100 они не меняются или обратное чтение показывает 100 — прошивка "
            "ограничивает диапазон, и для большего DPI нужен программный слой."
        ))
        card.add(muted(
            "Счётчики REL_X/REL_Y зависят от скорости и амплитуды движения. Для "
            "сравнения делайте одинаковый медленный полный круг стиком."
        ))
        self.add(card)
        self.add_stretch()

    # -- config -----------------------------------------------------------
    def _config_card(self) -> Card:
        card = Card("Режим мыши")
        self.side_combo = QComboBox()
        self.side_combo.addItem("Правый стик (RS)", 1)
        self.side_combo.addItem("Левый стик (LS)", 0)
        self.side_combo.currentIndexChanged.connect(self._load)
        row = card.row()
        row.addWidget(QLabel("Стик"))
        row.addWidget(self.side_combo, 1)
        self.mode_label = QLabel()
        set_pill(self.mode_label, "—", "muted")
        row.addWidget(self.mode_label)

        row = card.row()
        row.addWidget(QLabel("Режим"))
        self.mode = QComboBox()
        for value, label in STICK_MODE_LABELS.items():
            self.mode.addItem(label, value)
        self.mode.currentIndexChanged.connect(self._save)
        row.addWidget(self.mode, 1)

        self.dpi_x = SliderRow("DPI по X", 0, 255, 100, label_width=110)
        self.dpi_y = SliderRow("DPI по Y", 0, 255, 100, label_width=110)
        self.dpi_x.valueChanged.connect(self._dpi_x_changed)
        self.dpi_y.valueChanged.connect(self._dpi_y_changed)
        card.add(self.dpi_x)
        card.add(self.dpi_y)
        self.sync = QCheckBox("Одинаковый DPI по X и Y")
        self.sync.setChecked(True)
        self.sync.toggled.connect(self._sync_toggled)
        card.add(self.sync)
        self.dpi_note = note("Значение выше 100 записывается как есть, но прошивка "
                             "может его ограничить. Проверьте обратное чтение.")
        self.dpi_note.hide()
        card.add(self.dpi_note)

        self.invert_x = QCheckBox("Инвертировать движение мыши по X")
        self.invert_y = QCheckBox("Инвертировать движение мыши по Y")
        self.invert_x.toggled.connect(self._save)
        self.invert_y.toggled.connect(self._save)
        card.add(self.invert_x)
        card.add(self.invert_y)

        self.overlap = SliderRow("Угол перекрытия", 0, 100, 40, "%", 140)
        self.overlap.valueChanged.connect(self._save)
        card.add(self.overlap)

        self.readback = muted("Обратное чтение: —")
        card.add(self.readback)

        row = card.row()
        self.write_button = make_button("Записать стик сейчас", primary=True)
        self.write_button.setToolTip("Пишет режим, DPI, инверсию и кривую выбранного стика")
        self.write_button.clicked.connect(self._write_now)
        row.addWidget(self.write_button)
        apply_btn = make_button("Применить раздел")
        apply_btn.clicked.connect(lambda: self.app.apply_changes(["sticks"]))
        row.addWidget(apply_btn)
        row.addStretch(1)
        return card

    # -- measurement ------------------------------------------------------
    def _measure_card(self) -> Card:
        card = Card("Измерение движения мыши")
        self.nodes_label = muted("Поиск интерфейса мыши…")
        card.add(self.nodes_label)
        counter = QGridLayout()
        self.counter_labels = {}
        for index, (key, title) in enumerate((
                ("dx", "Сумма REL_X"), ("dy", "Сумма REL_Y"),
                ("events", "Событий"), ("wheel", "Колесо"))):
            label = QLabel(title)
            label.setObjectName("Muted")
            value = QLabel("0")
            value.setObjectName("Big")
            counter.addWidget(label, 0 if index < 2 else 2, (index % 2) * 2)
            counter.addWidget(value, 1 if index < 2 else 3, (index % 2) * 2)
            self.counter_labels[key] = value
        card.add_layout(counter)
        self.measure_status = muted("Монитор остановлен")
        card.add(self.measure_status)
        self.measure_button = make_button("Начать измерение", primary=True)
        self.measure_button.clicked.connect(self._toggle_measure)
        card.add(self.measure_button)
        self.reset_button = make_button("Сбросить счётчики")
        self.reset_button.clicked.connect(self._reset_counters)
        card.add(self.reset_button)
        card.add(muted(
            "Монитор читает /dev/input/event* интерфейса мыши контроллера. "
            "Для доступа к input-устройствам может понадобиться udev-правило "
            "с TAG+=\"uaccess\" (есть на странице диагностики)."
        ))
        return card

    # -- software boost ---------------------------------------------------
    def _boost_card(self) -> Card:
        card = Card("Программное усиление DPI (выше 255)")
        card.add(note(
            "Прошивка хранит чувствительность в одном байте, поэтому больше "
            "255 из контроллера не выжать. Усиление перехватывает движение "
            "мыши контроллера и умножает его через виртуальную мышь uinput. "
            "Работает, пока открыт Tarantula Studio или запущен "
            "`tarantula-studio boost`."
        ))
        row = card.row()
        row.addWidget(QLabel("Интерфейс мыши"))
        self.boost_node = QComboBox()
        row.addWidget(self.boost_node, 1)
        row = card.row()
        row.addWidget(QLabel("Цель"))
        target_1000 = make_button("≈1000")
        target_1000.clicked.connect(lambda: self._set_boost_target(1000))
        row.addWidget(target_1000)
        target_2000 = make_button("≈2000")
        target_2000.clicked.connect(lambda: self._set_boost_target(2000))
        row.addWidget(target_2000)
        self.boost_target_label = muted("")
        row.addWidget(self.boost_target_label, 1)
        self.boost_factor = SliderRow("Множитель", 1, 10, 4, "×", 130)
        self.boost_factor.valueChanged.connect(self._boost_factor_changed)
        card.add(self.boost_factor)
        self.boost_effective = info_label("Эффективный DPI: —")
        card.add(self.boost_effective)
        self.boost_enable = QCheckBox("Включить программное усиление")
        self.boost_enable.toggled.connect(self._toggle_boost)
        card.add(self.boost_enable)
        self.boost_status = muted("Усиление выключено")
        card.add(self.boost_status)
        card.add(muted(
            "Нужны права на /dev/input/event* и /dev/uinput. Правило udev на "
            "странице «Диагностика» выдаёт их активному пользователю. "
            "Во время усиления обычное измерение движения недоступно: "
            "устройство захвачено (EVIOCGRAB), чтобы не было двойного ввода."))
        return card

    def _set_boost_target(self, target: int):
        dpi = max(1, self.dpi_x.value())
        factor = max(1, min(10, math.ceil(target / dpi)))
        self.boost_factor.set_value(factor)
        self._update_boost_labels()

    def _boost_factor_changed(self, _value):
        if self.app.mouse_booster is not None:
            self.app.mouse_booster.set_factor(self.boost_factor.value())
        self._update_boost_labels()

    def _update_boost_labels(self):
        dpi = self.dpi_x.value()
        factor = self.boost_factor.value()
        self.boost_effective.setText(
            f"Эффективный DPI: {dpi} × {factor} = {dpi * factor}")
        if dpi * factor < 1000:
            self.boost_target_label.setText(
                "Для 1000+ поднимите DPI прошивки или множитель")
        else:
            self.boost_target_label.setText(
                f"Цель ≈1000: ×{max(1, math.ceil(1000 / max(1, dpi)))} · "
                f"≈2000: ×{max(1, math.ceil(2000 / max(1, dpi)))}")

    def _toggle_boost(self, enabled: bool):
        if not enabled:
            self._stop_boost()
            return
        if self.state.device_kind == "supernova":
            self.boost_enable.setChecked(False)
            QMessageBox.information(
                self, "Super Nova",
                "У Super Nova нет проверенного режима мыши/DPI, поэтому "
                "программное усиление для него недоступно.")
            return
        if self._monitor is not None:
            self._stop_measure()
        node_path = self.boost_node.currentData()
        booster = boost.MouseBooster(node=node_path or None,
                                     factor=self.boost_factor.value())
        try:
            booster.start()
        except boost.MouseBoostError as exc:
            self.boost_enable.setChecked(False)
            self.app.log(f"Усиление DPI не запущено: {exc}", "error")
            QMessageBox.warning(self, "Усиление DPI", str(exc))
            return
        self.app.mouse_booster = booster
        self._boost_timer.start()
        self.boost_status.setText(
            f"Усиление включено: {booster.node.path if booster.node else '?'} "
            f"×{booster.factor:g}")
        self.app.log(f"Программное усиление DPI включено: "
                     f"{booster.node.path if booster.node else '?'} "
                     f"×{booster.factor:g}.")
        self._sync_measure_availability()

    def _stop_boost(self):
        booster = self.app.mouse_booster
        self._boost_timer.stop()
        if booster is not None:
            try:
                booster.stop()
            except Exception as exc:
                self.app.log(f"Остановка усиления DPI: {exc}", "warning")
            self.app.mouse_booster = None
            self.app.log("Программное усиление DPI выключено.")
        self.boost_status.setText("Усиление выключено")
        self._sync_measure_availability()

    def _poll_boost(self):
        booster = self.app.mouse_booster
        if booster is None:
            self._boost_timer.stop()
            return
        status = booster.status()
        if not status["running"]:
            self._boost_timer.stop()
            self.app.mouse_booster = None
            self.boost_enable.setChecked(False)
            text = status.get("last_error") or "поток завершился"
            self.boost_status.setText(f"Усиление остановлено: {text}")
            if status.get("last_error"):
                self.app.log(f"Усиление DPI: {text}", "error")
            self._sync_measure_availability()
            return
        self.boost_status.setText(
            f"Усиление: ×{status['factor']:g} · событий {status['events']} · "
            f"{status['uptime']:.0f} с")

    def _sync_measure_availability(self):
        has_nodes = self.boost_node.count() > 0
        blocked = self.app.mouse_booster is not None
        allowed = self.state.device_kind != "supernova"
        self.measure_button.setEnabled(has_nodes and not blocked and allowed)

    # -- state ------------------------------------------------------------
    def _stick(self) -> dict:
        side = int(self.side_combo.currentData() or 1)
        return self.state.staged["stick_right" if side else "stick_left"]

    def _load(self):
        self._loading = True
        stick = self._stick()
        index = self.mode.findData(stick.get("mode", "native"))
        self.mode.setCurrentIndex(max(0, index))
        self.dpi_x.set_value(stick.get("mouse_dpi", 50))
        self.dpi_y.set_value(stick.get("mouse_dpi_y", stick.get("mouse_dpi", 50)))
        self.sync.setChecked(self.dpi_x.value() == self.dpi_y.value())
        self.invert_x.setChecked(bool(stick.get("mouse_invert_x", stick.get("invert_x", False))))
        self.invert_y.setChecked(bool(stick.get("mouse_invert_y", stick.get("invert_y", False))))
        self.overlap.set_value(stick.get("overlap_percent", 40))
        self._update_pill()
        self._dpi_note()
        self._loading = False
        self._update_readback(stick, None)

    def _update_pill(self):
        mode = self.mode.currentData()
        if mode == "mouse":
            set_pill(self.mode_label, "Мышь", "ok")
        else:
            set_pill(self.mode_label, STICK_MODE_LABELS.get(mode, mode), "muted")

    def _save(self, *_args):
        if self._loading:
            return
        stick = self._stick()
        stick["mode"] = self.mode.currentData() or "native"
        stick["mouse_dpi"] = self.dpi_x.value()
        stick["mouse_dpi_y"] = self.dpi_y.value()
        stick["mouse_invert_x"] = self.invert_x.isChecked()
        stick["mouse_invert_y"] = self.invert_y.isChecked()
        stick["overlap_percent"] = self.overlap.value()
        self._update_pill()
        self._dpi_note()
        self._update_readback(stick, None)
        self.state.touch()

    def _dpi_x_changed(self, value):
        if self._loading:
            return
        if self.sync.isChecked() and not self._syncing:
            self._syncing = True
            self.dpi_y.set_value(value)
            self._syncing = False
        self._save()

    def _dpi_y_changed(self, value):
        if self._loading:
            return
        if self.sync.isChecked() and not self._syncing:
            self._syncing = True
            self.dpi_x.set_value(value)
            self._syncing = False
        self._save()

    def _sync_toggled(self, enabled):
        if enabled and not self._loading:
            self._syncing = True
            self.dpi_y.set_value(self.dpi_x.value())
            self._syncing = False
            self._save()

    def _dpi_note(self):
        self.dpi_note.setVisible(self.dpi_x.value() > 100 or self.dpi_y.value() > 100)

    def _update_readback(self, stick, actual):
        source = actual if actual is not None else stick
        self.readback.setText(
            f"В профиле: mode={STICK_MODE_LABELS.get(source.get('mode'), source.get('mode'))} · "
            f"DPI X={source.get('mouse_dpi')} Y={source.get('mouse_dpi_y', source.get('mouse_dpi'))}"
        )

    # -- direct write -----------------------------------------------------
    def _write_now(self):
        if not self.state.device_present or self.state.device_kind == "supernova":
            return
        side = int(self.side_combo.currentData() or 1)
        stick = copy.deepcopy(self._stick())

        def job(progress):
            progress("Запись параметров стика…")
            with HidrawDevice() as dev:
                actual = devmod.write_stick_now(dev, side, stick)
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
            self._load()
            self._update_readback(actual, actual)
            self.app.log(
                f"Стик записан: mode={actual.get('mode')} DPI X={actual.get('mouse_dpi')} "
                f"Y={actual.get('mouse_dpi_y')}."
            )
            requested = stick.get("mouse_dpi")
            if requested and actual.get("mouse_dpi") != requested:
                self.app.show_warnings(
                    "Прошивка изменила DPI",
                    [f"Запрошено: {requested}",
                     f"Прочитано X: {actual.get('mouse_dpi')}",
                     f"Прочитано Y: {actual.get('mouse_dpi_y')}",
                     "Значения выше 100 могут ограничиваться прошивкой."],
                )

        self.app.run_task("Запись стика", job, done)

    # -- measurement ------------------------------------------------------
    def _scan_nodes(self):
        nodes = mouse.find_mouse_nodes()
        previous = self.boost_node.currentData()
        self.boost_node.blockSignals(True)
        self.boost_node.clear()
        for node in nodes:
            self.boost_node.addItem(node.describe(), node.path)
        index = self.boost_node.findData(previous) if previous else -1
        if index >= 0:
            self.boost_node.setCurrentIndex(index)
        self.boost_node.blockSignals(False)
        if nodes:
            self.nodes_label.setText("Интерфейсы мыши:\n" +
                                     "\n".join(node.describe() for node in nodes))
            self.measure_button.setEnabled(True)
        else:
            self.nodes_label.setText(
                "Интерфейс мыши не найден. Подключите контроллер в режиме PC/XInput "
                "и проверьте права на /dev/input/event*."
            )
            self.measure_button.setEnabled(False)
            if self._monitor:
                self._stop_measure()
        self._sync_measure_availability()
        self._update_boost_labels()

    def _toggle_measure(self):
        if self._monitor:
            self._stop_measure()
        else:
            self._start_measure()

    def _start_measure(self):
        if self.app.mouse_booster is not None:
            self.measure_status.setText(
                "Сначала выключите программное усиление: узел мыши захвачен.")
            return
        monitor = mouse.MouseMotionMonitor()
        if not monitor.available:
            self.measure_status.setText("Нет доступных узлов мыши.")
            return
        monitor.start()
        self._monitor = monitor
        self._measure_started = time.monotonic()
        self._measure_timer.start()
        self.measure_button.setText("Остановить измерение")
        self.measure_status.setText("Измерение… двигайте стик в режиме мыши.")
        if monitor.errors:
            self.measure_status.setText("Ошибки: " + "; ".join(monitor.errors))

    def _stop_measure(self):
        self._measure_timer.stop()
        if self._monitor:
            self._monitor.stop()
            self._monitor = None
        self.measure_button.setText("Начать измерение")
        self.measure_status.setText("Монитор остановлен")

    def _measure_tick(self):
        if not self._monitor:
            return
        dx, dy, events = self._monitor.snapshot()
        self.counter_labels["dx"].setText(str(dx))
        self.counter_labels["dy"].setText(str(dy))
        self.counter_labels["events"].setText(str(events))
        self.counter_labels["wheel"].setText(str(self._monitor.wheel))
        elapsed = time.monotonic() - self._measure_started
        self.measure_status.setText(f"Измерение… {elapsed:.1f} с")

    def _reset_counters(self):
        if self._monitor:
            self._stop_measure()
        for label in self.counter_labels.values():
            label.setText("0")

    def _busy_changed(self, busy):
        self.write_button.setEnabled(not busy and self.state.device_present
                                     and not self.state.access_error)
        self.boost_enable.setEnabled(not busy
                                     and self.state.device_kind != "supernova")

    def refresh(self):
        self._scan_nodes()
        self._load()
        self._busy_changed(self.state.busy)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def hideEvent(self, event):
        self._stop_measure()
        super().hideEvent(event)
