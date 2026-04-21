#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

WORKDIR = Path(__file__).resolve().parent
REPORT_SCRIPT = WORKDIR / "astro_report.py"
TELEGRAM_SCRIPT = WORKDIR / "send_telegram.py"


def main() -> int:
    natal_file = sys.argv[1] if len(sys.argv) > 1 else None
    cmd = ["python3", str(REPORT_SCRIPT)]
    if natal_file:
        cmd.append(natal_file)
    report = subprocess.run(cmd, check=True, capture_output=True, text=True)
    send = subprocess.run(["python3", str(TELEGRAM_SCRIPT)], input=report.stdout, text=True)
    return send.returncode


if __name__ == "__main__":
    raise SystemExit(main())
