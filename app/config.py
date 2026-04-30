import os
import base64
from cryptography.fernet import Fernet
from pydantic_settings import BaseSettings

DEFAULT_PAIRS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT",
    "ADA/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT", "UNI/USDT",
    "ATOM/USDT", "LTC/USDT", "BCH/USDT", "FIL/USDT", "APT/USDT",
    "ARB/USDT", "OP/USDT", "SUI/USDT", "TRX/USDT", "MATIC/USDT",
]


class Settings(BaseSettings):
    APP_NAME: str = "RSI Martin Trading Bot"
    SECRET_KEY: str = "CHANGE_THIS_IN_PRODUCTION_32CHARS_MIN"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    DATABASE_URL: str = "sqlite:///./trading.db"
    # Fernet encryption key for API secrets — auto-generated if not set
    ENCRYPTION_KEY: str = ""
    # Set to false in .env to close public registration
    ALLOW_REGISTER: bool = True

    class Config:
        env_file = ".env"


settings = Settings()

# Initialise Fernet key (persist in .env on first run)
_fernet_instance: Fernet | None = None


def get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance:
        return _fernet_instance

    key = settings.ENCRYPTION_KEY
    if not key:
        key = Fernet.generate_key().decode()
        settings.ENCRYPTION_KEY = key
        # Try to persist to .env if writable (works in dev; in Docker, set via env var instead)
        try:
            env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
            with open(env_path, "a") as f:
                f.write(f'\nENCRYPTION_KEY="{key}"\n')
        except (IOError, OSError):
            pass

    _fernet_instance = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet_instance


def encrypt_value(plaintext: str) -> str:
    return get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    return get_fernet().decrypt(ciphertext.encode()).decode()
