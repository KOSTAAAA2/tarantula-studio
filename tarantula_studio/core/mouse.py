"""Find and count relative mouse events from the controller's mouse interface.

The Tarantula Pro presents a HID mouse interface together with the gamepad.
When a stick is in Mouse mode, that interface emits REL_X/REL_Y events.  We
use those counts to verify empirically that DPI values above 100 take effect.
"""
from __future__ import annotations

import glob
import os
import select
import struct
import threading
import time
from dataclasses import dataclass

EV_REL = 0x02
REL_X = 0x00
REL_Y = 0x01
REL_WHEEL = 0x08

_INPUT_EVENT = struct.Struct("llHHi")
INPUT_EVENT_SIZE = _INPUT_EVENT.size


@dataclass
class MouseNode:
    path: str
    name: str
    vendor: int
    product: int
    phys: str
    rel_bits: int = 0

    def describe(self) -> str:
        return f"{self.path}  {self.name!r}  {self.vendor:04x}:{self.product:04x}"


def _parse_proc() -> list[dict]:
    try:
        with open("/proc/bus/input/devices", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return []
    blocks, current = [], {}
    for line in text.splitlines() + [""]:
        if not line.strip():
            if current:
                blocks.append(current)
                current = {}
            continue
        if len(line) > 2 and line[1] == ":":
            key, value = line[0], line[2:].strip()
            if key == "I":
                fields = {}
                for part in value.split():
                    if "=" in part:
                        k, v = part.split("=", 1)
                        fields[k] = v
                current["id"] = fields
            elif key in ("N", "P", "S", "H", "B"):
                current.setdefault(key, []).append(value)
    return blocks


def find_mouse_nodes(vendor: int = 0x3537) -> list[MouseNode]:
    nodes: list[MouseNode] = []
    for block in _parse_proc():
        ident = block.get("id", {})
        try:
            vid = int(ident.get("Vendor", "0"), 16)
            pid = int(ident.get("Product", "0"), 16)
        except ValueError:
            continue
        if vendor and vid != vendor:
            continue
        name = (block.get("N") or [""])[0].strip('"')
        handlers = " ".join(block.get("H") or [])
        bits = block.get("B") or []
        rel_bits = 0
        for line in bits:
            if line.startswith("REL="):
                try:
                    rel_bits = int(line.split("=", 1)[1].strip(), 16)
                except ValueError:
                    rel_bits = 0
                break
        if rel_bits:
            # The node must actually report relative X/Y.  This skips a
            # keyboard-only interface that happens to share the vendor id.
            is_mouse = (rel_bits & 0x3) == 0x3
        else:
            is_mouse = ("mouse" in name.lower() or "mouse" in handlers)
        if not is_mouse:
            continue
        for token in handlers.split():
            if token.startswith("event"):
                path = f"/dev/input/{token}"
                nodes.append(MouseNode(
                    path=path, name=name, vendor=vid, product=pid,
                    phys=(block.get("P") or [""])[0], rel_bits=rel_bits,
                ))
    return nodes


class MouseMotionMonitor:
    """Background reader for REL_X/REL_Y; safe to start/stop repeatedly."""

    def __init__(self, nodes: list[MouseNode] | None = None):
        self.nodes = nodes if nodes is not None else find_mouse_nodes()
        self.dx = 0
        self.dy = 0
        self.wheel = 0
        self.events = 0
        self.errors: list[str] = []
        self._fds: list[int] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return bool(self.nodes)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self.dx = self.dy = self.wheel = self.events = 0
        self.errors.clear()
        self._stop.clear()
        self._fds = []
        for node in self.nodes:
            try:
                fd = os.open(node.path, os.O_RDONLY | os.O_NONBLOCK)
                self._fds.append(fd)
            except OSError as exc:
                self.errors.append(f"{node.path}: {exc}")
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            if not self._fds:
                time.sleep(0.05)
                continue
            try:
                ready, _, _ = select.select(self._fds, [], [], 0.05)
            except (OSError, ValueError):
                break
            for fd in ready:
                try:
                    data = os.read(fd, INPUT_EVENT_SIZE * 64)
                except (BlockingIOError, OSError):
                    continue
                for offset in range(0, len(data) - INPUT_EVENT_SIZE + 1, INPUT_EVENT_SIZE):
                    _sec, _usec, etype, code, value = _INPUT_EVENT.unpack_from(data, offset)
                    if etype != EV_REL:
                        continue
                    with self._lock:
                        self.events += 1
                        if code == REL_X:
                            self.dx += value
                        elif code == REL_Y:
                            self.dy += value
                        elif code == REL_WHEEL:
                            self.wheel += value
        for fd in self._fds:
            try:
                os.close(fd)
            except OSError:
                pass
        self._fds = []

    def snapshot(self) -> tuple[int, int, int]:
        with self._lock:
            return self.dx, self.dy, self.events

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None


def measure_motion(seconds: float = 2.0) -> dict:
    monitor = MouseMotionMonitor()
    monitor.start()
    time.sleep(max(0.1, seconds))
    dx, dy, events = monitor.snapshot()
    monitor.stop()
    return {"dx": dx, "dy": dy, "events": events, "seconds": seconds,
            "nodes": [n.describe() for n in monitor.nodes], "errors": monitor.errors}
