"""Low-level hidraw transport and device discovery.

The Tarantula Pro exposes its configuration channel over a vendor HID
interface.  On Linux that is a /dev/hidraw node.  We speak the native
GameSir report protocol directly, with no vendor DLL and no libusb wrapper.

Only ordinary configuration reports are sent.  Firmware update, pairing,
calibration and device-identity commands are deliberately not implemented.
"""
from __future__ import annotations

import errno
import fcntl
import glob
import os
import select
import threading
import time
from dataclasses import dataclass, field

VENDOR_ID = 0x3537

# GameSir configuration identities.  0x103e is shared by the Tarantula Pro /
# T3 Pro and the Super Nova / T4 Nova Pro dongle; the device type from
# get_device_info tells them apart before any configuration is read.
CONFIG_PIDS = {
    0x103E: "GameSir 2.4 GHz dongle (T3 Pro / Super Nova)",
    0x1050: "Tarantula Pro (USB-C wired)",
    0x100E: "GameSir wired (T3 Pro / Super Nova input)",
}
# Identities we can recognise but do not speak the T3Pro config protocol to.
OTHER_PIDS = {
    0x103D: "Tarantula Pro 8K / other PC mode",
    0x103C: "Tarantula Pro (non-PC platform)",
    0x1042: "Tarantula Pro Xbox mode",
    0x1046: "Tarantula Pro wired (Xbox identity)",
    0x1008: "Tarantula Pro wired (alternate identity)",
    0x1007: "GameSir dongle (other mode)",
}

REPORT_SIZE = 32
READ_SIZE = 128
UNSOLICITED = (bytes([0x1A, 0x0A, 0x03]), bytes([0x05, 0x0A, 0x0D]))


class TransportError(RuntimeError):
    pass


class DeviceNotFound(TransportError):
    pass


class PermissionDenied(TransportError):
    pass


class DeviceError(TransportError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass
class HidrawInfo:
    path: str
    vid: int
    pid: int
    name: str
    has_config_reports: bool
    report_descriptor: bytes = field(repr=False, default=b"")
    readable: bool = False
    writable: bool = False
    driver: str = ""

    @property
    def supported(self) -> bool:
        return self.vid == VENDOR_ID and self.pid in CONFIG_PIDS and self.has_config_reports

    @property
    def product(self) -> str:
        return CONFIG_PIDS.get(self.pid) or OTHER_PIDS.get(self.pid) or self.name or "Unknown GameSir device"

    def describe(self) -> str:
        return (f"{self.path}  {self.vid:04x}:{self.pid:04x}  {self.product}  "
                f"config={'yes' if self.has_config_reports else 'no'}  "
                f"rw={'yes' if self.readable and self.writable else 'no'}")


def _read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _parse_hid_id(value: str) -> tuple[int, int]:
    """HID_ID=0003:00003537:0000103E -> (0x3537, 0x103e)."""
    parts = value.strip().split(":")
    if len(parts) != 3:
        return 0, 0
    try:
        return int(parts[1], 16), int(parts[2], 16)
    except ValueError:
        return 0, 0


def list_hidraw() -> list[HidrawInfo]:
    devices: list[HidrawInfo] = []
    for sys_path in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        node = "/dev/" + os.path.basename(sys_path)
        uevent = _read_text(os.path.join(sys_path, "device", "uevent"))
        fields = {}
        for line in uevent.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                fields[key] = value
        vid, pid = _parse_hid_id(fields.get("HID_ID", ""))
        desc = b""
        try:
            with open(os.path.join(sys_path, "device", "report_descriptor"), "rb") as fh:
                desc = fh.read()
        except OSError:
            pass
        has_config = b"\x85\x06" in desc and b"\x85\x07" in desc
        devices.append(HidrawInfo(
            path=node,
            vid=vid,
            pid=pid,
            name=fields.get("HID_NAME", ""),
            has_config_reports=has_config,
            report_descriptor=desc,
            readable=os.access(node, os.R_OK),
            writable=os.access(node, os.W_OK),
            driver=fields.get("DRIVER", ""),
        ))
    return devices


def find_device(prefer_wired: bool = False) -> HidrawInfo | None:
    """Find the best Tarantula Pro configuration node."""
    candidates = [d for d in list_hidraw() if d.supported]
    if not candidates:
        return None

    def rank(d: HidrawInfo):
        # Prefer a wired node only when asked; otherwise prefer the dongle.
        wired = d.pid in (0x1050, 0x100E)
        return (0 if (prefer_wired and wired) else 1, d.path)

    return sorted(candidates, key=rank)[0]


def diagnose() -> dict:
    nodes = list_hidraw()
    selected = find_device()
    udev_files = sorted(glob.glob("/etc/udev/rules.d/*gamesir*") +
                        glob.glob("/etc/udev/rules.d/*tarantula*"))
    return {
        "nodes": nodes,
        "selected": selected,
        "udev_files": udev_files,
        "is_root": os.geteuid() == 0,
        "rule_installed": bool(udev_files),
    }


def udev_rule_text() -> str:
    return (
        '# GameSir / Tarantula Studio - grant the logged-in desktop user access\n'
        'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="3537", TAG+="uaccess"\n'
        'SUBSYSTEM=="input", ATTRS{idVendor}=="3537", TAG+="uaccess"\n'
        '# Software DPI boost: a virtual mouse is created through /dev/uinput\n'
        'KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess"\n'
    )


class HidrawDevice:
    """One open hidraw conversation.  Use as a context manager."""

    _lock = threading.RLock()

    def __init__(self, info: HidrawInfo | None = None):
        self.info = info or find_device()
        self.fd: int | None = None
        self._locked = False

    def __enter__(self) -> "HidrawDevice":
        if self.info is None:
            raise DeviceNotFound(
                "GameSir controller not found. Connect it through the 2.4 GHz "
                "dongle or by USB in PC/XInput mode."
            )
        if not self.info.supported:
            raise DeviceNotFound(
                f"{self.info.path} is not a supported GameSir configuration interface "
                f"({self.info.product})."
            )
        HidrawDevice._lock.acquire()
        self._locked = True
        try:
            self.fd = os.open(self.info.path, os.O_RDWR | os.O_NONBLOCK)
            flags = fcntl.fcntl(self.fd, fcntl.F_GETFL)
            fcntl.fcntl(self.fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        except PermissionError as exc:
            self.close()
            raise PermissionDenied(
                f"No permission to open {self.info.path}. Install the udev rule from "
                f"the Diagnostics page (or run the app as root once)."
            ) from exc
        except OSError as exc:
            self.close()
            raise TransportError(f"Cannot open {self.info.path}: {exc}") from exc
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
        if self._locked:
            self._locked = False
            HidrawDevice._lock.release()

    # -- raw I/O ---------------------------------------------------------
    def _write(self, packet: bytes):
        if self.fd is None:
            raise TransportError("Device is not open")
        data = bytes(packet).ljust(REPORT_SIZE, b"\0")[:REPORT_SIZE]
        try:
            written = os.write(self.fd, data)
        except OSError as exc:
            raise TransportError(f"USB write failed: {exc}") from exc
        if written != REPORT_SIZE:
            raise TransportError(f"Short USB write: {written}/{REPORT_SIZE}")

    def _read(self, timeout: float) -> bytes | None:
        if self.fd is None:
            raise TransportError("Device is not open")
        try:
            ready, _, _ = select.select([self.fd], [], [], timeout)
        except (OSError, ValueError) as exc:
            raise TransportError(f"USB read failed: {exc}") from exc
        if not ready:
            return None
        try:
            data = os.read(self.fd, READ_SIZE)
        except BlockingIOError:
            return None
        except OSError as exc:
            if exc.errno in (errno.EIO, errno.ENODEV, errno.EPIPE):
                raise TransportError(f"Controller disconnected ({exc})") from exc
            raise TransportError(f"USB read failed: {exc}") from exc
        return data or None

    def drain(self, max_reads: int = 64):
        for _ in range(max_reads):
            if self._read(0.001) is None:
                break

    @staticmethod
    def _is_reply(data: bytes, obj: int, op: int) -> bool:
        return (len(data) >= 4 and data[0] == 0x06 and data[2] == obj and data[3] == op
                and data[1:4] not in UNSOLICITED)

    def _wait_reply(self, obj: int, op: int, timeout: float,
                    match: list[tuple[int, int]] | None = None) -> bytes:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = self._read(max(0.005, deadline - time.monotonic()))
            if data is None:
                continue
            if not self._is_reply(data, obj, op):
                continue
            if match and any(len(data) <= idx or data[idx] != value for idx, value in match):
                continue
            return data
        raise DeviceError(
            f"No reply to command obj=0x{obj:02x} op=0x{op:02x} within {timeout:.1f}s"
        )

    # -- protocol --------------------------------------------------------
    def set(self, obj: int, op: int, payload: bytes = b"", timeout: float = 0.8) -> int:
        """Send a SET command and return its status byte (0 = OK)."""
        self.drain()
        body = bytes([obj, op]) + bytes(payload)
        packet = bytes([0x07, len(body) + 1]) + body
        self._write(packet)
        reply = self._wait_reply(obj, op, timeout)
        status = reply[4] if len(reply) > 4 else 0xFF
        if status != 0:
            raise DeviceError(
                f"Controller rejected command {obj:02x}/{op:02x} with status 0x{status:02x}",
                status=status,
            )
        return status

    def get(self, obj: int, op: int, args: bytes = b"", *,
            req_len: int | None = None, timeout: float = 0.8,
            match: list[tuple[int, int]] | None = None) -> bytes:
        """Send a GET command and return the complete reply report.

        `req_len` reproduces the request length used by the vendor DLL.  The
        firmware tolerates a different length, but exact values keep captures
        comparable with the official app.
        """
        self.drain()
        body = bytes([obj, op]) + bytes(args)
        packet = bytes([0x07, req_len if req_len is not None else len(body) + 1]) + body
        self._write(packet)
        return self._wait_reply(obj, op, timeout, match=match)

    def save(self):
        self.set(0x08, 0x03)

    def set_state_report(self, mode: int):
        self.set(0x0A, 0x02, bytes([mode & 0xFF]))

    def rumble_test(self, left: int, right: int, lt: int = 0, rt: int = 0):
        self.set(0x0A, 0x04, bytes([
            max(0, min(100, int(left))), max(0, min(100, int(right))),
            max(0, min(100, int(lt))), max(0, min(100, int(rt))),
        ]))


def open_device(prefer_wired: bool = False) -> HidrawDevice:
    info = find_device(prefer_wired=prefer_wired)
    if info is None:
        raise DeviceNotFound(_not_found_text())
    return HidrawDevice(info)


def _not_found_text() -> str:
    all_nodes = list_hidraw()
    gamesir = [d for d in all_nodes if d.vid == VENDOR_ID]
    if not gamesir:
        return ("GameSir Tarantula Pro / Super Nova not found. Connect the controller "
                "through its 2.4 GHz dongle or by USB in PC/XInput mode "
                "(on some models hold Home + X for 2 seconds).")
    lines = ["GameSir device(s) found, but no supported configuration interface:"]
    for d in gamesir:
        extra = ""
        if d.pid in OTHER_PIDS:
            extra = f" ({OTHER_PIDS[d.pid]})"
        lines.append(f"  {d.path}: {d.vid:04x}:{d.pid:04x}{extra}, config reports: "
                     f"{'yes' if d.has_config_reports else 'no'}")
    lines.append("Switch the controller to PC/XInput mode and reconnect it.")
    return "\n".join(lines)
