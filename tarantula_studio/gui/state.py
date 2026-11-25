"""Application state and background work."""
from __future__ import annotations

import copy
import traceback

from PySide6.QtCore import QObject, QThread, Signal

from ..core import config as cfg
from ..core import supernova as snmod
from ..core.defaults import SECTION_KEYS, deep_merge_defaults, section_changed


class Worker(QThread):
    """Run one blocking device operation without freezing the GUI."""

    progressed = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            result = self.fn(self.progressed.emit)
        except Exception as exc:  # noqa: BLE001 - the message is shown to the user
            traceback.print_exc()
            self.failed.emit(str(exc) or exc.__class__.__name__)
        else:
            self.succeeded.emit(result)


class AppState(QObject):
    changed = Signal()
    configReplaced = Signal()
    deviceChanged = Signal()
    busyChanged = Signal(bool)
    statusMessage = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.staged = cfg.load_config()
        self.baseline = copy.deepcopy(self.staged)
        self.supernova: dict | None = None
        self.supernova_baseline: dict | None = None
        self.device_kind = "none"  # none / tarantula / supernova
        self.info: dict = {}
        self.device_present = False
        self.device_path = ""
        self.access_error = ""
        self.demo = True
        self.config_source = "Локальная копия"
        self.busy = False

    # -- dirty tracking ---------------------------------------------------
    def dirty_sections(self) -> list[str]:
        return [name for name in SECTION_KEYS
                if name != "advanced" and section_changed(self.baseline, self.staged, name)]

    def section_dirty(self, section: str) -> bool:
        if section == "advanced":
            return False
        return section_changed(self.baseline, self.staged, section)

    def touch(self):
        self.changed.emit()

    def save(self):
        try:
            cfg.save_config(self.staged)
        except OSError as exc:
            self.statusMessage.emit(f"Не удалось сохранить локальную копию: {exc}", "error")

    # -- replacement ------------------------------------------------------
    def replace_staged(self, config: dict, source: str | None = None):
        self.staged = deep_merge_defaults(copy.deepcopy(config))
        if source:
            self.config_source = source
        self.save()
        self.configReplaced.emit()
        self.changed.emit()

    def set_device_config(self, config: dict, info: dict | None = None):
        config = deep_merge_defaults(copy.deepcopy(config))
        self.staged = config
        self.baseline = copy.deepcopy(config)
        self.device_kind = "tarantula"
        self.supernova = None
        self.supernova_baseline = None
        self.info = info or {}
        self.device_present = True
        self.demo = False
        self.access_error = ""
        self.config_source = "Контроллер"
        self.save()
        self.deviceChanged.emit()
        self.configReplaced.emit()
        self.changed.emit()

    # -- Super Nova -------------------------------------------------------
    def set_supernova_config(self, config: dict, info: dict | None = None):
        config = copy.deepcopy(config)
        self.device_kind = "supernova"
        self.supernova = config
        self.supernova_baseline = copy.deepcopy(config)
        self.info = dict(info or config.get("info") or {})
        self.info.setdefault("product", snmod.PRODUCT)
        self.device_present = True
        self.demo = False
        self.access_error = ""
        self.config_source = "Super Nova"
        self.deviceChanged.emit()
        self.configReplaced.emit()
        self.changed.emit()

    def mark_supernova_applied(self, config: dict | None = None):
        if config is not None:
            self.supernova = copy.deepcopy(config)
        if self.supernova is not None:
            self.supernova_baseline = copy.deepcopy(self.supernova)
        self.changed.emit()

    def reset_supernova(self):
        if self.supernova_baseline is not None:
            self.supernova = copy.deepcopy(self.supernova_baseline)
        self.configReplaced.emit()
        self.changed.emit()

    def dirty_supernova_sections(self) -> list[str]:
        if self.supernova is None:
            return []
        return snmod.diff_sections(self.supernova_baseline, self.supernova)

    def mark_applied(self, config: dict | None = None):
        if config is not None:
            self.staged = deep_merge_defaults(copy.deepcopy(config))
        self.baseline = copy.deepcopy(self.staged)
        self.save()
        self.changed.emit()

    def reset_all(self):
        self.staged = copy.deepcopy(self.baseline)
        self.save()
        self.configReplaced.emit()
        self.changed.emit()

    def reset_section(self, section: str):
        for key in SECTION_KEYS.get(section, ()):
            self.staged[key] = copy.deepcopy(self.baseline.get(key))
        self.save()
        self.configReplaced.emit()
        self.changed.emit()

    def restore_key(self, key: str):
        if key in self.baseline:
            self.staged[key] = copy.deepcopy(self.baseline[key])
            self.save()
            self.configReplaced.emit()
            self.changed.emit()

    # -- busy -------------------------------------------------------------
    def set_busy(self, value: bool):
        if self.busy != value:
            self.busy = value
            self.busyChanged.emit(value)

    # -- presentation -----------------------------------------------------
    @property
    def status_text(self) -> str:
        if self.busy:
            return "Обмен с контроллером…"
        if self.device_present and not self.access_error:
            return ("Super Nova подключён" if self.device_kind == "supernova"
                    else "Контроллер подключён")
        if self.device_present and self.access_error:
            return "Нет доступа к контроллеру"
        return "Демо-режим — контроллер не найден"

    @property
    def status_level(self) -> str:
        if self.busy:
            return "warn"
        if self.device_present and not self.access_error:
            return "ok"
        if self.device_present:
            return "err"
        return "muted"

    def device_summary(self) -> str:
        info = self.info or {}
        product = info.get("product") or ""
        path = self.device_path or info.get("path") or ""
        bits = [part for part in (product, path) if part]
        return " · ".join(bits) if bits else "Устройство не подключено"

    def log(self, text: str, level: str = "info"):
        self.statusMessage.emit(text, level)
