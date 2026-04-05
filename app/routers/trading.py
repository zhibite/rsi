from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, ApiConfig, StrategyConfig, PairConfig, Position, BotLog, OrderRecord
from ..schemas import (
    ApiConfigCreate, ApiConfigUpdate, ApiConfigOut,
    StrategyConfigCreate, StrategyConfigOut,
    PairConfigCreate, PairConfigUpdate, PairConfigOut,
    PositionOut, BotLogOut, OrderRecordOut,
)
from ..auth import get_current_user
from ..config import encrypt_value, decrypt_value, DEFAULT_PAIRS
from ..services import engine
from ..services.okx_client import OKXClient
from ..services.okx_ws_scanner import scanner as ws_scanner

router = APIRouter(prefix="/api/trading", tags=["trading"])


# ── API Config ─────────────────────────────────────────────────────────────────

@router.get("/api-config", response_model=List[ApiConfigOut])
def list_api_configs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(ApiConfig).filter_by(user_id=current_user.id).all()


@router.post("/api-config", response_model=ApiConfigOut, status_code=201)
def create_api_config(
    body: ApiConfigCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cfg = ApiConfig(
        user_id=current_user.id,
        label=body.label,
        api_key=body.api_key,
        api_secret_encrypted=encrypt_value(body.api_secret),
        api_passphrase_encrypted=encrypt_value(body.api_passphrase),
        is_test_mode=body.is_test_mode,
        is_active=False,
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


@router.put("/api-config/{cfg_id}", response_model=ApiConfigOut)
def update_api_config(
    cfg_id: int,
    body: ApiConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cfg = db.query(ApiConfig).filter_by(id=cfg_id, user_id=current_user.id).first()
    if not cfg:
        raise HTTPException(404, "API config not found")

    if body.label is not None:
        cfg.label = body.label
    if body.api_key is not None:
        cfg.api_key = body.api_key
    if body.api_secret is not None:
        cfg.api_secret_encrypted = encrypt_value(body.api_secret)
    if body.api_passphrase is not None:
        cfg.api_passphrase_encrypted = encrypt_value(body.api_passphrase)
    if body.is_test_mode is not None:
        cfg.is_test_mode = body.is_test_mode
    if body.is_active is not None:
        if body.is_active:
            # Deactivate all other configs first
            db.query(ApiConfig).filter(
                ApiConfig.user_id == current_user.id,
                ApiConfig.id != cfg_id,
            ).update({"is_active": False})
        cfg.is_active = body.is_active

    db.commit()
    db.refresh(cfg)
    return cfg


@router.delete("/api-config/{cfg_id}", status_code=204)
def delete_api_config(
    cfg_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cfg = db.query(ApiConfig).filter_by(id=cfg_id, user_id=current_user.id).first()
    if not cfg:
        raise HTTPException(404, "API config not found")
    db.delete(cfg)
    db.commit()


# ── Strategy Config ────────────────────────────────────────────────────────────

@router.get("/strategy", response_model=StrategyConfigOut)
def get_strategy(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cfg = db.query(StrategyConfig).filter_by(user_id=current_user.id).first()
    if not cfg:
        raise HTTPException(404, "Strategy config not found")
    return cfg


@router.put("/strategy", response_model=StrategyConfigOut)
def update_strategy(
    body: StrategyConfigCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cfg = db.query(StrategyConfig).filter_by(user_id=current_user.id).first()
    if not cfg:
        cfg = StrategyConfig(user_id=current_user.id)
        db.add(cfg)

    for field, value in body.model_dump().items():
        setattr(cfg, field, value)

    db.commit()
    db.refresh(cfg)
    return cfg


@router.put("/strategy/pause-entries")
def toggle_pause_entries(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Toggle pause_new_entries flag for the current user's strategy."""
    cfg = db.query(StrategyConfig).filter_by(user_id=current_user.id).first()
    if not cfg:
        raise HTTPException(404, "Strategy config not found")
    cfg.pause_new_entries = not cfg.pause_new_entries
    db.commit()
    return {"pause_new_entries": cfg.pause_new_entries}


# ── Pair Config CRUD ───────────────────────────────────────────────────────────

@router.get("/pairs", response_model=List[PairConfigOut])
def list_pairs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(PairConfig).filter_by(user_id=current_user.id).order_by(PairConfig.symbol).all()


@router.post("/pairs", response_model=PairConfigOut, status_code=201)
def create_pair(
    body: PairConfigCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    symbol = body.symbol.upper()
    if not "/" in symbol:
        symbol += "/USDT"
    existing = db.query(PairConfig).filter_by(user_id=current_user.id, symbol=symbol).first()
    if existing:
        raise HTTPException(400, f"{symbol} already configured")
    pc = PairConfig(user_id=current_user.id, **{**body.model_dump(), "symbol": symbol})
    db.add(pc)
    db.commit()
    db.refresh(pc)
    ws_scanner.add_pairs([symbol])
    return pc


@router.put("/pairs/{pair_id}", response_model=PairConfigOut)
def update_pair(
    pair_id: int,
    body: PairConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pc = db.query(PairConfig).filter_by(id=pair_id, user_id=current_user.id).first()
    if not pc:
        raise HTTPException(404, "Pair not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(pc, field, value)
    db.commit()
    db.refresh(pc)
    return pc


@router.delete("/pairs/{pair_id}", status_code=204)
def delete_pair(
    pair_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pc = db.query(PairConfig).filter_by(id=pair_id, user_id=current_user.id).first()
    if not pc:
        raise HTTPException(404, "Pair not found")
    db.delete(pc)
    db.commit()


@router.post("/pairs/sync-precision")
async def sync_precision(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetch lot_sz from OKX public API for all configured pairs and save to DB."""
    pairs = db.query(PairConfig).filter_by(user_id=current_user.id).all()
    if not pairs:
        return {"updated": 0, "details": []}

    # Use a temporary OKXClient (only needs the public endpoint, no auth required)
    api_cfg = db.query(ApiConfig).filter_by(user_id=current_user.id, is_active=True).first()
    if api_cfg:
        from ..config import decrypt_value as _dv
        okx = OKXClient(
            api_key=api_cfg.api_key,
            api_secret=_dv(api_cfg.api_secret_encrypted),
            api_passphrase=_dv(api_cfg.api_passphrase_encrypted),
            is_test_mode=api_cfg.is_test_mode,
        )
    else:
        # No active API config — still works because fetch_lot_sz uses public endpoint
        okx = OKXClient(api_key="", api_secret="", api_passphrase="", is_test_mode=False)

    details = []
    updated = 0
    try:
        for pc in pairs:
            lot_sz = await okx.fetch_lot_sz(pc.symbol)
            if lot_sz is not None:
                pc.lot_sz = lot_sz
                updated += 1
            details.append({"symbol": pc.symbol, "lot_sz": lot_sz})
        db.commit()
    finally:
        await okx.close()

    return {"updated": updated, "details": details}


_STABLECOINS = {
    "USDC", "DAI", "TUSD", "BUSD", "USDD", "FRAX", "USDP", "SUSD", "LUSD",
    "GUSD", "USTC", "USDN", "DOLA", "EURS", "USDJ", "USDK", "USDX", "HUSD",
    "FDUSD", "PYUSD", "EURC", "CEUR", "USDE", "USDM",
}


@router.post("/pairs/batch-add-top")
async def batch_add_top_pairs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    top_n: int = Query(50, le=100),
):
    """Fetch top N USDT pairs by volume, skip stablecoins and existing pairs, batch-add with defaults."""
    # Always fetch fresh from OKX public REST (no auth needed, no ccxt)
    okx_tmp = OKXClient(api_key="", api_secret="", api_passphrase="", is_test_mode=False)
    try:
        by_vol = await okx_tmp.fetch_top_usdt_pairs(top_n=top_n + len(_STABLECOINS) + 10)
    finally:
        await okx_tmp.close()

    # Filter stablecoins
    candidates = [
        s for s in by_vol
        if s.endswith("/USDT") and s.split("/")[0] not in _STABLECOINS
    ][:top_n]

    # Skip already-configured pairs
    existing = {pc.symbol for pc in db.query(PairConfig).filter_by(user_id=current_user.id).all()}
    to_add = [s for s in candidates if s not in existing]

    if not to_add:
        return {"added": 0, "skipped": len(candidates), "symbols": []}

    # Use strategy defaults if available, otherwise hardcoded defaults
    strategy = db.query(StrategyConfig).filter_by(user_id=current_user.id).first()
    defaults = dict(
        first_order_amount=strategy.first_order_amount if strategy else 20.0,
        martin_multiplier=strategy.martin_multiplier if strategy else 2.0,
        max_martin_levels=strategy.max_martin_levels if strategy else 5,
        take_profit_pct=strategy.take_profit_pct if strategy else 1.3,
        trailing_stop_pct=strategy.trailing_stop_pct if strategy else 0.3,
        replenishment_retracement_pct=strategy.replenishment_retracement_pct if strategy else 0.3,
        grid_drops=list(strategy.grid_drops) if strategy and strategy.grid_drops else [1.0, 2.0, 3.0, 4.0, 5.0],
    )

    # Fetch lot_sz for all new pairs in parallel
    okx = OKXClient(api_key="", api_secret="", api_passphrase="", is_test_mode=False)
    lot_sz_map: dict[str, float | None] = {}
    try:
        import asyncio as _asyncio
        results = await _asyncio.gather(*[okx.fetch_lot_sz(s) for s in to_add], return_exceptions=True)
        for sym, r in zip(to_add, results):
            lot_sz_map[sym] = r if isinstance(r, float) else None
    finally:
        await okx.close()

    for sym in to_add:
        pc = PairConfig(
            user_id=current_user.id,
            symbol=sym,
            is_enabled=True,
            lot_sz=lot_sz_map.get(sym),
            **defaults,
        )
        db.add(pc)
    db.commit()

    ws_scanner.add_pairs(to_add)

    return {"added": len(to_add), "skipped": len(candidates) - len(to_add), "symbols": to_add}


@router.get("/pair-suggestions")
def pair_suggestions(limit: int = Query(20, le=50)):
    """Top USDT pairs by 24h volume from WS scanner (for UI suggestions)."""
    by_vol = sorted(
        [s for s in ws_scanner.volume_rank if s.endswith("/USDT")],
        key=lambda x: ws_scanner.volume_rank.get(x, 0),
        reverse=True,
    )
    if not by_vol:
        by_vol = list(ws_scanner.rsi_values.keys())[:limit]
    return {"symbols": by_vol[:limit]}


# ── Bot Control ────────────────────────────────────────────────────────────────

@router.get("/bot/status")
def bot_status(current_user: User = Depends(get_current_user)):
    running = engine.bot_is_running(current_user.id)
    rsi_data = engine.rsi_cache.get(current_user.id, {})
    return {"running": running, "rsi": rsi_data}


@router.post("/bot/start")
async def bot_start(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Validate prerequisites
    pair_count = db.query(PairConfig).filter_by(user_id=current_user.id, is_enabled=True).count()
    if pair_count == 0:
        raise HTTPException(400, "No trading pairs configured — please add pairs in settings")
    api_cfg = db.query(ApiConfig).filter_by(user_id=current_user.id, is_active=True).first()
    if not api_cfg:
        raise HTTPException(400, "No active API config — please add and activate an API key first")

    cfg = db.query(StrategyConfig).filter_by(user_id=current_user.id).first()
    if cfg:
        cfg.is_enabled = True
        db.commit()

    engine.start_bot(current_user.id)
    return {"message": "Bot started", "running": True}


@router.post("/bot/stop")
async def bot_stop(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cfg = db.query(StrategyConfig).filter_by(user_id=current_user.id).first()
    if cfg:
        cfg.is_enabled = False
        db.commit()

    engine.stop_bot(current_user.id)
    return {"message": "Bot stopped", "running": False}


# ── Balance & RSI Scan ────────────────────────────────────────────────────────

@router.get("/balance")
async def get_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetch USDT balance from OKX (requires active API config)."""
    api_cfg = db.query(ApiConfig).filter_by(user_id=current_user.id, is_active=True).first()
    if not api_cfg:
        return {"balance_usdt": None, "error": "请先添加并激活 API 配置"}
    try:
        client = OKXClient(
            api_key=api_cfg.api_key,
            api_secret=decrypt_value(api_cfg.api_secret_encrypted),
            api_passphrase=decrypt_value(api_cfg.api_passphrase_encrypted),
            is_test_mode=api_cfg.is_test_mode,
        )
        try:
            balance = await client.fetch_usdt_balance()
            return {"balance_usdt": round(balance, 2)}
        finally:
            await client.close()
    except Exception as e:
        return {"balance_usdt": None, "error": str(e)}


@router.get("/rsi-snapshot")
def rsi_snapshot(
    current_user: User = Depends(get_current_user),
):
    """
    基于全局 OKX 公共 WebSocket 扫描器的 RSI 快照。

    - 使用 OKX 公共行情，不依赖用户自己的 API Key。
    - 返回按 24h 交易额近似排序的 symbol 列表，以及最近一次 RSI 值等信息。
    """
    # 目前对所有用户返回同一份全局快照；后续如有需要，可按策略 pairs 做过滤。
    items = ws_scanner.get_history_snapshot()
    return {"items": items, "source": "okx_public_ws"}


# ── Positions ──────────────────────────────────────────────────────────────────

@router.get("/positions", response_model=List[PositionOut])
def get_open_positions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    positions = (
        db.query(Position)
        .filter_by(user_id=current_user.id, status="open")
        .order_by(Position.opened_at.desc())
        .all()
    )
    # Enrich with live price and unrealised P&L from WS scanner
    result = []
    for pos in positions:
        out = PositionOut.model_validate(pos)
        cp = ws_scanner.prices.get(pos.symbol)
        if cp and pos.avg_price and pos.avg_price > 0:
            out.current_price = cp
            # 与引擎保持一致：净利润（已扣卖出手续费）
            net_proceeds = pos.total_quantity * cp * (1 - 0.001)
            out.pnl_pct = round((net_proceeds - pos.total_invested) / pos.total_invested * 100, 2)
        result.append(out)
    return result


@router.get("/positions/history", response_model=List[PositionOut])
def get_position_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
    symbol: Optional[str] = Query(None),
):
    q = db.query(Position).filter_by(user_id=current_user.id, status="closed")
    if symbol:
        q = q.filter(Position.symbol == symbol)
    return q.order_by(Position.closed_at.desc()).offset(offset).limit(limit).all()


@router.get("/orders", response_model=List[OrderRecordOut])
def get_orders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    symbol: Optional[str] = Query(None),
    side: Optional[str] = Query(None),   # buy | sell
):
    """All order records (buys + sells) across all positions, newest first."""
    q = db.query(OrderRecord).filter_by(user_id=current_user.id)
    if symbol:
        q = q.filter(OrderRecord.symbol == symbol)
    if side:
        q = q.filter(OrderRecord.side == side)
    return q.order_by(OrderRecord.timestamp.desc()).offset(offset).limit(limit).all()


# ── Manual position operations ─────────────────────────────────────────────────

from pydantic import BaseModel as _BaseModel

class _ManualSellBody(_BaseModel):
    pct: int  # 25 | 50 | 100

class _ManualBuyBody(_BaseModel):
    amount_usdt: float


@router.post("/positions/{position_id}/manual-sell")
async def manual_sell_position(
    position_id: int,
    body: _ManualSellBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.pct not in (25, 50, 100):
        raise HTTPException(400, "pct must be 25, 50, or 100")
    pos = db.query(Position).filter_by(id=position_id, user_id=current_user.id, status="open").first()
    if not pos:
        raise HTTPException(404, "Position not found or already closed")
    try:
        result = await engine.manual_sell(current_user.id, position_id, body.pct)
        return result
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@router.post("/positions/{position_id}/manual-buy")
async def manual_buy_position(
    position_id: int,
    body: _ManualBuyBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.amount_usdt <= 0:
        raise HTTPException(400, "amount_usdt must be positive")
    pos = db.query(Position).filter_by(id=position_id, user_id=current_user.id, status="open").first()
    if not pos:
        raise HTTPException(404, "Position not found or already closed")
    try:
        result = await engine.manual_buy(current_user.id, position_id, body.amount_usdt)
        return result
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@router.post("/positions/{position_id}/force-close")
async def force_close_position(
    position_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Force-close a position in DB without placing an exchange order.
    Used when exchange balance is out of sync (e.g. manual trade on exchange side).
    """
    pos = db.query(Position).filter_by(id=position_id, user_id=current_user.id, status="open").first()
    if not pos:
        raise HTTPException(404, "Position not found or already closed")
    pos.status = "closed"
    pos.sell_price = None
    pos.realized_pnl = 0.0
    pos.closed_at = datetime.utcnow()
    pos.trailing_active = False
    db.add(BotLog(
        user_id=current_user.id,
        level="WARNING",
        message=f"Force-closed (DB only, no exchange order) — qty={pos.total_quantity:.8f} avg={pos.avg_price:.8f}",
        symbol=pos.symbol,
    ))
    db.commit()
    return {"ok": True, "symbol": pos.symbol, "position_id": position_id}


# ── Logs ───────────────────────────────────────────────────────────────────────

@router.get("/logs", response_model=List[BotLogOut])
def get_logs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(100, le=500),
):
    return (
        db.query(BotLog)
        .filter_by(user_id=current_user.id)
        .order_by(BotLog.timestamp.desc())
        .limit(limit)
        .all()
    )


# ── Default pairs ─────────────────────────────────────────────────────────────

# 稳定币 base 符号，获取「市值前100」时排除
STABLECOIN_BASES = frozenset({
    "USDT", "USDC", "DAI", "BUSD", "TUSD", "FRAX", "USDP", "USDD",
    "GUSD", "LUSD", "CUSD", "SUSD", "UST", "MIM", "FEI", "ALUSD", "DOLA",
})


@router.get("/default-pairs")
def get_default_pairs():
    return {"pairs": DEFAULT_PAIRS}


@router.get("/top-usdt-pairs")
async def get_top_usdt_pairs(
    current_user: User = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=200),
):
    """
    从 OKX 公共接口拉取 24h 成交额前 N 的 xxx/USDT 交易对（排除稳定币），
    用于「交易对配置」一键填充。
    """
    try:
        import asyncio
        import json
        import urllib.parse
        import urllib.request

        url = "https://www.okx.com/api/v5/market/tickers?" + urllib.parse.urlencode({"instType": "SPOT"})

        def _fetch():
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "bquant-rsi/1.0 (+fastapi)",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read()

        raw = await asyncio.to_thread(_fetch)
        payload = json.loads(raw.decode("utf-8"))
        items = payload.get("data") or []

        candidates = []
        for it in items:
            inst = (it or {}).get("instId")  # e.g. "BTC-USDT"
            if not inst or not inst.endswith("-USDT"):
                continue
            base = inst.split("-")[0].upper()
            if base in STABLECOIN_BASES:
                continue
            # OKX returns quote volume in volCcy24h (quote currency amount)
            vol_quote = float((it or {}).get("volCcy24h") or 0)
            sym = f"{base}/USDT"
            candidates.append((sym, vol_quote))

        candidates.sort(key=lambda x: x[1], reverse=True)
        pairs = [s for s, _ in candidates[:limit]]
        return {"pairs": pairs}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"获取 OKX 行情失败: {e}")
