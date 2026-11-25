"""Profiles, local backups and JSON import/export."""
from __future__ import annotations

import json
from datetime import datetime

from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QVBoxLayout,
)
from PySide6.QtCore import Qt

from ...core import config as cfg
from ..widgets import Card, Page, make_button, muted, note


class ProfilesPage(Page):
    TITLE = "Профили и копии"
    SUBTITLE = "Локальные профили, резервные копии и JSON-обмен"

    def __init__(self, app):
        super().__init__(app)
        self._build()
        self.state.configReplaced.connect(self._update_source)
        self.state.deviceChanged.connect(self._update_source)

    def _build(self):
        self.source_label = muted("Текущий источник: —")
        self.add(self.source_label)

        cols = QHBoxLayout()
        cols.setSpacing(16)
        cols.addWidget(self._profiles_card(), 1)
        cols.addWidget(self._backups_card(), 1)
        self.add_layout(cols)

        card = Card("Импорт и экспорт")
        card.add(muted("Экспорт сохраняет текущее состояние редактора в JSON. Импорт "
                       "загружает JSON в редактор; чтобы записать его в контроллер, "
                       "нажмите «Применить»."))
        row = card.row()
        export = make_button("Экспортировать JSON…")
        export.clicked.connect(self._export)
        row.addWidget(export)
        import_btn = make_button("Импортировать JSON…")
        import_btn.clicked.connect(self._import)
        row.addWidget(import_btn)
        row.addStretch(1)
        self.add(card)
        self.add(note("Перед каждой записью в контроллер приложение автоматически создаёт "
                      "резервную копию. Откат можно сделать, загрузив копию в редактор и "
                      "применив её."))
        self.add_stretch()

    def _profiles_card(self) -> Card:
        card = Card("Профили")
        self.profile_list = QListWidget()
        self.profile_list.setMinimumHeight(260)
        self.profile_list.itemDoubleClicked.connect(lambda _item: self._load_profile())
        card.add(self.profile_list)
        row = card.row()
        save = make_button("Сохранить текущий", primary=True)
        save.clicked.connect(self._save_profile)
        row.addWidget(save)
        load = make_button("Загрузить")
        load.clicked.connect(self._load_profile)
        row.addWidget(load)
        active = make_button("Сделать активным")
        active.clicked.connect(self._activate_profile)
        row.addWidget(active)
        row.addStretch(1)
        row = card.row()
        delete = make_button("Удалить", danger=True)
        delete.clicked.connect(self._delete_profile)
        row.addWidget(delete)
        row.addStretch(1)
        return card

    def _backups_card(self) -> Card:
        card = Card("Резервные копии")
        self.backup_list = QListWidget()
        self.backup_list.setMinimumHeight(260)
        card.add(self.backup_list)
        row = card.row()
        create = make_button("Создать копию", primary=True)
        create.clicked.connect(lambda: self.app.backup_now(self.refresh_lists))
        row.addWidget(create)
        restore = make_button("Загрузить в редактор")
        restore.clicked.connect(self._restore_backup)
        row.addWidget(restore)
        row.addStretch(1)
        row = card.row()
        delete = make_button("Удалить", danger=True)
        delete.clicked.connect(self._delete_backup)
        row.addWidget(delete)
        row.addStretch(1)
        return card

    # -- data -------------------------------------------------------------
    def refresh(self):
        self.refresh_lists()
        self._update_source()

    def refresh_lists(self):
        active = cfg.get_active_profile()
        self.profile_list.clear()
        for profile in cfg.list_profiles():
            suffix = "  ·  активен" if profile["name"] == active else ""
            item = QListWidgetItem(f"{profile['name']}  —  {profile['updated']}{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, profile["name"])
            self.profile_list.addItem(item)
        self.backup_list.clear()
        for backup in cfg.list_backups():
            label = backup.get("label") or "копия"
            saved = backup.get("saved_at") or ""
            item = QListWidgetItem(f"{saved}  ·  {label}  ·  {backup['name']}")
            item.setData(Qt.ItemDataRole.UserRole, backup["path"])
            self.backup_list.addItem(item)

    def _update_source(self, *_args):
        self.source_label.setText(
            f"Текущий источник: {self.state.config_source} · "
            f"профиль: {cfg.get_active_profile() or 'не выбран'}"
        )

    def _selected_profile(self) -> str | None:
        item = self.profile_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected_backup(self) -> str | None:
        item = self.backup_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    # -- profiles ---------------------------------------------------------
    def _save_profile(self):
        name, ok = QInputDialog.getText(self, "Сохранить профиль", "Имя профиля:")
        if not ok or not name.strip():
            return
        try:
            saved = cfg.save_profile(name, self.state.staged, make_active=True)
        except ValueError as exc:
            QMessageBox.warning(self, "Имя профиля", str(exc))
            return
        self.state.config_source = f"Профиль «{saved}»"
        self.state.save()
        self.refresh_lists()
        self._update_source()
        self.app.log(f"Профиль сохранён: {saved}")

    def _load_profile(self):
        name = self._selected_profile()
        if not name:
            return
        try:
            config = cfg.load_profile(name)
        except Exception as exc:
            QMessageBox.warning(self, "Профиль", f"Не удалось загрузить: {exc}")
            return
        self.state.replace_staged(config, f"Профиль «{name}»")
        cfg.set_active_profile(name)
        self.app.refresh_pages()
        self._update_source()
        self.app.log(f"Профиль загружен в редактор: {name}. Нажмите «Применить» "
                     f"для записи в контроллер.")

    def _activate_profile(self):
        name = self._selected_profile()
        if not name:
            return
        cfg.set_active_profile(name)
        self.refresh_lists()
        self._update_source()

    def _delete_profile(self):
        name = self._selected_profile()
        if not name:
            return
        if QMessageBox.question(self, "Удалить профиль",
                                f"Удалить профиль «{name}»?") \
                != QMessageBox.StandardButton.Yes:
            return
        cfg.delete_profile(name)
        self.refresh_lists()
        self._update_source()

    # -- backups ----------------------------------------------------------
    def _restore_backup(self):
        path = self._selected_backup()
        if not path:
            return
        try:
            config = cfg.load_backup(path)
        except Exception as exc:
            QMessageBox.warning(self, "Резервная копия", f"Не удалось прочитать: {exc}")
            return
        self.state.replace_staged(config, "Резервная копия")
        self.app.refresh_pages()
        self._update_source()
        self.app.log("Резервная копия загружена в редактор. Нажмите «Применить».")

    def _delete_backup(self):
        path = self._selected_backup()
        if not path:
            return
        if QMessageBox.question(self, "Удалить копию",
                                "Удалить выбранную резервную копию?") \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            cfg.delete_backup(path)
        except OSError as exc:
            QMessageBox.warning(self, "Резервная копия", str(exc))
            return
        self.refresh_lists()

    # -- import/export ----------------------------------------------------
    def _export(self):
        path, _filter = QFileDialog.getSaveFileName(
            self, "Экспортировать конфигурацию", "tarantula-profile.json",
            "JSON (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        payload = {
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "label": "export",
            "config": self.state.staged,
        }
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
        except OSError as exc:
            QMessageBox.warning(self, "Экспорт", str(exc))
            return
        self.app.log(f"Конфигурация экспортирована: {path}")

    def _import(self):
        path, _filter = QFileDialog.getOpenFileName(
            self, "Импортировать конфигурацию", "", "JSON (*.json)")
        if not path:
            return
        try:
            config = cfg.load_backup(path)
        except Exception as exc:
            QMessageBox.warning(self, "Импорт", f"Не удалось прочитать JSON: {exc}")
            return
        self.state.replace_staged(config, "Импорт JSON")
        self.app.refresh_pages()
        self._update_source()
        self.app.log(f"Конфигурация импортирована: {path}. Нажмите «Применить».")

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
