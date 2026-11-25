"""Local configuration, named profiles and backups."""
from __future__ import annotations

import copy
import json
import os
import re
from datetime import datetime
from pathlib import Path

from .defaults import deep_merge_defaults, factory_defaults

APP_DIR = Path(os.environ.get("TARANTULA_STUDIO_CONFIG", Path.home() / ".config" / "tarantula-studio"))
CONFIG_FILE = APP_DIR / "config.json"
PROFILES_DIR = APP_DIR / "profiles"
BACKUPS_DIR = APP_DIR / "backups"
SUPERNOVA_BACKUPS_DIR = APP_DIR / "supernova-backups"
ACTIVE_PROFILE_FILE = APP_DIR / "active_profile"

_NAME_RE = re.compile(r"^[\w][\w \-().]{0,63}$", re.UNICODE)


def ensure_dirs():
    for path in (APP_DIR, PROFILES_DIR, BACKUPS_DIR, SUPERNOVA_BACKUPS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    ensure_dirs()
    if not CONFIG_FILE.exists():
        config = factory_defaults()
        save_config(config)
        return config
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("config root is not an object")
        return deep_merge_defaults(data)
    except Exception:
        broken = CONFIG_FILE.with_suffix(".broken.json")
        try:
            CONFIG_FILE.replace(broken)
        except OSError:
            pass
        config = factory_defaults()
        save_config(config)
        return config


def save_config(config: dict):
    ensure_dirs()
    tmp = CONFIG_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2, ensure_ascii=False)
    tmp.replace(CONFIG_FILE)


def sanitize_profile_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("Profile name is required")
    if not _NAME_RE.match(name):
        raise ValueError("Profile name: letters, digits, spaces, - _ ( ) . only, max 64")
    return name


def _profile_path(name: str) -> Path:
    return PROFILES_DIR / f"{sanitize_profile_name(name)}.json"


def list_profiles() -> list[dict]:
    ensure_dirs()
    active = get_active_profile()
    result = []
    for path in sorted(PROFILES_DIR.glob("*.json")):
        name = path.stem
        try:
            mtime = path.stat().st_mtime
            updated = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            updated = ""
        result.append({"name": name, "updated": updated, "active": name == active})
    return result


def save_profile(name: str, config: dict | None = None, make_active: bool = True):
    ensure_dirs()
    name = sanitize_profile_name(name)
    config = copy.deepcopy(config if config is not None else load_config())
    payload = {"name": name, "saved_at": datetime.now().isoformat(timespec="seconds"),
               "config": config}
    path = _profile_path(name)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    tmp.replace(path)
    if make_active:
        set_active_profile(name)
    return name


def load_profile(name: str) -> dict:
    path = _profile_path(name)
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {name}")
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict) and isinstance(data.get("config"), dict):
        return deep_merge_defaults(data["config"])
    if isinstance(data, dict):
        return deep_merge_defaults(data)
    raise ValueError(f"Invalid profile: {name}")


def delete_profile(name: str):
    path = _profile_path(name)
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {name}")
    path.unlink()
    if get_active_profile() == name:
        set_active_profile(None)


def get_active_profile() -> str | None:
    try:
        value = ACTIVE_PROFILE_FILE.read_text(encoding="utf-8").strip()
        return value or None
    except OSError:
        return None


def set_active_profile(name: str | None):
    ensure_dirs()
    if not name:
        try:
            ACTIVE_PROFILE_FILE.unlink()
        except OSError:
            pass
        return
    ACTIVE_PROFILE_FILE.write_text(sanitize_profile_name(name), encoding="utf-8")


def backup_config(config: dict, label: str = "backup") -> Path:
    """Write a JSON snapshot; returns the file path."""
    ensure_dirs()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    safe_label = re.sub(r"[^\w.-]+", "-", label).strip("-") or "backup"
    path = BACKUPS_DIR / f"{stamp}-{safe_label}.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump({"saved_at": datetime.now().isoformat(timespec="seconds"),
                   "label": label, "config": config}, fh, indent=2, ensure_ascii=False)
    return path


def backup_supernova(config: dict, label: str = "supernova") -> Path:
    """Snapshot Super Nova settings in their own directory.

    The T3 Pro profile/backup pages must never try to restore one of these as
    a Tarantula config, so they are kept separate.
    """
    ensure_dirs()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    safe_label = re.sub(r"[^\w.-]+", "-", label).strip("-") or "supernova"
    path = SUPERNOVA_BACKUPS_DIR / f"{stamp}-{safe_label}.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump({"saved_at": datetime.now().isoformat(timespec="seconds"),
                   "label": label, "kind": "supernova", "config": config},
                  fh, indent=2, ensure_ascii=False)
    return path


def list_backups() -> list[dict]:
    ensure_dirs()
    out = []
    for path in sorted(BACKUPS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            label = data.get("label", "")
            saved = data.get("saved_at", "")
        except Exception:
            label, saved = "", ""
        out.append({"path": str(path), "name": path.name, "label": label, "saved_at": saved})
    return out


def load_backup(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    config = data.get("config", data)
    if not isinstance(config, dict):
        raise ValueError("Invalid backup")
    return deep_merge_defaults(config)


def delete_backup(path: str | Path):
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Backup not found: {target}")
    target.unlink()
