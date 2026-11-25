from __future__ import annotations

import sys


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    from .cli import build_parser, main as cli_main
    parser = build_parser()
    # argparse subparsers are not in _actions; use the known command list.
    commands = {"doctor", "read", "dpi", "apply", "restore", "backup",
                "mouse-scan", "mouse-test", "boost", "udev-rule", "demo", "gui"}
    if argv and argv[0] in commands:
        return cli_main(argv)
    if argv and argv[0] in ("--help", "-h"):
        print("Tarantula Studio\n\nGUI:  python3 -m tarantula_studio\nCLI:  python3 -m tarantula_studio --help-cli\n")
        return 0
    if argv and argv[0] == "--help-cli":
        parser.print_help()
        return 0
    if argv and argv[0] == "--version":
        from . import __version__
        print(__version__)
        return 0
    from .gui import run
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
