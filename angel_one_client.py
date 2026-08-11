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
import sys
import json
import datetime as dt
import pyotp
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

# Auto-load local .env file if present
env_file = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_file):
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.environ.get("ANGEL_API_KEY", "")
CLIENT_CODE = os.environ.get("ANGEL_CLIENT_CODE", "")
PASSWORD = os.environ.get("ANGEL_PASSWORD", "")
TOTP_SECRET = os.environ.get("ANGEL_TOTP_SECRET", "")






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

    def login(self):
        """Authenticate and generate active JWT session."""
        if not self.client_code or not self.password or not self.totp_secret:
            print("[Angel One] Credentials incomplete (CLIENT_CODE, PASSWORD, or TOTP_SECRET missing).")
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
                print(f"[Angel One] Login Successful for Client: {self.client_code}")
                return True
            else:
                msg = data.get("message", "Unknown error") if data else "No response"
                print(f"[Angel One Login Failed] {msg}")
                return False
        except Exception as e:
            print(f"[Angel One Login Exception] {e}")
            return False

    def get_profile(self):
        """Fetch user profile information."""
        if not self.smart_api and not self.login():
            return None
        try:
            return self.smart_api.getProfile(self.refresh_token)
        except Exception as e:
            print(f"[Angel One Profile Error] {e}")
            return None

    def get_holdings(self):
        """Fetch equity holdings."""
        if not self.smart_api and not self.login():
            return None
        try:
            return self.smart_api.holding()
        except Exception as e:
            print(f"[Angel One Holdings Error] {e}")
            return None

    def get_positions(self):
        """Fetch open positions."""
        if not self.smart_api and not self.login():
            return None
        try:
            return self.smart_api.position()
        except Exception as e:
            print(f"[Angel One Positions Error] {e}")
            return None

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
        """Place trading order (NSE/NFO). Side: 'BUY' or 'SELL'."""
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
        if not self.auth_token or not self.feed_token:
            if not self.login():
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
    print(f"Angel One SmartAPI Client Initialized (API Key: {API_KEY})")
    if CLIENT_CODE and PASSWORD and TOTP_SECRET:
        if manager.login():
            print("Profile details:", manager.get_profile())
    else:
        print("Ready. Pass CLIENT_CODE, PASSWORD, and TOTP_SECRET to connect live.")
