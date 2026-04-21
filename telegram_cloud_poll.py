#!/usr/bin/env python3
import json
import os
import subprocess
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from send_telegram import send_message, split_message


WORKDIR = Path(__file__).resolve().parent
REPORT_SCRIPT = WORKDIR / "astro_report.py"
OFFSET_FILE = WORKDIR / ".telegram_offset"


def get_updates(token: str, offset: Optional[str]):
    params = {"timeout": 1}
    if offset:
        params["offset"] = offset
    url = f"https://api.telegram.org/bot{token}/getUpdates?{urlencode(params)}"
    request = Request(url, method="GET")
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def build_transit_reply() -> str:
    result = subprocess.run(
        ["python3", str(REPORT_SCRIPT)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def read_offset() -> Optional[str]:
    if not OFFSET_FILE.exists():
        return None
    raw = OFFSET_FILE.read_text(encoding="utf-8").strip()
    return raw or None


def write_offset(offset: str) -> None:
    OFFSET_FILE.write_text(f"{offset}\n", encoding="utf-8")


def run_git(args: list[str]) -> None:
    subprocess.run(["git", *args], check=True, cwd=WORKDIR)


def persist_offset(offset: str, branch: str) -> None:
    previous = read_offset()
    if previous == offset:
        return

    write_offset(offset)
    run_git(["config", "user.name", "github-actions[bot]"])
    run_git(["config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])
    run_git(["add", str(OFFSET_FILE.name)])
    diff = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=WORKDIR,
    )
    if diff.returncode == 0:
        return
    run_git(["commit", "-m", "Update Telegram offset"])
    subprocess.run(["git", "pull", "--rebase", "origin", branch], check=True, cwd=WORKDIR)
    run_git(["push", "origin", f"HEAD:{branch}"])


def command_reply(text: str) -> str:
    command = text.strip().split()[0].lower()
    if command == "/start":
        return "Bot en la nube activo.\n\nComandos:\n/transitos o transitos\n/ayuda"
    if command == "/ayuda":
        return "Comandos:\n/transitos o transitos - informe completo actual\n/ayuda"
    if command in {"/transitos", "transitos"}:
        return build_transit_reply()
    return "No reconozco ese comando. Proba con /transitos, transitos o /ayuda."


def main() -> int:
    telegram_token = os.environ["TELEGRAM_BOT_TOKEN"]
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    offset = read_offset()
    payload = get_updates(telegram_token, offset)
    updates = payload.get("result", [])
    last_offset = offset
    processed = 0
    for update in updates:
        update_id = update["update_id"]
        last_offset = str(update_id + 1)
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        text = message.get("text", "").strip()
        if not chat_id or not text:
            continue
        reply = command_reply(text)
        for chunk in split_message(reply):
            result = send_message(telegram_token, str(chat_id), chunk)
            if not result.get("ok"):
                raise RuntimeError(f"Telegram error: {result}")
        processed += 1
    if last_offset and last_offset != offset:
        persist_offset(last_offset, branch)
    print(f"processed={processed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
