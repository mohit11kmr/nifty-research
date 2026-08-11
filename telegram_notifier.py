"""Telegram notification helper for NIFTY Research alerts.

Usage:
    python telegram_notifier.py "Your alert message here"
    Or import and call send_alert(message)
"""
import os
import sys
import requests

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def send_alert(message, bot_token=None, chat_id=None):
    token = bot_token or BOT_TOKEN
    cid = chat_id or CHAT_ID
    if not token or not cid:
        print("[Telegram Alert Skipped] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set.")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": cid,
        "text": message,
        "parse_mode": "Markdown",
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print("[Telegram Alert Sent] Message delivered successfully.")
            return True
        else:
            print(f"[Telegram Alert Failed] Status {r.status_code}: {r.text}")
            return False
    except Exception as e:
        print(f"[Telegram Alert Error] {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        msg = " ".join(sys.argv[1:])
        send_alert(msg)
    else:
        print("Provide message to send: python telegram_notifier.py 'Test message'")
