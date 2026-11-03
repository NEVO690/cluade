"""AVEN AI Desktop entry point."""

from __future__ import annotations

import sys


def main() -> int:
    if "--self-test" in sys.argv:  # used by CI to verify a packaged build
        from app.selftest import main as self_test

        return self_test(sys.argv)
    try:
        from app.application import run

        return run(sys.argv)
    except Exception as exc:  # show a useful message instead of failing silently
        try:
            from app.application import report_startup_failure

            report_startup_failure(exc)
        except Exception:
            if sys.stderr is not None:
                raise
        return 1


if __name__ == "__main__":
    sys.exit(main())
