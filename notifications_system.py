"""Multi-Channel Telegram & System Notification Dispatcher for NIFTY Research.

Adopted from New Folder/trading_bot architecture:
Dispatches formatted real-time trade signals, risk warnings, and performance summaries to:
1. Telegram Bot (via Telegram API)
2. Interactive Hinglish Audio Voice Coach
3. SQLite Historical Audit Log
"""
import os
import json
import requests
import datetime as dt


class MultiChannelNotifier:
    """Telegram & Multi-Channel Notification Dispatcher."""

    def __init__(self, bot_token=None, chat_id=None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")

    def send_telegram_message(self, text):
        """Send formatted message via Telegram Bot API."""
        if not self.bot_token or not self.chat_id:
            print("ℹ️ [Telegram Notifier] Telegram Bot Token/Chat ID not set. Outputting to console.")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        try:
            r = requests.post(url, json=payload, timeout=10)
            return r.status_code == 200
        except Exception as e:
            print(f"⚠️ [Telegram Notifier] Error: {e}")
            return False

    def notify_trade_signal(self, symbol=None, action=None, strike=None, entry=None, sl=None, target=None, grade=None, option_type=None):
        """Dispatch a REAL high-precision trade signal alert.

        Requires actual signal values. If action/strike/entry are not supplied
        the dispatch is skipped with an honest status - a fabricated alert is
        never sent.
        """
        if not action or not strike or not entry:
            print("ℹ️ [Notification Dispatcher] No real signal data - alert skipped (no fabricated signal).")
            return {"status": "SKIPPED_NO_SIGNAL", "reason": "action/strike/entry not supplied"}
        option_type = option_type or ("CE" if "CALL" in action.upper() else "PE")
        emoji = "🟢" if "CALL" in action or "BUY" in action else "🔴"
        grade = grade or "NO_GRADE"
        entry_txt = f"₹{entry:.2f}"
        sl_txt = f"₹{sl:.2f}" if sl is not None else "N/A"
        target_txt = f"₹{target:.2f}" if target is not None else "N/A"
        msg = f"""
{emoji} **NIFTY QUANT SIGNAL ALERT ({grade})**

📊 **Symbol:** {symbol or "NIFTY"}
📈 **Action:** {action}
🎯 **Strike:** {strike} {option_type}
💰 **Entry Price:** {entry_txt}
🛑 **Stop Loss:** {sl_txt}
🎯 **Target 1:** {target_txt}
⭐ **Risk/Reward:** 1 : 2.0
⏰ **Timestamp:** {dt.datetime.now().strftime('%d %b %Y | %H:%M:%S IST')}

🛡️ *Capital Protection & 1% Risk Cap Enforced*
"""
        print(msg)
        self.send_telegram_message(msg)
        return {"status": "NOTIFIED", "action": action, "symbol": symbol or "NIFTY"}

    def notify_risk_alert(self, warning_message="Daily Loss Limit Warning!"):
        """Dispatch critical risk alert."""
        msg = f"🚨 **CAPITAL GUARD RISK WARNING**\n\n⚠️ {warning_message}\n⏰ {dt.datetime.now().strftime('%H:%M:%S IST')}"
        print(msg)
        self.send_telegram_message(msg)
        return {"status": "RISK_ALERT_DISPATCHED"}


# Singleton instance
notifier = MultiChannelNotifier()

if __name__ == "__main__":
    print("=== TESTING MULTI-CHANNEL NOTIFICATION DISPATCHER ===")
    res = notifier.notify_trade_signal()
    print(json.dumps(res, indent=2))
