"""Live gamepad input from the Linux joystick API (/dev/input/js*)."""
from __future__ import annotations

import array
import fcntl
import glob
import os
import struct
import threading

JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_INIT = 0x80

BUTTON_CODES = {
    0x130: "a", 0x131: "b", 0x133: "x", 0x134: "y",
    0x136: "lb", 0x137: "rb", 0x138: "lt", 0x139: "rt",
    0x13A: "view", 0x13B: "menu", 0x13C: "capture", 0x135: "capture",
    0x13D: "l3", 0x13E: "r3",
    0x220: "dpad_up", 0x221: "dpad_down", 0x222: "dpad_left", 0x223: "dpad_right",
}
ABS_X, ABS_Y, ABS_Z, ABS_RX, ABS_RY, ABS_RZ, ABS_HAT0X, ABS_HAT0Y = 0, 1, 2, 3, 4, 5, 0x10, 0x11
JSIOCGAXES = 0x80016A11
JSIOCGBUTTONS = 0x80016A12
JSIOCGAXMAP = 0x80406A32
JSIOCGBTNMAP = 0x80406A34

SKIP = ("mouse", "keyboard", "passthrough")
PREFER = ("x-box", "xbox", "gamepad", "game sir", "gamesir", "tarantula", "controller")

_lock = threading.Lock()
_fd: int | None = None
_path: str | None = None
_name: str | None = None
_axes: dict[int, float] = {}
_buttons: dict[int, int] = {}
_axis_code: dict[int, int] = {}
_button_code: dict[int, int] = {}


def _js_name(path: str) -> str:
    base = os.path.basename(path)
    try:
        return open(f"/sys/class/input/{base}/device/name", encoding="utf-8").read().strip()
    except OSError:
        return base


def find_js() -> tuple[str, str] | None:
    candidates = []
    for path in sorted(glob.glob("/dev/input/js*")):
        name = _js_name(path)
        low = name.lower()
        if any(part in low for part in SKIP):
            continue
        score = 10 if any(part in low for part in PREFER) else 0
        if "xbox" in low or "x-box" in low:
            score += 5
        candidates.append((score, path, name))
    if not candidates:
        return None
    candidates.sort(key=lambda row: (-row[0], row[1]))
    return candidates[0][1], candidates[0][2]


def _close():
    global _fd, _path, _name
    if _fd is not None:
        try:
            os.close(_fd)
        except OSError:
            pass
    _fd = None
    _path = None
    _name = None
    _axes.clear()
    _buttons.clear()
    _axis_code.clear()
    _button_code.clear()


def _ensure() -> bool:
    global _fd, _path, _name
    if _fd is not None:
        return True
    found = find_js()
    if not found:
        return False
    path, name = found
    try:
        _fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        _close()
        return False
    _path, _name = path, name
    try:
        n_axes = array.array("B", [0])
        n_buttons = array.array("B", [0])
        fcntl.ioctl(_fd, JSIOCGAXES, n_axes, True)
        fcntl.ioctl(_fd, JSIOCGBUTTONS, n_buttons, True)
        axmap = array.array("B", [0] * 64)
        btnmap = array.array("H", [0] * 512)
        fcntl.ioctl(_fd, JSIOCGAXMAP, axmap, True)
        fcntl.ioctl(_fd, JSIOCGBTNMAP, btnmap, True)
        _axis_code.update(enumerate(axmap[: n_axes[0]]))
        _button_code.update(enumerate(btnmap[: n_buttons[0]]))
    except OSError:
        _axis_code.update(enumerate([ABS_X, ABS_Y, ABS_Z, ABS_RX, ABS_RY, ABS_RZ, ABS_HAT0X, ABS_HAT0Y]))
        _button_code.update(enumerate([0x130, 0x131, 0x133, 0x134, 0x136, 0x137,
                                       0x13A, 0x13B, 0x13C, 0x13D, 0x13E]))
    return True


def _drain() -> bool:
    if _fd is None:
        return False
    while True:
        try:
            data = os.read(_fd, 8)
        except BlockingIOError:
            return True
        except OSError:
            _close()
            return False
        if len(data) < 8:
            _close()
            return False
        _t, value, typ, number = struct.unpack("IhBB", data)
        typ &= ~JS_EVENT_INIT
        if typ == JS_EVENT_AXIS:
            _axes[number] = max(-1.0, min(1.0, value / 32767.0))
        elif typ == JS_EVENT_BUTTON:
            _buttons[number] = 1 if value else 0


def _trigger(value: float) -> float:
    return max(0.0, min(1.0, (value + 1.0) / 2.0))


def _dpad(x: float, y: float) -> list[str]:
    out = []
    if x < -0.5:
        out.append("dpad_left")
    if x > 0.5:
        out.append("dpad_right")
    if y < -0.5:
        out.append("dpad_up")
    if y > 0.5:
        out.append("dpad_down")
    return out


def read_state() -> dict:
    with _lock:
        if not _ensure() or not _drain():
            return {"connected": False, "name": None, "path": None,
                    "left": {"x": 0.0, "y": 0.0}, "right": {"x": 0.0, "y": 0.0},
                    "lt": 0.0, "rt": 0.0, "pressed": []}
        axes = {_axis_code.get(i, -1): v for i, v in _axes.items()}
        buttons = dict(_buttons)
        codes = dict(_button_code)
        name, path = _name, _path

    pressed = []
    for index, value in buttons.items():
        if value and codes.get(index) in BUTTON_CODES:
            pressed.append(BUTTON_CODES[codes[index]])
    pressed.extend(_dpad(float(axes.get(ABS_HAT0X, 0.0)), float(axes.get(ABS_HAT0Y, 0.0))))
    lt = _trigger(float(axes[ABS_Z])) if ABS_Z in axes else float("lt" in pressed)
    rt = _trigger(float(axes[ABS_RZ])) if ABS_RZ in axes else float("rt" in pressed)
    if lt > 0.5:
        pressed.append("lt")
    if rt > 0.5:
        pressed.append("rt")

    seen, ordered = set(), []
    for item in pressed:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return {
        "connected": True,
        "name": name,
        "path": path,
        "left": {"x": float(axes.get(ABS_X, 0.0)), "y": float(axes.get(ABS_Y, 0.0))},
        "right": {"x": float(axes.get(ABS_RX, 0.0)), "y": float(axes.get(ABS_RY, 0.0))},
        "lt": lt,
        "rt": rt,
        "pressed": ordered,
    }


def close():
    with _lock:
        _close()
