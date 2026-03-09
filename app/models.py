from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean,
    DateTime, Text, ForeignKey, JSON,
)
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    api_configs = relationship("ApiConfig", back_populates="user", cascade="all, delete-orphan")
    strategy_configs = relationship("StrategyConfig", back_populates="user", cascade="all, delete-orphan")
    pair_configs = relationship("PairConfig", back_populates="user", cascade="all, delete-orphan")
    positions = relationship("Position", back_populates="user", cascade="all, delete-orphan")
    bot_logs = relationship("BotLog", back_populates="user", cascade="all, delete-orphan")


class ApiConfig(Base):
    __tablename__ = "api_configs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    label = Column(String(100), default="Main Account")
    api_key = Column(String(255), nullable=False)
    api_secret_encrypted = Column(Text, nullable=False)
    api_passphrase_encrypted = Column(Text, nullable=False)
    is_test_mode = Column(Boolean, default=True)  # paper-trading / simulated
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="api_configs")


class StrategyConfig(Base):
    __tablename__ = "strategy_configs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # Trading pairs (list of "XXX/USDT")
    pairs = Column(JSON, default=list)
    first_order_amount = Column(Float, default=20.0)     # first buy in USDT
    martin_multiplier = Column(Float, default=2.0)        # multiply per level
    take_profit_pct = Column(Float, default=1.3)          # % above avg cost to activate trailing
    trailing_stop_pct = Column(Float, default=0.3)        # % drawdown from peak to sell
    replenishment_retracement_pct = Column(Float, default=0.3)  # 补仓前从谷底反弹的幅度 %（0=立即补仓）
    rsi_overbought = Column(Float, default=70.0)           # 超买立即止盈 RSI 基准阈值 (L0)
    overbought_min_profit_pct = Column(Float, default=1.0) # 超买止盈最低净利润 % (L0)
    overbought_rsi_step = Column(Float, default=2.0)       # 每层 RSI 阈值降低步长
    overbought_profit_step = Column(Float, default=0.1)    # 每层最低利润降低步长 %
    # Price-drop % triggers for each Martingale level (list of 5 floats)
    grid_drops = Column(JSON, default=[1.0, 2.0, 3.0, 4.0, 5.0])
    rsi_period = Column(Integer, default=14)
    rsi_oversold = Column(Float, default=30.0)
    max_martin_levels = Column(Integer, default=5)
    max_open_positions = Column(Integer, default=5)  # B方案：最多同时持仓数
    is_enabled = Column(Boolean, default=False)
    scan_interval = Column(Integer, default=2)              # seconds between scans
    # ── 风险控制参数 ──────────────────────────────────────────────────────────
    max_loss_pct = Column(Float, nullable=True)             # 硬止损: 浮亏达此% 强制平仓 (None=关闭)
    martin_cooldown_seconds = Column(Integer, default=0)    # 补仓冷却: 两次补仓最小间隔秒数 (0=不限)
    btc_drop_pct = Column(Float, default=5.0)               # BTC熔断: 监测窗口内跌幅触发阈值 %
    btc_drop_minutes = Column(Integer, default=15)          # BTC熔断: 监测窗口时长 (分钟)
    btc_pause_minutes = Column(Integer, default=60)         # BTC熔断: 触发后暂停开新仓时长 (分钟, 0=关闭)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="strategy_configs")


class PairConfig(Base):
    """Per-pair martingale strategy configuration."""
    __tablename__ = "pair_configs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    symbol = Column(String(50), nullable=False)
    is_enabled = Column(Boolean, default=True)
    first_order_amount = Column(Float, default=20.0)
    martin_multiplier = Column(Float, default=2.0)
    max_martin_levels = Column(Integer, default=5)
    grid_drops = Column(JSON, default=lambda: [1.0, 2.0, 3.0, 4.0, 5.0])
    take_profit_pct = Column(Float, default=1.3)
    trailing_stop_pct = Column(Float, default=0.3)
    replenishment_retracement_pct = Column(Float, default=0.3)
    lot_sz = Column(Float, nullable=True)   # OKX instrument lotSz, e.g. 0.01 for FLOW/USDT
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="pair_configs")


class Position(Base):
    __tablename__ = "positions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    symbol = Column(String(20), nullable=False)
    status = Column(String(20), default="open")   # open | closed
    avg_price = Column(Float, default=0.0)
    total_quantity = Column(Float, default=0.0)
    total_invested = Column(Float, default=0.0)
    martin_level = Column(Integer, default=0)     # how many extra buys done
    last_buy_price = Column(Float, default=0.0)
    peak_price = Column(Float, default=0.0)       # highest price seen after profit target hit
    trailing_active = Column(Boolean, default=False)
    martin_trigger_price = Column(Float, nullable=True)   # 补仓触发价，用于”反弹确认”
    martin_bounce_seen = Column(Boolean, default=False)   # 是否已见到补仓回撤反弹
    last_martin_at = Column(DateTime, nullable=True)       # 最后一次补仓时间（用于冷却期）
    realized_pnl = Column(Float, default=0.0)
    sell_price = Column(Float, nullable=True)
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="positions")
    orders = relationship("OrderRecord", back_populates="position", cascade="all, delete-orphan")


class OrderRecord(Base):
    __tablename__ = "order_records"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=False)
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)   # buy | sell
    amount_usdt = Column(Float, default=0.0)
    quantity = Column(Float, default=0.0)
    price = Column(Float, default=0.0)
    martin_level = Column(Integer, default=0)
    exchange_order_id = Column(String(100), nullable=True)
    status = Column(String(20), default="filled")
    realized_pnl = Column(Float, nullable=True)   # sell orders only
    note = Column(String(50), nullable=True)       # seed | ladder_N | trailing_stop | manual_sell etc.
    timestamp = Column(DateTime, default=datetime.utcnow)

    position = relationship("Position", back_populates="orders")


class BotLog(Base):
    __tablename__ = "bot_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    level = Column(String(10), default="INFO")   # INFO | WARNING | ERROR
    message = Column(Text, nullable=False)
    symbol = Column(String(20), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="bot_logs")
