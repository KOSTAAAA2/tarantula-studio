"""GameSir Super Nova / T4 Nova Pro support over the 2.4 GHz dongle.

The Super Nova shares the ``3537:103e`` dongle identity with the Tarantula
Pro / T3 Pro.  It speaks a different configuration protocol with different
block layouts, so every session must first read ``get_device_info`` and check
that the device type byte is 3 before reading or writing anything else.

Only the four writes that were verified on real hardware from Linux are
implemented here: gamepad-to-gamepad remaps, vibration strength and the start
deadzones of the sticks and triggers.  Curves, anti-deadzone, hair trigger,
lighting, gyro, macros and mouse/DPI are not exposed: their write shapes were
never verified on a Super Nova.

Protocol knowledge adapted from the Deadband project's
``vendors/gamesir/models/supernova`` module (GPL-3.0-or-later), PR #27:
https://github.com/broroeror/gamesir-linux-tools/pull/27

Every write is a read-modify-write of a whole block.  The result is read back
and compared before anything is saved; on any mismatch or failure the original
blocks are restored and ``save_config_page`` is not sent.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable

from .transport import HidrawDevice, TransportError

Progress = Callable[[str], None] | None

PRODUCT = "GameSir Super Nova / T4 Nova Pro"
DEVICE_TYPE_ID = 3

VENDOR_ID = 0x3537
PID_DONGLE = 0x103E
SHARED_PIDS = {PID_DONGLE: "T3 Pro / Super Nova"}

REPORT_OUT = 0x07
REPORT_IN = 0x06

# Requests we are allowed to send.  Anything else is refused by the caller.
GET_INFO = (0x0A, 0x01)
GET_VERSION = (0x84, 0x01)
GET_KEY = (0x05, 0x02)
SET_KEY = (0x05, 0x01)
GET_STICK_CURVE = (0x02, 0x02)
SET_STICK_CURVE = (0x02, 0x01)
GET_TRIGGER = (0x03, 0x02)
SET_TRIGGER = (0x03, 0x01)
GET_VIBRATION = (0x06, 0x02)
SET_VIBRATION = (0x06, 0x01)
SET_VIBRATION_TEST = (0x0A, 0x04)
SAVE = (0x08, 0x03)

# get_device_info body: 03 01 06 <6-byte address> <battery> 00
INFO_BATTERY = 9
INFO_BATTERY_CHARGING = 0xFF

# key_mapping block (16 bytes): 0 page, 1 key, 2 trigger, 3..5 colour,
# 6 source key, 7 toggle, 8 turbo mode, 9 turbo times, 10 mapping type,
# 11 key count, 12..15 target codes.
KEY_SOURCE, KEY_TURBO_TIMES = 6, 9
KEY_TYPE, KEY_COUNT, KEY_CODES = 10, 11, 12
KEY_LEN = 16
KEY_TYPE_VACANT, KEY_TYPE_GAMEPAD = 0, 1
KEY_TURBO_MODE = 8
KEY_TURBO_OFF = 0

# Stick curve block (21 bytes); the 10-point list starts at byte 9:
# begin dz, begin anti-dz, x0,y0, x1,y1, x2,y2, end dz, end anti-dz.
STICK_POINTS = 9
STICK_LEN = 21
# Trigger parameter block (16 bytes); the same list starts at byte 4.
TRIG_POINTS = 4
TRIG_LEN = 16

P_DZ_BEGIN, P_ADZ_BEGIN, P_CURVE_X, P_DZ_END, P_ADZ_END = 0, 1, (2, 4, 6), 8, 9

FACTORY_POINTS = {
    STICK_POINTS: (5, 0, 20, 16, 53, 50, 85, 84, 100, 100),
    TRIG_POINTS: (5, 0, 19, 16, 50, 50, 81, 84, 95, 100),
}
FACTORY_SHAPE_TOLERANCE = 0.05

# Buttons GameSir's app reads on connect and this app can remap.  The names
# are used verbatim in the JSON config and in the UI.
REMAP_SOURCES = (
    ("A", 0x01), ("B", 0x00), ("X", 0x03), ("Y", 0x02),
    ("LB", 0x04), ("LT", 0x05), ("LS", 0x06),
    ("RB", 0x07), ("RT", 0x08), ("RS", 0x09),
    ("D-Pad ↑", 0x0E), ("D-Pad ↓", 0x0F),
    ("D-Pad ←", 0x0C), ("D-Pad →", 0x0D),
    ("L4", 0x24), ("R4", 0x25),
    ("View", 0x0A), ("Menu", 0x0B), ("Capture", 0x2D),
)
# Writes to L4/R4 as a *target* were not verified; keep them out.
REMAP_TARGETS = tuple((name, code) for name, code in REMAP_SOURCES
                      if name not in ("L4", "R4"))
SOURCE_CODES = dict(REMAP_SOURCES)
CODE_NAMES = {code: name for name, code in REMAP_SOURCES}
TARGET_NAMES = tuple(name for name, _code in REMAP_TARGETS)

SECTIONS = ("remaps", "vibration", "deadzones")


class SuperNovaError(RuntimeError):
    pass


@dataclass
class ApplyResult:
    ok: bool = True
    changed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _data(reply: bytes) -> bytes:
    return reply[4:] if len(reply) > 4 else b""


def _get(dev: HidrawDevice, command: tuple[int, int], args: bytes = b"") -> bytes:
    obj, op = command
    return _data(dev.get(obj, op, args=args))


def _get_block(dev: HidrawDevice, command: tuple[int, int], args: bytes,
               length: int) -> bytes:
    """Read one block and trim hidraw's zero padding to its logical length."""
    body = _get(dev, command, args)
    if len(body) < length:
        raise SuperNovaError(
            f"Super Nova вернул {len(body)} байт вместо {length} для "
            f"команды {command[0]:02x}/{command[1]:02x}")
    return body[:length]


def _progress(progress: Progress, text: str):
    if progress:
        progress(text)


def _round_half_up(value: float) -> int:
    return int(value + 0.5)


def _rescaled(x: int, dz_from: int, dz_to: int, end: int) -> int:
    return _round_half_up(dz_to + (x - dz_from) * (end - dz_to) / (end - dz_from))


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------
def probe(dev: HidrawDevice) -> bool:
    """True only when the pad replies to get_device_info with type 3.

    This is the guard that keeps the Tarantula Pro protocol away from a
    Super Nova, because both share dongle PID 103e.
    """
    try:
        body = _get(dev, GET_INFO)
    except TransportError:
        return False
    return bool(body) and body[0] == DEVICE_TYPE_ID


def read_info(dev: HidrawDevice) -> dict:
    body = _get(dev, GET_INFO)
    if not body:
        raise SuperNovaError("Super Nova не ответил на запрос информации об устройстве")
    if body[0] != DEVICE_TYPE_ID:
        raise SuperNovaError(
            f"Устройство сообщает тип {body[0]}, а не Super Nova (3); "
            f"запись и чтение конфигурации отменены")
    battery_raw = body[INFO_BATTERY] if len(body) > INFO_BATTERY else None
    if battery_raw == INFO_BATTERY_CHARGING:
        battery, charging = None, True
    elif battery_raw is not None and battery_raw <= 100:
        battery, charging = battery_raw, False
    else:
        battery, charging = None, False
    fw_major = body[1] if len(body) > 1 else 0
    fw_minor = body[2] if len(body) > 2 else 0
    return {
        "device_type": body[0],
        "product": PRODUCT,
        "firmware": f"{fw_major}.{fw_minor // 10}.{fw_minor % 10}",
        "firmware_bytes": [fw_major, fw_minor],
        "mac": ":".join(f"{body[3 + i]:02x}" for i in range(6) if 3 + i < len(body)),
        "battery": battery,
        "charging": charging,
        "battery_raw": battery_raw,
    }


def _read_key_block(dev: HidrawDevice, source_code: int) -> bytes:
    body = _get_block(dev, GET_KEY, bytes([0, source_code]), KEY_LEN)
    if body[KEY_SOURCE] != source_code:
        raise SuperNovaError(
            f"Блок кнопки 0x{source_code:02x} описывает источник "
            f"0x{body[KEY_SOURCE]:02x}")
    return body


def _read_stick_block(dev: HidrawDevice, side: int) -> bytes:
    body = _get_block(dev, GET_STICK_CURVE, bytes([side, 0]), STICK_LEN)
    if body[0] != side:
        raise SuperNovaError(
            f"Блок стика {side} описывает стик {body[0]}")
    return body


def _read_trigger_block(dev: HidrawDevice, side: int) -> bytes:
    body = _get_block(dev, GET_TRIGGER, bytes([side]), TRIG_LEN)
    if body[0] != side:
        raise SuperNovaError(
            f"Блок курка {side} описывает курок {body[0]}")
    return body


def _read_vibration_block(dev: HidrawDevice) -> bytes:
    return _get_block(dev, GET_VIBRATION, b"", 6)


def read_config(dev: HidrawDevice, progress: Progress = None) -> dict:
    """Read the verified Super Nova settings plus device info.

    Raises SuperNovaError when the pad is not a Super Nova or a block cannot
    be read, so a partial snapshot can never become an apply baseline.
    """
    info = read_info(dev)
    config = config_defaults()
    config["info"] = info

    _progress(progress, "Переназначения кнопок")
    remaps = {}
    for name, code in REMAP_SOURCES:
        body = _read_key_block(dev, code)
        if body[KEY_TYPE] == KEY_TYPE_GAMEPAD and body[KEY_COUNT] >= 1:
            target = CODE_NAMES.get(body[KEY_CODES])
            if target and target != name:
                remaps[name] = target
    config["remaps"] = remaps

    _progress(progress, "Вибрация")
    vibration = _read_vibration_block(dev)
    config["vibration"] = {"left": vibration[0], "right": vibration[1]}

    for side, key in ((0, "stick_left"), (1, "stick_right")):
        _progress(progress, f"Мёртвая зона стика {key}")
        body = _read_stick_block(dev, side)
        config[key] = {
            "deadzone_min": body[STICK_POINTS + P_DZ_BEGIN],
            "deadzone_max": body[STICK_POINTS + P_DZ_END],
        }
    for side, key in ((0, "trigger_left"), (1, "trigger_right")):
        _progress(progress, f"Мёртвая зона курка {key}")
        body = _read_trigger_block(dev, side)
        config[key] = {
            "deadzone_min": body[TRIG_POINTS + P_DZ_BEGIN],
            "deadzone_max": body[TRIG_POINTS + P_DZ_END],
        }
    return config


def config_defaults() -> dict:
    return {
        "version": 1,
        "info": {},
        "remaps": {},
        "vibration": {"left": 75, "right": 75},
        "stick_left": {"deadzone_min": 5, "deadzone_max": 100},
        "stick_right": {"deadzone_min": 5, "deadzone_max": 100},
        "trigger_left": {"deadzone_min": 5, "deadzone_max": 95},
        "trigger_right": {"deadzone_min": 5, "deadzone_max": 95},
    }


def remap_targets(config: dict) -> dict[str, str]:
    """Complete source -> target map; a missing entry means the factory one."""
    values = config.get("remaps") or {}
    return {name: values.get(name, name) for name, _code in REMAP_SOURCES}


def diff_sections(previous: dict | None, config: dict) -> list[str]:
    previous = previous or {}
    changed = []
    if remap_targets(previous) != remap_targets(config):
        changed.append("remaps")
    if (previous.get("vibration") or {}) != (config.get("vibration") or {}):
        changed.append("vibration")
    for key in ("stick_left", "stick_right", "trigger_left", "trigger_right"):
        old = previous.get(key) or {}
        new = config.get(key) or {}
        if old != new:
            changed.append("deadzones")
            break
    return changed


# ---------------------------------------------------------------------------
# Curve helpers (ported from Deadband's supernova protocol module)
# ---------------------------------------------------------------------------
def has_factory_shape(data: bytes, points_at: int) -> bool:
    ref = FACTORY_POINTS.get(points_at)
    if ref is None:
        return False
    pts = data[points_at:points_at + 10]
    if len(pts) < 10:
        return False
    if any(pts[i] != ref[i] for i in (P_ADZ_BEGIN, 3, 5, 7, P_DZ_END, P_ADZ_END)):
        return False
    dz, end = pts[P_DZ_BEGIN], pts[P_DZ_END]
    rdz = ref[P_DZ_BEGIN]
    if dz >= end:
        return False
    return all(
        abs((pts[ix] - dz) / (end - dz) - (ref[ix] - rdz) / (end - rdz))
        <= FACTORY_SHAPE_TOLERANCE
        for ix in P_CURVE_X
    )


def with_begin_deadzone(data: bytes, points_at: int, new_dz: int) -> bytes:
    """Return a curve block with only its start deadzone changed.

    The three curve X coordinates are rescaled the way GameSir's app does,
    using the factory points when the current shape is still factory-like so
    repeated edits do not accumulate rounding.
    """
    out = bytearray(data)
    p = points_at
    old, end = out[p + P_DZ_BEGIN], out[p + P_DZ_END]
    if not 0 <= new_dz < end or old >= end:
        raise SuperNovaError(f"Мёртвая зона {new_dz} должна быть меньше {end}")
    if has_factory_shape(data, p):
        ref = FACTORY_POINTS[p]
        dz_from = ref[P_DZ_BEGIN]
        source_x = {ix: ref[ix] for ix in P_CURVE_X}
    else:
        dz_from = old
        source_x = {ix: data[p + ix] for ix in P_CURVE_X}
    out[p + P_DZ_BEGIN] = new_dz
    for ix in P_CURVE_X:
        out[p + ix] = _rescaled(source_x[ix], dz_from, new_dz, end)
    return bytes(out)


def with_key_target(data: bytes, target_code: int) -> bytes:
    """Return a key-mapping block mapped to one gamepad button."""
    out = bytearray(data)
    own = out[KEY_SOURCE]
    out[KEY_TYPE] = KEY_TYPE_GAMEPAD
    out[KEY_COUNT] = 1
    if target_code == own and out[KEY_TURBO_MODE] == KEY_TURBO_OFF:
        out[KEY_TURBO_TIMES] = 0
    else:
        out[KEY_TURBO_TIMES] = max(out[KEY_TURBO_TIMES], 1)
    out[KEY_CODES:KEY_CODES + 4] = bytes((target_code, 0, 0, 0))
    return bytes(out)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------
def _set(dev: HidrawDevice, command: tuple[int, int], payload: bytes):
    obj, op = command
    dev.set(obj, op, payload)


def _put_back(dev: HidrawDevice, set_command: tuple[int, int],
              get_command: tuple[int, int], args: bytes, original: bytes):
    """Best effort restore after a failed write."""
    try:
        current = _get(dev, get_command, args)
        if current[:len(original)] != original:
            _set(dev, set_command, original)
    except TransportError:
        pass


def _write_verified(dev: HidrawDevice, set_command: tuple[int, int],
                    get_command: tuple[int, int], args: bytes,
                    original: bytes, desired: bytes, label: str,
                    verify: bool) -> bool:
    """Write one block and read it back.  Restores `original` on failure."""
    if desired == original:
        return False
    try:
        _set(dev, set_command, desired)
        if verify:
            got = _get(dev, get_command, args)
            if got[:len(desired)] != desired:
                _put_back(dev, set_command, get_command, args, original)
                raise SuperNovaError(
                    f"{label}: после записи прочитано {got[:len(desired)].hex()}, "
                    f"ожидалось {desired.hex()}; исходный блок восстановлен, "
                    f"сохранение отменено")
    except Exception:
        _put_back(dev, set_command, get_command, args, original)
        raise
    return True


def _write_remaps(dev: HidrawDevice, config: dict, previous: dict | None,
                  verify: bool, written: list, progress: Progress):
    old_map = remap_targets(previous or {})
    new_map = remap_targets(config)
    for name, code in REMAP_SOURCES:
        target_name = new_map[name]
        if target_name == old_map[name]:
            continue
        if target_name not in SOURCE_CODES or target_name in ("L4", "R4"):
            raise SuperNovaError(f"{name}: неподдерживаемая цель {target_name!r}")
        target_code = SOURCE_CODES[target_name]
        _progress(progress, f"Переназначение: {name} → {target_name}")
        original = _read_key_block(dev, code)
        desired = with_key_target(original, target_code)
        if _write_verified(dev, SET_KEY, GET_KEY, bytes([0, code]), original,
                           desired, f"кнопка {name}", verify):
            written.append((SET_KEY, GET_KEY, bytes([0, code]), original))


def _write_vibration(dev: HidrawDevice, config: dict, previous: dict | None,
                     verify: bool, written: list, progress: Progress):
    old = (previous or {}).get("vibration") or {}
    new = config.get("vibration") or {}
    if old == new:
        return
    _progress(progress, "Сила вибрации")
    original = _read_vibration_block(dev)
    desired = bytearray(original)
    desired[0] = max(0, min(100, int(new.get("left", original[0]))))
    desired[1] = max(0, min(100, int(new.get("right", original[1]))))
    if _write_verified(dev, SET_VIBRATION, GET_VIBRATION, b"", original,
                       bytes(desired), "вибрация", verify):
        written.append((SET_VIBRATION, GET_VIBRATION, b"", original))


def _write_deadzones(dev: HidrawDevice, config: dict, previous: dict | None,
                     verify: bool, written: list, progress: Progress):
    for side, key, set_command, get_command, points_at in (
            (0, "stick_left", SET_STICK_CURVE, GET_STICK_CURVE, STICK_POINTS),
            (1, "stick_right", SET_STICK_CURVE, GET_STICK_CURVE, STICK_POINTS),
            (0, "trigger_left", SET_TRIGGER, GET_TRIGGER, TRIG_POINTS),
            (1, "trigger_right", SET_TRIGGER, GET_TRIGGER, TRIG_POINTS)):
        old = (previous or {}).get(key) or {}
        new = config.get(key) or {}
        if old == new:
            continue
        _progress(progress, f"Мёртвая зона: {key}")
        if key.startswith("stick"):
            original = _read_stick_block(dev, side)
            args = bytes([side, 0])
        else:
            original = _read_trigger_block(dev, side)
            args = bytes([side])
        desired = with_begin_deadzone(
            original, points_at, int(new.get("deadzone_min", old.get("deadzone_min", 5))))
        if _write_verified(dev, set_command, get_command, args, original,
                           desired, f"мёртвая зона {key}", verify):
            written.append((set_command, get_command, args, original))


def apply_config(dev: HidrawDevice, config: dict, previous: dict | None = None,
                 sections: list[str] | None = None, progress: Progress = None,
                 verify: bool = True) -> ApplyResult:
    """Write changed verified blocks and save them.

    A type check runs first.  If any block fails or does not read back, every
    block written during this call is restored and the config page is not
    saved.
    """
    result = ApplyResult()
    if not probe(dev):
        result.ok = False
        result.errors.append(
            "Устройство не отвечает как Super Nova (тип устройства не 3). "
            "Запись отменена.")
        return result

    config = copy.deepcopy(config)
    previous = copy.deepcopy(previous) if previous is not None else {}

    detected = diff_sections(previous, config)
    if sections:
        chosen = [name for name in sections if name in SECTIONS]
    else:
        chosen = detected
    result.changed = chosen
    if not chosen:
        result.warnings.append("Нет изменений для записи.")
        return result

    written: list[tuple[tuple[int, int], tuple[int, int], bytes, bytes]] = []
    try:
        if "remaps" in chosen:
            _write_remaps(dev, config, previous, verify, written, progress)
        if "vibration" in chosen:
            _write_vibration(dev, config, previous, verify, written, progress)
        if "deadzones" in chosen:
            _write_deadzones(dev, config, previous, verify, written, progress)

        if written:
            _progress(progress, "Сохранение страницы конфигурации")
            _set(dev, SAVE, b"")
        else:
            result.warnings.append("Записывать было нечего: блоки уже совпадают.")
    except Exception as exc:
        result.ok = False
        result.errors.append(str(exc) or exc.__class__.__name__)
        _progress(progress, "Откат изменений")
        for set_command, get_command, args, original in reversed(written):
            _put_back(dev, set_command, get_command, args, original)
    return result


def vibrate_test(dev: HidrawDevice, left: int = 0, right: int = 0):
    """One short factory test pulse.  It is not stored and does not save."""
    if not probe(dev):
        raise SuperNovaError("Подключённое устройство не является Super Nova")
    left = max(0, min(100, int(left)))
    right = max(0, min(100, int(right)))
    _set(dev, SET_VIBRATION_TEST, bytes([left, right, 0, 0]))
