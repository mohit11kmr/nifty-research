"""Central configuration - loads .env once and exposes parsed settings.

Every module should read secrets from here (or from os.environ after this
module is imported) instead of re-parsing .env with its own ad-hoc loader.
Without a central load, settings silently differ by import order (SECURITY
finding S-M2).
"""
import os

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

_ENV_LOADED = False


def load_env(force=False):
    """Load project .env into os.environ once (idempotent, never overwrites)."""
    global _ENV_LOADED
    if _ENV_LOADED and not force:
        return True
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if load_dotenv is not None and os.path.exists(env_file):
        load_dotenv(env_file, override=False)
    elif os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
    _ENV_LOADED = True
    return True


def get(key, default=""):
    """Read a config value, loading .env first if needed."""
    load_env()
    return os.environ.get(key, default)


load_env()
