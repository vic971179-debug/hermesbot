#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


WORKDIR = Path(__file__).resolve().parent
ENV_FILE = WORKDIR / ".env"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def send_message(token: str, chat_id: str, text: str) -> dict:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = Request(url, data=payload, method="POST")
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def split_message(text: str, limit: int = 3800) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    remaining = text.strip()
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n\n", 0, limit)
        if cut == -1:
            cut = remaining.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    return [chunk for chunk in chunks if chunk]


def main() -> int:
    load_dotenv(ENV_FILE)
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        sys.stderr.write("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID\n")
        return 1
    text = sys.stdin.read().strip()
    if not text:
        sys.stderr.write("No hay contenido para enviar\n")
        return 1
    for chunk in split_message(text):
        result = send_message(token, chat_id, chunk)
        if not result.get("ok"):
            sys.stderr.write(json.dumps(result, ensure_ascii=False) + "\n")
            return 1
    sys.stdout.write("Mensajes enviados a Telegram\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
