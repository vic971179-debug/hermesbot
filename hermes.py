#!/usr/bin/env python3
"""Punto de entrada unificado del bot Hermes."""
import os
import sys
from send_telegram import ENV_FILE, load_dotenv

def main() -> int:
    load_dotenv(ENV_FILE)
    mode = sys.argv[1] if len(sys.argv) > 1 else "report"
    if mode == "report":
        from run_and_send_report import main as send_report
        return send_report()
    if mode == "poll":
        from telegram_cloud_poll import main as poll
        return poll()
    print(f"Modo desconocido: {mode}")
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
