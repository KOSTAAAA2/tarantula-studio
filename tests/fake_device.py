"""A fake Tarantula Pro hidraw endpoint for protocol tests.

The simulator is deliberately simple: each writable register stores the exact
32-byte SET payload, and GET replies return that payload.  This mirrors how the
read helpers interpret the vendor reports and lets the tests exercise the real
framing, read, write and verify code without a physical controller.
"""
from __future__ import annotations

import copy
import socket
import threading

from tarantula_studio.core import keys
from tarantula_studio.core.defaults import factory_defaults
from tarantula_studio.core.transport import HidrawDevice, HidrawInfo

REPORT_SIZE = 32


def _packet_payload(packet: bytes) -> bytes:
    return packet[4:]


class FakeTarantula:
    def __init__(self, *, clamp_dpi: bool = False):
        self.clamp_dpi = clamp_dpi
        self._sock, self._peer = socket.socketpair()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._init_state()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # -- state ------------------------------------------------------------
    def _init_state(self):
        defaults = factory_defaults()
        self.info = bytes([1, 1, 23, 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 87,
                           1, 0, 0, 0, 0, 0])
        self.version = bytes([0, 1, 2, 3, 2, 0, 1, 1, 0, 2, 3, 0, 1, 0, 0, 0])
        self.dpad = _packet_payload(keys.set_dpad_packet(**{
            "dpad_type": defaults["dpad"]["dpad_type"],
            "swap": defaults["dpad"]["swap"],
            "layout": defaults["dpad"]["layout"],
            "auto_onoff": defaults["dpad"]["auto_onoff"],
            "fast_trigger": defaults["dpad"]["fast_trigger"],
            "macro_switch": defaults["dpad"]["macro_switch"],
        }))[:8]
        self.stick_mapping = []
        self.stick_curve = []
        for side, key in ((0, "stick_left"), (1, "stick_right")):
            stick = defaults[key]
            self.stick_mapping.append(_packet_payload(keys.set_stick_mapping_packet(
                side, invert_x=stick["invert_x"], invert_y=stick["invert_y"],
                mode=stick["mode"], overlap=stick["overlap_percent"],
                dpi_x=stick["mouse_dpi"], dpi_y=stick["mouse_dpi_y"],
                mouse_invert_x=stick["mouse_invert_x"],
                mouse_invert_y=stick["mouse_invert_y"]))[:15])
            self.stick_curve.append(_packet_payload(keys.set_stick_curve_packet(
                side, axis_ratio=stick["axis_ratio"],
                deadzone_min=stick["deadzone_min"], deadzone_max=stick["deadzone_max"],
                antideadzone_min=stick["antideadzone_min"],
                antideadzone_max=stick["antideadzone_max"],
                is_circle=stick["is_circle"], curve_preset=stick["curve_preset"],
                curve_intensity=stick["curve_intensity"],
                curve_points=stick["curve_points"]))[:24])
        self.trigger = []
        for side, key in ((0, "trigger_left"), (1, "trigger_right")):
            trigger = defaults[key]
            self.trigger.append(_packet_payload(keys.set_trigger_packet(
                side, hair_mode=trigger["hair_mode"],
                hair_begin=trigger["hair_trigger_begin"],
                hair_end=trigger["hair_trigger_end"],
                deadzone_min=trigger["deadzone_min"],
                deadzone_max=trigger["deadzone_max"],
                antideadzone_min=trigger["antideadzone_min"],
                antideadzone_max=trigger["antideadzone_max"],
                curve_preset=trigger["curve_preset"],
                curve_intensity=trigger["curve_intensity"],
                curve_points=trigger["curve_points"]))[:24])
        gyro = defaults["gyro"]
        self.gyro_curve = _packet_payload(keys.set_gyro_curve_packet(
            axis_ratio=gyro["axis_ratio"], deadzone_min=gyro["deadzone_min"],
            deadzone_max=gyro["deadzone_max"],
            antideadzone_min=gyro["antideadzone_min"],
            antideadzone_max=gyro["antideadzone_max"],
            curve_preset=gyro["curve_preset"],
            curve_intensity=gyro["curve_intensity"],
            curve_points=gyro["curve_points"]))[:20]
        self.gyro_mapping = _packet_payload(keys.set_gyro_mapping_packet(
            output_mode=gyro["output_mode"], motion_mode=gyro["motion_mode"],
            axis_mode=gyro["axis_mode"], activate_button=gyro["activate_button"],
            activate_method=gyro["activate_method"],
            x_sensitivity=gyro["x_sensitivity"], y_sensitivity=gyro["y_sensitivity"],
            overlap=gyro["overlap_percent"],
            output_trigger_range=gyro["output_trigger_range"],
            invert_x=gyro["invert_x"], invert_y=gyro["invert_y"]))[:15]
        lighting = defaults["lighting"]
        self.lighting = _packet_payload(keys.set_light_packet(
            mode=lighting["lighting_mode"], brightness=lighting["brightness"],
            speed=lighting["lighting_speed"]))[:4]
        self.colors = {
            keys.LIGHT_NAMES["home"]: _packet_payload(keys.set_light_color_packet(
                "home", [tuple(lighting["home_hsv"])]))[:16],
            keys.LIGHT_NAMES["panel"]: _packet_payload(keys.set_light_color_packet(
                "panel", [tuple(lighting["panel_hsv"])]))[:16],
            keys.LIGHT_NAMES["abxy"]: _packet_payload(keys.set_light_color_packet(
                "abxy", [tuple(c) for c in lighting["abxy_hsv"]]))[:16],
            keys.LIGHT_NAMES["bayx"]: _packet_payload(keys.set_light_color_packet(
                "bayx", [tuple(c) for c in lighting["bayx_hsv"]]))[:16],
        }
        rumble = defaults["rumble"]
        self.rumble = _packet_payload(keys.set_vibration_packet(
            rumble["left"], rumble["right"], rumble["lt_mode"],
            rumble["rt_mode"], rumble["lt_level"], rumble["rt_level"]))[:9]
        self.mappings: dict[int, bytearray] = {}
        self.macro_steps: dict[tuple[int, int], bytearray] = {}
        self.saved = 0
        self._getters = {
            (0x0A, 0x01): self._get_info,
            (0x84, 0x01): self._get_version,
            (0x09, 0x02): self._get_dpad,
            (0x02, 0x04): self._get_stick_mapping,
            (0x02, 0x02): self._get_stick_curve,
            (0x03, 0x02): self._get_trigger,
            (0x04, 0x02): self._get_gyro_curve,
            (0x04, 0x04): self._get_gyro_mapping,
            (0x06, 0x07): self._get_lighting,
            (0x07, 0x04): self._get_color,
            (0x06, 0x02): self._get_rumble,
            (0x05, 0x02): self._get_mapping,
            (0x01, 0x02): self._get_macro,
        }
        self._setters = {
            (0x09, 0x01): self._set_dpad,
            (0x02, 0x03): self._set_stick_mapping,
            (0x02, 0x01): self._set_stick_curve,
            (0x03, 0x01): self._set_trigger,
            (0x04, 0x01): self._set_gyro_curve,
            (0x04, 0x03): self._set_gyro_mapping,
            (0x07, 0x01): self._set_lighting,
            (0x07, 0x03): self._set_color,
            (0x06, 0x01): self._set_rumble,
            (0x05, 0x01): self._set_mapping,
            (0x01, 0x01): self._set_macro,
            (0x08, 0x03): self._set_save,
        }

    # -- endpoint ---------------------------------------------------------
    @property
    def device(self) -> HidrawDevice:
        return FakeHidraw(self)

    def stop(self):
        self._stop.set()
        try:
            self._peer.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self._thread.join(timeout=2.0)
        for sock in (self._sock, self._peer):
            try:
                sock.close()
            except OSError:
                pass

    def _run(self):
        self._peer.settimeout(0.1)
        buffer = b""
        while not self._stop.is_set():
            try:
                chunk = self._peer.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not chunk:
                break
            buffer += chunk
            while len(buffer) >= REPORT_SIZE:
                packet, buffer = buffer[:REPORT_SIZE], buffer[REPORT_SIZE:]
                reply = self._handle(packet)
                try:
                    self._peer.sendall(reply.ljust(REPORT_SIZE, b"\0"))
                except OSError:
                    return

    def _handle(self, packet: bytes) -> bytes:
        if len(packet) < 4 or packet[0] != 0x07:
            return self._reply(packet[2] if len(packet) > 2 else 0,
                               packet[3] if len(packet) > 3 else 0, b"", status=1)
        obj, op = packet[2], packet[3]
        payload = packet[4:]
        with self._lock:
            getter = self._getters.get((obj, op))
            if getter is not None:
                return self._reply(obj, op, getter(payload))
            setter = self._setters.get((obj, op))
            if setter is not None:
                setter(payload)
                return self._reply(obj, op, b"", status=0)
        return self._reply(obj, op, b"", status=1)

    @staticmethod
    def _reply(obj: int, op: int, data: bytes, status: int = 0) -> bytes:
        if not data and status == 0:
            data = b""
        reply = bytearray(REPORT_SIZE)
        reply[0] = 0x06
        reply[1] = min(REPORT_SIZE, 4 + len(data) + (1 if not data else 0))
        reply[2] = obj
        reply[3] = op
        reply[4] = status
        if data:
            reply[4:4 + min(len(data), REPORT_SIZE - 4)] = data[:REPORT_SIZE - 4]
        return bytes(reply)

    # -- getters ----------------------------------------------------------
    def _get_info(self, _payload):
        return self.info

    def _get_version(self, payload):
        return self.version

    def _get_dpad(self, _payload):
        return bytes(self.dpad)

    def _get_stick_mapping(self, payload):
        side = payload[0] if payload else 0
        return bytes(self.stick_mapping[1 if side else 0])

    def _get_stick_curve(self, payload):
        side = payload[0] if payload else 0
        return bytes(self.stick_curve[1 if side else 0])

    def _get_trigger(self, payload):
        side = payload[0] if payload else 0
        return bytes(self.trigger[1 if side else 0])

    def _get_gyro_curve(self, _payload):
        return bytes(self.gyro_curve)

    def _get_gyro_mapping(self, _payload):
        return bytes(self.gyro_mapping)

    def _get_lighting(self, _payload):
        return bytes(self.lighting)

    def _get_color(self, payload):
        name = payload[0] if payload else 0
        return bytes(self.colors.get(name, bytes(16)))

    def _get_rumble(self, _payload):
        return bytes(self.rumble)

    def _get_mapping(self, payload):
        source = payload[1] if len(payload) > 1 else 0
        record = self.mappings.get(source)
        if record is not None:
            return bytes(record)
        data = bytearray(16)
        data[6] = source
        data[8] = 0x00
        data[9] = 0x14
        data[10] = 0x01
        return bytes(data)

    def _get_macro(self, payload):
        source = payload[0] if payload else 0
        index = payload[1] if len(payload) > 1 else 0
        record = self.macro_steps.get((source, index))
        if record is not None:
            return bytes(record)
        data = bytearray(16)
        data[0] = source
        data[1] = index
        return bytes(data)

    # -- setters ----------------------------------------------------------
    def _set_dpad(self, payload):
        self.dpad = bytearray(payload[:8])

    def _set_stick_mapping(self, payload):
        side = payload[0] if payload else 0
        record = bytearray(payload[:15])
        if self.clamp_dpi:
            record[8] = min(record[8], 100)
            record[9] = min(record[9], 100)
        self.stick_mapping[1 if side else 0] = record

    def _set_stick_curve(self, payload):
        side = payload[0] if payload else 0
        self.stick_curve[1 if side else 0] = bytearray(payload[:24])

    def _set_trigger(self, payload):
        side = payload[0] if payload else 0
        self.trigger[1 if side else 0] = bytearray(payload[:24])

    def _set_gyro_curve(self, payload):
        self.gyro_curve = bytearray(payload[:20])

    def _set_gyro_mapping(self, payload):
        self.gyro_mapping = bytearray(payload[:15])

    def _set_lighting(self, payload):
        self.lighting = bytearray(payload[:4])

    def _set_color(self, payload):
        name = payload[0] if payload else 0
        self.colors[name] = bytearray(payload[:16])

    def _set_rumble(self, payload):
        self.rumble = bytearray(payload[:9])

    def _set_mapping(self, payload):
        source = payload[6] if len(payload) > 6 else 0
        self.mappings[source] = bytearray(payload[:16])

    def _set_macro(self, payload):
        source = payload[0] if payload else 0
        index = payload[1] if len(payload) > 1 else 0
        if index == 0xFF:
            for key in [key for key in self.macro_steps if key[0] == source]:
                del self.macro_steps[key]
        else:
            self.macro_steps[(source, index)] = bytearray(payload[:16])

    def _set_save(self, _payload):
        self.saved += 1


class FakeHidraw(HidrawDevice):
    """HidrawDevice bound to a socketpair instead of /dev/hidraw."""

    def __init__(self, simulator: FakeTarantula):
        self.simulator = simulator
        self.fd = simulator._sock.fileno()
        self.info = HidrawInfo(
            path="fake://tarantula", vid=0x3537, pid=0x1050,
            name="Fake Tarantula Pro", has_config_reports=True,
            readable=True, writable=True,
        )
        self._locked = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass

    def close(self):
        pass


def simulate(simulator: FakeTarantula):
    """Context manager helper: yields a fake device and stops the sim."""
    class _Ctx:
        def __enter__(self):
            return simulator.device

        def __exit__(self, exc_type, exc, tb):
            simulator.stop()

    return _Ctx()
