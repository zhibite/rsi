from typing import List
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models import User, Position
from ..schemas import StatsSummary, DailyPnl
from ..services.okx_client import FEE_RATE
from ..auth import get_current_user

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/summary", response_model=StatsSummary)
def get_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    closed = (
        db.query(Position)
        .filter_by(user_id=current_user.id, status="closed")
        .all()
    )
    active_count = (
        db.query(func.count(Position.id))
        .filter_by(user_id=current_user.id, status="open")
        .scalar()
    )

    total_pnl = sum(p.realized_pnl for p in closed)
    total_trades = len(closed)
    win_trades = sum(1 for p in closed if p.realized_pnl > 0)
    loss_trades = total_trades - win_trades
    win_rate = (win_trades / total_trades * 100) if total_trades else 0.0
    avg_pnl = (total_pnl / total_trades) if total_trades else 0.0
    total_invested = sum(p.total_invested for p in closed)
    # Fees: buy fee taken from coins (≈ invested * 0.1%) + sell fee taken from USDT (qty * price * 0.1%)
    total_fees = sum(
        p.total_invested * FEE_RATE
        + p.total_quantity * (p.sell_price or 0.0) * FEE_RATE
        for p in closed
    )

    return StatsSummary(
        total_pnl=round(total_pnl, 4),
        total_trades=total_trades,
        win_trades=win_trades,
        loss_trades=loss_trades,
        win_rate=round(win_rate, 2),
        avg_pnl_per_trade=round(avg_pnl, 4),
        total_invested=round(total_invested, 2),
        total_fees=round(total_fees, 4),
        active_positions=active_count or 0,
    )


@router.get("/daily-pnl", response_model=List[DailyPnl])
def get_daily_pnl(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    days: int = 30,
):
    since = datetime.utcnow() - timedelta(days=days)
    closed = (
        db.query(Position)
        .filter(
            Position.user_id == current_user.id,
            Position.status == "closed",
            Position.closed_at >= since,
        )
        .all()
    )

    daily: dict[str, dict] = {}
    for pos in closed:
        date_str = pos.closed_at.strftime("%Y-%m-%d")
        if date_str not in daily:
            daily[date_str] = {"pnl": 0.0, "trades": 0}
        daily[date_str]["pnl"] += pos.realized_pnl
        daily[date_str]["trades"] += 1

    result = [
        DailyPnl(date=d, pnl=round(v["pnl"], 4), trades=v["trades"])
        for d, v in sorted(daily.items())
    ]
    return result


@router.get("/symbol-pnl")
def get_symbol_pnl(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    closed = (
        db.query(Position)
        .filter_by(user_id=current_user.id, status="closed")
        .all()
    )

    by_symbol: dict[str, dict] = {}
    for pos in closed:
        s = pos.symbol
        if s not in by_symbol:
            by_symbol[s] = {"pnl": 0.0, "trades": 0, "wins": 0}
        by_symbol[s]["pnl"] += pos.realized_pnl
        by_symbol[s]["trades"] += 1
        if pos.realized_pnl > 0:
            by_symbol[s]["wins"] += 1

    result = []
    for sym, data in sorted(by_symbol.items(), key=lambda x: x[1]["pnl"], reverse=True):
        result.append({
            "symbol": sym,
            "pnl": round(data["pnl"], 4),
            "trades": data["trades"],
            "win_rate": round(data["wins"] / data["trades"] * 100, 1) if data["trades"] else 0,
        })
    return result
