#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path


WORKDIR = Path(__file__).resolve().parent
REPORT_SCRIPT = WORKDIR / "astro_report.py"
TELEGRAM_SCRIPT = WORKDIR / "send_telegram.py"


def main() -> int:
    report = subprocess.run(
        ["python3", str(REPORT_SCRIPT)],
        check=True,
        capture_output=True,
        text=True,
    )
    send = subprocess.run(
        ["python3", str(TELEGRAM_SCRIPT)],
        input=report.stdout,
        text=True,
    )
    return send.returncode


if __name__ == "__main__":
    raise SystemExit(main())
