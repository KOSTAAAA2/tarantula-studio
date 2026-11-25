"""Factory defaults (from GameSir Connect's T3Pro default profile)."""
from __future__ import annotations

import copy

CURVE_POINTS = [[30, 30], [50, 50], [70, 70]]


def stick_defaults() -> dict:
    return {
        "mode": "native",
        "is_circle": True,
        "axis_ratio": 50,
        "overlap_percent": 40,
        "mouse_dpi": 50,
        "mouse_dpi_y": 50,
        "invert_x": False,
        "invert_y": False,
        "mouse_invert_x": False,
        "mouse_invert_y": False,
        "deadzone_min": 5,
        "antideadzone_min": 0,
        "deadzone_max": 100,
        "antideadzone_max": 100,
        "curve_preset": "linear",
        "curve_intensity": 100,
        "curve_points": copy.deepcopy(CURVE_POINTS),
        "keyboard": {
            "left": "key:a", "right": "key:d", "up": "key:w", "down": "key:s",
            "outline": "key:left_shift",
            "left_outer": "", "right_outer": "", "up_outer": "", "down_outer": "",
        },
    }


def trigger_defaults() -> dict:
    return {
        "hair_mode": "off",
        "hair_trigger_begin": 10,
        "hair_trigger_end": 20,
        "deadzone_min": 5,
        "deadzone_max": 95,
        "antideadzone_min": 0,
        "antideadzone_max": 100,
        "curve_preset": "linear",
        "curve_intensity": 100,
        "curve_points": copy.deepcopy(CURVE_POINTS),
    }


def gyro_defaults() -> dict:
    return {
        "output_mode": "off",
        "motion_mode": "aim",
        "axis_mode": "yaw",
        "activate_button": "b",
        "activate_method": "off",
        "invert_x": False,
        "invert_y": False,
        "x_sensitivity": 50,
        "y_sensitivity": 50,
        "axis_ratio": 50,
        "overlap_percent": 40,
        "output_trigger_range": 40,
        "deadzone_min": 0,
        "antideadzone_min": 0,
        "deadzone_max": 100,
        "antideadzone_max": 100,
        "curve_preset": "linear",
        "curve_intensity": 100,
        "curve_points": copy.deepcopy(CURVE_POINTS),
        "kb_up": "key:w",
        "kb_down": "key:s",
        "kb_left": "key:a",
        "kb_right": "key:d",
    }


def lighting_defaults() -> dict:
    return {
        "lighting_mode": "colorful",
        "brightness": 50,
        "lighting_speed": 50,
        "panel_hsv": [240, 100, 50],
        "home_hsv": [0, 0, 100],
        # [hue in degrees 0-360, saturation 0-100, value 0-100]
        "abxy_hsv": [[120, 100, 6], [0, 100, 6], [240, 100, 6], [59, 100, 6]],
        "bayx_hsv": [[0, 0, 6], [0, 0, 6], [0, 0, 6], [0, 0, 6]],
    }


def rumble_defaults() -> dict:
    return {
        "left": 75, "right": 75,
        "lt_mode": 0, "rt_mode": 0,
        "lt_level": 0, "rt_level": 0,
    }


def dpad_defaults() -> dict:
    return {
        "dpad_type": "8way",
        "swap": "off",
        "layout": "xbox",
        "auto_onoff": True,
        "fast_trigger": True,
        "macro_switch": "none",
    }


def factory_defaults() -> dict:
    return {
        "version": 1,
        "stick_left": stick_defaults(),
        "stick_right": stick_defaults(),
        "trigger_left": trigger_defaults(),
        "trigger_right": trigger_defaults(),
        "gyro": gyro_defaults(),
        "lighting": lighting_defaults(),
        "rumble": rumble_defaults(),
        "dpad": dpad_defaults(),
        "key_mappings": {},
        "turbo_settings": {},
        "macro_settings": {},
        # Per-keyboard-key polling is not exposed by the T3Pro protocol.
        "advanced": {
            "dpi_experimental": True,
            "auto_apply": False,
        },
    }


SECTION_KEYS = {
    "sticks": ("stick_left", "stick_right"),
    "triggers": ("trigger_left", "trigger_right"),
    "gyro": ("gyro",),
    "lighting": ("lighting",),
    "rumble": ("rumble",),
    "dpad": ("dpad",),
    "mappings": ("key_mappings", "turbo_settings", "macro_settings"),
    "advanced": ("advanced",),
}

SECTIONS = {
    "sticks": lambda: {"stick_left": stick_defaults(), "stick_right": stick_defaults()},
    "triggers": lambda: {"trigger_left": trigger_defaults(), "trigger_right": trigger_defaults()},
    "gyro": lambda: {"gyro": gyro_defaults()},
    "lighting": lambda: {"lighting": lighting_defaults()},
    "rumble": lambda: {"rumble": rumble_defaults()},
    "dpad": lambda: {"dpad": dpad_defaults()},
    "mappings": lambda: {"key_mappings": {}, "turbo_settings": {}, "macro_settings": {}},
}


def reset_sections(config: dict, sections: list[str] | None = None) -> dict:
    names = list(SECTIONS) if not sections or "all" in sections else list(sections)
    unknown = [n for n in names if n not in SECTIONS]
    if unknown:
        raise ValueError(f"Unknown section(s): {', '.join(unknown)}")
    out = copy.deepcopy(config)
    for name in names:
        out.update(SECTIONS[name]())
    return out


def deep_merge_defaults(config: dict) -> dict:
    """Fill missing keys from defaults without replacing user values."""
    base = factory_defaults()

    def merge(dst, src):
        for key, value in src.items():
            if key not in dst:
                dst[key] = copy.deepcopy(value)
            elif isinstance(value, dict) and isinstance(dst.get(key), dict):
                merge(dst[key], value)

    merge(config, base)
    return config


def section_changed(old: dict, new: dict, section: str) -> bool:
    keys = SECTION_KEYS.get(section)
    if not keys:
        return old != new
    return any(old.get(k) != new.get(k) for k in keys)
