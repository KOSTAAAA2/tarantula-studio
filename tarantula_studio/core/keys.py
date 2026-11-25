"""GameSir Tarantula Pro (T3 Pro) key codes and config packet builders.

Protocol findings: see doc/PROTOCOL.md and the upstream GameGent project
(https://github.com/HttpKiwi/GameGent, GPL-3.0).  Packet layout:

    OUT 07 len obj op payload...      (32-byte HID report)
    IN  06 len obj op data...         (GET reply starts at byte 4)
    SET reply is 06 04 obj op status  (status 0 = OK)

Everything here is firmware configuration only.  No bootloader, pairing,
calibration or device-identity command is ever built by this module.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# USB HID keyboard usage IDs (HID Usage Tables, page 0x07)
# ---------------------------------------------------------------------------
KEYBOARD_USAGE = {
    "reserved": 0x00, "error_rollover": 0x01, "post_fail": 0x02, "error_undefined": 0x03,
    "a": 0x04, "b": 0x05, "c": 0x06, "d": 0x07, "e": 0x08, "f": 0x09,
    "g": 0x0A, "h": 0x0B, "i": 0x0C, "j": 0x0D, "k": 0x0E, "l": 0x0F,
    "m": 0x10, "n": 0x11, "o": 0x12, "p": 0x13, "q": 0x14, "r": 0x15,
    "s": 0x16, "t": 0x17, "u": 0x18, "v": 0x19, "w": 0x1A, "x": 0x1B,
    "y": 0x1C, "z": 0x1D,
    "1": 0x1E, "2": 0x1F, "3": 0x20, "4": 0x21, "5": 0x22,
    "6": 0x23, "7": 0x24, "8": 0x25, "9": 0x26, "0": 0x27,
    "enter": 0x28, "escape": 0x29, "backspace": 0x2A, "tab": 0x2B,
    "space": 0x2C,
    "minus": 0x2D, "equal": 0x2E, "bracket_left": 0x2F, "bracket_right": 0x30,
    "backslash": 0x31, "hash_non_us": 0x32, "semicolon": 0x33, "quote": 0x34,
    "grave": 0x35, "comma": 0x36, "period": 0x37, "slash": 0x38,
    "caps_lock": 0x39,
    "f1": 0x3A, "f2": 0x3B, "f3": 0x3C, "f4": 0x3D,
    "f5": 0x3E, "f6": 0x3F, "f7": 0x40, "f8": 0x41,
    "f9": 0x42, "f10": 0x43, "f11": 0x44, "f12": 0x45,
    "f13": 0x68, "f14": 0x69, "f15": 0x6A, "f16": 0x6B,
    "f17": 0x6C, "f18": 0x6D, "f19": 0x6E, "f20": 0x6F,
    "f21": 0x70, "f22": 0x71, "f23": 0x72, "f24": 0x73,
    "print_screen": 0x46, "scroll_lock": 0x47, "pause": 0x48,
    "insert": 0x49, "home": 0x4A, "page_up": 0x4B,
    "delete": 0x4C, "end": 0x4D, "page_down": 0x4E,
    "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52,
    "num_lock": 0x53,
    "kp_divide": 0x54, "kp_multiply": 0x55, "kp_minus": 0x56,
    "kp_plus": 0x57, "kp_enter": 0x58,
    "kp_1": 0x59, "kp_2": 0x5A, "kp_3": 0x5B,
    "kp_4": 0x5C, "kp_5": 0x5D, "kp_6": 0x5E,
    "kp_7": 0x5F, "kp_8": 0x60, "kp_9": 0x61,
    "kp_0": 0x62, "kp_dot": 0x63,
    "backslash_non_us": 0x64, "application": 0x65, "power": 0x66, "kp_equal": 0x67,
    "left_ctrl": 0xE0, "left_shift": 0xE1, "left_alt": 0xE2, "left_gui": 0xE3,
    "right_ctrl": 0xE4, "right_shift": 0xE5, "right_alt": 0xE6, "right_gui": 0xE7,
}
USAGE_TO_KEY = {v: k for k, v in KEYBOARD_USAGE.items()}

MOUSE_BUTTON = {
    "left_click": 0x01,
    "right_click": 0x02,
    "middle_click": 0x04,
    "button_5": 0x08,
    "button_4": 0x10,
}
MOUSE_SCROLL = {"scroll_up": 0x01, "scroll_down": 0xFF}
SCROLL_BOTH = 0x80

# Buttons that can host a macro (official app: 12 steps maximum).
MACRO_SOURCES = ("l4", "r4", "t1", "t2", "t3", "c1", "c2", "c3", "c4")

# Wheel-mode key zones (SAPJoyUniKey): inner and outer rings.  The right stick
# uses the same layout shifted by four.
INNER_ZONES = {"left": 0x10, "right": 0x11, "up": 0x12, "down": 0x13}
OUTER_ZONES = {"left": 0x18, "right": 0x19, "up": 0x1A, "down": 0x1B}
GYRO_ZONES = {"left": 0x20, "right": 0x21, "up": 0x22, "down": 0x23}

# Physical buttons / remap sources.  The IDs are SAPJoyUniKey values.
CONTROLLER_SOURCE = {
    "b": 0x00, "a": 0x01, "y": 0x02, "x": 0x03,
    "lb": 0x04, "lt": 0x05, "l3": 0x06, "rb": 0x07,
    "rt": 0x08, "r3": 0x09, "view": 0x0A, "menu": 0x0B,
    "dpad_left": 0x0C, "dpad_right": 0x0D, "dpad_up": 0x0E, "dpad_down": 0x0F,
    "l4": 0x24, "r4": 0x25,
    "t1": 0x26, "t2": 0x27, "t3": 0x28,
    "c1": 0x29, "c2": 0x2A, "c3": 0x2B, "c4": 0x2C,
    "capture": 0x2D,
}

# Friendly aliases
SOURCE_ALIASES = {
    "back": "view", "start": "menu", "share": "capture", "screenshot": "capture",
    "guide": "home", "home_button": "capture",
    "dpadleft": "dpad_left", "dpadright": "dpad_right",
    "dpadup": "dpad_up", "dpaddown": "dpad_down",
    "l1": "lb", "r1": "rb", "l2": "lt", "r2": "rt",
}
CONTROLLER_BUTTON = dict(CONTROLLER_SOURCE)
CONTROLLER_BUTTON["screenshot"] = 0x2D

# Stick-direction key IDs usable as macro steps / wheel zones.
STICK_DIRECTION = {
    "ls_left": 0x10, "ls_right": 0x11, "ls_up": 0x12, "ls_down": 0x13,
    "rs_left": 0x14, "rs_right": 0x15, "rs_up": 0x16, "rs_down": 0x17,
    "lstick_left": 0x10, "lstick_right": 0x11, "lstick_up": 0x12, "lstick_down": 0x13,
    "rstick_left": 0x14, "rstick_right": 0x15, "rstick_up": 0x16, "rstick_down": 0x17,
}

# Button -> factory target (only the extras differ from mapping to self).
FACTORY_TARGET = {
    0x29: 0x0A, 0x2A: 0x0A,   # C1/C2 -> View
    0x2B: 0x0B, 0x2C: 0x0B,   # C3/C4 -> Menu
    0x28: 0x2D,               # T3 -> Capture
}

# Report type bytes: mapping type, key count.  A 16-byte code payload follows.
REPORT_CONTROLLER = b"\x01\x01"
REPORT_KEYBOARD = b"\x02\x02"
REPORT_MOUSE = b"\x03\x04"
REPORT_MEDIA = b"\x04\x04"
REPORT_UNBIND = b"\x00\x00"
REPORT_NATIVE = b"\x14\x01"

MODIFIER_BITS = {
    "left_ctrl": 0, "ctrl": 0, "lctrl": 0, "control": 0,
    "left_shift": 1, "shift": 1, "lshift": 1,
    "left_alt": 2, "alt": 2, "lalt": 2,
    "left_gui": 3, "gui": 3, "win": 3, "super": 3, "meta": 3, "lgui": 3,
    "right_ctrl": 4, "rctrl": 4,
    "right_shift": 5, "rshift": 5,
    "right_alt": 6, "ralt": 6, "altgr": 6,
    "right_gui": 7, "rgui": 7,
}
CANONICAL_MODIFIER = [
    "left_ctrl", "left_shift", "left_alt", "left_gui",
    "right_ctrl", "right_shift", "right_alt", "right_gui",
]
MEDIA_BITS = {
    "mute": 0, "vol_down": 1, "vol_up": 2, "mic_mute": 3,
    "play": 4, "prev": 5, "stop": 6, "next": 7,
}
MEDIA_NAMES = {v: k for k, v in MEDIA_BITS.items()}
MOUSE_NAMES = {v: k for k, v in MOUSE_BUTTON.items()}

# UI lists
STICK_MODES = {"native": 0x00, "mouse": 0x01, "wheel": 0x02, "clone": 0x03}
STICK_MODE_NAMES = {v: k for k, v in STICK_MODES.items()}
CURVE_TYPES = {"linear": 0x00, "expo": 0x01, "s-curve": 0x02, "custom": 0x03}
CURVE_NAMES = {v: k for k, v in CURVE_TYPES.items()}
HAIR_MODES = {"off": 0x00, "adaptive": 0x01, "fixed": 0x02}
HAIR_NAMES = {v: k for k, v in HAIR_MODES.items()}
GYRO_OUTPUT = {"off": 0x00, "left_stick": 0x01, "right_stick": 0x02, "keyboard": 0x03, "mouse": 0x04}
GYRO_OUTPUT_NAMES = {v: k for k, v in GYRO_OUTPUT.items()}
GYRO_MOTION = {"aim": 0x00, "tilt": 0x01}
GYRO_MOTION_NAMES = {v: k for k, v in GYRO_MOTION.items()}
GYRO_METHOD = {"off": 0x00, "press": 0x01, "hold": 0x02, "always": 0x03}
GYRO_METHOD_NAMES = {v: k for k, v in GYRO_METHOD.items()}
GYRO_AXIS = {"yaw": 0x00, "roll": 0x01, "global": 0x02}
GYRO_AXIS_NAMES = {v: k for k, v in GYRO_AXIS.items()}
LIGHT_MODES = {"off": 0x00, "static": 0x01, "breathing": 0x02,
               "colorful": 0x03, "rainbow": 0x04, "radar": 0x05}
LIGHT_MODE_NAMES = {v: k for k, v in LIGHT_MODES.items()}
LIGHT_NAMES = {"home": 0x00, "panel": 0x04, "abxy": 0x05, "bayx": 0x06}
LIGHT_NAME_IDS = {v: k for k, v in LIGHT_NAMES.items()}
DPAD_TYPES = {"8way": 0x00, "4way": 0x01}
DPAD_TYPE_NAMES = {v: k for k, v in DPAD_TYPES.items()}
DPAD_SWAP = {"off": 0x00, "dpad_to_ls": 0x01, "dpad_to_rs": 0x02, "ls_rs": 0x03}
DPAD_SWAP_NAMES = {v: k for k, v in DPAD_SWAP.items()}
LAYOUTS = {"xbox": 0x01, "switch": 0x02}
LAYOUT_NAMES = {v: k for k, v in LAYOUTS.items()}


def normalize_source(name: str) -> str:
    name = str(name).strip().lower().replace("-", "_").replace(" ", "_")
    return SOURCE_ALIASES.get(name, name)


def button_id(name_or_id) -> int:
    """Resolve a source/target name, hex string or int to a hardware button id."""
    if isinstance(name_or_id, int):
        return name_or_id
    text = str(name_or_id).strip().lower()
    if text.startswith("0x"):
        return int(text, 16)
    text = normalize_source(text)
    if text in CONTROLLER_SOURCE:
        return CONTROLLER_SOURCE[text]
    if text in CONTROLLER_BUTTON:
        return CONTROLLER_BUTTON[text]
    if text in STICK_DIRECTION:
        return STICK_DIRECTION[text]
    try:
        return int(text, 10)
    except ValueError as exc:
        raise ValueError(f"Unknown button: {name_or_id}") from exc


def button_name(value: int) -> str:
    for name, idx in CONTROLLER_SOURCE.items():
        if idx == value:
            return name
    for name, idx in STICK_DIRECTION.items():
        if idx == value and not name.startswith(("lstick", "rstick")):
            return name
    return f"0x{value:02x}"


# ---------------------------------------------------------------------------
# Encoding mapping targets
# ---------------------------------------------------------------------------
_PREFIXES = {
    "controller": ("controller", "btn", "button", "pad"),
    "key": ("key", "keyboard", "kb"),
    "mouse": ("mouse",),
    "media": ("media",),
}


def parse_target(target: str) -> tuple[str, list[str]] | None:
    """Public parser used by the GUI; returns (kind, tokens) or None."""
    return _split_target(target)


def _split_target(target: str):
    head, sep, rest = target.lower().strip().partition(":")
    if not sep:
        return None
    for kind, names in _PREFIXES.items():
        if head in names:
            tokens = []
            for token in rest.split("+"):
                token = token.strip()
                if ":" in token:
                    prefix, token = token.split(":", 1)
                    if prefix.strip() not in names:
                        raise ValueError(f"Mixed target prefixes in {target!r}")
                    token = token.strip()
                if token:
                    tokens.append(token)
            return kind, tokens
    return None


def encode_target(target: str) -> tuple[bytes, bytes]:
    """Return (report_type_2_bytes, code_16_bytes) for a UI target string."""
    target = (target or "").strip().lower()
    parsed = _split_target(target)
    if parsed is None:
        # Bare names for convenience: "a", "left_click", "w".
        for kind, table in (("mouse", MOUSE_BUTTON), ("mouse", MOUSE_SCROLL),
                            ("key", KEYBOARD_USAGE), ("controller", CONTROLLER_SOURCE),
                            ("controller", STICK_DIRECTION)):
            if target in table:
                parsed = (kind, [target])
                break
    if parsed is None:
        raise ValueError(f"Unknown target: {target!r}")
    kind, tokens = parsed

    if kind == "controller":
        ids = []
        for token in tokens:
            token = normalize_source(token)
            if token in CONTROLLER_SOURCE:
                ids.append(CONTROLLER_SOURCE[token])
            elif token in CONTROLLER_BUTTON:
                ids.append(CONTROLLER_BUTTON[token])
            elif token in STICK_DIRECTION:
                ids.append(STICK_DIRECTION[token])
            else:
                raise ValueError(f"Unknown controller button: {token}")
        if not 1 <= len(ids) <= 3:
            raise ValueError("A controller target takes 1..3 buttons")
        return bytes([0x01, len(ids)]), bytes(ids).ljust(16, b"\0")

    if kind == "key":
        mods, keys = 0, []
        for token in tokens:
            token = normalize_source(token)
            if token in MODIFIER_BITS:
                mods |= 1 << MODIFIER_BITS[token]
            elif token in KEYBOARD_USAGE:
                keys.append(KEYBOARD_USAGE[token])
            else:
                raise ValueError(f"Unknown keyboard key: {token}")
        if len(keys) > 3:
            raise ValueError("At most 3 keyboard keys plus modifiers")
        if not keys and not mods:
            raise ValueError("Empty keyboard target")
        return bytes([0x02, 1 + len(keys)]), bytes([mods, *keys]).ljust(16, b"\0")

    if kind == "mouse":
        bits, up, down = 0, False, False
        for token in tokens:
            if token in MOUSE_BUTTON:
                bits |= MOUSE_BUTTON[token]
            elif token == "scroll_up":
                up = True
            elif token == "scroll_down":
                down = True
            elif token == "scroll":
                up = down = True
            else:
                raise ValueError(f"Unknown mouse target: {token}")
        scroll = SCROLL_BOTH if up and down else 0x01 if up else 0xFF if down else 0
        return bytes([0x03, 0x04]), bytes([0, 0, scroll, bits]).ljust(16, b"\0")

    bits = 0
    for token in tokens:
        if token not in MEDIA_BITS:
            raise ValueError(f"Unknown media key: {token}")
        bits |= 1 << MEDIA_BITS[token]
    return bytes([0x04, 0x04]), bytes([0, 0, 0, bits]).ljust(16, b"\0")


def decode_target(report_type: bytes, payload: bytes) -> str | None:
    """Decode a GET reply's mapping type/count (2 bytes) and 16-byte code area."""
    if len(report_type) < 2:
        return None
    kind, count = report_type[0], report_type[1]
    payload = payload + b"\0" * max(0, 16 - len(payload))
    if kind == 0x00:
        return None
    if kind == 0x01 and 1 <= count <= 3:
        ids = list(payload[:count])
        if not ids:
            return None
        return "+".join(f"controller:{button_name(v)}" for v in ids)
    if kind == 0x02 and count >= 1:
        mods = payload[0]
        parts = [f"key:{CANONICAL_MODIFIER[b]}" for b in range(8) if mods >> b & 1]
        keys = list(payload[1:count])
        parts += [f"key:{USAGE_TO_KEY.get(v, f'0x{v:02x}')}" for v in keys]
        return "+".join(parts) or None
    if kind == 0x03 and count == 4:
        scroll, bits = payload[2], payload[3]
        parts = [f"mouse:{MOUSE_NAMES.get(1 << b, f'0x{1 << b:02x}')}" for b in range(8) if bits >> b & 1]
        if scroll == SCROLL_BOTH:
            parts += ["mouse:scroll_up", "mouse:scroll_down"]
        elif scroll == 0x01:
            parts.append("mouse:scroll_up")
        elif scroll == 0xFF:
            parts.append("mouse:scroll_down")
        return "+".join(parts) or None
    if kind == 0x04 and count == 4:
        parts = [f"media:{MEDIA_NAMES[b]}" for b in range(8) if payload[3] >> b & 1]
        return "+".join(parts) or None
    return None


# ---------------------------------------------------------------------------
# Packet builders
# ---------------------------------------------------------------------------
def remap_packet(source_id: int, report_type: bytes, code: bytes) -> bytes:
    """SetKeyMapping 07 13 05 01: page 0, key 0, trigger 0, colour 0, source, flags."""
    assert len(report_type) == 2
    pkt = bytearray(32)
    pkt[0:4] = [0x07, 0x13, 0x05, 0x01]
    pkt[4] = 0x00          # page 0
    pkt[5] = 0x00          # key (shift key)
    pkt[6] = 0x00          # trigger
    pkt[7:10] = b"\0\0\0"  # HSV
    pkt[10] = source_id & 0xFF
    pkt[11] = 0x00         # toggle
    pkt[12] = 0x00         # turbo mode
    pkt[13] = 0x01         # turbo times
    pkt[14:16] = report_type
    pkt[16:20] = code[:4]
    return bytes(pkt)


def mapping_packet(source, target: str) -> bytes:
    """Full mapping packet for a target string."""
    source_id = button_id(source)
    t = (target or "").strip().lower()
    if t in ("none", "unbind", "nc", "disabled"):
        return remap_packet(source_id, REPORT_UNBIND, bytes(16))
    if t in ("reset", "factory", "default"):
        factory = FACTORY_TARGET.get(source_id, source_id)
        return remap_packet(source_id, REPORT_CONTROLLER, bytes([factory]).ljust(16, b"\0"))
    report, code = encode_target(t)
    return remap_packet(source_id, report, code)


def apply_turbo(packet: bytes, rate_hz: int | None, continuous: bool = False) -> bytes:
    """Add turbo/toggle flags to a SetKeyMapping packet.

    The official app encodes rate as a mode (A/B/C) plus a rate byte.  A rate of
    None means "toggle only, no turbo".
    """
    pkt = bytearray(packet)
    pkt[11] = 0x01 if continuous else 0x00
    if rate_hz is None or rate_hz <= 1:
        pkt[12] = 0x00
        pkt[13] = 0x01
    else:
        rate = max(2, min(255, int(rate_hz)))
        mode = 3 if rate >= 20 else 2 if rate >= 12 else 1
        pkt[12] = mode
        pkt[13] = rate
    return bytes(pkt)


def macro_clear_packet(button: int) -> bytes:
    pkt = bytearray(32)
    pkt[0:4] = [0x07, 0x13, 0x01, 0x01]
    pkt[4] = button_id(button) & 0xFF
    pkt[5] = 0xFF
    return bytes(pkt)


def macro_unbind_packet(button: int) -> bytes:
    """Turn a button into a macro slot (vacant mapping) before writing steps."""
    return remap_packet(button_id(button), REPORT_UNBIND, bytes(16))


def macro_step_packet(button: int, index: int, target: str,
                      press_ms: int, release_ms: int,
                      macro_type: int = 1, loop: bool = False, loop_ms: int = 0) -> bytes:
    report, code = encode_target(target if ":" in target else f"controller:{target}")
    pkt = bytearray(32)
    pkt[0:4] = [0x07, 0x13, 0x01, 0x01]
    pkt[4] = button_id(button) & 0xFF
    pkt[5] = index & 0xFF
    pkt[6] = macro_type & 0xFF
    pkt[7] = 0x01 if loop else 0x00
    pkt[8] = (loop_ms >> 8) & 0xFF
    pkt[9] = loop_ms & 0xFF
    pkt[10:12] = report
    pkt[12:16] = code[:4]
    pkt[16] = (press_ms >> 8) & 0xFF
    pkt[17] = press_ms & 0xFF
    pkt[18] = (release_ms >> 8) & 0xFF
    pkt[19] = release_ms & 0xFF
    return bytes(pkt)


def zone_packet(zone_id: int, target: str) -> bytes:
    t = (target or "").strip().lower()
    if t in ("", "none", "nc", "unbind"):
        return remap_packet(zone_id, REPORT_UNBIND, bytes(16))
    report, code = encode_target(t)
    return remap_packet(zone_id, report, code)


def set_stick_mapping_packet(stick: int, *, invert_x=False, invert_y=False,
                             mode="native", overlap=40, dpi_x=50, dpi_y=None,
                             mouse_invert_x=None, mouse_invert_y=None) -> bytes:
    mode_byte = STICK_MODES.get(str(mode).lower(), 0x00)
    if dpi_y is None:
        dpi_y = dpi_x
    if mouse_invert_x is None:
        mouse_invert_x = invert_x
    if mouse_invert_y is None:
        mouse_invert_y = invert_y
    pkt = bytearray(32)
    pkt[0:4] = [0x07, 0x0F, 0x02, 0x03]
    pkt[4] = 1 if stick else 0
    pkt[5] = _pct(overlap)
    pkt[6] = 40
    pkt[7] = 80
    pkt[8] = int(bool(invert_x))
    pkt[9] = int(bool(invert_y))
    pkt[10] = mode_byte
    pkt[11] = 0x01
    pkt[12] = _byte(dpi_x)
    pkt[13] = _byte(dpi_y)
    pkt[14] = int(bool(mouse_invert_x))
    pkt[15] = int(bool(mouse_invert_y))
    return bytes(pkt)


def set_stick_curve_packet(stick: int, *, axis_ratio=50, deadzone_min=5,
                           deadzone_max=100, antideadzone_min=0, antideadzone_max=100,
                           is_circle=True, curve_preset="linear", curve_intensity=100,
                           curve_points=None) -> bytes:
    pkt = bytearray(32)
    pkt[0:4] = [0x07, 0x18, 0x02, 0x01]
    pkt[4] = 1 if stick else 0
    pkt[5] = 0x00
    pkt[6] = 1 if stick else 0
    pkt[7] = 0x00
    pkt[11] = 0x01 if is_circle else 0x00
    pkt[12] = _pct(axis_ratio)
    pkt[13] = _pct(deadzone_min)
    pkt[14] = _pct(antideadzone_min)
    pts = curve_points or [[30, 30], [50, 50], [70, 70]]
    flat = [max(0, min(100, int(v))) for pt in pts[:3] for v in pt[:2]]
    flat = (flat + [0] * 6)[:6]
    pkt[15:21] = bytes(flat)
    pkt[21] = _pct(deadzone_max)
    pkt[22] = _pct(antideadzone_max)
    pkt[23] = CURVE_TYPES.get(str(curve_preset).lower(), 0)
    pkt[24] = _pct(curve_intensity)
    return bytes(pkt)


def set_trigger_packet(trigger: int, *, hair_mode="off", hair_begin=10,
                       hair_end=20, deadzone_min=5, deadzone_max=95,
                       antideadzone_min=0, antideadzone_max=100,
                       curve_preset="linear", curve_intensity=100,
                       curve_points=None) -> bytes:
    pkt = bytearray(32)
    pkt[0:4] = [0x07, 0x13, 0x03, 0x01]
    pkt[4] = 1 if trigger else 0
    pkt[5] = HAIR_MODES.get(str(hair_mode).lower(), 0)
    pkt[6] = _pct(hair_begin)
    pkt[7] = _pct(hair_end)
    pkt[8] = _pct(deadzone_min)
    pkt[9] = _pct(antideadzone_min)
    pts = curve_points or [[30, 30], [50, 50], [70, 70]]
    flat = [max(0, min(100, int(v))) for pt in pts[:3] for v in pt[:2]]
    flat = (flat + [0] * 6)[:6]
    pkt[10:16] = bytes(flat)
    pkt[16] = _pct(deadzone_max)
    pkt[17] = _pct(antideadzone_max)
    pkt[18] = CURVE_TYPES.get(str(curve_preset).lower(), 0)
    pkt[19] = _pct(curve_intensity)
    return bytes(pkt)


def set_gyro_curve_packet(*, axis_ratio=50, deadzone_min=0, deadzone_max=100,
                          antideadzone_min=0, antideadzone_max=100,
                          curve_preset="linear", curve_intensity=100,
                          curve_points=None) -> bytes:
    pkt = bytearray(32)
    pkt[0:4] = [0x07, 0x16, 0x04, 0x01]
    pkt[4:10] = b"\0" * 6
    pkt[10] = _pct(axis_ratio)
    pkt[11] = _pct(deadzone_min)
    pkt[12] = _pct(antideadzone_min)
    pts = curve_points or [[30, 30], [50, 50], [70, 70]]
    flat = [max(0, min(100, int(v))) for pt in pts[:3] for v in pt[:2]]
    flat = (flat + [0] * 6)[:6]
    pkt[13:19] = bytes(flat)
    pkt[19] = _pct(deadzone_max)
    pkt[20] = _pct(antideadzone_max)
    pkt[21] = CURVE_TYPES.get(str(curve_preset).lower(), 0)
    pkt[22] = _pct(curve_intensity)
    return bytes(pkt)


def set_gyro_mapping_packet(*, output_mode="off", motion_mode="aim", axis_mode="yaw",
                            activate_button="b", activate_method="off",
                            x_sensitivity=50, y_sensitivity=50,
                            overlap=40, output_trigger_range=40,
                            invert_x=False, invert_y=False) -> bytes:
    pkt = bytearray(32)
    pkt[0:4] = [0x07, 0x0E, 0x04, 0x03]
    pkt[4] = _pct(overlap)
    pkt[5] = _pct(output_trigger_range)
    pkt[6] = GYRO_OUTPUT.get(str(output_mode).lower(), 0)
    pkt[7] = GYRO_MOTION.get(str(motion_mode).lower(), 0)
    pkt[8] = GYRO_AXIS.get(str(axis_mode).lower(), 0)
    pkt[9] = button_id(activate_button) & 0xFF
    pkt[10] = GYRO_METHOD.get(str(activate_method).lower(), 0)
    pkt[11] = _byte(x_sensitivity)
    pkt[12] = _byte(y_sensitivity)
    pkt[13] = int(bool(invert_x))
    pkt[14] = int(bool(invert_y))
    return bytes(pkt)


def set_vibration_packet(left, right, lt_mode=0, rt_mode=0, lt_level=0, rt_level=0) -> bytes:
    pkt = bytearray(32)
    pkt[0:4] = [0x07, 0x09, 0x06, 0x01]
    pkt[4] = _pct(left)
    pkt[5] = _pct(right)
    pkt[6] = 0 if not lt_mode else 1
    pkt[7] = 0 if not rt_mode else 1
    pkt[8] = _pct(lt_level)
    pkt[9] = _pct(rt_level)
    return bytes(pkt)


def set_light_packet(mode="static", brightness=100, speed=50) -> bytes:
    pkt = bytearray(32)
    pkt[0:4] = [0x07, 0x06, 0x07, 0x01]
    pkt[4] = _pct(brightness)
    pkt[5] = _pct(speed)
    pkt[6] = LIGHT_MODES.get(str(mode).lower(), 0)
    return bytes(pkt)


def set_light_color_packet(name: str, colors: list[tuple[int, int, int]]) -> bytes:
    name_id = LIGHT_NAMES.get(str(name).lower())
    if name_id is None:
        raise ValueError(f"Unknown light name: {name}")
    pkt = bytearray(32)
    pkt[0:4] = [0x07, 0x10, 0x07, 0x03]
    pkt[4] = name_id
    for i, (hue, sat, val) in enumerate(colors[:4]):
        pkt[5 + i * 3:8 + i * 3] = bytes([
            (max(0, min(360, int(hue))) * 255) // 360,
            _pct(sat), _pct(val),
        ])
    return bytes(pkt)


def set_dpad_packet(*, dpad_type="8way", swap="off", layout="xbox",
                    auto_onoff=True, fast_trigger=True, macro_switch="none") -> bytes:
    pkt = bytearray(32)
    pkt[0:4] = [0x07, 0x09, 0x09, 0x01]
    pkt[4] = DPAD_TYPES.get(str(dpad_type).lower(), 0)
    pkt[5] = DPAD_SWAP.get(str(swap).lower(), 0)
    pkt[6] = LAYOUTS.get(str(layout).lower(), 1)
    pkt[7] = 0 if auto_onoff else 1
    pkt[8] = 0 if fast_trigger else 1
    pkt[9] = button_id(macro_switch) & 0xFF if macro_switch not in (None, "", "none") else 0
    return bytes(pkt)


def rumble_test_packet(left, right, lt=0, rt=0) -> bytes:
    pkt = bytearray(32)
    pkt[0:4] = [0x07, 0x07, 0x0A, 0x04]
    pkt[4] = _pct(left)
    pkt[5] = _pct(right)
    pkt[6] = _pct(lt)
    pkt[7] = _pct(rt)
    return bytes(pkt)


def state_report_packet(mode=1) -> bytes:
    """0 off, 1 original/raw, 2 mapped.  The app uses this only for live input."""
    return bytes([0x07, 0x04, 0x0A, 0x02, int(mode) & 0xFF]) + bytes(27)


SAVE_PACKET = bytes([0x07, 0x03, 0x08, 0x03]) + bytes(28)
READ_DEVICE_INFO = bytes([0x07, 0x03, 0x0A, 0x01]) + bytes(28)


def _pct(value) -> int:
    return max(0, min(100, int(value)))


def _byte(value) -> int:
    return max(0, min(255, int(value)))
