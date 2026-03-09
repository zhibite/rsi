from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr


# ── Pair Config ───────────────────────────────────────────────────────────────

class PairConfigCreate(BaseModel):
    symbol: str
    is_enabled: bool = True
    first_order_amount: float = 20.0
    martin_multiplier: float = 2.0
    max_martin_levels: int = 5
    grid_drops: List[float] = [1.0, 2.0, 3.0, 4.0, 5.0]
    take_profit_pct: float = 1.3
    trailing_stop_pct: float = 0.3
    replenishment_retracement_pct: float = 0.3


class PairConfigUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    first_order_amount: Optional[float] = None
    martin_multiplier: Optional[float] = None
    max_martin_levels: Optional[int] = None
    grid_drops: Optional[List[float]] = None
    take_profit_pct: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    replenishment_retracement_pct: Optional[float] = None


class PairConfigOut(PairConfigCreate):
    id: int
    user_id: int
    lot_sz: Optional[float] = None

    class Config:
        from_attributes = True


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── API Config ─────────────────────────────────────────────────────────────────

class ApiConfigCreate(BaseModel):
    label: str = "Main Account"
    api_key: str
    api_secret: str
    api_passphrase: str
    is_test_mode: bool = True


class ApiConfigUpdate(BaseModel):
    label: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    api_passphrase: Optional[str] = None
    is_test_mode: Optional[bool] = None
    is_active: Optional[bool] = None


class ApiConfigOut(BaseModel):
    id: int
    label: str
    api_key: str
    is_test_mode: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Strategy Config ────────────────────────────────────────────────────────────

class StrategyConfigCreate(BaseModel):
    pairs: List[str] = []
    first_order_amount: float = 20.0
    martin_multiplier: float = 2.0
    take_profit_pct: float = 1.3
    trailing_stop_pct: float = 0.3
    replenishment_retracement_pct: float = 0.3
    rsi_overbought: float = 70.0
    overbought_min_profit_pct: float = 1.0
    overbought_rsi_step: float = 2.0
    overbought_profit_step: float = 0.1
    grid_drops: List[float] = [1.0, 2.0, 3.0, 4.0, 5.0]
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    max_martin_levels: int = 5
    max_open_positions: int = 5
    scan_interval: int = 1
    max_loss_pct: Optional[float] = None
    martin_cooldown_seconds: int = 0
    btc_drop_pct: float = 5.0
    btc_drop_minutes: int = 15
    btc_pause_minutes: int = 60


class StrategyConfigOut(BaseModel):
    id: int
    pairs: List[str]
    first_order_amount: float
    martin_multiplier: float
    take_profit_pct: float
    trailing_stop_pct: float
    replenishment_retracement_pct: float
    rsi_overbought: float
    overbought_min_profit_pct: float
    overbought_rsi_step: float
    overbought_profit_step: float
    grid_drops: List[float]
    rsi_period: int
    rsi_oversold: float
    max_martin_levels: int
    max_open_positions: int
    is_enabled: bool
    scan_interval: int
    max_loss_pct: Optional[float] = None
    martin_cooldown_seconds: int
    btc_drop_pct: float
    btc_drop_minutes: int
    btc_pause_minutes: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Positions & Orders ─────────────────────────────────────────────────────────

class OrderRecordOut(BaseModel):
    id: int
    symbol: str
    side: str
    amount_usdt: float
    quantity: float
    price: float
    martin_level: int
    status: str
    realized_pnl: Optional[float] = None
    note: Optional[str] = None
    timestamp: datetime

    class Config:
        from_attributes = True


class PositionOut(BaseModel):
    id: int
    symbol: str
    status: str
    avg_price: float
    total_quantity: float
    total_invested: float
    martin_level: int
    last_buy_price: float
    peak_price: float
    trailing_active: bool
    martin_trigger_price: Optional[float] = None
    martin_bounce_seen: bool = False
    realized_pnl: float
    sell_price: Optional[float]
    opened_at: datetime
    closed_at: Optional[datetime]
    orders: List[OrderRecordOut] = []
    # Enriched at query time from WS scanner
    current_price: Optional[float] = None
    pnl_pct: Optional[float] = None

    class Config:
        from_attributes = True


# ── Stats ──────────────────────────────────────────────────────────────────────

class StatsSummary(BaseModel):
    total_pnl: float
    total_trades: int
    win_trades: int
    loss_trades: int
    win_rate: float
    avg_pnl_per_trade: float
    total_invested: float
    total_fees: float          # estimated fees paid (buy + sell, 0.1% each)
    active_positions: int


class DailyPnl(BaseModel):
    date: str
    pnl: float
    trades: int


# ── Bot Log ───────────────────────────────────────────────────────────────────

class BotLogOut(BaseModel):
    id: int
    level: str
    message: str
    symbol: Optional[str]
    timestamp: datetime

    class Config:
        from_attributes = True
