"""
Core trading engine.

Each user with an enabled strategy runs an independent asyncio task that:
  1. Fetches RSI for each configured pair (1-min candles).
  2. Opens a new position when RSI < oversold threshold (no active position for that pair).
  3. Applies Martingale grid buys if price drops beyond each grid level from the previous buy.
  4. Sells when RSI reaches overbought threshold and profit meets dynamic minimum.
  5. Force-sells in low-balance mode when profit meets the low-balance minimum.

Martingale sizes (default, multiplier=2x):
  Level 0 (initial):  20 USDT
  Level 1:  40 USDT   triggers when price drops grid_drops[0] % from level-0 buy price
  Level 2:  80 USDT   triggers when price drops grid_drops[1] % from level-1 buy price
  Level 3: 160 USDT
  Level 4: 320 USDT
  Level 5: 640 USDT
  Max total: 1 260 USDT
"""

import asyncio
import logging
import time
import types
from collections import deque
from datetime import datetime

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import ApiConfig, BotLog, OrderRecord, PairConfig, Position, StrategyConfig
from ..config import decrypt_value
from .okx_client import FEE_RATE, OKXClient, floor_to_lot_sz
from .okx_ws_scanner import scanner as ws_scanner

logger = logging.getLogger(__name__)

# user_id → running asyncio Task
_running_bots: dict[int, asyncio.Task] = {}

# Real-time RSI cache: user_id → {symbol: rsi_value}
rsi_cache: dict[int, dict[str, float]] = {}

# Symbols currently under manual operation — bot skips these to avoid conflicts
# Structure: user_id → set of symbols
_manual_op_symbols: dict[int, set[str]] = {}

# ── 风控状态 ──────────────────────────────────────────────────────────────────
# BTC 价格历史 (unix_ts, price)，用于计算短时跌幅
_btc_price_history: deque = deque(maxlen=2000)
# BTC 熔断暂停到期时间戳：user_id → unix_ts
_circuit_breaker_until: dict[int, float] = {}
# 全局开单频率限制：user_id → 上次新开仓的 unix_ts
_last_entry_time: dict[int, float] = {}
# USDT 余额缓存：user_id → (cached_at_ts, available_usdt)，避免每次 scan 都打 API
_usdt_balance_cache: dict[int, tuple[float, float]] = {}
_BALANCE_CACHE_TTL = 30.0  # 余额缓存 30 秒
# 当前余额消耗比例缓存：user_id → consumed_pct，每轮 _process_pairs 更新一次
_balance_consumed_pct: dict[int, float] = {}

# WebSocket broadcast callback (set by main.py)
_ws_broadcast_fn = None


def set_ws_broadcast(fn):
    global _ws_broadcast_fn
    _ws_broadcast_fn = fn


def _fallback_pair_cfg(strategy: StrategyConfig, symbol: str):
    """Build a PairConfig-like namespace from StrategyConfig global defaults."""
    return types.SimpleNamespace(
        symbol=symbol,
        first_order_amount=strategy.first_order_amount,
        martin_multiplier=strategy.martin_multiplier,
        max_martin_levels=strategy.max_martin_levels,
        grid_drops=strategy.grid_drops or [1.0, 2.0, 3.0, 4.0, 5.0],
        take_profit_pct=getattr(strategy, "take_profit_pct", 1.3) or 1.3,
        trailing_stop_pct=getattr(strategy, "trailing_stop_pct", 0.3) or 0.3,
    )


async def _broadcast(user_id: int, event_type: str, data: dict):
    if _ws_broadcast_fn:
        await _ws_broadcast_fn(user_id, {"type": event_type, **data})


# ── Bot lifecycle ──────────────────────────────────────────────────────────────

def _is_btc_dropping(drop_pct: float, drop_minutes: int) -> bool:
    """判断 BTC 在过去 drop_minutes 分钟内是否下跌超过 drop_pct%。drop_pct<=0 表示关闭检测。"""
    if drop_pct <= 0:
        return False
    if len(_btc_price_history) < 2:
        return False
    now = time.time()
    cutoff = now - drop_minutes * 60
    window = [(t, p) for t, p in _btc_price_history if t >= cutoff]
    if len(window) < 2:
        return False
    oldest_price = window[0][1]
    latest_price = window[-1][1]
    drop = (oldest_price - latest_price) / oldest_price * 100
    return drop >= drop_pct


def start_bot(user_id: int):
    if user_id in _running_bots and not _running_bots[user_id].done():
        return  # already running

    # Register all enabled pair symbols with the WS scanner
    with SessionLocal() as db:
        pair_cfgs = db.query(PairConfig).filter_by(user_id=user_id, is_enabled=True).all()
        symbols = [pc.symbol for pc in pair_cfgs]
    if symbols:
        ws_scanner.add_pairs(symbols)
    ws_scanner.add_pairs(["BTC/USDT"])  # 熔断监测始终订阅 BTC

    task = asyncio.create_task(_run_bot(user_id))
    _running_bots[user_id] = task
    logger.info(f"Bot started for user {user_id}")


def stop_bot(user_id: int):
    task = _running_bots.pop(user_id, None)
    if task and not task.done():
        task.cancel()
        logger.info(f"Bot stopped for user {user_id}")


def bot_is_running(user_id: int) -> bool:
    t = _running_bots.get(user_id)
    return t is not None and not t.done()


def get_all_running_user_ids() -> list[int]:
    return [uid for uid, t in _running_bots.items() if not t.done()]


# ── DB helpers (sync, called in executor) ─────────────────────────────────────

def _db_log(db: Session, user_id: int, message: str, level: str = "INFO", symbol: str = None):
    entry = BotLog(user_id=user_id, level=level, message=message, symbol=symbol)
    db.add(entry)
    db.commit()


def _get_strategy(db: Session, user_id: int) -> StrategyConfig | None:
    return (
        db.query(StrategyConfig)
        .filter_by(user_id=user_id, is_enabled=True)
        .first()
    )


def _get_api_config(db: Session, user_id: int) -> ApiConfig | None:
    return (
        db.query(ApiConfig)
        .filter_by(user_id=user_id, is_active=True)
        .first()
    )


def _open_positions_by_symbol(db: Session, user_id: int) -> dict[str, Position]:
    positions = (
        db.query(Position)
        .filter_by(user_id=user_id, status="open")
        .all()
    )
    return {p.symbol: p for p in positions}


def _martin_order_amount(pair_cfg, level: int) -> float:
    return pair_cfg.first_order_amount * (pair_cfg.martin_multiplier ** level)


def _remaining_martin_budget(pair_cfg, current_level: int) -> float:
    max_levels = getattr(pair_cfg, "max_martin_levels", 0) or 0
    if current_level >= max_levels:
        return 0.0
    return sum(_martin_order_amount(pair_cfg, level) for level in range(current_level + 1, max_levels + 1))


def _new_position_seed_amount(pair_cfg, double_first: bool) -> float:
    return pair_cfg.first_order_amount * (2 if double_first else 1)


def _new_position_committed_usdt(pair_cfg, double_first: bool) -> float:
    return _new_position_seed_amount(pair_cfg, double_first) + _remaining_martin_budget(pair_cfg, current_level=0)


def _position_committed_usdt(pos: Position, pair_cfg) -> float:
    return pos.total_invested + _remaining_martin_budget(pair_cfg, current_level=pos.martin_level)


def _total_open_invested(open_positions: dict[str, Position]) -> float:
    return sum(pos.total_invested for pos in open_positions.values())


def _total_committed_exposure(
    open_positions: dict[str, Position],
    pair_cfg_map: dict[str, PairConfig],
    strategy: StrategyConfig,
) -> float:
    total = 0.0
    for symbol, pos in open_positions.items():
        pair_cfg = pair_cfg_map.get(symbol) or _fallback_pair_cfg(strategy, symbol)
        total += _position_committed_usdt(pos, pair_cfg)
    return total


def _create_position(
    db: Session, user_id: int, symbol: str,
    price: float, amount_usdt: float, qty: float, order_id: str
) -> Position:
    pos = Position(
        user_id=user_id,
        symbol=symbol,
        status="open",
        avg_price=price,
        total_quantity=qty,
        total_invested=amount_usdt,
        martin_level=0,
        last_buy_price=price,
        peak_price=price,
    )
    db.add(pos)
    db.flush()

    order = OrderRecord(
        user_id=user_id,
        position_id=pos.id,
        symbol=symbol,
        side="buy",
        amount_usdt=amount_usdt,
        quantity=qty,
        price=price,
        martin_level=0,
        exchange_order_id=order_id,
        status="filled",
        note="seed",
    )
    db.add(order)
    db.commit()
    db.refresh(pos)
    return pos


def _add_martin_buy(
    db: Session, pos: Position,
    price: float, amount_usdt: float, qty: float,
    martin_level: int, order_id: str
):
    new_qty = pos.total_quantity + qty
    new_invested = pos.total_invested + amount_usdt
    pos.avg_price = new_invested / new_qty
    pos.total_quantity = new_qty
    pos.total_invested = new_invested
    pos.martin_level = martin_level
    pos.last_buy_price = price

    order = OrderRecord(
        user_id=pos.user_id,
        position_id=pos.id,
        symbol=pos.symbol,
        side="buy",
        amount_usdt=amount_usdt,
        quantity=qty,
        price=price,
        martin_level=martin_level,
        exchange_order_id=order_id,
        status="filled",
        note=f"ladder_{martin_level}",
    )
    db.add(order)
    db.commit()


def _partial_close_position(
    db: Session, pos: Position,
    sell_price: float, sell_qty: float, order_id: str
) -> float:
    """Partially sell sell_qty coins. Position stays open; avg_price unchanged."""
    cost_basis = pos.avg_price * sell_qty
    proceeds = sell_qty * sell_price * (1 - FEE_RATE)
    partial_pnl = proceeds - cost_basis

    pos.total_quantity -= sell_qty
    pos.total_invested -= cost_basis   # keeps avg_price = total_invested / total_quantity

    order = OrderRecord(
        user_id=pos.user_id,
        position_id=pos.id,
        symbol=pos.symbol,
        side="sell",
        amount_usdt=proceeds,
        quantity=sell_qty,
        price=sell_price,
        martin_level=pos.martin_level,
        exchange_order_id=order_id,
        status="filled",
        realized_pnl=round(partial_pnl, 6),
        note="manual_sell",
    )
    db.add(order)
    db.commit()
    return round(partial_pnl, 6)


def _close_position(
    db: Session, pos: Position,
    sell_price: float, order_id: str, reason: str = "sell"
):
    proceeds = pos.total_quantity * sell_price * (1 - FEE_RATE)
    pnl = proceeds - pos.total_invested
    pos.status = "closed"
    pos.sell_price = sell_price
    pos.realized_pnl = round(pnl, 6)
    pos.closed_at = datetime.utcnow()
    pos.trailing_active = False

    order = OrderRecord(
        user_id=pos.user_id,
        position_id=pos.id,
        symbol=pos.symbol,
        side="sell",
        amount_usdt=proceeds,
        quantity=pos.total_quantity,
        price=sell_price,
        martin_level=pos.martin_level,
        exchange_order_id=order_id,
        status="filled",
        realized_pnl=round(pnl, 6),
        note=reason,
    )
    db.add(order)
    db.commit()


# ── Main bot loop ──────────────────────────────────────────────────────────────

async def _run_bot(user_id: int):
    logger.info(f"[Bot {user_id}] Task started")

    # Build OKXClient once for the entire bot session
    okx: OKXClient | None = None
    try:
        with SessionLocal() as db:
            api_cfg = _get_api_config(db, user_id)
        if not api_cfg:
            logger.warning(f"[Bot {user_id}] No active API config, stopping")
            return
        secret = decrypt_value(api_cfg.api_secret_encrypted)
        passphrase = decrypt_value(api_cfg.api_passphrase_encrypted)
        okx = OKXClient(
            api_key=api_cfg.api_key,
            api_secret=secret,
            api_passphrase=passphrase,
            is_test_mode=api_cfg.is_test_mode,
        )
    except Exception as exc:
        logger.error(f"[Bot {user_id}] Failed to initialize OKXClient: {exc}", exc_info=True)
        return

    try:
        while True:
            try:
                await _scan_cycle(user_id, okx)
            except asyncio.CancelledError:
                logger.info(f"[Bot {user_id}] Cancelled")
                return
            except Exception as exc:
                logger.error(f"[Bot {user_id}] Unexpected error: {exc}", exc_info=True)
                with SessionLocal() as db:
                    _db_log(db, user_id, f"Bot error: {exc}", level="ERROR")
                await asyncio.sleep(30)
    finally:
        if okx:
            await okx.close()


async def _scan_cycle(user_id: int, okx: OKXClient):
    with SessionLocal() as db:
        strategy = _get_strategy(db, user_id)
        if not strategy:
            await asyncio.sleep(60)
            return

        pair_cfgs = db.query(PairConfig).filter_by(user_id=user_id, is_enabled=True).all()
        scan_interval = strategy.scan_interval

    if pair_cfgs:
        ws_scanner.add_pairs([pc.symbol for pc in pair_cfgs])

    await _process_pairs(user_id, okx, strategy, pair_cfgs)
    await asyncio.sleep(scan_interval)


async def _refresh_balance_consumed_pct(
    user_id: int,
    okx: OKXClient,
    open_positions: dict,
) -> None:
    """每轮 scan 更新余额消耗比例缓存，供补仓冷却判断使用。"""
    total_invested = sum(pos.total_invested for pos in open_positions.values())
    now = time.time()
    cached = _usdt_balance_cache.get(user_id)
    if cached and now - cached[0] < _BALANCE_CACHE_TTL:
        available = cached[1]
    else:
        try:
            available = await okx.fetch_usdt_balance()
            _usdt_balance_cache[user_id] = (now, available)
        except Exception as e:
            logger.warning(f"[Bot {user_id}] Failed to fetch USDT balance: {e}")
            return  # 保留上次缓存值
    total = total_invested + available
    _balance_consumed_pct[user_id] = (total_invested / total * 100) if total > 0 else 0.0


def _is_low_balance(user_id: int, low_balance_pct: float) -> bool:
    """
    判断剩余可用余额是否低于阈值（即进入低余额模式）。
    low_balance_pct == 0 → 关闭低余额模式，始终返回 False
    low_balance_pct > 0  → 剩余余额% = (100 - consumed_pct) < low_balance_pct 时返回 True
    缓存未初始化时保守返回 False（不触发限制）。
    """
    if low_balance_pct <= 0:
        return False
    consumed = _balance_consumed_pct.get(user_id)
    if consumed is None:
        return False
    remaining = 100.0 - consumed
    return remaining < low_balance_pct


async def _process_pairs(
    user_id: int,
    okx: OKXClient,
    strategy: StrategyConfig,
    pair_cfgs: list,  # list[PairConfig]
):
    with SessionLocal() as db:
        open_positions = _open_positions_by_symbol(db, user_id)

    pair_cfg_map = {pc.symbol: pc for pc in pair_cfgs}
    rsi_cache.setdefault(user_id, {})
    max_pos = getattr(strategy, "max_open_positions", 5) or 5

    # ── 余额消耗比例（每轮更新，供补仓冷却判断使用）────────────────────────────
    await _refresh_balance_consumed_pct(user_id, okx, open_positions)

    # ── BTC 价格记录 & 熔断检查 ───────────────────────────────────────────────
    btc_price = ws_scanner.prices.get("BTC/USDT")
    if btc_price:
        _btc_price_history.append((time.time(), btc_price))

    btc_pause_minutes = getattr(strategy, "btc_pause_minutes", 0) or 0
    circuit_open = False
    if btc_pause_minutes > 0:
        cb_until = _circuit_breaker_until.get(user_id, 0)
        if time.time() < cb_until:
            circuit_open = True
        else:
            _circuit_breaker_until.pop(user_id, None)
            btc_drop_pct = getattr(strategy, "btc_drop_pct", 5.0) or 0.0
            btc_drop_minutes = getattr(strategy, "btc_drop_minutes", 15) or 15
            if _is_btc_dropping(btc_drop_pct, btc_drop_minutes):
                expire = time.time() + btc_pause_minutes * 60
                _circuit_breaker_until[user_id] = expire
                circuit_open = True
                with SessionLocal() as db:
                    _db_log(db, user_id,
                        f"⚡ BTC熔断触发: {btc_drop_minutes}min内跌幅≥{btc_drop_pct}%, "
                        f"暂停开新仓 {btc_pause_minutes}min",
                        level="WARNING")

    # 1. Manage all currently open positions (even if pair was removed from config)
    for symbol, pos_ref in list(open_positions.items()):
        ws_price = ws_scanner.prices.get(symbol)
        if ws_price is None:
            continue
        ws_rsi = ws_scanner.confirmed_rsi_values.get(symbol)
        rsi_cache[user_id][symbol] = ws_rsi or 0
        pc = pair_cfg_map.get(symbol) or _fallback_pair_cfg(strategy, symbol)
        try:
            with SessionLocal() as db:
                pos = db.query(Position).filter_by(id=pos_ref.id, status="open").first()
                if pos:
                    await _manage_position(
                        db, user_id, okx, strategy, pc, pos, ws_price, open_positions, ws_rsi
                    )
                    db.refresh(pos)
                    if pos.status == "closed":
                        open_positions.pop(symbol, None)  # 已平仓，从字典移除，让 len() 计数正确
                    else:
                        open_positions[symbol] = pos
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"[Bot {user_id}] Error managing {symbol}: {exc}", exc_info=True)
            with SessionLocal() as db:
                _db_log(db, user_id, f"Error managing {symbol}: {exc}", level="ERROR", symbol=symbol)

    # 2. Scan enabled pairs for new entry signals (熔断期间跳过)
    for pc in pair_cfgs:
        symbol = pc.symbol
        if symbol in open_positions:
            continue  # already managed above
        if circuit_open:
            continue  # BTC 熔断，暂停开新仓
        if getattr(strategy, "pause_new_entries", False):
            continue  # 手动停止开新仓
        try:
            ws_rsi = ws_scanner.confirmed_rsi_values.get(symbol)
            ws_price = ws_scanner.prices.get(symbol)
            if ws_rsi is None or ws_price is None:
                continue

            rsi_cache[user_id][symbol] = ws_rsi
            await _broadcast(user_id, "rsi_update", {"symbol": symbol, "rsi": ws_rsi, "price": ws_price})

            if ws_rsi > 0 and ws_rsi < strategy.rsi_oversold:
                if len(open_positions) >= max_pos:
                    logger.info(
                        f"[Bot {user_id}] {symbol} RSI={ws_rsi:.1f} oversold but "
                        f"max_open_positions={max_pos} reached (current={len(open_positions)}), skip"
                    )
                else:
                    entry_interval = getattr(strategy, "entry_interval_seconds", 0) or 0
                    if entry_interval > 0:
                        last_entry = _last_entry_time.get(user_id, 0)
                        elapsed = time.time() - last_entry
                        if elapsed < entry_interval:
                            logger.info(
                                f"[Bot {user_id}] {symbol} RSI={ws_rsi:.1f} oversold but "
                                f"entry interval not reached ({elapsed:.0f}s < {entry_interval}s), skip"
                            )
                            continue
                    double_first = getattr(strategy, "double_first_order", True)
                    seed_amount = _new_position_seed_amount(pc, double_first)
                    max_total_exposure = getattr(strategy, "max_total_exposure_usdt", 0.0) or 0.0
                    if max_total_exposure > 0:
                        projected_exposure = _total_open_invested(open_positions) + seed_amount
                        if projected_exposure > max_total_exposure:
                            logger.info(
                                f"[Bot {user_id}] {symbol} skipped: projected exposure "
                                f"{projected_exposure:.2f} > max_total_exposure_usdt={max_total_exposure:.2f}"
                            )
                            continue
                    max_total_committed = getattr(strategy, "max_total_committed_usdt", 0.0) or 0.0
                    if max_total_committed > 0:
                        projected_committed = (
                            _total_committed_exposure(open_positions, pair_cfg_map, strategy)
                            + _new_position_committed_usdt(pc, double_first)
                        )
                        if projected_committed > max_total_committed:
                            logger.info(
                                f"[Bot {user_id}] {symbol} skipped: projected committed exposure "
                                f"{projected_committed:.2f} > max_total_committed_usdt={max_total_committed:.2f}"
                            )
                            continue
                    with SessionLocal() as db:
                        _db_log(
                            db, user_id,
                            f"RSI={ws_rsi:.1f} < {strategy.rsi_oversold} — opening position "
                            f"({len(open_positions)+1}/{max_pos})",
                            symbol=symbol,
                        )
                    new_pos = await _open_new_position(user_id, okx, pc, symbol, ws_price, double_first)
                    if new_pos:
                        _last_entry_time[user_id] = time.time()
                        open_positions[symbol] = new_pos
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"[Bot {user_id}] Error processing {symbol}: {exc}", exc_info=True)
            with SessionLocal() as db:
                _db_log(db, user_id, f"Error on {symbol}: {exc}", level="ERROR", symbol=symbol)


async def _open_new_position(
    user_id: int,
    okx: OKXClient,
    pair_cfg,  # PairConfig or SimpleNamespace fallback
    symbol: str,
    current_price: float,
    double_first: bool = True,
) -> Position | None:
    amount_usdt = pair_cfg.first_order_amount * (2 if double_first else 1)
    try:
        order = await okx.create_market_buy_order(symbol, amount_usdt, hint_price=current_price)
        hint_qty = amount_usdt / current_price * (1 - FEE_RATE)
        fill_price, fill_qty = await okx.get_order_fill(order, symbol, hint_price=current_price, hint_qty=hint_qty)
        if fill_qty:
            # accFillSz is gross coins before fee; actual received = gross * (1 - fee)
            qty = fill_qty * (1 - FEE_RATE)
        else:
            qty = amount_usdt / fill_price * (1 - FEE_RATE)
            logger.warning(f"[Bot {user_id}] {symbol} accFillSz unavailable, using estimated qty={qty:.8f}")
        order_id = str(order.get("id", ""))

        with SessionLocal() as db:
            pos = _create_position(db, user_id, symbol, fill_price, amount_usdt, qty, order_id)
            _db_log(
                db, user_id,
                f"Opened position: {amount_usdt} USDT @ {fill_price}, qty={qty:.8f}",
                symbol=symbol,
            )
            await _broadcast(user_id, "position_opened", {
                "symbol": symbol, "price": fill_price, "amount_usdt": amount_usdt
            })
            return pos
    except Exception as e:
        err_msg = str(e)
        with SessionLocal() as db:
            _db_log(db, user_id, f"Failed to open position: {err_msg}", level="ERROR", symbol=symbol)
            # Auto-disable pair if instrument doesn't exist on exchange (e.g. not in paper trading)
            if "doesn't exist" in err_msg or "Instrument ID" in err_msg:
                pc = db.query(PairConfig).filter_by(user_id=user_id, symbol=symbol).first()
                if pc:
                    pc.is_enabled = False
                    db.commit()
                    _db_log(db, user_id,
                        f"Auto-disabled {symbol}: instrument not available on exchange",
                        level="WARNING", symbol=symbol)
        return None


async def _manage_position(
    db: Session,
    user_id: int,
    okx: OKXClient,
    strategy: StrategyConfig,
    pair_cfg,
    pos: Position,
    current_price: float,
    open_positions: dict[str, Position],
    rsi_val: float | None = None,
):
    # Skip if a manual operation is in progress for this symbol
    if pos.symbol in _manual_op_symbols.get(user_id, set()):
        return

    # ── Check take-profit / trailing stop ─────────────────────────────────────
    # Net proceeds after sell fee vs total invested
    net_proceeds = pos.total_quantity * current_price * (1 - FEE_RATE)
    unrealised_pct = (net_proceeds - pos.total_invested) / pos.total_invested * 100

    # ── 硬止损：浮亏超过阈值强制平仓 ──────────────────────────────────────────
    max_loss_pct = getattr(strategy, "max_loss_pct", None)
    if max_loss_pct and unrealised_pct <= -max_loss_pct:
        with SessionLocal() as db2:
            _db_log(db2, user_id,
                f"🛑 硬止损触发: 浮亏={unrealised_pct:.2f}% <= -{max_loss_pct}%, 强制平仓",
                level="WARNING", symbol=pos.symbol)
        await _execute_sell(db, user_id, okx, pos, current_price, "stop_loss",
                            lot_sz=getattr(pair_cfg, "lot_sz", None))
        return

    # ── 止盈出场 ─────────────────────────────────────────────────────────────

    # 路径A：利润驱动追踪止盈（与 RSI 无关）
    # 净利润 >= take_profit_pct → 激活追踪，记录/更新峰值价
    # 激活后从峰值回撤 >= trailing_stop_pct → 卖出
    take_profit_pct  = getattr(pair_cfg, "take_profit_pct",  1.3) or 1.3
    trailing_stop_pct = getattr(pair_cfg, "trailing_stop_pct", 0.3) or 0.3

    if unrealised_pct >= take_profit_pct:
        if not pos.trailing_active:
            pos.trailing_active = True
            pos.peak_price = current_price
            db.commit()
            with SessionLocal() as db2:
                _db_log(db2, user_id,
                    f"追踪止盈激活: profit={unrealised_pct:.2f}% >= {take_profit_pct}%, peak={current_price}",
                    symbol=pos.symbol)
        else:
            if current_price > pos.peak_price:
                pos.peak_price = current_price
                db.commit()

    if pos.trailing_active:
        drawdown_pct = (pos.peak_price - current_price) / pos.peak_price * 100
        if drawdown_pct >= trailing_stop_pct:
            with SessionLocal() as db2:
                _db_log(db2, user_id,
                    f"追踪止盈触发: 从峰值回撤={drawdown_pct:.2f}% >= {trailing_stop_pct}%, "
                    f"peak={pos.peak_price}, current={current_price}, profit={unrealised_pct:.2f}%",
                    symbol=pos.symbol)
            await _execute_sell(db, user_id, okx, pos, current_price, "trailing_stop",
                                lot_sz=getattr(pair_cfg, "lot_sz", None))
            return

    # 路径B：RSI 超买止盈
    # 阈值随马丁层级梯度降低（L0=70, L1=68, ...最低50），利润门槛随 RSI 强度线性递减
    rsi_overbought_base = getattr(strategy, "rsi_overbought", 70.0) or 70.0
    rsi_step = getattr(strategy, "overbought_rsi_step", None) or 2.0
    effective_overbought = max(50.0, rsi_overbought_base - rsi_step * pos.martin_level)
    overbought_min_profit = getattr(strategy, "overbought_min_profit_pct", None) or 1.0

    # 路径C：低余额强制止盈（余额紧张时只要达到低余额专用最低利润即立刻出场）
    low_balance_pct = getattr(strategy, "low_balance_pct", 0.0) or 0.0
    low_balance_min_profit = getattr(strategy, "low_balance_min_profit_pct", 0.6) or 0.6
    if _is_low_balance(user_id, low_balance_pct) and unrealised_pct >= low_balance_min_profit:
        with SessionLocal() as db2:
            _db_log(
                db2, user_id,
                f"低余额强制止盈: 剩余余额<{low_balance_pct}%, profit={unrealised_pct:.2f}% >= {low_balance_min_profit}% — 强制卖出",
                level="WARNING", symbol=pos.symbol,
            )
        await _execute_sell(db, user_id, okx, pos, current_price, "low_balance_sell",
                            lot_sz=getattr(pair_cfg, "lot_sz", None))
        return

    # 常规 RSI 超买止盈（利润门槛随 RSI 强度线性递减）
    # RSI 刚过阈值 → 要求完整利润 overbought_min_profit
    # RSI 达到 overbought_rsi_max → 要求降至 overbought_profit_floor
    # 中间线性插值：RSI 越强越积极出场
    if rsi_val is not None and rsi_val >= effective_overbought:
        rsi_max = getattr(strategy, "overbought_rsi_max", 85.0) or 85.0
        profit_floor = getattr(strategy, "overbought_profit_floor_pct", 0.5) or 0.5
        max_excess = max(rsi_max - effective_overbought, 1.0)
        ratio = min(1.0, (rsi_val - effective_overbought) / max_excess)
        required_profit = overbought_min_profit - ratio * (overbought_min_profit - profit_floor)
        if unrealised_pct >= required_profit:
            with SessionLocal() as db2:
                _db_log(
                    db2, user_id,
                    f"RSI={rsi_val:.1f} >= {effective_overbought:.1f} (L{pos.martin_level}) "
                    f"& profit={unrealised_pct:.2f}% >= {required_profit:.2f}% (动态门槛) — sell",
                    symbol=pos.symbol,
                )
            await _execute_sell(db, user_id, okx, pos, current_price, "overbought_sell",
                                lot_sz=getattr(pair_cfg, "lot_sz", None))
            return

    # ── Check Martingale grid buys ─────────────────────────────────────────────
    # 暂停补仓：用户手动冻结该交易对的马丁加仓
    if getattr(pair_cfg, "pause_martin", False):
        return

    # 补仓冷却：低余额时两次补仓之间必须间隔至少 martin_cooldown_seconds 秒
    martin_cooldown = getattr(strategy, "martin_cooldown_seconds", 0) or 0
    if martin_cooldown > 0 and pos.last_martin_at:
        elapsed = (datetime.utcnow() - pos.last_martin_at).total_seconds()
        if elapsed < martin_cooldown:
            return  # 冷却期内跳过补仓

    # ── 马丁补仓：跌幅达标 + RSI 超卖双重确认 ───────────────────────────────────
    # 仅当价格从上次买入跌幅 >= 网格阈值，且 RSI 同时处于超卖区时才补仓，
    # 避免在反弹途中或强势下跌初期盲目加仓
    grid_drops = pair_cfg.grid_drops or [1.0, 2.0, 3.0, 4.0, 5.0]
    if pos.martin_level < pair_cfg.max_martin_levels:
        drop_threshold = grid_drops[pos.martin_level] if pos.martin_level < len(grid_drops) else grid_drops[-1]
        drop_from_last = (pos.last_buy_price - current_price) / pos.last_buy_price * 100

        if drop_from_last >= drop_threshold:
            rsi_oversold = getattr(strategy, "rsi_oversold", 30.0) or 30.0
            if rsi_val is not None and rsi_val > 0 and rsi_val <= rsi_oversold:
                next_level = pos.martin_level + 1
                amount_usdt = pair_cfg.first_order_amount * (pair_cfg.martin_multiplier ** next_level)
                max_total_exposure = getattr(strategy, "max_total_exposure_usdt", 0.0) or 0.0
                if max_total_exposure > 0:
                    projected_exposure = _total_open_invested(open_positions) + amount_usdt
                    if projected_exposure > max_total_exposure:
                        logger.info(
                            f"[Bot {user_id}] {pos.symbol} Martin L{next_level} skipped: projected exposure "
                            f"{projected_exposure:.2f} > max_total_exposure_usdt={max_total_exposure:.2f}"
                        )
                        return
                await _execute_martin_buy(db, user_id, okx, pos, current_price, next_level, amount_usdt)


async def _execute_martin_buy(
    db: Session,
    user_id: int,
    okx: OKXClient,
    pos: Position,
    current_price: float,
    next_level: int,
    amount_usdt: float,
):
    try:
        order = await okx.create_market_buy_order(pos.symbol, amount_usdt, hint_price=current_price)
        hint_qty = amount_usdt / current_price * (1 - FEE_RATE)
        fill_price, fill_qty = await okx.get_order_fill(order, pos.symbol, hint_price=current_price, hint_qty=hint_qty)
        if fill_qty:
            # accFillSz is gross coins before fee; actual received = gross * (1 - fee)
            qty = fill_qty * (1 - FEE_RATE)
        else:
            qty = amount_usdt / fill_price * (1 - FEE_RATE)
            logger.warning(f"[Bot {user_id}] {pos.symbol} Martin L{next_level} accFillSz unavailable, using estimated qty={qty:.8f}")
        order_id = str(order.get("id", ""))
        _add_martin_buy(db, pos, fill_price, amount_usdt, qty, next_level, order_id)
        pos.last_martin_at = datetime.utcnow()
        db.commit()
        _db_log(
            db, user_id,
            f"Martin level {next_level}: bought {amount_usdt} USDT @ {fill_price} "
            f"(avg={pos.avg_price:.6f})",
            symbol=pos.symbol,
        )
        await _broadcast(user_id, "martin_buy", {
            "symbol": pos.symbol,
            "level": next_level,
            "price": fill_price,
            "amount_usdt": amount_usdt,
            "avg_price": pos.avg_price,
        })
    except Exception as e:
        _db_log(db, user_id, f"Martin buy failed at level {next_level}: {e}", level="ERROR", symbol=pos.symbol)


async def _execute_sell(
    db: Session,
    user_id: int,
    okx: OKXClient,
    pos: Position,
    current_price: float,
    reason: str,
    lot_sz: float | None = None,
):
    try:
        sell_qty = floor_to_lot_sz(pos.total_quantity, lot_sz)
        try:
            order = await okx.create_market_sell_order(pos.symbol, sell_qty, hint_price=current_price)
        except Exception as e:
            err = str(e).lower()
            if "insufficient" in err or "balance" in err:
                # Query actual exchange balance and retry with real qty
                currency = pos.symbol.split("/")[0]
                actual_qty = await okx.fetch_coin_balance(currency)
                actual_qty = floor_to_lot_sz(actual_qty, lot_sz)
                if actual_qty <= 0:
                    # No balance at all — position already gone on exchange, close DB only
                    _db_log(db, user_id,
                        f"[{reason}] Exchange balance=0 for {currency}, force-closing DB position",
                        level="WARNING", symbol=pos.symbol)
                    pos.status = "closed"
                    pos.sell_price = current_price
                    pos.realized_pnl = round(
                        pos.total_quantity * current_price * (1 - FEE_RATE) - pos.total_invested, 6
                    )
                    pos.closed_at = datetime.utcnow()
                    pos.trailing_active = False
                    db.commit()
                    await _broadcast(user_id, "position_closed", {
                        "symbol": pos.symbol, "sell_price": current_price,
                        "pnl": pos.realized_pnl, "reason": reason,
                    })
                    return
                # Retry with actual balance
                _db_log(db, user_id,
                    f"[{reason}] Retrying sell with actual balance: {actual_qty} (DB had {sell_qty})",
                    level="WARNING", symbol=pos.symbol)
                order = await okx.create_market_sell_order(pos.symbol, actual_qty, hint_price=current_price)
                sell_qty = actual_qty
            else:
                raise

        fill_price, _ = await okx.get_order_fill(order, pos.symbol, hint_price=current_price)
        order_id = str(order.get("id", ""))
        _close_position(db, pos, fill_price, order_id, reason=reason)
        pnl = pos.realized_pnl
        _db_log(
            db, user_id,
            f"Sold [{reason}] @ {fill_price} — PnL: {pnl:.4f} USDT",
            symbol=pos.symbol,
        )
        await _broadcast(user_id, "position_closed", {
            "symbol": pos.symbol,
            "sell_price": fill_price,
            "pnl": pnl,
            "reason": reason,
        })
    except Exception as e:
        _db_log(db, user_id, f"Sell failed [{reason}]: {e}", level="ERROR", symbol=pos.symbol)


# ── Manual operations (called from API router) ─────────────────────────────────

def _build_okx_client(user_id: int) -> OKXClient | None:
    """Build an OKXClient from the user's active ApiConfig. Returns None if not found."""
    with SessionLocal() as db:
        api_cfg = _get_api_config(db, user_id)
    if not api_cfg:
        return None
    secret = decrypt_value(api_cfg.api_secret_encrypted)
    passphrase = decrypt_value(api_cfg.api_passphrase_encrypted)
    return OKXClient(
        api_key=api_cfg.api_key,
        api_secret=secret,
        api_passphrase=passphrase,
        is_test_mode=api_cfg.is_test_mode,
    )


async def manual_sell(user_id: int, position_id: int, pct: int) -> dict:
    """Manually sell pct% (25/50/100) of a position.

    - pct=100: fully closes the position (status='closed'), strategy resets
    - pct=25/50: partial sell, position stays open with reduced quantity
    Returns a result dict or raises RuntimeError on failure.
    """
    with SessionLocal() as db:
        pos = db.query(Position).filter_by(id=position_id, user_id=user_id, status="open").first()
        if not pos:
            raise RuntimeError("Position not found or already closed")
        pair_cfg = db.query(PairConfig).filter_by(user_id=user_id, symbol=pos.symbol).first()
        lot_sz = pair_cfg.lot_sz if pair_cfg else None
        symbol = pos.symbol
        total_qty = pos.total_quantity

    sell_qty = floor_to_lot_sz(total_qty * pct / 100.0, lot_sz)
    if sell_qty <= 0:
        raise RuntimeError(f"Calculated sell quantity too small: {sell_qty}")

    okx = _build_okx_client(user_id)
    if not okx:
        raise RuntimeError("No active API config")

    _manual_op_symbols.setdefault(user_id, set()).add(symbol)
    try:
        order = await okx.create_market_sell_order(symbol, sell_qty)
        fill_price, _ = await okx.get_order_fill(order, symbol)
        order_id = str(order.get("id", ""))

        with SessionLocal() as db:
            pos = db.query(Position).filter_by(id=position_id, status="open").first()
            if not pos:
                raise RuntimeError("Position disappeared during sell")

            if pct == 100:
                _close_position(db, pos, fill_price, order_id, reason="manual_sell")
                pnl = pos.realized_pnl
                _db_log(db, user_id, f"Sold [manual_sell 100%] @ {fill_price} — PnL: {pnl:.4f} USDT", symbol=symbol)
                await _broadcast(user_id, "position_closed", {
                    "symbol": symbol, "sell_price": fill_price, "pnl": pnl, "reason": "manual_sell",
                })
                return {"symbol": symbol, "pct": 100, "fill_price": fill_price, "pnl": pnl}
            else:
                pnl = _partial_close_position(db, pos, fill_price, sell_qty, order_id)
                _db_log(db, user_id,
                    f"Partial sell [manual {pct}%] {sell_qty:.6f} @ {fill_price} — PnL: {pnl:.4f} USDT",
                    symbol=symbol)
                await _broadcast(user_id, "position_partial_sell", {
                    "symbol": symbol, "pct": pct, "sell_price": fill_price,
                    "pnl": pnl, "remaining_qty": pos.total_quantity,
                })
                return {"symbol": symbol, "pct": pct, "fill_price": fill_price, "pnl": pnl,
                        "remaining_qty": pos.total_quantity}
    finally:
        _manual_op_symbols.get(user_id, set()).discard(symbol)
        await okx.close()


async def manual_buy(user_id: int, position_id: int, amount_usdt: float) -> dict:
    """Manually add to an open position (replenishment buy).

    Recalculates avg_price and resets trailing stop so the strategy
    continues from the new cost basis.
    Returns a result dict or raises RuntimeError on failure.
    """
    with SessionLocal() as db:
        pos = db.query(Position).filter_by(id=position_id, user_id=user_id, status="open").first()
        if not pos:
            raise RuntimeError("Position not found or already closed")
        symbol = pos.symbol
        next_level = pos.martin_level + 1
        strategy = db.query(StrategyConfig).filter_by(user_id=user_id).first()
        open_positions = _open_positions_by_symbol(db, user_id)
        pair_cfg_map = {pc.symbol: pc for pc in db.query(PairConfig).filter_by(user_id=user_id).all()}
        max_total_exposure = getattr(strategy, "max_total_exposure_usdt", 0.0) or 0.0
        if max_total_exposure > 0:
            projected_exposure = _total_open_invested(open_positions) + amount_usdt
            if projected_exposure > max_total_exposure:
                raise RuntimeError(
                    f"Manual buy blocked: projected exposure {projected_exposure:.2f} "
                    f"> max_total_exposure_usdt={max_total_exposure:.2f}"
                )
        max_total_committed = getattr(strategy, "max_total_committed_usdt", 0.0) or 0.0
        if max_total_committed > 0:
            projected_committed = _total_committed_exposure(open_positions, pair_cfg_map, strategy) + amount_usdt
            if projected_committed > max_total_committed:
                raise RuntimeError(
                    f"Manual buy blocked: projected committed exposure {projected_committed:.2f} "
                    f"> max_total_committed_usdt={max_total_committed:.2f}"
                )

    okx = _build_okx_client(user_id)
    if not okx:
        raise RuntimeError("No active API config")

    _manual_op_symbols.setdefault(user_id, set()).add(symbol)
    try:
        order = await okx.create_market_buy_order(symbol, amount_usdt)
        hint_qty = amount_usdt / (await okx.fetch_last_price(symbol)) * (1 - FEE_RATE)
        fill_price, fill_qty = await okx.get_order_fill(order, symbol, hint_qty=hint_qty)
        qty = fill_qty * (1 - FEE_RATE) if fill_qty else amount_usdt / fill_price * (1 - FEE_RATE)
        order_id = str(order.get("id", ""))

        with SessionLocal() as db:
            pos = db.query(Position).filter_by(id=position_id, status="open").first()
            if not pos:
                raise RuntimeError("Position disappeared during buy")
            _add_martin_buy(db, pos, fill_price, amount_usdt, qty, next_level, order_id)
            # 补仓后重置追踪止盈，从新均价重新计算盈利阈值
            pos.trailing_active = False
            pos.peak_price = pos.avg_price
            db.commit()
            _db_log(db, user_id,
                f"Manual replenishment: {amount_usdt} USDT @ {fill_price} "
                f"(new avg={pos.avg_price:.6f}, level={next_level})",
                symbol=symbol)
            await _broadcast(user_id, "martin_buy", {
                "symbol": symbol, "level": next_level,
                "price": fill_price, "amount_usdt": amount_usdt, "avg_price": pos.avg_price,
            })
            return {
                "symbol": symbol, "fill_price": fill_price,
                "amount_usdt": amount_usdt, "qty": qty,
                "new_avg_price": pos.avg_price, "martin_level": next_level,
            }
    finally:
        _manual_op_symbols.get(user_id, set()).discard(symbol)
        await okx.close()
