"""Main window and application entry point."""
from __future__ import annotations

import copy
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import __version__
from ..core import config as cfg
from ..core import device as devmod
from ..core import live
from ..core import supernova as snmod
from ..core.transport import (
    DeviceError, DeviceNotFound, HidrawDevice, PermissionDenied, TransportError,
    find_device,
)
from .pages import (
    ButtonsPage, DashboardPage, DiagnosticsPage, DpadPage, GyroPage,
    LightingPage, MacrosPage, MouseDPIPage, ProfilesPage, SticksPage,
    SuperNovaPage, TriggersPage, VibrationPage,
)
from .state import AppState, Worker
from .theme import apply_theme
from .widgets import make_button, muted, set_pill, show_text_dialog

SECTION_LABELS = {
    "sticks": "стики",
    "triggers": "курки",
    "gyro": "гироскоп",
    "lighting": "подсветка",
    "rumble": "вибрация",
    "dpad": "D-Pad и раскладка",
    "mappings": "кнопки и макросы",
}

SUPERNOVA_SECTION_LABELS = {
    "remaps": "переназначения кнопок",
    "vibration": "вибрация",
    "deadzones": "мёртвые зоны",
}


class MainWindow(QMainWindow):
    def __init__(self, demo=False):
        super().__init__()
        self.demo_forced = bool(demo)
        self.state = AppState()
        self._worker: Worker | None = None
        self._building = True
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(800)
        self._save_timer.timeout.connect(self.state.save)
        self._nav_keys: list[str] = []
        self._nav_items: dict[str, QListWidgetItem] = {}
        self._current_key = "overview"
        self.mouse_booster = None
        self._setup_window()
        self._build()
        self._connect_state()
        self._building = False
        self._update_status()
        self._update_apply_bar()
        self.navigate("overview")
        QTimer.singleShot(250, self._startup)

    # -- construction -----------------------------------------------------
    def _setup_window(self):
        self.setWindowTitle("Tarantula Studio — GameSir T3 Pro / Super Nova")
        self.resize(1280, 880)
        self.setMinimumSize(1020, 700)

    def _build(self):
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._build_header())

        self.stack = QStackedWidget()
        self.pages: dict[str, object] = {}
        page_specs = [
            ("overview", "Обзор", DashboardPage),
            ("supernova", "T4 Nova Pro", SuperNovaPage),
            ("mouse", "Мышь и DPI", MouseDPIPage),
            ("sticks", "Стики", SticksPage),
            ("triggers", "Курки", TriggersPage),
            ("buttons", "Кнопки", ButtonsPage),
            ("macros", "Макросы", MacrosPage),
            ("gyro", "Гироскоп", GyroPage),
            ("lighting", "Подсветка", LightingPage),
            ("vibration", "Вибрация", VibrationPage),
            ("dpad", "D-Pad и раскладка", DpadPage),
            ("profiles", "Профили и копии", ProfilesPage),
            ("diagnostics", "Диагностика", DiagnosticsPage),
        ]
        for key, _label, cls in page_specs:
            page = cls(self)
            self.pages[key] = page
            self.stack.addWidget(page)
        right_layout.addWidget(self.stack, 1)
        right_layout.addWidget(self._build_apply_bar())
        layout.addWidget(right, 1)
        self.statusBar().showMessage("Готово")

        self.read_shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
        self.read_shortcut.activated.connect(lambda: self.read_controller())
        self.apply_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.apply_shortcut.activated.connect(lambda: self.apply_changes())

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(224)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 20, 0, 14)
        layout.setSpacing(8)

        brand = QLabel('TARANTULA <span style="color:#ff6b35">STUDIO</span>')
        brand.setObjectName("Brand")
        brand.setTextFormat(Qt.TextFormat.RichText)
        brand.setContentsMargins(20, 0, 12, 0)
        layout.addWidget(brand)
        sub = QLabel("GameSir T3 Pro · Super Nova / T4 Nova Pro")
        sub.setObjectName("BrandSub")
        sub.setContentsMargins(20, 0, 12, 10)
        layout.addWidget(sub)

        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setFrameShape(QFrame.Shape.NoFrame)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_items = [
            ("overview", "Обзор"),
            ("supernova", "T4 Nova Pro"),
            ("mouse", "Мышь и DPI"),
            ("sticks", "Стики"),
            ("triggers", "Курки"),
            ("buttons", "Кнопки"),
            ("macros", "Макросы"),
            ("gyro", "Гироскоп"),
            ("lighting", "Подсветка"),
            ("vibration", "Вибрация"),
            ("dpad", "D-Pad и раскладка"),
            ("profiles", "Профили и копии"),
            ("diagnostics", "Диагностика"),
        ]
        for key, label in nav_items:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.nav.addItem(item)
            self._nav_keys.append(key)
            self._nav_items[key] = item
        self.nav.currentRowChanged.connect(self._nav_changed)
        layout.addWidget(self.nav, 1)

        self.side_pill = QLabel()
        set_pill(self.side_pill, "Демо-режим", "muted")
        self.side_pill.setContentsMargins(20, 4, 20, 2)
        layout.addWidget(self.side_pill)
        version = QLabel(f"v{__version__} · GPL-3.0")
        version.setObjectName("BrandSub")
        version.setContentsMargins(20, 0, 12, 0)
        layout.addWidget(version)
        return sidebar

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("Header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 16, 24, 14)
        layout.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.page_title = QLabel("Обзор")
        self.page_title.setObjectName("PageTitle")
        self.page_subtitle = QLabel("")
        self.page_subtitle.setObjectName("PageSubtitle")
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_subtitle)
        layout.addLayout(titles, 1)
        self.header_pill = QLabel()
        set_pill(self.header_pill, "Демо-режим", "muted")
        layout.addWidget(self.header_pill)
        read = make_button("Прочитать")
        read.setToolTip("Считать конфигурацию из контроллера (Ctrl+R)")
        read.clicked.connect(lambda: self.read_controller())
        layout.addWidget(read)
        return header

    def _build_apply_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("ApplyBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 10, 24, 10)
        layout.setSpacing(10)
        self.dirty_label = muted("Все изменения применены")
        layout.addWidget(self.dirty_label, 1)
        self.discard_button = make_button("Отменить изменения")
        self.discard_button.clicked.connect(self.discard_changes)
        layout.addWidget(self.discard_button)
        self.apply_button = make_button("Применить", primary=True)
        self.apply_button.setToolTip("Записать изменения в контроллер (Ctrl+Enter)")
        self.apply_button.clicked.connect(lambda: self.apply_changes())
        layout.addWidget(self.apply_button)
        return bar

    def _connect_state(self):
        self.state.changed.connect(self._state_changed)
        self.state.configReplaced.connect(self._config_replaced)
        self.state.deviceChanged.connect(self._device_changed)
        self.state.busyChanged.connect(self._busy_changed)
        self.state.statusMessage.connect(self._log_message)
        self.state.changed.connect(lambda: self._save_timer.start())

    # -- navigation -------------------------------------------------------
    def navigate(self, key: str):
        if key not in self._nav_keys:
            return
        index = self._nav_keys.index(key)
        if self.nav.currentRow() != index:
            self.nav.setCurrentRow(index)
        else:
            self._nav_changed(index)

    def _nav_changed(self, row: int):
        if row < 0 or row >= len(self._nav_keys):
            return
        key = self._nav_keys[row]
        self._current_key = key
        page = self.pages.get(key)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        self.page_title.setText(page.TITLE)
        self.page_subtitle.setText(page.SUBTITLE)
        try:
            page.refresh()
        except Exception as exc:
            self.log(f"Ошибка обновления страницы {key}: {exc}", "error")

    def refresh_pages(self):
        for key, page in self.pages.items():
            try:
                page.refresh()
            except Exception as exc:
                self.log(f"Ошибка обновления страницы {key}: {exc}", "error")

    # -- device operations ------------------------------------------------
    def _startup(self):
        if self.demo_forced:
            self.state.demo = True
            self.state.device_kind = "none"
            self.state.device_present = False
            self.state.access_error = ""
            self.state.device_path = ""
            self._update_device_ui()
            self.state.deviceChanged.emit()
            self.log("Демо-режим: работаем с локальной копией конфигурации.")
            return
        info = find_device()
        if info is None:
            self.state.device_kind = "none"
            self.state.device_present = False
            self.state.access_error = ""
            self.state.device_path = ""
            self.state.demo = True
            self._update_device_ui()
            self.state.deviceChanged.emit()
            self.log("Контроллер не найден. Открыт демо-режим; подключите геймпад "
                     "и нажмите «Прочитать».")
            return
        self.state.device_present = True
        self.state.device_path = info.path
        self.state.demo = False
        if not (info.readable and info.writable):
            self.state.device_kind = "none"
            self.state.access_error = "Нет прав на hidraw"
            self._update_device_ui()
            self.state.deviceChanged.emit()
            self.log(f"Нет доступа к {info.path}. Установите udev-правило на странице "
                     f"«Диагностика».", "error")
            return
        self.state.access_error = ""
        self.state.deviceChanged.emit()
        self.read_controller(silent=True)

    def read_controller(self, silent=False):
        if self.state.busy:
            return
        info = find_device()
        if info is None:
            self.state.device_kind = "none"
            self.state.device_present = False
            self.state.access_error = ""
            self.state.device_path = ""
            self.state.demo = True
            self._update_device_ui()
            self.state.deviceChanged.emit()
            self.log("Контроллер не найден.")
            if not silent:
                QMessageBox.information(
                    self, "Контроллер не найден",
                    "Подключите GameSir Tarantula Pro / T4 Nova Pro через донгл "
                    "2.4 ГГц или по USB в режиме PC/XInput "
                    "(на некоторых прошивках — удерживайте Home + X около 2 секунд) "
                    "и нажмите «Прочитать».")
            return
        self.state.device_present = True
        self.state.device_path = info.path
        self.state.demo = False
        if not (info.readable and info.writable):
            self.state.device_kind = "none"
            self.state.access_error = "Нет прав на hidraw"
            self._update_device_ui()
            self.state.deviceChanged.emit()
            self.log(f"Нет доступа к {info.path}. Нужно udev-правило.", "error")
            if not silent:
                QMessageBox.warning(
                    self, "Нет доступа",
                    f"Нет прав на {info.path}.\n\nОткройте «Диагностика» и установите "
                    f"udev-правило, затем подключите контроллер заново.")
            return
        self.state.access_error = ""
        self.state.deviceChanged.emit()

        def job(progress):
            with HidrawDevice(info) as dev:
                if snmod.probe(dev):
                    progress("Устройство: Super Nova / T4 Nova Pro")
                    config = snmod.read_config(dev, progress=progress)
                    devinfo = dict(config.get("info") or {})
                    devinfo["product"] = snmod.PRODUCT
                    devinfo["path"] = dev.info.path
                    return "supernova", config, devinfo, []
                config, devinfo, warnings = devmod.read_all(dev, progress=progress)
                devinfo = dict(devinfo or {})
                devinfo["product"] = dev.info.product
                devinfo["path"] = dev.info.path
                return "tarantula", config, devinfo, warnings

        def done(payload):
            kind, config, devinfo, warnings = payload
            if kind == "supernova":
                self.state.set_supernova_config(config, devinfo)
                self._update_device_ui()
                self.refresh_pages()
                battery = devinfo.get("battery")
                battery_text = ("заряжается" if devinfo.get("charging")
                                else (f"{battery}%" if battery is not None else "?"))
                self.log(
                    f"Super Nova / T4 Nova Pro: прошивка {devinfo.get('firmware', '?')} · "
                    f"батарея {battery_text} · переназначений "
                    f"{len(config.get('remaps') or {})}.")
                if warnings:
                    for warning in warnings:
                        self.log(warning, "warning")
                    if not silent:
                        self.show_warnings("Чтение завершено с предупреждениями", warnings)
                return
            self.state.set_device_config(config, devinfo)
            self._update_device_ui()
            self.refresh_pages()
            self.log(
                f"Конфигурация считана: {devinfo.get('product', 'T3 Pro')} · "
                f"прошивка {devinfo.get('firmware', '?')} · "
                f"кнопок {len(config.get('key_mappings') or {})} · "
                f"макросов {len(config.get('macro_settings') or {})}."
            )
            if warnings:
                for warning in warnings:
                    self.log(warning, "warning")
                if not silent:
                    self.show_warnings("Чтение завершено с предупреждениями", warnings)

        def failed(message):
            self.state.device_kind = "none"
            self.state.access_error = message
            self._update_device_ui()
            self.state.deviceChanged.emit()
            self.log(f"Ошибка чтения: {message}", "error")
            if not silent:
                QMessageBox.critical(self, "Ошибка чтения", message)

        self.run_task("Чтение конфигурации", job, done, on_error=failed)

    def apply_changes(self, sections: list[str] | None = None):
        if self.state.busy:
            return
        if self.state.device_kind == "supernova":
            self._apply_supernova(sections)
            return
        if not self.state.device_present:
            QMessageBox.information(
                self, "Контроллер не подключён",
                "Изменения сохранены в локальной копии. Подключите контроллер "
                "и нажмите «Прочитать», затем примените изменения.")
            return
        if self.state.access_error:
            QMessageBox.warning(
                self, "Нет доступа",
                "Приложение не может открыть hidraw. Установите udev-правило "
                "на странице «Диагностика».")
            return
        dirty = self.state.dirty_sections()
        if sections is None:
            chosen = dirty
        else:
            chosen = [name for name in sections if name in dirty]
        if not chosen:
            self.log("Нет изменений для применения.")
            return
        labels = ", ".join(SECTION_LABELS.get(name, name) for name in chosen)
        pair = QMessageBox.question(
            self, "Применить изменения",
            f"Записать в контроллер: {labels}?\n\nПеред записью будет создана "
            f"резервная копия текущего состояния.")
        if pair != QMessageBox.StandardButton.Yes:
            return
        staged = copy.deepcopy(self.state.staged)
        baseline = copy.deepcopy(self.state.baseline)

        def job(progress):
            with HidrawDevice() as dev:
                backup_path = cfg.backup_config(baseline, "before-apply")
                progress("Запись параметров…")
                result = devmod.apply_config(
                    dev, staged, previous=baseline, sections=chosen,
                    progress=progress)
                fresh, read_info, read_warnings = None, {}, []
                if result.ok:
                    progress("Повторное чтение…")
                    try:
                        fresh, read_info, read_warnings = devmod.read_all(dev, progress=progress)
                    except TransportError as exc:
                        read_warnings = [f"Повторное чтение не удалось: {exc}"]
                read_info = dict(read_info or {})
                read_info["product"] = dev.info.product
                read_info["path"] = dev.info.path
                return result, fresh, read_info, read_warnings, backup_path

        def done(payload):
            result, fresh, devinfo, read_warnings, backup_path = payload
            if not result.ok:
                lines = list(result.warnings) + list(result.errors)
                lines.append(f"Резервная копия: {backup_path}")
                self.log(f"Применение не завершено: {'; '.join(result.errors)}", "error")
                self.show_warnings("Применение не завершено", lines)
                return
            if fresh is not None:
                self.state.set_device_config(fresh, devinfo)
            else:
                self.state.mark_applied(staged)
            self.state.save()
            self.refresh_pages()
            self.log(f"Применено: {labels}. Резервная копия: {backup_path}")
            warnings = list(result.warnings) + list(read_warnings)
            for warning in warnings:
                self.log(warning, "warning")
            if warnings:
                self.show_warnings("Применено с предупреждениями", warnings)

        self.run_task("Применение конфигурации", job, done)

    def _apply_supernova(self, sections: list[str] | None = None):
        if not self.state.device_present:
            QMessageBox.information(
                self, "Контроллер не подключён",
                "Подключите GameSir Super Nova / T4 Nova Pro через донгл 2.4 ГГц "
                "в режиме PC и нажмите «Прочитать».")
            return
        if self.state.access_error:
            QMessageBox.warning(
                self, "Нет доступа",
                "Приложение не может открыть hidraw. Установите udev-правило "
                "на странице «Диагностика».")
            return
        if not self.state.supernova:
            QMessageBox.information(
                self, "Нет данных Super Nova",
                "Сначала нажмите «Прочитать»: параметры Super Nova ещё не считаны.")
            return
        dirty = self.state.dirty_supernova_sections()
        chosen = [name for name in (sections or dirty) if name in dirty]
        if not chosen:
            self.log("Нет изменений Super Nova для применения.")
            return
        labels = ", ".join(SUPERNOVA_SECTION_LABELS.get(name, name) for name in chosen)
        if QMessageBox.question(
                self, "Применить изменения Super Nova",
                f"Записать в контроллер: {labels}?\n\n"
                f"Перед записью будет создана резервная копия считанных настроек. "
                f"Каждый блок проверяется обратным чтением; при ошибке изменения "
                f"откатываются.") != QMessageBox.StandardButton.Yes:
            return
        staged = copy.deepcopy(self.state.supernova)
        baseline = copy.deepcopy(self.state.supernova_baseline or staged)

        def job(progress):
            with HidrawDevice() as dev:
                if not snmod.probe(dev):
                    raise RuntimeError(
                        "Подключённое устройство не отвечает как Super Nova "
                        "(тип устройства не 3). Запись отменена.")
                backup_path = cfg.backup_supernova(baseline, "before-supernova-apply")
                progress("Запись параметров Super Nova…")
                result = snmod.apply_config(
                    dev, staged, previous=baseline, sections=chosen,
                    progress=progress)
                fresh = None
                read_warnings = []
                if result.ok:
                    progress("Повторное чтение…")
                    try:
                        fresh = snmod.read_config(dev, progress=progress)
                    except Exception as exc:  # noqa: BLE001 - applied anyway
                        read_warnings = [f"Повторное чтение не удалось: {exc}"]
                try:
                    info = snmod.read_info(dev)
                except Exception:  # noqa: BLE001 - info is optional here
                    info = {}
                return result, fresh, info, read_warnings, backup_path

        def done(payload):
            result, fresh, info, read_warnings, backup_path = payload
            if not result.ok:
                lines = list(result.warnings) + list(result.errors)
                lines.append(f"Резервная копия: {backup_path}")
                self.log(f"Super Nova: применение не завершено: "
                         f"{'; '.join(result.errors)}", "error")
                self.show_warnings("Применение Super Nova не завершено", lines)
                return
            if fresh is not None:
                self.state.set_supernova_config(fresh, info)
            else:
                self.state.mark_supernova_applied(staged)
            self._update_device_ui()
            self.refresh_pages()
            self.log(f"Super Nova: применено ({labels}). Копия: {backup_path}")
            warnings = list(result.warnings) + list(read_warnings)
            for warning in warnings:
                self.log(warning, "warning")
            if warnings:
                self.show_warnings("Super Nova: применено с предупреждениями", warnings)

        self.run_task("Применение Super Nova", job, done)

    def backup_now(self, done=None):
        try:
            active = cfg.get_active_profile() or "manual"
            path = cfg.backup_config(self.state.staged, active)
        except OSError as exc:
            QMessageBox.warning(self, "Резервная копия", str(exc))
            return
        self.log(f"Резервная копия создана: {path}")
        self.statusBar().showMessage(f"Резервная копия: {path}", 6000)
        if done:
            done()

    def discard_changes(self):
        if self.state.device_kind == "supernova":
            dirty = self.state.dirty_supernova_sections()
            if not dirty:
                return
            labels = ", ".join(SUPERNOVA_SECTION_LABELS.get(name, name)
                               for name in dirty)
            if QMessageBox.question(
                    self, "Отменить изменения Super Nova",
                    f"Отменить несохранённые изменения ({labels}) и вернуться к "
                    f"состоянию контроллера?") \
                    != QMessageBox.StandardButton.Yes:
                return
            self.state.reset_supernova()
            self.refresh_pages()
            self.log("Изменения Super Nova отменены.")
            return
        dirty = self.state.dirty_sections()
        if not dirty:
            return
        labels = ", ".join(SECTION_LABELS.get(name, name) for name in dirty)
        if QMessageBox.question(
                self, "Отменить изменения",
                f"Отменить несохранённые изменения ({labels}) и вернуться к "
                f"состоянию контроллера/последней копии?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.state.reset_all()
        self.refresh_pages()
        self.log("Изменения отменены.")

    # -- tasks ------------------------------------------------------------
    def run_task(self, title: str, fn, on_done=None, on_error=None):
        if self.state.busy:
            self.log("Дождитесь завершения текущей операции.", "warning")
            return False
        worker = Worker(fn, self)
        self._worker = worker
        self.state.set_busy(True)
        self.statusBar().showMessage(f"{title}…")
        worker.progressed.connect(
            lambda text: self.statusBar().showMessage(f"{title}: {text}"))
        worker.succeeded.connect(
            lambda result: self._task_done(worker, title, result, on_done))
        worker.failed.connect(
            lambda message: self._task_failed(worker, title, message, on_error))
        worker.finished.connect(worker.deleteLater)
        worker.start()
        return True

    def _task_done(self, worker, title, result, on_done):
        self._worker = None
        self.state.set_busy(False)
        if on_done:
            try:
                on_done(result)
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                self.log(f"{title}: ошибка обработки результата: {exc}", "error")
                QMessageBox.critical(self, title, str(exc))
        self.statusBar().showMessage(f"{title}: готово", 5000)

    def _task_failed(self, worker, title, message, on_error):
        self._worker = None
        self.state.set_busy(False)
        self.log(f"{title}: {message}", "error")
        if on_error:
            try:
                on_error(message)
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                QMessageBox.critical(self, title, str(exc))
        else:
            QMessageBox.critical(self, title, message)
        self.statusBar().showMessage(f"{title}: ошибка", 8000)

    # -- state signals ----------------------------------------------------
    def _state_changed(self):
        self._update_apply_bar()
        self._update_status()

    def _config_replaced(self):
        if not self._building:
            self._update_status()

    def _device_changed(self):
        self._update_device_ui()
        self._update_status()

    def _busy_changed(self, busy):
        self._update_apply_bar()
        self._update_status()
        if busy:
            self.statusBar().showMessage("Обмен с контроллером…")

    def _update_status(self):
        set_pill(self.header_pill, self.state.status_text, self.state.status_level)
        set_pill(self.side_pill, self.state.status_text, self.state.status_level)
        self.header_pill.setToolTip(self.state.device_summary())
        self.side_pill.setToolTip(self.state.device_summary())

    def _update_device_ui(self):
        """Show only the pages that make sense for the detected device."""
        sn = self.state.device_kind == "supernova"
        allowed = {"overview", "supernova", "diagnostics"}
        for key, item in self._nav_items.items():
            item.setHidden(sn and key not in allowed)
        if sn and self._current_key not in allowed:
            self.navigate("supernova")

    def _update_apply_bar(self):
        sn = self.state.device_kind == "supernova"
        if sn:
            dirty = self.state.dirty_supernova_sections()
            labels = ", ".join(SUPERNOVA_SECTION_LABELS.get(name, name)
                               for name in dirty)
        else:
            dirty = self.state.dirty_sections()
            labels = ", ".join(SECTION_LABELS.get(name, name) for name in dirty)
        if dirty:
            if self.state.device_present:
                self.dirty_label.setText(f"Изменено: {labels}")
            else:
                self.dirty_label.setText(
                    f"Изменено: {labels} · демо-режим, изменения сохраняются локально")
            self.apply_button.setText(f"Применить ({len(dirty)})")
        else:
            self.dirty_label.setText("Все изменения применены")
            self.apply_button.setText("Применить")
        can_apply = (bool(dirty) and self.state.device_present
                     and not self.state.access_error and not self.state.busy)
        self.apply_button.setEnabled(can_apply)
        self.discard_button.setEnabled(bool(dirty) and not self.state.busy)
        if not self.state.device_present:
            self.apply_button.setToolTip("Подключите контроллер, чтобы применить изменения")
        elif self.state.access_error:
            self.apply_button.setToolTip("Нет доступа к hidraw — откройте «Диагностика»")
        elif not dirty:
            self.apply_button.setToolTip("Нет изменений для записи")
        else:
            self.apply_button.setToolTip("Записать изменения в контроллер (Ctrl+Enter)")

    # -- messages ---------------------------------------------------------
    def log(self, text: str, level: str = "info"):
        self.state.log(text, level)

    def _log_message(self, text: str, level: str):
        self.statusBar().showMessage(text, 6000)

    def show_warnings(self, title: str, warnings: list[str]):
        if not warnings:
            return
        text = "\n".join(f"• {warning}" for warning in warnings)
        show_text_dialog(self, title, text)

    # -- close ------------------------------------------------------------
    def closeEvent(self, event):
        if self.state.busy:
            QMessageBox.information(
                self, "Операция выполняется",
                "Дождитесь завершения обмена с контроллером и закройте окно.")
            event.ignore()
            return
        if self.mouse_booster is not None:
            try:
                self.mouse_booster.stop()
            except Exception:
                traceback.print_exc()
            self.mouse_booster = None
        self.state.save()
        live.close()
        event.accept()


def run(argv=None) -> int:
    argv = list(argv or [])
    demo = "--demo" in argv
    app = QApplication.instance()
    if app is None:
        args = [sys.argv[0]] + [item for item in argv if item != "--demo"]
        app = QApplication(args)
    app.setApplicationName("Tarantula Studio")
    app.setApplicationDisplayName("Tarantula Studio")
    app.setOrganizationName("Tarantula Studio")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("tarantula-studio")
    icon_path = Path(__file__).resolve().parents[1] / "assets" / "tarantula-studio.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    apply_theme(app)
    window = MainWindow(demo=demo)
    window.show()
    return app.exec()
