"""A fake GameSir Super Nova for protocol and rollback tests.

The simulator answers the same request framing as a real dongle and keeps the
four verified blocks (key mappings, stick curves, trigger parameters and
vibration) as byte strings.  Failure injection lets tests prove that a failed
write is restored and that ``save_config_page`` is not sent.
"""
from __future__ import annotations

import socket
import threading

from tarantula_studio.core import supernova as sn
from tarantula_studio.core.transport import HidrawDevice, HidrawInfo

REPORT_SIZE = 32

KEY = sn.GET_KEY
STICK = sn.GET_STICK_CURVE
TRIGGER = sn.GET_TRIGGER
VIBRATION = sn.GET_VIBRATION
INFO = sn.GET_INFO
SAVE = sn.SAVE
VIBRATION_TEST = sn.SET_VIBRATION_TEST


def _factory_stick(side: int) -> bytearray:
    block = bytearray(sn.STICK_LEN)
    block[0] = side
    block[8] = 1  # factory type: raw/circle-capable, never inspected by tests
    block[sn.STICK_POINTS:sn.STICK_POINTS + 10] = bytes(
        sn.FACTORY_POINTS[sn.STICK_POINTS])
    return block


def _factory_trigger(side: int) -> bytearray:
    block = bytearray(sn.TRIG_LEN)
    block[0] = side
    block[sn.TRIG_POINTS:sn.TRIG_POINTS + 10] = bytes(
        sn.FACTORY_POINTS[sn.TRIG_POINTS])
    return block


def _info(device_type: int, battery: int, charging: bool) -> bytearray:
    data = bytearray(16)
    data[0] = device_type
    data[1] = 1
    data[2] = 6
    data[3:9] = bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])
    data[sn.INFO_BATTERY] = 0xFF if charging else battery
    return data


class FakeSuperNova:
    def __init__(self, *, device_type: int = 3, battery: int = 87,
                 charging: bool = False):
        self.device_type = device_type
        self._sock, self._peer = socket.socketpair()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._init_state(battery, charging)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # -- state ------------------------------------------------------------
    def _init_state(self, battery: int, charging: bool):
        self.info = _info(self.device_type, battery, charging)
        self.keys: dict[int, bytearray] = {}
        for _name, code in sn.REMAP_SOURCES:
            block = bytearray(sn.KEY_LEN)
            block[sn.KEY_SOURCE] = code
            block[sn.KEY_TYPE] = sn.KEY_TYPE_GAMEPAD
            block[sn.KEY_COUNT] = 1
            block[sn.KEY_CODES] = code
            self.keys[code] = block
        self.sticks = {0: _factory_stick(0), 1: _factory_stick(1)}
        self.triggers = {0: _factory_trigger(0), 1: _factory_trigger(1)}
        self.vibration = bytearray([75, 75, 75, 75, 0, 0])
        self.saved = 0
        self.writes: list[tuple[tuple[int, int], bytes]] = []
        self.attempts: list[tuple[tuple[int, int], bytes, bool]] = []
        self.vibration_tests: list[bytes] = []
        # Tests add a command tuple here to simulate a verification mismatch
        # or a rejected write once.
        self.mangle_reads: set[tuple[int, int]] = set()
        self.fail_sets: set[tuple[int, int]] = set()
        # Set to True to corrupt exactly the next read-back that follows a
        # successful vibration write.  Useful for testing rollback.
        self.mangle_verification_once = False

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
                               packet[3] if len(packet) > 3 else 0,
                               b"", status=1)
        command = (packet[2], packet[3])
        payload = bytes(packet[4:])
        with self._lock:
            getter = self._getters().get(command)
            if getter is not None:
                return self._reply(command[0], command[1], getter(payload))
            setter = self._setters().get(command)
            if setter is not None:
                if command in self.fail_sets:
                    self.fail_sets.remove(command)
                    self.attempts.append((command, payload, False))
                    return self._reply(command[0], command[1], b"", status=1)
                setter(payload)
                self.attempts.append((command, payload, True))
                return self._reply(command[0], command[1], b"", status=0)
        return self._reply(command[0], command[1], b"", status=1)

    @staticmethod
    def _reply(obj: int, op: int, data: bytes, status: int = 0) -> bytes:
        reply = bytearray(REPORT_SIZE)
        reply[0] = 0x06
        reply[1] = min(REPORT_SIZE, 4 + len(data) + (1 if not data else 0))
        reply[2] = obj
        reply[3] = op
        reply[4] = status
        if data:
            reply[4:4 + min(len(data), REPORT_SIZE - 4)] = data[:REPORT_SIZE - 4]
        return bytes(reply)

    def _getters(self):
        return {
            INFO: self._get_info,
            KEY: self._get_key,
            STICK: self._get_stick,
            TRIGGER: self._get_trigger,
            VIBRATION: self._get_vibration,
        }

    def _setters(self):
        return {
            sn.SET_KEY: self._set_key,
            sn.SET_STICK_CURVE: self._set_stick,
            sn.SET_TRIGGER: self._set_trigger,
            sn.SET_VIBRATION: self._set_vibration,
            VIBRATION_TEST: self._set_vibration_test,
            SAVE: self._set_save,
        }

    # -- getters ----------------------------------------------------------
    def _maybe_mangle(self, command, data: bytes) -> bytes:
        if command in self.mangle_reads:
            self.mangle_reads.remove(command)
            changed = bytearray(data)
            if changed:
                changed[0] ^= 0x01
            return bytes(changed)
        return bytes(data)

    def _get_info(self, _payload):
        return self._maybe_mangle(INFO, self.info)

    def _get_key(self, payload):
        code = payload[1] if len(payload) > 1 else 0
        block = self.keys.get(code, bytearray(sn.KEY_LEN))
        return self._maybe_mangle(KEY, block)

    def _get_stick(self, payload):
        side = payload[0] if payload else 0
        return self._maybe_mangle(STICK, self.sticks.get(side, bytearray(sn.STICK_LEN)))

    def _get_trigger(self, payload):
        side = payload[0] if payload else 0
        return self._maybe_mangle(
            TRIGGER, self.triggers.get(side, bytearray(sn.TRIG_LEN)))

    def _get_vibration(self, _payload):
        return self._maybe_mangle(VIBRATION, self.vibration)

    # -- setters ----------------------------------------------------------
    def _set_key(self, payload):
        code = payload[sn.KEY_SOURCE]
        self.keys[code] = bytearray(payload[:sn.KEY_LEN])
        self.writes.append((sn.SET_KEY, bytes(payload[:sn.KEY_LEN])))

    def _set_stick(self, payload):
        side = payload[0] if payload else 0
        self.sticks[side] = bytearray(payload[:sn.STICK_LEN])
        self.writes.append((sn.SET_STICK_CURVE, bytes(payload[:sn.STICK_LEN])))

    def _set_trigger(self, payload):
        side = payload[0] if payload else 0
        self.triggers[side] = bytearray(payload[:sn.TRIG_LEN])
        self.writes.append((sn.SET_TRIGGER, bytes(payload[:sn.TRIG_LEN])))

    def _set_vibration(self, payload):
        self.vibration = bytearray(payload[:6])
        self.writes.append((sn.SET_VIBRATION, bytes(payload[:6])))
        if self.mangle_verification_once:
            self.mangle_verification_once = False
            self.mangle_reads.add(VIBRATION)

    def _set_vibration_test(self, payload):
        self.vibration_tests.append(bytes(payload[:4]))

    def _set_save(self, _payload):
        self.saved += 1


class FakeHidraw(HidrawDevice):
    """HidrawDevice bound to a socketpair instead of /dev/hidraw."""

    def __init__(self, simulator: FakeSuperNova):
        self.simulator = simulator
        self.fd = simulator._sock.fileno()
        self.info = HidrawInfo(
            path="fake://supernova", vid=0x3537, pid=0x103E,
            name="Fake GameSir Super Nova", has_config_reports=True,
            readable=True, writable=True,
        )
        self._locked = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass

    def close(self):
        pass
