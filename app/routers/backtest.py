"""
Backtest router
===============
使用 OKX 历史 K 线数据对已配置的交易对进行策略回测。
- 默认使用 1h K 线，回测 180 天
- 每个交易对使用各自的 PairConfig 参数（首单金额、马丁倍率、网格跌幅等）
- RSI 入场/出场阈值使用 StrategyConfig 中的全局配置
- 后台异步任务 + 轮询状态接口
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta

import ccxt.async_support as ccxt
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import PairConfig, StrategyConfig, User
from ..services.rsi_calculator import calculate_rsi_series

router = APIRouter(prefix="/api/backtest", tags=["backtest"])
logger = logging.getLogger(__name__)

FEE_RATE = 0.001

# 内存中存储任务状态（单进程单用户够用）
_tasks: dict[str, dict] = {}


# ── 请求参数 ──────────────────────────────────────────────────────────────────

class BacktestParams(BaseModel):
    timeframe: str = "1m"           # 1m / 15m / 1h（策略实盘使用 1m）
    days: int = 30                  # 回测天数（1m K线数据量大，默认30天）
    rsi_period: int = 14
    rsi_oversold: float = 30.0      # 入场 RSI 阈值
    rsi_overbought: float = 70.0    # 超买出场基础阈值（梯度：每层 -2）
    overbought_min_profit_pct: float = 0.3  # RSI 超买出场最低涨幅要求 %（需高于双边手续费 0.2%）
    first_order_amount: float = 20.0        # 首单额度（纯RSI模式使用；马丁模式使用各对自身配置）
    enable_martin: bool = True      # False = 纯RSI信号模式（禁用马丁补仓）


def _tf_ms(tf: str) -> int:
    return {"1m": 60_000, "5m": 300_000, "15m": 900_000,
            "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}.get(tf, 3_600_000)


# ── 逐 K 线模拟马丁策略 ───────────────────────────────────────────────────────

def _simulate(
    closes: list[float],
    rsis: list[float | None],
    params: BacktestParams,
    pc: PairConfig,
) -> dict | None:
    """对单个交易对的历史 K 线进行策略模拟，返回统计指标。
    出场逻辑：RSI 超买立即止盈（梯度阈值），不使用追踪止盈。
    纯RSI模式（enable_martin=False）：使用 params.first_order_amount，禁用补仓，固定超买阈值出场。
    """
    first_order = params.first_order_amount if not params.enable_martin else pc.first_order_amount
    multiplier  = pc.martin_multiplier
    max_levels  = pc.max_martin_levels
    grid_drops  = pc.grid_drops or [1.0, 2.0, 3.0, 4.0, 5.0]

    trades = []
    pos = None  # None 或 dict 代表当前持仓

    for i, (price, rsi) in enumerate(zip(closes, rsis)):
        if rsi is None:
            continue

        if pos is None:
            # ── 寻找入场信号 ─────────────────────────────────────────────────
            if 0 < rsi < params.rsi_oversold:
                qty = first_order / price * (1 - FEE_RATE)
                pos = {
                    "entry_bar":      i,
                    "martin_level":   0,
                    "last_buy_price": price,
                    "total_invested": first_order,
                    "total_qty":      qty,
                }
        else:
            avg_price = pos["total_invested"] / pos["total_qty"]

            # ── RSI 超买立即止盈 ──────────────────────────────────────────────
            # 纯信号模式：只判断 RSI >= 超买，不要求涨幅
            # 马丁模式：梯度阈值（每层 -2），且要求价格 >= 均价×(1+min_profit%)
            # 马丁模式：梯度阈值（每层 -2），要求价格 >= 均价×(1+min_profit%)
            # 纯RSI模式：固定超买阈值，同样要求最低涨幅（需覆盖双边手续费 0.2%）
            effective_overbought = (
                max(50.0, params.rsi_overbought - 2 * pos["martin_level"])
                if params.enable_martin else params.rsi_overbought
            )
            min_price = avg_price * (1 + params.overbought_min_profit_pct / 100)
            should_exit = rsi >= effective_overbought and price >= min_price
            if should_exit:
                proceeds = pos["total_qty"] * price * (1 - FEE_RATE)
                trades.append({
                    "bars_held":    i - pos["entry_bar"],
                    "pnl":          proceeds - pos["total_invested"],
                    "martin_level": pos["martin_level"],
                    "exit_reason":  "overbought_sell",
                })
                pos = None
                continue

            # ── 马丁补仓检查（纯信号模式下跳过）────────────────────────────
            if params.enable_martin and pos["martin_level"] < max_levels:
                grid_idx   = min(pos["martin_level"], len(grid_drops) - 1)
                drop_pct   = (pos["last_buy_price"] - price) / pos["last_buy_price"] * 100
                if drop_pct >= grid_drops[grid_idx]:
                    amount = first_order * (multiplier ** (pos["martin_level"] + 1))
                    qty    = amount / price * (1 - FEE_RATE)
                    pos["martin_level"]   += 1
                    pos["last_buy_price"] = price
                    pos["total_invested"] += amount
                    pos["total_qty"]      += qty

    # 数据结束时平掉剩余持仓（以最后收盘价计算）
    if pos and closes:
        price    = closes[-1]
        proceeds = pos["total_qty"] * price * (1 - FEE_RATE)
        trades.append({
            "bars_held":    len(closes) - 1 - pos["entry_bar"],
            "pnl":          proceeds - pos["total_invested"],
            "martin_level": pos["martin_level"],
            "exit_reason":  "end_of_data",
        })

    if not trades:
        return None

    pnls         = [t["pnl"] for t in trades]
    closed_trades = [t for t in trades if t["exit_reason"] != "end_of_data"]
    total_trades  = len(closed_trades)  # 只统计已平仓的交易
    wins          = sum(1 for t in closed_trades if t["pnl"] > 0)

    return {
        "total_trades": total_trades,
        "win_rate":     round(wins / total_trades * 100, 1) if total_trades else 0,
        "total_pnl":    round(sum(t["pnl"] for t in closed_trades), 4),
        "avg_pnl":      round(sum(t["pnl"] for t in closed_trades) / total_trades, 4) if total_trades else 0,
        "max_loss":     round(min(pnls), 4),
        "max_profit":   round(max(pnls), 4),
        "max_martin":   max(t["martin_level"] for t in trades),
        "avg_hold_bars": round(
            sum(t["bars_held"] for t in closed_trades) / total_trades, 1
        ) if total_trades else 0,
        "open_position": trades[-1]["exit_reason"] == "end_of_data",
    }


# ── 数据拉取（分页） ──────────────────────────────────────────────────────────

# ccxt 格式 → OKX 原生 bar 格式（小时必须大写 H）
_CCXT_TO_OKX_BAR = {
    "1m": "1m",  "3m": "3m",  "5m": "5m",  "15m": "15m", "30m": "30m",
    "1h": "1H",  "2h": "2H",  "4h": "4H",  "6h": "6H",   "12h": "12H",
    "1d": "1D",  "3d": "3D",  "1w": "1W",  "1M": "1M",
}


async def _fetch_ohlcv(exchange, symbol: str, timeframe: str, days: int) -> list:
    """
    OKX 历史 K 线分页拉取。
    直接调用 /api/v5/market/history-candles，支持拉取 3 年内的完整历史。
    OKX 参数说明（易混淆）：
      after=T  → 返回时间戳 < T 的更早数据（向过去翻页，需要此参数）
      before=T → 返回时间戳 > T 的更新数据（向未来翻页，不使用）
    """
    cutoff_ms = int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)
    inst_id   = symbol.replace("/", "-")
    okx_bar   = _CCXT_TO_OKX_BAR.get(timeframe, timeframe)   # 1h → 1H
    all_bars: list = []
    after_ts: str | None = None   # 向过去翻页：取比此时间戳更早的数据

    while True:
        # 限速重试：OKX 50011 Too Many Requests 时等待后重试，最多 5 次
        data = []
        for attempt in range(5):
            try:
                req: dict = {"instId": inst_id, "bar": okx_bar, "limit": "100"}
                if after_ts is not None:
                    req["after"] = after_ts        # 取比 after_ts 更早的数据
                resp = await exchange.publicGetMarketHistoryCandles(req)
                data = resp.get("data") or []
                break  # 成功，退出重试
            except Exception as e:
                err = str(e)
                if "50011" in err:               # Too Many Requests
                    wait = 2.0 * (attempt + 1)
                    logger.debug(f"history-candles {symbol}: rate limit, retry in {wait}s")
                    await asyncio.sleep(wait)
                    continue
                logger.warning(f"history-candles {symbol}: {e}")
                return []                        # 不可恢复的错误，返回空

        if not data:
            break

        # OKX 返回顺序：newest-first；转换为 [ts, o, h, l, c, vol]
        converted = [
            [int(d[0]), float(d[1]), float(d[2]), float(d[3]), float(d[4]), float(d[5])]
            for d in data
        ]
        # 排序成 oldest-first，prepend 到总数组
        converted.sort(key=lambda x: x[0])
        all_bars = converted + all_bars

        oldest_ts = converted[0][0]
        if oldest_ts <= cutoff_ms or len(data) < 100:
            break

        after_ts = str(oldest_ts)    # 下次取比这更早的 K 线
        await asyncio.sleep(0.3)     # 页间间隔：0.1s 触发限速，改为 0.3s

    # 按时间升序，只保留 cutoff 之后的
    result = [b for b in all_bars if b[0] >= cutoff_ms]
    result.sort(key=lambda x: x[0])
    return result


# ── 后台任务主体 ───────────────────────────────────────────────────────────────

async def _run_task(
    task_id: str,
    pair_cfgs: list[PairConfig],
    params: BacktestParams,
):
    task = _tasks[task_id]
    task.update(status="running", total=len(pair_cfgs), done=0, results=[])

    exchange = ccxt.okx({"enableRateLimit": True})
    sem = asyncio.Semaphore(2)   # 最多 2 个并发：1m数据页数多，并发高容易触发限速

    async def process(pc: PairConfig):
        async with sem:
            symbol = pc.symbol
            try:
                bars = await _fetch_ohlcv(exchange, symbol, params.timeframe, params.days)
                logger.info(f"Backtest {symbol}: fetched {len(bars)} bars")
                if len(bars) < params.rsi_period + 10:
                    logger.warning(f"Backtest {symbol}: insufficient bars ({len(bars)}), skip")
                    return symbol, None
                closes = [float(b[4]) for b in bars]
                rsis   = calculate_rsi_series(closes, params.rsi_period)
                result = _simulate(closes, rsis, params, pc)
                return symbol, result
            except Exception as e:
                logger.warning(f"Backtest {symbol}: {e}", exc_info=True)
                return symbol, None

    for coro in asyncio.as_completed([process(pc) for pc in pair_cfgs]):
        symbol, result = await coro
        task["done"] += 1
        task["progress"] = round(task["done"] / task["total"] * 100)
        if result:
            task["results"].append({"symbol": symbol, **result})

    await exchange.close()

    # 按总盈亏降序排列
    task["results"].sort(key=lambda x: x["total_pnl"], reverse=True)

    # 汇总
    r = task["results"]
    if r:
        task["summary"] = {
            "symbols":       len(r),
            "total_trades":  sum(x["total_trades"] for x in r),
            "total_pnl":     round(sum(x["total_pnl"] for x in r), 4),
            "avg_win_rate":  round(sum(x["win_rate"] for x in r) / len(r), 1),
        }
    task["status"] = "done"


# ── API 端点 ───────────────────────────────────────────────────────────────────

@router.post("/run")
async def start_backtest(
    params: BacktestParams,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pair_cfgs = (
        db.query(PairConfig)
        .filter_by(user_id=current_user.id, is_enabled=True)
        .all()
    )
    if not pair_cfgs:
        return {"error": "没有已启用的交易对"}

    # 用策略全局配置填充默认值
    strategy = db.query(StrategyConfig).filter_by(user_id=current_user.id).first()
    if strategy:
        if params.rsi_oversold == 30.0 and strategy.rsi_oversold:
            params.rsi_oversold = strategy.rsi_oversold
        if strategy.rsi_overbought:
            params.rsi_overbought = strategy.rsi_overbought

    task_id = uuid.uuid4().hex[:8]
    _tasks[task_id] = {
        "status": "pending", "progress": 0,
        "done": 0, "total": 0,
        "results": [], "summary": None,
    }
    asyncio.create_task(_run_task(task_id, list(pair_cfgs), params))
    return {"task_id": task_id, "pairs_count": len(pair_cfgs)}


@router.get("/status/{task_id}")
def get_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    task = _tasks.get(task_id)
    if not task:
        return {"error": "任务不存在或已过期"}
    return task


@router.get("/strategy-defaults")
def get_strategy_defaults(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """返回当前策略配置，供前端预填参数。"""
    strategy = db.query(StrategyConfig).filter_by(user_id=current_user.id).first()
    pairs_count = db.query(PairConfig).filter_by(user_id=current_user.id, is_enabled=True).count()
    if not strategy:
        return {"pairs_count": pairs_count}
    return {
        "pairs_count":    pairs_count,
        "rsi_oversold":   strategy.rsi_oversold,
        "rsi_overbought": strategy.rsi_overbought,
        "rsi_period":     strategy.rsi_period,
    }
