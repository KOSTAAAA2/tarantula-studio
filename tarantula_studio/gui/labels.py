"""Human-readable labels shared by the GUI."""
from __future__ import annotations

from ..core import keys

SOURCE_LABELS = {
    "a": "A", "b": "B", "x": "X", "y": "Y",
    "lb": "LB", "rb": "RB", "lt": "LT", "rt": "RT",
    "l3": "L3", "r3": "R3", "view": "View", "menu": "Menu",
    "dpad_left": "D-Pad ←", "dpad_right": "D-Pad →",
    "dpad_up": "D-Pad ↑", "dpad_down": "D-Pad ↓",
    "l4": "L4", "r4": "R4",
    "t1": "T1", "t2": "T2", "t3": "T3",
    "c1": "C1", "c2": "C2", "c3": "C3", "c4": "C4",
    "capture": "Capture",
    "ls_left": "LS ←", "ls_right": "LS →", "ls_up": "LS ↑", "ls_down": "LS ↓",
    "rs_left": "RS ←", "rs_right": "RS →", "rs_up": "RS ↑", "rs_down": "RS ↓",
}

SOURCE_ORDER = [
    "a", "b", "x", "y", "lb", "rb", "lt", "rt", "l3", "r3",
    "view", "menu", "dpad_left", "dpad_right", "dpad_up", "dpad_down",
    "l4", "r4", "t1", "t2", "t3", "c1", "c2", "c3", "c4", "capture",
]

STICK_MODE_LABELS = {
    "native": "Нативный стик",
    "mouse": "Мышь (HID)",
    "wheel": "Клавиши по зонам (wheel)",
    "clone": "Трансляция на другой стик",
}
CURVE_LABELS = {
    "linear": "Линейная",
    "expo": "Экспонента",
    "s-curve": "S-кривая",
    "custom": "Своя (3 точки)",
}
HAIR_LABELS = {
    "off": "Выключен (линейный)",
    "adaptive": "Адаптивный (быстрый)",
    "fixed": "Фиксированный (быстрый)",
}
GYRO_OUTPUT_LABELS = {
    "off": "Выключен",
    "left_stick": "Левый стик",
    "right_stick": "Правый стик",
    "keyboard": "Клавиши (зоны)",
    "mouse": "Мышь",
}
GYRO_MOTION_LABELS = {"aim": "Прицеливание (shooting)", "tilt": "Наклон (racing)"}
GYRO_AXIS_LABELS = {"yaw": "YZ (yaw)", "roll": "XY (roll)", "global": "XYZ (global)"}
GYRO_METHOD_LABELS = {
    "off": "Без активации",
    "press": "Нажатие (переключение)",
    "hold": "Удержание",
    "always": "Всегда включён",
}
LIGHT_MODE_LABELS = {
    "off": "Выключена",
    "static": "Постоянный цвет",
    "breathing": "Дыхание",
    "colorful": "Перелив цвета",
    "rainbow": "Радуга",
    "radar": "Радар",
}
DPAD_TYPE_LABELS = {"8way": "8 направлений", "4way": "4 направления"}
DPAD_SWAP_LABELS = {
    "off": "Выключено",
    "dpad_to_ls": "D-Pad → левый стик",
    "dpad_to_rs": "D-Pad → правый стик",
    "ls_rs": "Левый ↔ правый стик",
}
LAYOUT_LABELS = {"xbox": "ABXY (Xbox)", "switch": "BAYX (Switch)"}
TARGET_KIND_LABELS = {
    "factory": "Заводское значение",
    "controller": "Кнопка контроллера",
    "key": "Клавиша клавиатуры",
    "mouse": "Мышь",
    "media": "Медиа-клавиша",
    "unbind": "Отключить кнопку",
}
MOUSE_TARGET_LABELS = {
    "left_click": "ЛКМ", "right_click": "ПКМ", "middle_click": "СКМ",
    "button_4": "Боковая 4", "button_5": "Боковая 5",
    "scroll_up": "Колесо ↑", "scroll_down": "Колесо ↓",
}
MEDIA_TARGET_LABELS = {
    "mute": "Mute", "vol_down": "Громкость −", "vol_up": "Громкость +",
    "mic_mute": "Микрофон", "play": "Play", "prev": "Prev",
    "stop": "Stop", "next": "Next",
}
KEY_LABELS = {
    "left_ctrl": "Left Ctrl", "left_shift": "Left Shift", "left_alt": "Left Alt",
    "left_gui": "Left Win", "right_ctrl": "Right Ctrl", "right_shift": "Right Shift",
    "right_alt": "Right Alt", "right_gui": "Right Win", "ctrl": "Ctrl",
    "shift": "Shift", "alt": "Alt", "gui": "Win", "super": "Super", "meta": "Meta",
    "enter": "Enter", "escape": "Esc", "backspace": "Backspace", "tab": "Tab",
    "space": "Space", "caps_lock": "Caps Lock", "print_screen": "Print Screen",
    "scroll_lock": "Scroll Lock", "pause": "Pause", "insert": "Insert",
    "home": "Home", "page_up": "Page Up", "delete": "Delete", "end": "End",
    "page_down": "Page Down", "left": "←", "right": "→", "up": "↑", "down": "↓",
    "num_lock": "Num Lock", "kp_divide": "Num /", "kp_multiply": "Num *",
    "kp_minus": "Num −", "kp_plus": "Num +", "kp_enter": "Num Enter",
    "kp_dot": "Num .", "kp_equal": "Num =",
    "minus": "−", "equal": "=", "bracket_left": "[", "bracket_right": "]",
    "backslash": "\\", "semicolon": ";", "quote": "'", "grave": "`",
    "comma": ",", "period": ".", "slash": "/", "application": "Menu",
}


def pretty_key(name: str) -> str:
    if name in KEY_LABELS:
        return KEY_LABELS[name]
    if len(name) == 1:
        return name.upper()
    if name.startswith("f") and name[1:].isdigit():
        return name.upper()
    if name.startswith("kp_") and name[3:].isdigit():
        return "Num " + name[3:]
    return name.replace("_", " ").title()


def source_label(name: str) -> str:
    return SOURCE_LABELS.get(name, name.replace("_", " ").title())


def target_label(target: str | None) -> str:
    if not target:
        return "Заводское"
    text = str(target).strip()
    if text.lower() in ("none", "unbind", "nc", "disabled"):
        return "Отключено"
    if text.lower().startswith("macro:"):
        return "Макрос"
    parts = []
    for token in text.split("+"):
        token = token.strip()
        if not token:
            continue
        head, sep, rest = token.partition(":")
        if not sep:
            parts.append(source_label(token))
            continue
        head = head.lower()
        if head in ("controller", "btn", "button", "pad"):
            parts.append(source_label(rest))
        elif head in ("key", "keyboard", "kb"):
            parts.append(pretty_key(rest))
        elif head == "mouse":
            parts.append(MOUSE_TARGET_LABELS.get(rest, rest))
        elif head == "media":
            parts.append(MEDIA_TARGET_LABELS.get(rest, rest))
        else:
            parts.append(rest or token)
    return " + ".join(parts)


def macro_description(macro: dict | None) -> str:
    if not macro:
        return "—"
    steps = macro.get("steps") or []
    flags = []
    if macro.get("hold"):
        flags.append("удержание")
    if macro.get("loop"):
        flags.append("цикл")
    suffix = f" · {', '.join(flags)}" if flags else ""
    return f"{len(steps)} шаг(ов){suffix}"


def combo_values(mapping: dict) -> list[str]:
    return list(mapping.keys())
