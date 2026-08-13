"""Angel One SmartAPI Official Client Integration for NIFTY Research.

Implements official Angel One SmartAPI specs:
- Session generation via API Key, Client ID, PIN & TOTP (pyotp)
- JWT auth_token & feed_token extraction
- Historical Candle Data fetching (getCandleData)
- Portfolio Holdings & Positions tracking
- Order placement helper (placeOrder)
- SmartWebSocketV2 real-time streaming integration
"""
import os
import time
import pyotp
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

import config  # central .env load (SECURITY S-M2)

API_KEY = config.get("ANGEL_API_KEY", "")
CLIENT_CODE = config.get("ANGEL_CLIENT_CODE", "")
PASSWORD = config.get("ANGEL_PASSWORD", "")
TOTP_SECRET = config.get("ANGEL_TOTP_SECRET", "")

# Angel One JWT sessions are short-lived (~30-60 min). Re-authenticate
# proactively before expiry (SECURITY S-M3) so stale tokens are never reused.
TOKEN_TTL_SECONDS = int(config.get("ANGEL_TOKEN_TTL_SECONDS", "1500"))  # 25 min



class AngelOneManager:
    """Manager for Angel One SmartAPI sessions and endpoints."""

    def __init__(self, api_key=None, client_code=None, password=None, totp_secret=None):
        self.api_key = api_key or API_KEY
        self.client_code = client_code or CLIENT_CODE
        self.password = password or PASSWORD
        self.totp_secret = totp_secret or TOTP_SECRET
        self.smart_api = None
        self.auth_token = None
        self.refresh_token = None
        self.feed_token = None
        self.user_profile = None
        self.token_issued_at = None

    # --- session lifecycle (SECURITY S-M3) ---

    def _session_expired(self):
        """True when the current JWT session is older than TOKEN_TTL_SECONDS."""
        if self.smart_api is None:
            return True
        if self.token_issued_at is None:
            return True
        return time.time() - self.token_issued_at > TOKEN_TTL_SECONDS

    def _ensure_session(self):
        """Log in if there is no usable session; fail closed (False) otherwise."""
        if self.smart_api is not None and not self._session_expired():
            return True
        return self.login()

    def login(self):
        """Authenticate and generate a fresh JWT session."""
        if not self.client_code or not self.password or not self.totp_secret:
            print("[Angel One] Credentials incomplete (CLIENT_CODE, PASSWORD, or TOTP_SECRET missing).")
            self._reset_session()
            return False

        try:
            self.smart_api = SmartConnect(api_key=self.api_key)
            totp_code = pyotp.TOTP(self.totp_secret).now()
            data = self.smart_api.generateSession(self.client_code, self.password, totp_code)

            if data and data.get("status"):
                self.auth_token = data["data"]["jwtToken"]
                self.refresh_token = data["data"]["refreshToken"]
                self.feed_token = self.smart_api.getfeedToken()
                self.user_profile = data["data"]
                self.token_issued_at = time.time()
                print("[Angel One] Login Successful")
                return True
            else:
                msg = data.get("message", "Unknown error") if data else "No response"
                print(f"[Angel One Login Failed] {msg}")
                self._reset_session()
                return False
        except Exception as e:
            print(f"[Angel One Login Exception] {e}")
            self._reset_session()
            return False

    def _reset_session(self):
        self.smart_api = None
        self.auth_token = None
        self.refresh_token = None
        self.feed_token = None
        self.user_profile = None
        self.token_issued_at = None

    def logout(self):
        """Revoke the session server-side and drop all token state."""
        try:
            if self.smart_api is not None:
                self.smart_api.terminateSession(clientCode=self.client_code)
        except Exception as e:
            print(f"[Angel One Logout Error] {e}")
        finally:
            self._reset_session()
        return True

    def _data_call(self, fn_name, *args, retried=False, **kwargs):
        """Run one authenticated SmartAPI call, transparently re-authenticating
        once if the session expired mid-call (SECURITY S-M3). Fail closed."""
        if not self._ensure_session():
            return None
        try:
            return getattr(self.smart_api, fn_name)(*args, **kwargs)
        except Exception as e:
            print(f"[Angel One {fn_name} Error] {e}")
            if not retried and self._session_expired():
                if self.login():
                    try:
                        return getattr(self.smart_api, fn_name)(*args, **kwargs)
                    except Exception as e2:
                        print(f"[Angel One {fn_name} Retry Error] {e2}")
            return None

    def get_profile(self):
        """Fetch user profile information."""
        return self._data_call("getProfile", self.refresh_token)

    def get_holdings(self):
        """Fetch equity holdings."""
        return self._data_call("holding")

    def get_positions(self):
        """Fetch open positions."""
        return self._data_call("position")

    def get_candles(self, exchange, symbol_token, interval, from_date, to_date):
        """Fetch historical candle OHLCV data.

        interval choices: ONE_MINUTE, THREE_MINUTE, FIVE_MINUTE, FIFTEEN_MINUTE,
                         THIRTY_MINUTE, ONE_HOUR, ONE_DAY
        from_date / to_date format: 'YYYY-MM-DD HH:MM'
        """
        if not self.smart_api and not self.login():
            return None
        param = {
            "exchange": exchange,
            "symboltoken": str(symbol_token),
            "interval": interval,
            "fromdate": from_date,
            "todate": to_date,
        }
        try:
            res = self.smart_api.getCandleData(param)
            return res.get("data") if res and res.get("status") else None
        except Exception as e:
            print(f"[Angel One Candle Error] {e}")
            return None

    def place_order(self, symbol, symbol_token, exchange, side, quantity, price=0.0, order_type="MARKET", product_type="CARRYFORWARD"):
        """Place trading order (NSE/NFO). Side: 'BUY' or 'SELL'.

        DANGER PRIMITIVE (SECURITY S-L2): this is a REAL-MONEY order call with
        NO confirmation, NO authorization gate and NO capital-guard check at
        this boundary. It has zero callers today. Do NOT wire it into any
        automated flow until it gains an explicit authorize() step (e.g. an
        env-gated allowlist + capital-guard approval) - keep it manual-only.
        """
        if not self.smart_api and not self.login():
            return None
        param = {
            "variety": "NORMAL",
            "tradingsymbol": symbol,
            "symboltoken": str(symbol_token),
            "transactiontype": side.upper(),
            "exchange": exchange.upper(),
            "ordertype": order_type.upper(),
            "producttype": product_type.upper(),
            "duration": "DAY",
            "price": str(price),
            "squareoff": "0",
            "stoploss": "0",
            "quantity": str(quantity),
        }
        try:
            return self.smart_api.placeOrder(param)
        except Exception as e:
            print(f"[Angel One Order Error] {e}")
            return None

    def create_websocket(self, on_data_cb, on_open_cb=None, on_error_cb=None, on_close_cb=None):
        """Initialize SmartWebSocketV2 streaming instance."""
        if not self._ensure_session():
            return None

        ws = SmartWebSocketV2(
            auth_token=self.auth_token,
            api_key=self.api_key,
            client_code=self.client_code,
            feed_token=self.feed_token,
        )
        ws._on_data = on_data_cb
        if on_open_cb:
            ws._on_open = on_open_cb
        if on_error_cb:
            ws._on_error = on_error_cb
        if on_close_cb:
            ws._on_close = on_close_cb
        return ws


# Singleton global manager instance
manager = AngelOneManager()

if __name__ == "__main__":
    if CLIENT_CODE and PASSWORD and TOTP_SECRET:
        if manager.login():
            print("Profile details:", manager.get_profile())
    else:
        print("Ready. Pass CLIENT_CODE, PASSWORD, and TOTP_SECRET to connect live.")
