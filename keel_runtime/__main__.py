"""Lets `python3 -m keel_runtime connect ...` run this package uninstalled (spec FR-024)."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
