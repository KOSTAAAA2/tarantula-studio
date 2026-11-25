"""Software mouse gain for the Tarantula Pro's mouse mode.

The controller stores its mouse sensitivity in one byte (0..255), and the
official app caps it at 100.  Even the full byte is far below a modern gaming
mouse, so this module multiplies REL_X/REL_Y in software:

* open the controller's relative mouse event node,
* grab it exclusively with EVIOCGRAB (no double input),
* create a virtual mouse with /dev/uinput,
* forward buttons, wheel and SYN events unchanged, and scale relative motion.

The boost only works while this process (the GUI or the ``boost`` CLI command)
is running.  It needs read access to /dev/input/event* and write access to
/dev/uinput; the recommended udev rule in ``transport.udev_rule_text`` grants
both to the active desktop user.
"""
from __future__ import annotations

import errno
import fcntl
import math
import os
import select
import struct
import threading
import time

from .mouse import EV_REL, REL_WHEEL, REL_X, REL_Y, MouseNode, find_mouse_nodes

EV_SYN = 0x00
EV_KEY = 0x01
EV_MSC = 0x04

SYN_REPORT = 0x00
REL_HWHEEL = 0x06
REL_WHEEL_HI_RES = 0x0B
REL_HWHEEL_HI_RES = 0x0C

INPUT_EVENT = struct.Struct("llHHi")
INPUT_EVENT_SIZE = INPUT_EVENT.size

# linux/uinput.h
UINPUT_MAX_NAME_SIZE = 80
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
UI_DEV_SETUP = 0x405C5503
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_SET_RELBIT = 0x40045566

BUS_USB = 0x03
BTN_LEFT, BTN_RIGHT, BTN_MIDDLE = 0x110, 0x111, 0x112
BTN_SIDE, BTN_EXTRA, BTN_FORWARD, BTN_BACK, BTN_TASK = 0x113, 0x114, 0x115, 0x116, 0x117
MOUSE_BUTTONS = (BTN_LEFT, BTN_RIGHT, BTN_MIDDLE, BTN_SIDE, BTN_EXTRA,
                 BTN_FORWARD, BTN_BACK, BTN_TASK)
MOUSE_REL_AXES = (REL_X, REL_Y, REL_WHEEL, REL_HWHEEL,
                  REL_WHEEL_HI_RES, REL_HWHEEL_HI_RES)

EVIOCGRAB = 0x40044590


class MouseBoostError(RuntimeError):
    pass


class AxisScaler:
    """Scale one relative axis while carrying the fractional remainder.

    ``factor`` may be fractional.  The accumulator keeps the sum exact over a
    burst of events instead of rounding every tiny movement to zero.
    """

    def __init__(self, factor: float = 1.0):
        self.factor = float(factor)
        self._carry = 0.0

    def apply(self, value: int) -> int:
        self._carry += int(value) * self.factor
        out = math.trunc(self._carry)
        self._carry -= out
        return out

    def reset(self):
        self._carry = 0.0


def scale_relative(code: int, value: int, x_scaler: AxisScaler,
                   y_scaler: AxisScaler) -> int:
    """Scale REL_X/REL_Y; wheel and all other axes pass through."""
    if code == REL_X:
        return x_scaler.apply(value)
    if code == REL_Y:
        return y_scaler.apply(value)
    return value


def uinput_path() -> str:
    return os.environ.get("TARANTULA_STUDIO_UINPUT", "/dev/uinput")


def uinput_available() -> bool:
    path = uinput_path()
    return os.path.exists(path) and os.access(path, os.R_OK | os.W_OK)


def pick_mouse_node(nodes: list[MouseNode] | None = None) -> MouseNode | None:
    nodes = find_mouse_nodes() if nodes is None else list(nodes)
    return nodes[0] if nodes else None


class VirtualMouse:
    """A small uinput virtual mouse."""

    def __init__(self, name: str = "Tarantula Studio Virtual Mouse"):
        self.name = name
        self.fd: int | None = None

    def open(self):
        path = uinput_path()
        try:
            fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
        except FileNotFoundError as exc:
            raise MouseBoostError(
                f"{path} не найден. Загрузите модуль uinput: "
                f"sudo modprobe uinput") from exc
        except PermissionError as exc:
            raise MouseBoostError(
                f"Нет прав на {path}. Установите udev-правило (страница "
                f"«Диагностика») или добавьте пользователя в группу input.") from exc
        except OSError as exc:
            raise MouseBoostError(f"Не удалось открыть {path}: {exc}") from exc

        try:
            self._setup(fd)
        except Exception as exc:
            try:
                os.close(fd)
            except OSError:
                pass
            if isinstance(exc, MouseBoostError):
                raise
            raise MouseBoostError(f"uinput не принял виртуальную мышь: {exc}") from exc
        self.fd = fd

    def _setup(self, fd: int):
        for event_type in (EV_SYN, EV_KEY, EV_REL, EV_MSC):
            fcntl.ioctl(fd, UI_SET_EVBIT, event_type)
        for code in MOUSE_BUTTONS:
            fcntl.ioctl(fd, UI_SET_KEYBIT, code)
        for code in MOUSE_REL_AXES:
            fcntl.ioctl(fd, UI_SET_RELBIT, code)

        name = self.name.encode("utf-8")[:UINPUT_MAX_NAME_SIZE - 1]
        # struct input_id { __u16 bustype, vendor, product, version; }
        setup = struct.pack(
            "HHHH80sI", BUS_USB, 0x3537, 0x0001, 1, name, 0)
        try:
            fcntl.ioctl(fd, UI_DEV_SETUP, setup)
        except OSError as exc:
            # Kernels before 4.5 have no UI_DEV_SETUP.  Fall back to the old
            # name ioctl, which is fine for a simple relative device.
            if exc.errno not in (errno.EINVAL, errno.ENOTTY):
                raise
            ui_set_name = 0x40045563  # _IOW('U', 3, char[80])
            fcntl.ioctl(fd, ui_set_name, name.ljust(UINPUT_MAX_NAME_SIZE, b"\0"))
        fcntl.ioctl(fd, UI_DEV_CREATE)

    def emit(self, events) -> None:
        if self.fd is None:
            raise MouseBoostError("Виртуальная мышь не открыта")
        payload = bytearray()
        for event_type, code, value in events:
            payload += INPUT_EVENT.pack(0, 0, event_type, code, value)
        if payload:
            os.write(self.fd, payload)

    def close(self):
        if self.fd is not None:
            try:
                fcntl.ioctl(self.fd, UI_DEV_DESTROY)
            except OSError:
                pass
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


class MouseBooster:
    """Grab one mouse event node and emit scaled events through uinput."""

    def __init__(self, node: MouseNode | str | None = None, factor: float = 4.0):
        self.node = self._resolve_node(node)
        self.factor = max(0.1, float(factor))
        self._x = AxisScaler(self.factor)
        self._y = AxisScaler(self.factor)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._fd: int | None = None
        self._mouse: VirtualMouse | None = None
        self._grabbed = False
        self._lock = threading.Lock()
        self.events = 0
        self.last_error = ""
        self.started_at = 0.0

    @staticmethod
    def _resolve_node(node: MouseNode | str | None) -> MouseNode | None:
        if isinstance(node, MouseNode):
            return node
        if isinstance(node, str):
            for candidate in find_mouse_nodes():
                if candidate.path == node:
                    return candidate
            return MouseNode(path=node, name="mouse", vendor=0x3537,
                             product=0, phys="")
        return pick_mouse_node()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def set_factor(self, factor: float):
        self.factor = max(0.1, float(factor))
        self._x.factor = self.factor
        self._y.factor = self.factor

    def start(self):
        if self.running:
            return
        if self.node is None:
            raise MouseBoostError(
                "Интерфейс мыши контроллера не найден. Включите режим «Мышь (HID)» "
                "на стике и проверьте права на /dev/input/event*.")
        try:
            self._fd = os.open(self.node.path, os.O_RDONLY | os.O_NONBLOCK)
        except PermissionError as exc:
            raise MouseBoostError(
                f"Нет прав на {self.node.path}. Установите udev-правило.") from exc
        except OSError as exc:
            raise MouseBoostError(f"Не удалось открыть {self.node.path}: {exc}") from exc

        try:
            fcntl.ioctl(self._fd, EVIOCGRAB, 1)
            self._grabbed = True
        except OSError as exc:
            self._close_fd()
            raise MouseBoostError(
                f"Не удалось захватить {self.node.path}: {exc}. "
                f"Возможно, устройство уже захвачено другой программой.") from exc

        try:
            self._mouse = VirtualMouse()
            self._mouse.open()
        except Exception:
            self._ungrab()
            self._close_fd()
            raise

        self.events = 0
        self.last_error = ""
        self.started_at = time.monotonic()
        self._stop.clear()
        self._x.reset()
        self._y.reset()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="tarantula-mouse-boost")
        self._thread.start()

    def _run(self):
        try:
            while not self._stop.is_set():
                try:
                    ready, _, _ = select.select([self._fd], [], [], 0.1)
                except (OSError, ValueError):
                    break
                if not ready:
                    continue
                try:
                    data = os.read(self._fd, INPUT_EVENT_SIZE * 64)
                except BlockingIOError:
                    continue
                except OSError as exc:
                    if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                        self.last_error = f"Чтение {self.node.path}: {exc}"
                    break
                if not data:
                    break
                events = []
                for offset in range(0, len(data) - INPUT_EVENT_SIZE + 1,
                                    INPUT_EVENT_SIZE):
                    _sec, _usec, event_type, code, value = \
                        INPUT_EVENT.unpack_from(data, offset)
                    if event_type == EV_REL:
                        value = scale_relative(code, value, self._x, self._y)
                    if event_type in (EV_SYN, EV_KEY, EV_REL, EV_MSC):
                        events.append((event_type, code, value))
                if events:
                    try:
                        self._mouse.emit(events)
                    except OSError as exc:
                        self.last_error = f"uinput: {exc}"
                        break
                    with self._lock:
                        self.events += len(events)
        finally:
            self._ungrab()
            if self._mouse is not None:
                self._mouse.close()
                self._mouse = None
            self._close_fd()

    def _ungrab(self):
        if self._grabbed and self._fd is not None:
            try:
                fcntl.ioctl(self._fd, EVIOCGRAB, 0)
            except OSError:
                pass
        self._grabbed = False

    def _close_fd(self):
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def status(self) -> dict:
        with self._lock:
            events = self.events
        return {
            "running": self.running,
            "node": self.node.path if self.node else "",
            "factor": self.factor,
            "events": events,
            "last_error": self.last_error,
            "uptime": (time.monotonic() - self.started_at)
            if self.started_at and self.running else 0.0,
        }

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.5)
            self._thread = None
        else:
            self._ungrab()
            if self._mouse is not None:
                self._mouse.close()
                self._mouse = None
            self._close_fd()
