"""Command-line tools: diagnostics, snapshots and the DPI experiment."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

from .core import boost
from .core import config as cfg
from .core import device as devmod
from .core import keys
from .core import mouse
from .core import supernova as snmod
from .core.transport import (
    DeviceError, DeviceNotFound, HidrawDevice, PermissionDenied,
    TransportError, diagnose, find_device, list_hidraw, udev_rule_text,
)


def _print_devices():
    nodes = list_hidraw()
    if not nodes:
        print("No hidraw devices found.")
        return
    for node in nodes:
        print(("  * " if node.supported else "    ") + node.describe())


def cmd_doctor(args) -> int:
    diag = diagnose()
    print("Tarantula Studio diagnostics")
    print("============================")
    print(f"root: {'yes' if diag['is_root'] else 'no'}")
    print(f"udev rule installed: {'yes' if diag['rule_installed'] else 'no'}")
    if diag["udev_files"]:
        for path in diag["udev_files"]:
            print(f"  {path}")
    print("\nUSB / hidraw devices:")
    _print_devices()
    selected = diag["selected"]
    print("\nSelected:", selected.describe() if selected else "none")
    if selected:
        print("report descriptor bytes:", len(selected.report_descriptor))
        if not (selected.readable and selected.writable):
            print("ACCESS: no read/write permission. Install the udev rule:")
            print(udev_rule_text())
    else:
        known = [d for d in diag["nodes"] if d.vid == 0x3537]
        if known:
            print("\nGameSir nodes were found but none is a supported config channel.")
            print("Switch to PC/XInput mode (Home + X for 2 s on some models) and replug.")
    print("\nMouse event nodes (for DPI measurement):")
    for node in mouse.find_mouse_nodes():
        print("  " + node.describe())
    if not mouse.find_mouse_nodes():
        print("  none found (the controller may be in a mode without a mouse interface)")
    print("\nSoftware DPI boost:")
    print(f"  /dev/uinput: {'available' if boost.uinput_available() else 'missing or not writable'}")
    print("  (needed for effective DPI above the firmware byte; see `boost --help`)")
    return 0


def cmd_read(args) -> int:
    try:
        with HidrawDevice() as dev:
            if snmod.probe(dev):
                config = snmod.read_config(
                    dev, progress=_progress if args.verbose else None)
                info = dict(config.get("info") or {})
                info["path"] = dev.info.path
                kind = "supernova"
                warnings = []
            else:
                config, info, warnings = devmod.read_all(
                    dev, progress=_progress if args.verbose else None)
                info = dict(info or {})
                info["path"] = dev.info.path
                kind = "tarantula"
    except (DeviceNotFound, PermissionDenied, DeviceError, TransportError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.save:
        if kind == "supernova":
            path = cfg.backup_supernova(config, "cli-read")
            print(f"Super Nova backup: {path}", file=sys.stderr)
        else:
            cfg.save_config(config)
            print(f"Saved to {cfg.CONFIG_FILE}", file=sys.stderr)

    if args.json:
        print(json.dumps({"kind": kind, "config": config, "info": info,
                          "warnings": warnings}, indent=2, ensure_ascii=False))
        return 0

    if kind == "supernova":
        battery = info.get("battery")
        battery_text = ("charging" if info.get("charging")
                        else (f"{battery}%" if battery is not None else "?"))
        print("Device: GameSir Super Nova / T4 Nova Pro")
        print(f"Firmware: {info.get('firmware', '?')}   battery: {battery_text}   "
              f"MAC: {info.get('mac', '?')}")
        remaps = config.get("remaps") or {}
        print("Remaps: " + (", ".join(f"{src}->{dst}" for src, dst in remaps.items())
                            or "factory"))
        vib = config.get("vibration") or {}
        print(f"Vibration: {vib.get('left')}/{vib.get('right')}")
        for key in ("stick_left", "stick_right", "trigger_left", "trigger_right"):
            dz = config.get(key) or {}
            print(f"{key}: deadzone {dz.get('deadzone_min')}-{dz.get('deadzone_max')}")
        print("Super Nova: only remaps, vibration and begin deadzones are "
              "writable from this app.")
        return 0

    print(f"Firmware: {info.get('firmware', '?')}   "
          f"battery: {'charging' if info.get('charging') else (str(info.get('battery')) + '%' if info.get('battery') is not None else '?')}   "
          f"MAC: {info.get('mac', '?')}")
    print(f"Sticks: left={config['stick_left']['mode']} dpi={config['stick_left']['mouse_dpi']}, "
          f"right={config['stick_right']['mode']} dpi={config['stick_right']['mouse_dpi']}")
    print(f"Light: {config['lighting']['lighting_mode']} "
          f"brightness={config['lighting']['brightness']} speed={config['lighting']['lighting_speed']}")
    print(f"Layout: {config['dpad']['layout']}  rumble: {config['rumble']['left']}/{config['rumble']['right']}")
    print(f"Mappings: {len(config['key_mappings'])}  macros: {len(config['macro_settings'])}")
    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"  - {warning}")
    return 0


def _progress(text: str):
    print(f"  {text}...", file=sys.stderr, flush=True)


def _refuse_supernova(dev, action: str) -> bool:
    """The T3 Pro packet layouts must never reach a Super Nova."""
    if not snmod.probe(dev):
        return False
    print(f"ERROR: this is a GameSir Super Nova / T4 Nova Pro, not a T3 Pro. "
          f"{action} uses Tarantula packets and was not sent.\n"
          f"Use `read`, `backup` or the GUI T4 Nova Pro page for the verified "
          f"Super Nova settings.", file=sys.stderr)
    return True


def cmd_dpi(args) -> int:
    side = 1 if args.side == "right" else 0
    values = []
    if args.sweep:
        values = [int(v.strip()) for v in args.sweep.split(",") if v.strip()]
    if args.value is not None:
        values.append(args.value)
    if not values:
        print("Specify a DPI value or --sweep 50,100,150,255", file=sys.stderr)
        return 2
    for value in values:
        if not 0 <= value <= 255:
            print(f"DPI must be 0..255 (got {value})", file=sys.stderr)
            return 2

    try:
        with HidrawDevice() as dev:
            if _refuse_supernova(dev, "DPI/mouse-mode configuration"):
                return 2
            before = devmod.read_stick(dev, side)
            print(f"Before: mode={before['mode']} dpi={before['mouse_dpi']} "
                  f"dpi_y={before['mouse_dpi_y']}")
            if args.backup:
                full, _info, _warnings = devmod.read_all(dev, progress=_progress)
                path = cfg.backup_config(full, "before-dpi")
                print(f"Full backup: {path}")
            for value in values:
                print(f"\nWriting DPI {value} ...")
                actual = devmod.quick_set_dpi(dev, side, value, enable_mouse=not args.no_mouse)
                print(f"Read back: mode={actual['mode']} dpi={actual['mouse_dpi']} "
                      f"dpi_y={actual['mouse_dpi_y']}")
                if actual["mouse_dpi"] != value:
                    print(f"!! Firmware reports {actual['mouse_dpi']} instead of {value}. "
                          f"The value may be clamped or wrapped.")
                if args.measure:
                    print(f"Move the {args.side} stick in a slow full circle for "
                          f"{args.measure:g} seconds (starting in 2 s)...")
                    time.sleep(2)
                    result = mouse.measure_motion(args.measure)
                    print(f"Mouse counts: dx={result['dx']} dy={result['dy']} "
                          f"events={result['events']} in {result['seconds']:g}s")
                    if result["errors"]:
                        print("Mouse read errors: " + "; ".join(result["errors"]))
                    if result["dx"] == 0 and result["dy"] == 0:
                        print("No movement seen. Is the stick in Mouse mode and the mouse "
                              "interface accessible? Try `doctor`.")
    except (DeviceNotFound, PermissionDenied, DeviceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


def cmd_apply(args) -> int:
    path = Path(args.file)
    data = json.loads(path.read_text(encoding="utf-8"))
    new_config = data.get("config", data)
    if not isinstance(new_config, dict):
        print("Invalid config file", file=sys.stderr)
        return 2
    try:
        with HidrawDevice() as dev:
            if _refuse_supernova(dev, "Applying a T3 Pro config"):
                return 2
            current, info, warnings = devmod.read_all(dev, progress=_progress)
            cfg.backup_config(current, "before-cli-apply")
            result = devmod.apply_config(dev, new_config, previous=current, progress=_progress)
            cfg.save_config(new_config)
            print(f"changed: {', '.join(result.changed) or 'nothing'}")
            for warning in result.warnings:
                print(f"WARNING: {warning}")
            for error in result.errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 0 if result.ok else 1
    except (DeviceNotFound, PermissionDenied, DeviceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


def cmd_restore(args) -> int:
    try:
        config = cfg.load_backup(args.file)
    except Exception as exc:
        print(f"Cannot read backup: {exc}", file=sys.stderr)
        return 2
    try:
        with HidrawDevice() as dev:
            if _refuse_supernova(dev, "Restoring a T3 Pro backup"):
                return 2
            current, _info, _warnings = devmod.read_all(dev, progress=_progress)
            result = devmod.apply_config(dev, config, previous=current, progress=_progress)
            cfg.save_config(config)
            print(f"changed: {', '.join(result.changed) or 'nothing'}")
            for warning in result.warnings:
                print(f"WARNING: {warning}")
            for error in result.errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 0 if result.ok else 1
    except (DeviceNotFound, PermissionDenied, DeviceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


def cmd_backup(args) -> int:
    try:
        with HidrawDevice() as dev:
            if snmod.probe(dev):
                config = snmod.read_config(dev, progress=_progress)
                path = cfg.backup_supernova(config, args.label)
                print(f"Super Nova backup: {path}")
                return 0
            config, info, warnings = devmod.read_all(dev, progress=_progress)
    except (DeviceNotFound, PermissionDenied, DeviceError, TransportError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    path = cfg.backup_config(config, args.label)
    print(f"Backup: {path}")
    return 0


def cmd_mouse_scan(args) -> int:
    nodes = mouse.find_mouse_nodes()
    if not nodes:
        print("No GameSir mouse event nodes found.")
        return 1
    for node in nodes:
        print(node.describe())
    return 0


def cmd_mouse_test(args) -> int:
    nodes = mouse.find_mouse_nodes()
    if not nodes:
        print("No GameSir mouse event nodes found.", file=sys.stderr)
        return 1
    print("Move the controller's mouse-mode stick now ...")
    result = mouse.measure_motion(args.seconds)
    print(json.dumps(result, indent=2))
    return 0 if result["events"] else 1


def cmd_boost(args) -> int:
    if args.seconds < 0:
        print("ERROR: --seconds cannot be negative.", file=sys.stderr)
        return 2
    factor = args.factor
    firmware_dpi = None
    if args.target is not None:
        try:
            with HidrawDevice() as dev:
                if _refuse_supernova(dev, "Software DPI boost"):
                    return 2
                stick = devmod.read_stick(
                    dev, 1 if args.side == "right" else 0)
                firmware_dpi = int(stick.get("mouse_dpi") or 0)
        except (DeviceNotFound, PermissionDenied, DeviceError, TransportError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        if firmware_dpi <= 0:
            print("ERROR: the controller reports firmware DPI 0; set a DPI first "
                  "or use --factor.", file=sys.stderr)
            return 2
        factor = args.target / firmware_dpi
    if factor is None:
        factor = 4.0
    if not math.isfinite(factor) or factor <= 0:
        print("ERROR: the boost factor must be a positive number.", file=sys.stderr)
        return 2

    booster = boost.MouseBooster(node=args.node, factor=factor)
    try:
        booster.start()
    except boost.MouseBoostError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    node = booster.node.path if booster.node else "?"
    effective = (f" (firmware DPI {firmware_dpi} x {factor:g} "
                 f"= {firmware_dpi * factor:.0f})" if firmware_dpi else "")
    print(f"Software mouse boost: {node} x{factor:g}{effective}")
    print("Press Ctrl+C to stop." if not args.seconds
          else f"Running for {args.seconds:g} s.")
    deadline = time.monotonic() + args.seconds if args.seconds else None
    last_report = 0.0
    try:
        while True:
            time.sleep(0.25)
            status = booster.status()
            if not status["running"]:
                print(f"ERROR: boost stopped: {status.get('last_error') or 'thread exited'}",
                      file=sys.stderr)
                return 1
            if deadline is not None and time.monotonic() >= deadline:
                break
            now = time.monotonic()
            if now - last_report >= 5.0 and not args.seconds:
                print(f"  events={status['events']} uptime={status['uptime']:.0f}s")
                last_report = now
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        status = booster.status()
        booster.stop()
    print(f"Boost stopped: {status['events']} events, "
          f"{status['uptime']:.0f} s.")
    return 0 if not status.get("last_error") else 1


def cmd_show_rule(args) -> int:
    print(udev_rule_text())
    return 0


def cmd_demo(args) -> int:
    print(json.dumps(cfg.factory_defaults(), indent=2, ensure_ascii=False))
    return 0


def cmd_gui(args) -> int:
    from .gui import run
    argv = ["--demo"] if getattr(args, "demo", False) else []
    return run(argv)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tarantula-studio",
        description="Linux configurator for GameSir T3 Pro / Super Nova (T4 Nova Pro)")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("doctor", help="check device, permissions and mouse nodes")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("read", help="read the whole controller configuration")
    p.add_argument("--json", action="store_true")
    p.add_argument("--save", action="store_true", help="save result as the local working config")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_read)

    p = sub.add_parser("dpi", help="set mouse-mode DPI (0..255) and read it back")
    p.add_argument("value", nargs="?", type=int)
    p.add_argument("--sweep", help="comma-separated values, e.g. 50,100,150,255")
    p.add_argument("--side", choices=("left", "right"), default="right")
    p.add_argument("--no-mouse", action="store_true", help="do not switch the stick to Mouse mode")
    p.add_argument("--measure", type=float, metavar="SECONDS",
                   help="measure relative mouse counts while you move the stick")
    p.add_argument("--backup", action="store_true")
    p.set_defaults(func=cmd_dpi)

    p = sub.add_parser("apply", help="apply a JSON config to the controller")
    p.add_argument("file")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("restore", help="restore a JSON backup")
    p.add_argument("file")
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("backup", help="read the controller and save a JSON backup")
    p.add_argument("--label", default="cli-backup")
    p.set_defaults(func=cmd_backup)

    p = sub.add_parser("mouse-scan", help="list the controller's mouse event nodes")
    p.set_defaults(func=cmd_mouse_scan)

    p = sub.add_parser("mouse-test", help="count relative mouse events")
    p.add_argument("--seconds", type=float, default=3.0)
    p.set_defaults(func=cmd_mouse_test)

    p = sub.add_parser(
        "boost", help="software-multiply the mouse interface above firmware DPI 255")
    target = p.add_mutually_exclusive_group()
    target.add_argument("--factor", type=float,
                        help="motion multiplier (default 4; fractions allowed)")
    target.add_argument("--target", type=int,
                        help="desired effective DPI, e.g. 1000 or 2000; "
                             "computes the factor from the firmware DPI")
    p.add_argument("--side", choices=("left", "right"), default="right")
    p.add_argument("--node", help="input event node; default: first GameSir mouse node")
    p.add_argument("--seconds", type=float, default=0.0,
                   help="run time; omit to run until Ctrl+C")
    p.set_defaults(func=cmd_boost)

    p = sub.add_parser("udev-rule", help="print the recommended udev rule")
    p.set_defaults(func=cmd_show_rule)

    p = sub.add_parser("demo", help="print the factory default config")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("gui", help="start the graphical interface")
    p.add_argument("--demo", action="store_true", help="stay offline, with local config only")
    p.set_defaults(func=cmd_gui)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
