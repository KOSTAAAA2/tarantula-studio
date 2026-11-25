"""High-level controller configuration: read, write, verify.

All register layouts come from the reverse-engineered Tarantula Pro protocol
(see doc/PROTOCOL.md).  Writes are always followed by a read-back check; the
caller decides whether to keep or restore a snapshot.
"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Callable

from . import keys
from .defaults import factory_defaults, section_changed, stick_defaults, SECTION_KEYS
from .transport import HidrawDevice, TransportError

Progress = Callable[[str], None] | None


@dataclass
class ApplyResult:
    ok: bool = True
    changed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    readback: dict | None = None
    readback_config: dict | None = None


def _data(reply: bytes) -> bytes:
    return reply[4:] if len(reply) > 4 else b""


def _get(data: bytes, index: int, default=0) -> int:
    return data[index] if 0 <= index < len(data) else default


def _bool(value) -> bool:
    return bool(value)


def _pct(value) -> int:
    return max(0, min(100, int(value)))


def _dpi(value) -> int:
    return max(0, min(255, int(value)))


def _curve_points(data: bytes, offset: int) -> list[list[int]]:
    values = [_get(data, offset + i) for i in range(6)]
    return [[values[i], values[i + 1]] for i in range(0, 6, 2)]


def _progress(progress: Progress, text: str):
    if progress:
        progress(text)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
def read_device_info(dev: HidrawDevice) -> dict:
    info_reply = dev.get(0x0A, 0x01, req_len=0x03)
    d = _data(info_reply)
    battery_raw = _get(d, 9, 0)
    info = {
        "id": _get(d, 0),
        "firmware": f"{_get(d, 1)}.{_get(d, 2) // 10}.{_get(d, 2) % 10}",
        "firmware_bytes": [_get(d, 1), _get(d, 2)],
        "mac": ":".join(f"{_get(d, 3 + i):02x}" for i in range(6)),
        "battery": None if battery_raw == 255 else min(battery_raw, 100),
        "charging": battery_raw == 255,
        "battery_raw": battery_raw,
        "type": _get(d, 10),
    }
    try:
        ver = dev.get(0x84, 0x01, args=bytes([1]), req_len=0x04)
        vd = _data(ver)
        info["controller_version"] = {
            "engineer": vd[1:4].hex(),
            "protocol": vd[4:7].hex(),
            "firmware": vd[7:11].hex().upper(),
            "hardware": vd[11:14].hex(),
        }
    except TransportError:
        info["controller_version"] = None
    try:
        ver = dev.get(0x84, 0x01, args=bytes([2]), req_len=0x04)
        vd = _data(ver)
        info["dongle_version"] = {
            "engineer": vd[1:4].hex(),
            "protocol": vd[4:7].hex(),
            "firmware": vd[7:11].hex().upper(),
            "hardware": vd[11:14].hex(),
        }
    except TransportError:
        info["dongle_version"] = None
    return info


def read_dpad(dev: HidrawDevice) -> dict:
    d = _data(dev.get(0x09, 0x02, req_len=0x03))
    return {
        "dpad_type": keys.DPAD_TYPE_NAMES.get(_get(d, 0), "8way"),
        "swap": keys.DPAD_SWAP_NAMES.get(_get(d, 1), "off"),
        "layout": keys.LAYOUT_NAMES.get(_get(d, 2), "xbox"),
        "auto_onoff": _get(d, 3, 0) == 0,
        "fast_trigger": _get(d, 4, 0) == 0,
        "macro_switch": keys.button_name(_get(d, 5)) if _get(d, 5) else "none",
    }


def read_wheel_keys(dev: HidrawDevice, side: int) -> dict:
    """Read wheel-mode key zones for one stick.

    Factory/native mappings are kept verbatim (``controller:ls_left`` etc.) so
    writing a freshly read config back is idempotent.
    """
    keyboard = stick_defaults()["keyboard"]
    offset = 4 if side else 0
    try:
        for name, zone in keys.INNER_ZONES.items():
            target, _tb = read_mapping(dev, zone + offset, collapse_factory=False)
            keyboard[name] = target or "none"
        outer = {}
        for name, zone in keys.OUTER_ZONES.items():
            target, _tb = read_mapping(dev, zone + offset, collapse_factory=False)
            outer[name] = target or "none"
    except TransportError:
        return keyboard
    if len(set(outer.values())) == 1:
        keyboard["outline"] = outer["left"]
        for name in outer:
            keyboard[f"{name}_outer"] = ""
    else:
        keyboard["outline"] = ""
        for name, target in outer.items():
            keyboard[f"{name}_outer"] = target
    return keyboard


def read_stick(dev: HidrawDevice, side: int) -> dict:
    side = 1 if side else 0
    mapping = _data(dev.get(0x02, 0x04, args=bytes([side]), req_len=0x0F))
    curve = _data(dev.get(0x02, 0x02, args=bytes([side, 0, side]), req_len=0x18))
    out = {
        "mode": keys.STICK_MODE_NAMES.get(_get(mapping, 6), "native"),
        "overlap_percent": _get(mapping, 1, 40),
        "invert_x": _bool(_get(mapping, 4)),
        "invert_y": _bool(_get(mapping, 5)),
        "mouse_dpi": _get(mapping, 8, 50),
        "mouse_dpi_y": _get(mapping, 9, _get(mapping, 8, 50)),
        "mouse_invert_x": _bool(_get(mapping, 10, _get(mapping, 4))),
        "mouse_invert_y": _bool(_get(mapping, 11, _get(mapping, 5))),
        "is_circle": _get(curve, 7, 1) == 1,
        "axis_ratio": _get(curve, 8, 50),
        "deadzone_min": _get(curve, 9, 5),
        "antideadzone_min": _get(curve, 10, 0),
        "curve_points": _curve_points(curve, 11),
        "deadzone_max": _get(curve, 17, 100),
        "antideadzone_max": _get(curve, 18, 100),
        "curve_preset": keys.CURVE_NAMES.get(_get(curve, 19), "linear"),
        "curve_intensity": _get(curve, 20, 100),
        "keyboard": read_wheel_keys(dev, side),
    }
    return out


def read_trigger(dev: HidrawDevice, side: int) -> dict:
    side = 1 if side else 0
    d = _data(dev.get(0x03, 0x02, args=bytes([side, 0]), req_len=0x05))
    return {
        "hair_mode": keys.HAIR_NAMES.get(_get(d, 1), "off"),
        "hair_trigger_begin": _get(d, 2, 10),
        "hair_trigger_end": _get(d, 3, 20),
        "deadzone_min": _get(d, 4, 5),
        "antideadzone_min": _get(d, 5, 0),
        "curve_points": _curve_points(d, 6),
        "deadzone_max": _get(d, 12, 95),
        "antideadzone_max": _get(d, 13, 100),
        "curve_preset": keys.CURVE_NAMES.get(_get(d, 14), "linear"),
        "curve_intensity": _get(d, 15, 100),
    }


def read_gyro(dev: HidrawDevice) -> dict:
    curve = _data(dev.get(0x04, 0x02, req_len=0x0E))
    mapping = _data(dev.get(0x04, 0x04, req_len=0x0E))
    out = {
        "output_mode": keys.GYRO_OUTPUT_NAMES.get(_get(mapping, 2), "off"),
        "motion_mode": keys.GYRO_MOTION_NAMES.get(_get(mapping, 3), "aim"),
        "axis_mode": keys.GYRO_AXIS_NAMES.get(_get(mapping, 4), "yaw"),
        "activate_button": keys.button_name(_get(mapping, 5)),
        "activate_method": keys.GYRO_METHOD_NAMES.get(_get(mapping, 6), "off"),
        "x_sensitivity": _get(mapping, 7, 50),
        "y_sensitivity": _get(mapping, 8, 50),
        "invert_x": _bool(_get(mapping, 9)),
        "invert_y": _bool(_get(mapping, 10)),
        "overlap_percent": _get(mapping, 0, 40),
        "output_trigger_range": _get(mapping, 1, 40),
        "axis_ratio": _get(curve, 6, 50),
        "deadzone_min": _get(curve, 7, 0),
        "antideadzone_min": _get(curve, 8, 0),
        "curve_points": _curve_points(curve, 9),
        "deadzone_max": _get(curve, 15, 100),
        "antideadzone_max": _get(curve, 16, 100),
        "curve_preset": keys.CURVE_NAMES.get(_get(curve, 17), "linear"),
        "curve_intensity": _get(curve, 18, 100),
        "kb_up": "key:w",
        "kb_down": "key:s",
        "kb_left": "key:a",
        "kb_right": "key:d",
    }
    try:
        for name, zone in keys.GYRO_ZONES.items():
            target, _tb = read_mapping(dev, zone, collapse_factory=False)
            out[f"kb_{name}"] = target or "none"
    except TransportError:
        pass
    return out


def read_lighting(dev: HidrawDevice) -> dict:
    d = _data(dev.get(0x06, 0x07, req_len=0x03))
    out = {
        "brightness": _get(d, 0, 50),
        "lighting_speed": _get(d, 1, 50),
        "lighting_mode": keys.LIGHT_MODE_NAMES.get(_get(d, 2), "colorful"),
        "panel_hsv": [240, 100, 50],
        "home_hsv": [0, 0, 100],
        "abxy_hsv": [[120, 100, 6], [0, 100, 6], [240, 100, 6], [59, 100, 6]],
        "bayx_hsv": [[0, 0, 6], [0, 0, 6], [0, 0, 6], [0, 0, 6]],
    }
    for name in ("panel", "home", "abxy", "bayx"):
        try:
            cd = _data(dev.get(0x07, 0x04, args=bytes([keys.LIGHT_NAMES[name]]), req_len=0x10))
            colors = []
            for i in range(4):
                h = _get(cd, 1 + i * 3)
                s = _get(cd, 2 + i * 3)
                v = _get(cd, 3 + i * 3)
                colors.append([round(h * 360 / 255), s, v])
            if name in ("panel", "home"):
                out[f"{name}_hsv"] = colors[0]
            else:
                out[f"{name}_hsv"] = colors
        except TransportError:
            pass
    return out


def read_rumble(dev: HidrawDevice) -> dict:
    d = _data(dev.get(0x06, 0x02, req_len=0x09))
    return {
        "left": _get(d, 0, 75),
        "right": _get(d, 1, 75),
        "lt_mode": _get(d, 2, 0),
        "rt_mode": _get(d, 3, 0),
        "lt_level": _get(d, 4, 0),
        "rt_level": _get(d, 5, 0),
    }


def read_mapping(dev: HidrawDevice, source_id: int, *,
                 collapse_factory: bool = True) -> tuple[str | None, dict | None]:
    """Return (target string or None for factory/native, turbo settings or None)."""
    reply = dev.get(0x05, 0x02, args=bytes([0, source_id]), req_len=0x05,
                    match=[(10, source_id)])
    if len(reply) < 16:
        return None, None
    # Native slot: bytes 13..14 are 14 01 and turbo mode is off.
    if reply[13:15] == b"\x14\x01" and _get(reply, 12) == 0:
        return None, None
    if reply[14:16] == b"\x00\x00":
        return None, None
    target = keys.decode_target(reply[14:16], reply[16:20])
    if collapse_factory:
        factory_id = keys.FACTORY_TARGET.get(source_id, source_id)
        if target == f"controller:{keys.button_name(factory_id)}":
            target = None
    turbo = None
    continuous = _get(reply, 11) == 1
    mode = _get(reply, 12)
    if mode in (1, 2, 3) or continuous:
        turbo = {"rate": _get(reply, 13, 10), "continuous": continuous,
                 "turbo": mode in (1, 2, 3)}
    return target, turbo


def read_macro_steps(dev: HidrawDevice, source_id: int, max_steps: int = 12) -> list[dict]:
    steps = []
    for index in range(max_steps):
        try:
            reply = dev.get(0x01, 0x02, args=bytes([source_id, index]), req_len=0x13,
                            match=[(4, source_id), (5, index)], timeout=0.5)
        except TransportError:
            break
        if len(reply) < 20:
            break
        if _get(reply, 10) == 0 and all(v == 0 for v in reply[12:16]):
            break
        target = keys.decode_target(reply[10:12], reply[12:16])
        if target is None:
            target = f"controller:{keys.button_name(_get(reply, 12))}"
        steps.append({
            "target": target,
            "press_ms": (_get(reply, 16) << 8) | _get(reply, 17),
            "release_ms": (_get(reply, 18) << 8) | _get(reply, 19),
            "macro_type": _get(reply, 6, 1),
            "loop": bool(_get(reply, 7)),
        })
    return steps


def read_mappings(dev: HidrawDevice, progress: Progress = None) -> tuple[dict, dict, dict, list[str]]:
    mappings: dict[str, str] = {}
    turbo: dict[str, dict] = {}
    macros: dict[str, dict] = {}
    warnings: list[str] = []
    ids = sorted(keys.CONTROLLER_SOURCE.items(), key=lambda kv: kv[1])
    for name, source_id in ids:
        _progress(progress, f"Кнопки: {name}")
        try:
            target, tb = read_mapping(dev, source_id)
        except TransportError as exc:
            warnings.append(f"{name}: {exc}")
            continue
        if target:
            mappings[name] = target
            if tb:
                turbo[name] = {"rate": tb["rate"], "continuous": tb["continuous"]}
            continue
        # A 00 00 slot can be an unbind or a macro.  Probe macro steps.
        try:
            steps = read_macro_steps(dev, source_id)
        except TransportError:
            steps = []
        if steps:
            macros[name] = {
                "steps": [[s["target"], s["press_ms"], s["release_ms"]] for s in steps],
                "hold": steps[0]["macro_type"] == 2,
                "loop": steps[0]["loop"],
            }
            mappings[name] = "macro:" + "+".join(s["target"] for s in steps)
    return mappings, turbo, macros, warnings


def read_all(dev: HidrawDevice, progress: Progress = None) -> tuple[dict, dict, list[str]]:
    """Read the whole device. Returns (config, info, warnings)."""
    config = factory_defaults()
    warnings: list[str] = []
    _progress(progress, "Информация об устройстве")
    info = {}
    try:
        info = read_device_info(dev)
    except TransportError as exc:
        warnings.append(f"Device info: {exc}")

    readers = [
        ("dpad", lambda: read_dpad(dev)),
        ("stick_left", lambda: read_stick(dev, 0)),
        ("stick_right", lambda: read_stick(dev, 1)),
        ("trigger_left", lambda: read_trigger(dev, 0)),
        ("trigger_right", lambda: read_trigger(dev, 1)),
        ("gyro", lambda: read_gyro(dev)),
        ("lighting", lambda: read_lighting(dev)),
        ("rumble", lambda: read_rumble(dev)),
    ]
    for name, fn in readers:
        _progress(progress, f"Чтение: {name}")
        try:
            value = fn()
            if name == "lighting":
                # preserve defaults for fields the device did not answer
                config["lighting"].update({k: v for k, v in value.items() if v is not None})
            else:
                config[name] = value
        except TransportError as exc:
            warnings.append(f"{name}: {exc}")

    _progress(progress, "Кнопки и макросы")
    mappings, turbo, macros, map_warnings = read_mappings(dev, progress)
    warnings.extend(map_warnings)
    config["key_mappings"] = mappings
    config["turbo_settings"] = turbo
    config["macro_settings"] = macros
    return config, info, warnings


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------
def _write_stick(dev: HidrawDevice, side: int, stick: dict):
    dev.set(0x02, 0x03, keys.set_stick_mapping_packet(
        side,
        invert_x=stick.get("invert_x", False),
        invert_y=stick.get("invert_y", False),
        mode=stick.get("mode", "native"),
        overlap=stick.get("overlap_percent", 40),
        dpi_x=_dpi(stick.get("mouse_dpi", 50)),
        dpi_y=_dpi(stick.get("mouse_dpi_y", stick.get("mouse_dpi", 50))),
        mouse_invert_x=stick.get("mouse_invert_x", stick.get("invert_x", False)),
        mouse_invert_y=stick.get("mouse_invert_y", stick.get("invert_y", False)),
    )[4:])
    time.sleep(0.02)
    dev.set(0x02, 0x01, keys.set_stick_curve_packet(
        side,
        axis_ratio=stick.get("axis_ratio", 50),
        deadzone_min=stick.get("deadzone_min", 5),
        deadzone_max=stick.get("deadzone_max", 100),
        antideadzone_min=stick.get("antideadzone_min", 0),
        antideadzone_max=stick.get("antideadzone_max", 100),
        is_circle=stick.get("is_circle", True),
        curve_preset=stick.get("curve_preset", "linear"),
        curve_intensity=stick.get("curve_intensity", 100),
        curve_points=stick.get("curve_points"),
    )[4:])
    if str(stick.get("mode", "native")).lower() == "wheel":
        _write_wheel_keys(dev, side, stick.get("keyboard") or {})


def _write_wheel_keys(dev: HidrawDevice, side: int, keyboard: dict):
    offset = 4 if side else 0
    for name, zone in keys.INNER_ZONES.items():
        target = keyboard.get(name) or "none"
        dev.set(0x05, 0x01, keys.zone_packet(zone + offset, target)[4:])
        time.sleep(0.02)
    outline = keyboard.get("outline") or "none"
    for name, zone in keys.OUTER_ZONES.items():
        target = keyboard.get(f"{name}_outer") or outline
        dev.set(0x05, 0x01, keys.zone_packet(zone + offset, target)[4:])
        time.sleep(0.02)


def _write_trigger(dev: HidrawDevice, side: int, trigger: dict):
    dev.set(0x03, 0x01, keys.set_trigger_packet(
        side,
        hair_mode=trigger.get("hair_mode", "off"),
        hair_begin=trigger.get("hair_trigger_begin", 10),
        hair_end=trigger.get("hair_trigger_end", 20),
        deadzone_min=trigger.get("deadzone_min", 5),
        deadzone_max=trigger.get("deadzone_max", 95),
        antideadzone_min=trigger.get("antideadzone_min", 0),
        antideadzone_max=trigger.get("antideadzone_max", 100),
        curve_preset=trigger.get("curve_preset", "linear"),
        curve_intensity=trigger.get("curve_intensity", 100),
        curve_points=trigger.get("curve_points"),
    )[4:])


def _write_gyro(dev: HidrawDevice, gyro: dict):
    dev.set(0x04, 0x01, keys.set_gyro_curve_packet(
        axis_ratio=gyro.get("axis_ratio", 50),
        deadzone_min=gyro.get("deadzone_min", 0),
        deadzone_max=gyro.get("deadzone_max", 100),
        antideadzone_min=gyro.get("antideadzone_min", 0),
        antideadzone_max=gyro.get("antideadzone_max", 100),
        curve_preset=gyro.get("curve_preset", "linear"),
        curve_intensity=gyro.get("curve_intensity", 100),
        curve_points=gyro.get("curve_points"),
    )[4:])
    time.sleep(0.02)
    dev.set(0x04, 0x03, keys.set_gyro_mapping_packet(
        output_mode=gyro.get("output_mode", "off"),
        motion_mode=gyro.get("motion_mode", "aim"),
        axis_mode=gyro.get("axis_mode", "yaw"),
        activate_button=gyro.get("activate_button", "b"),
        activate_method=gyro.get("activate_method", "off"),
        x_sensitivity=gyro.get("x_sensitivity", 50),
        y_sensitivity=gyro.get("y_sensitivity", 50),
        overlap=gyro.get("overlap_percent", 40),
        output_trigger_range=gyro.get("output_trigger_range", 40),
        invert_x=gyro.get("invert_x", False),
        invert_y=gyro.get("invert_y", False),
    )[4:])
    if str(gyro.get("output_mode", "")).lower() == "keyboard":
        for direction, zone in keys.GYRO_ZONES.items():
            target = gyro.get(f"kb_{direction}") or "none"
            dev.set(0x05, 0x01, keys.zone_packet(zone, target)[4:])
            time.sleep(0.02)


def _write_lighting(dev: HidrawDevice, lighting: dict):
    dev.set(0x07, 0x01, keys.set_light_packet(
        mode=lighting.get("lighting_mode", "static"),
        brightness=lighting.get("brightness", 100),
        speed=lighting.get("lighting_speed", 50),
    )[4:])
    time.sleep(0.02)
    panel = lighting.get("panel_hsv", [240, 100, 50])
    # Official app overwrites panel value with the brightness setting.
    dev.set(0x07, 0x03, keys.set_light_color_packet(
        "panel", [(panel[0], panel[1], lighting.get("brightness", 50))])[4:])
    time.sleep(0.02)
    home = lighting.get("home_hsv", [0, 0, 100])
    dev.set(0x07, 0x03, keys.set_light_color_packet(
        "home", [(home[0], home[1], home[2])])[4:])
    time.sleep(0.02)
    for name, key in (("abxy", "abxy_hsv"), ("bayx", "bayx_hsv")):
        colors = lighting.get(key) or []
        if len(colors) >= 4:
            dev.set(0x07, 0x03, keys.set_light_color_packet(
                name, [tuple(c) for c in colors[:4]])[4:])
            time.sleep(0.02)


def _write_rumble(dev: HidrawDevice, rumble: dict):
    dev.set(0x06, 0x01, keys.set_vibration_packet(
        rumble.get("left", 75), rumble.get("right", 75),
        rumble.get("lt_mode", 0), rumble.get("rt_mode", 0),
        rumble.get("lt_level", 0), rumble.get("rt_level", 0),
    )[4:])


def _write_dpad(dev: HidrawDevice, dpad: dict):
    dev.set(0x09, 0x01, keys.set_dpad_packet(
        dpad_type=dpad.get("dpad_type", "8way"),
        swap=dpad.get("swap", "off"),
        layout=dpad.get("layout", "xbox"),
        auto_onoff=dpad.get("auto_onoff", True),
        fast_trigger=dpad.get("fast_trigger", True),
        macro_switch=dpad.get("macro_switch", "none"),
    )[4:])


def _write_mapping(dev: HidrawDevice, name: str, target: str, turbo: dict | None):
    source = keys.button_id(name)
    packet = keys.mapping_packet(source, target)
    if turbo and target not in ("none", "unbind", "reset", "factory", "default"):
        rate = int(turbo.get("rate", 10))
        packet = keys.apply_turbo(packet, rate, bool(turbo.get("continuous", False)))
    else:
        packet = keys.apply_turbo(packet, None, bool(turbo.get("continuous", False)) if turbo else False)
    dev.set(0x05, 0x01, packet[4:])


def _write_macro(dev: HidrawDevice, name: str, macro: dict):
    source = keys.button_id(name)
    steps = macro.get("steps") or []
    if not steps:
        dev.set(0x05, 0x01, keys.macro_unbind_packet(source)[4:])
        dev.set(0x01, 0x01, keys.macro_clear_packet(source)[4:])
        return
    if len(steps) > 12:
        raise ValueError(f"{name}: macro has {len(steps)} steps, maximum is 12")
    dev.set(0x05, 0x01, keys.macro_unbind_packet(source)[4:])
    time.sleep(0.02)
    dev.set(0x01, 0x01, keys.macro_clear_packet(source)[4:])
    time.sleep(0.02)
    macro_type = 2 if macro.get("hold") else 1
    loop = bool(macro.get("loop"))
    for index, step in enumerate(steps):
        target, press, release = step[0], int(step[1]), int(step[2])
        dev.set(0x01, 0x01, keys.macro_step_packet(
            source, index, target, press, release, macro_type=macro_type, loop=loop)[4:])
        time.sleep(0.02)


def _mapping_names(config: dict) -> set[str]:
    names = set((config.get("key_mappings") or {}).keys())
    names |= set((config.get("macro_settings") or {}).keys())
    names |= set((config.get("turbo_settings") or {}).keys())
    return names


def _write_mappings(dev: HidrawDevice, config: dict, previous: dict | None,
                    progress: Progress = None):
    old_maps = (previous or {}).get("key_mappings") or {}
    old_turbo = (previous or {}).get("turbo_settings") or {}
    old_macros = (previous or {}).get("macro_settings") or {}
    new_maps = config.get("key_mappings") or {}
    new_turbo = config.get("turbo_settings") or {}
    new_macros = config.get("macro_settings") or {}

    if previous is None:
        names = _mapping_names(config)
    else:
        names = {n for n in _mapping_names(config) | _mapping_names(previous)
                 if (old_maps.get(n) != new_maps.get(n)
                     or old_turbo.get(n) != new_turbo.get(n)
                     or old_macros.get(n) != new_macros.get(n))}

    for name in sorted(names):
        _progress(progress, f"Запись кнопки: {name}")
        target = new_maps.get(name)
        macro = new_macros.get(name)
        if macro:
            _write_macro(dev, name, macro)
            continue
        if target is None:
            # Removed mapping -> factory state, and clear a stale macro.
            if old_macros.get(name):
                dev.set(0x01, 0x01, keys.macro_clear_packet(name)[4:])
            _write_mapping(dev, name, "reset", None)
            continue
        if str(target).startswith("macro:"):
            # Summary without steps: cannot rebuild; skip it.
            continue
        _write_mapping(dev, name, str(target), new_turbo.get(name))


def _write_section(dev: HidrawDevice, section: str, config: dict,
                   previous: dict | None, progress: Progress = None):
    if section == "sticks":
        for side, key in ((0, "stick_left"), (1, "stick_right")):
            _progress(progress, f"Стик: {key}")
            _write_stick(dev, side, config[key])
        dev.save()
    elif section == "triggers":
        for side, key in ((0, "trigger_left"), (1, "trigger_right")):
            _progress(progress, f"Курок: {key}")
            _write_trigger(dev, side, config[key])
        dev.save()
    elif section == "gyro":
        _progress(progress, "Гироскоп")
        _write_gyro(dev, config["gyro"])
        dev.save()
    elif section == "lighting":
        _progress(progress, "Подсветка")
        _write_lighting(dev, config["lighting"])
        dev.save()
    elif section == "rumble":
        _progress(progress, "Вибрация")
        _write_rumble(dev, config["rumble"])
        dev.save()
    elif section == "dpad":
        _progress(progress, "D-pad и раскладка")
        _write_dpad(dev, config["dpad"])
        dev.save()
    elif section == "mappings":
        _write_mappings(dev, config, previous, progress)
        dev.save()
    else:
        raise ValueError(f"Unknown section: {section}")


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
def _compare(label: str, expected, actual, diffs: list[str]):
    if expected != actual:
        diffs.append(f"{label}: ожидалось {expected!r}, получено {actual!r}")


def _verify_stick(expected: dict, actual: dict, side: str, diffs: list[str]):
    for key in ("mode", "overlap_percent", "invert_x", "invert_y",
                "is_circle", "axis_ratio", "deadzone_min", "deadzone_max",
                "antideadzone_min", "antideadzone_max", "curve_preset",
                "curve_intensity", "curve_points"):
        _compare(f"{side}.{key}", expected.get(key), actual.get(key), diffs)
    for key in ("mouse_dpi", "mouse_dpi_y"):
        exp = _dpi(expected.get(key, 50))
        got = actual.get(key)
        if exp != got:
            if exp > 100 and got is not None and got <= 100:
                diffs.append(
                    f"{side}.{key}: контроллер принял {got} вместо {exp} — прошивка, похоже, "
                    f"ограничивает DPI значением 100"
                )
            else:
                diffs.append(f"{side}.{key}: ожидалось {exp!r}, получено {got!r}")
    if str(expected.get("mode", "")).lower() == "wheel":
        exp_kb = expected.get("keyboard") or {}
        got_kb = actual.get("keyboard") or {}
        for name in keys.INNER_ZONES:
            _compare(f"{side}.keyboard.{name}", _zone(exp_kb.get(name)),
                     _zone(got_kb.get(name)), diffs)
        for name in keys.OUTER_ZONES:
            _compare(f"{side}.keyboard.{name}_outer",
                     _zone(exp_kb.get(f"{name}_outer") or exp_kb.get("outline")),
                     _zone(got_kb.get(f"{name}_outer") or got_kb.get("outline")), diffs)


def _zone(target) -> str:
    return target or "none"


def _canonical_target(target):
    """Normalize a target string so verification compares meaning, not spelling.

    The UI accepts compact forms such as ``key:left_ctrl+c`` while the readback
    decoder emits ``key:left_ctrl+key:c``; both encode to the same bytes.
    """
    if target is None:
        return None
    try:
        report, code = keys.encode_target(str(target))
        return keys.decode_target(report, code) or str(target)
    except ValueError:
        return str(target)


def _compare_hsv(label: str, expected, actual, diffs: list[str], tolerance: int = 2):
    """Compare HSV colours allowing for byte<->degree rounding."""
    if not expected and not actual:
        return
    if not isinstance(expected, (list, tuple)) or not isinstance(actual, (list, tuple)):
        _compare(label, expected, actual, diffs)
        return
    expected = list(expected)
    actual = list(actual)
    if len(expected) != len(actual):
        _compare(label, expected, actual, diffs)
        return
    for index, (exp, got) in enumerate(zip(expected, actual)):
        if isinstance(exp, (list, tuple)) or isinstance(got, (list, tuple)):
            _compare_hsv(f"{label}[{index}]", exp, got, diffs, tolerance)
            continue
        try:
            if abs(int(exp) - int(got)) > tolerance:
                _compare(label, expected, actual, diffs)
                return
        except (TypeError, ValueError):
            if exp != got:
                _compare(label, expected, actual, diffs)
                return


def verify_section(dev: HidrawDevice, config: dict, section: str) -> list[str]:
    diffs: list[str] = []
    if section == "sticks":
        _verify_stick(config["stick_left"], read_stick(dev, 0), "left", diffs)
        _verify_stick(config["stick_right"], read_stick(dev, 1), "right", diffs)
    elif section == "triggers":
        for side, key in ((0, "trigger_left"), (1, "trigger_right")):
            expected = config[key]
            actual = read_trigger(dev, side)
            for field in ("hair_mode", "hair_trigger_begin", "hair_trigger_end",
                          "deadzone_min", "deadzone_max", "antideadzone_min",
                          "antideadzone_max", "curve_preset", "curve_intensity",
                          "curve_points"):
                _compare(f"{key}.{field}", expected.get(field), actual.get(field), diffs)
    elif section == "gyro":
        actual = read_gyro(dev)
        for field in ("output_mode", "motion_mode", "axis_mode", "activate_button",
                      "activate_method", "x_sensitivity", "y_sensitivity",
                      "invert_x", "invert_y", "overlap_percent",
                      "output_trigger_range", "axis_ratio", "deadzone_min",
                      "deadzone_max", "antideadzone_min", "antideadzone_max",
                      "curve_preset", "curve_intensity"):
            _compare(f"gyro.{field}", config["gyro"].get(field), actual.get(field), diffs)
        if str(config["gyro"].get("output_mode", "")).lower() == "keyboard":
            for direction in keys.GYRO_ZONES:
                _compare(f"gyro.kb_{direction}", _zone(config["gyro"].get(f"kb_{direction}")),
                         _zone(actual.get(f"kb_{direction}")), diffs)
    elif section == "lighting":
        actual = read_lighting(dev)
        for field in ("lighting_mode", "brightness", "lighting_speed"):
            _compare(f"lighting.{field}", config["lighting"].get(field), actual.get(field), diffs)
        # panel value is intentionally overwritten by brightness
        _compare_hsv("lighting.home_hsv", config["lighting"].get("home_hsv"),
                     actual.get("home_hsv"), diffs)
        for name in ("abxy", "bayx"):
            exp = config["lighting"].get(f"{name}_hsv")
            got = actual.get(f"{name}_hsv")
            if exp and got:
                # saturation/value may be rounded; hue is stored as 0-255
                _compare_hsv(f"lighting.{name}_hsv", exp, got, diffs)
    elif section == "rumble":
        actual = read_rumble(dev)
        for field in ("left", "right", "lt_mode", "rt_mode", "lt_level", "rt_level"):
            _compare(f"rumble.{field}", config["rumble"].get(field), actual.get(field), diffs)
    elif section == "dpad":
        actual = read_dpad(dev)
        for field in ("dpad_type", "swap", "layout", "auto_onoff", "fast_trigger"):
            _compare(f"dpad.{field}", config["dpad"].get(field), actual.get(field), diffs)
    elif section == "mappings":
        expected_maps = config.get("key_mappings") or {}
        expected_macros = config.get("macro_settings") or {}
        for name in sorted(set(expected_maps) | set(expected_macros)):
            source = keys.button_id(name)
            macro = expected_macros.get(name)
            if macro:
                steps = read_macro_steps(dev, source)
                expected_steps = [
                    [_canonical_target(step[0]), int(step[1]), int(step[2])]
                    for step in macro.get("steps") or []
                ]
                got_steps = [
                    [_canonical_target(s["target"]), s["press_ms"], s["release_ms"]]
                    for s in steps
                ]
                _compare(f"macro.{name}", expected_steps, got_steps, diffs)
                continue
            target, _tb = read_mapping(dev, source)
            expected = expected_maps.get(name)
            if expected in (None, "reset", "factory", "default"):
                expected = None
            if expected in ("none", "unbind", "nc"):
                expected = None
            _compare(f"mapping.{name}", _canonical_target(expected),
                     _canonical_target(target), diffs)
    return diffs


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------
def apply_config(dev: HidrawDevice, config: dict, previous: dict | None = None,
                 sections: list[str] | None = None, progress: Progress = None,
                 verify: bool = True) -> ApplyResult:
    result = ApplyResult()
    config = copy.deepcopy(config)
    previous = copy.deepcopy(previous) if previous is not None else None

    if sections:
        changed = [s for s in sections if s in SECTION_KEYS]
    elif previous is None:
        changed = [s for s in SECTION_KEYS if s != "advanced"]
    else:
        changed = [s for s in SECTION_KEYS if s != "advanced"
                   and section_changed(previous, config, s)]
    result.changed = changed
    if not changed:
        result.warnings.append("Нет изменений для записи.")
        return result

    try:
        for section in changed:
            _write_section(dev, section, config, previous, progress)
        _progress(progress, "Проверка записанных значений")
        if verify:
            for section in changed:
                try:
                    diffs = verify_section(dev, config, section)
                except TransportError as exc:
                    result.errors.append(f"{section}: проверка не удалась: {exc}")
                    continue
                result.warnings.extend(diffs)
        result.readback = read_device_info(dev)
        result.readback_config = config
        result.ok = not result.errors
    except Exception as exc:
        result.ok = False
        result.errors.append(str(exc))
    return result


def fire_rumble(dev: HidrawDevice, left: int, right: int, duration_ms: int = 500,
                lt: int = 0, rt: int = 0):
    deadline = time.monotonic() + max(0.05, duration_ms / 1000.0)
    while time.monotonic() < deadline:
        dev.rumble_test(left, right, lt, rt)
        time.sleep(0.03)
    dev.rumble_test(0, 0, 0, 0)


def quick_set_dpi(dev: HidrawDevice, side: int, dpi: int, *, enable_mouse: bool = True) -> dict:
    """Set one stick's mouse-mode DPI and read it back (used by the CLI/GUI test)."""
    current = read_stick(dev, side)
    current["mouse_dpi"] = _dpi(dpi)
    current["mouse_dpi_y"] = _dpi(dpi)
    if enable_mouse:
        current["mode"] = "mouse"
    _write_stick(dev, side, current)
    dev.save()
    return read_stick(dev, side)


def write_stick_now(dev: HidrawDevice, side: int, stick: dict) -> dict:
    """Write one complete stick section immediately and read it back."""
    _write_stick(dev, side, copy.deepcopy(stick))
    dev.save()
    return read_stick(dev, side)
