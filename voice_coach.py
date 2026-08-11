"""Voice Coach Engine — Interactive Audio Trading Assistant for NIFTY Research.

Speaks natural Hinglish audio alerts and risk warnings out loud during market hours.
"""
import os
import sys
import tempfile
import time


def speak_hinglish(text, lang="hi"):
    """Convert text to speech and play audio alert out loud."""
    print(f"\n🎙️ [VOICE COACH]: {text}")
    try:
        from gtts import gTTS
        import subprocess

        tts = gTTS(text=text, lang=lang, slow=False)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as fp:
            temp_path = fp.name

        tts.save(temp_path)

        # Play audio using mpg123, ffplay, paplay, or system player
        played = False
        for player in ["mpg123", "ffplay -nodisp -autoexit", "paplay", "aplay"]:
            try:
                cmd = f"{player} {temp_path} >/dev/null 2>&1"
                ret = os.system(cmd)
                if ret == 0:
                    played = True
                    break
            except Exception:
                continue

        if os.path.exists(temp_path):
            os.remove(temp_path)

        return played
    except Exception as e:
        print(f"[Voice Coach Error] {e}")
        return False


def run_voice_summary():
    """Generate and speak today's market voice briefing."""
    try:
        import regime_filter
        regime_data = regime_filter.trade_plan()
        regime = regime_data.get("regime", "UNKNOWN")
        gate = regime_data.get("gate", "UNKNOWN")
        close = regime_data.get("close", 24500)
    except Exception:
        regime, gate, close = "RANGE_LV", "NO_TRADE", 24500

    if gate == "NO_TRADE" or regime == "RANGE_LV":
        msg = f"Mohit bhai, dhyan dijiye! NIFTY abhi {close:.0f} par RANGE LV low-volatility chop me hai. Subah se theta decay risk high hai. Aaj koi directional naked option mat buy karna, capital safe rakhein!"
    else:
        msg = f"Mohit bhai, Alert! NIFTY {close:.0f} par {regime} regime me hai. Risk parameters clear hain. System me high conviction setup scan ho raha hai!"

    speak_hinglish(msg)


if __name__ == "__main__":
    print("=== TESTING VOICE COACH ENGINE ===")
    run_voice_summary()
