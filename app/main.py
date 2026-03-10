"""
FastAPI application entry point.
Serves REST API + static frontend files + WebSocket for real-time updates.
"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .config import settings, DEFAULT_PAIRS
from .database import engine as db_engine, SessionLocal
from .models import Base, StrategyConfig
from .auth import get_current_user
from .routers import auth as auth_router
from .routers import trading as trading_router
from .routers import stats as stats_router
from .routers import backtest as backtest_router
from .services import engine as trading_engine
from .services.okx_ws_scanner import scanner as okx_ws_scanner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── WebSocket connection manager ───────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self._connections: Dict[int, list[WebSocket]] = {}

    async def connect(self, user_id: int, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(user_id, []).append(ws)

    def disconnect(self, user_id: int, ws: WebSocket):
        conns = self._connections.get(user_id, [])
        if ws in conns:
            conns.remove(ws)

    async def broadcast(self, user_id: int, data: dict):
        conns = self._connections.get(user_id, [])
        dead = []
        for ws in conns:
            try:
                await ws.send_text(json.dumps(data))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)


ws_manager = ConnectionManager()

class PublicConnectionManager:
    def __init__(self):
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket):
        self._connections.discard(ws)

    async def broadcast(self, data: dict):
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_text(json.dumps(data))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


public_rsi_ws_manager = PublicConnectionManager()


async def _ws_broadcast_callback(user_id: int, data: dict):
    await ws_manager.broadcast(user_id, data)


# ── App lifecycle ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=db_engine)
    logger.info("Database tables created/verified")

    # Wire up WebSocket broadcast to the trading engine
    trading_engine.set_ws_broadcast(_ws_broadcast_callback)

    # Start global OKX public WebSocket RSI scanner (public market data)
    try:
        # 从 PairConfig 读取所有已配置的交易对作为种子
        from .models import PairConfig as _PC
        with SessionLocal() as db:
            configured = [pc.symbol for pc in db.query(_PC).all()]
        seed = configured if configured else DEFAULT_PAIRS
        okx_ws_scanner.start(initial_pairs=seed)
    except Exception as e:
        logger.warning(f"Failed to start OKX WS scanner: {e}")

    async def _public_rsi_broadcast_loop():
        while True:
            try:
                items = okx_ws_scanner.get_history_snapshot(top_n=100)
                await public_rsi_ws_manager.broadcast({"type": "public_rsi_snapshot", "items": items})
            except Exception as e:
                logger.debug(f"Public RSI broadcast failed: {e}")
            await asyncio.sleep(1)

    app.state.public_rsi_task = asyncio.create_task(_public_rsi_broadcast_loop())

    # Re-start bots for users with enabled strategies
    with SessionLocal() as db:
        enabled = db.query(StrategyConfig).filter_by(is_enabled=True).all()
        for cfg in enabled:
            trading_engine.start_bot(cfg.user_id)
            logger.info(f"Auto-started bot for user {cfg.user_id}")

    yield

    # Graceful shutdown: stop all bots
    try:
        t = getattr(app.state, "public_rsi_task", None)
        if t:
            t.cancel()
    except Exception:
        pass
    for uid in list(trading_engine._running_bots.keys()):
        trading_engine.stop_bot(uid)
    # Stop OKX WS scanner
    try:
        okx_ws_scanner.stop()
    except Exception:
        pass
    logger.info("All bots stopped")


app = FastAPI(
    title="RSI Martin Trading Bot",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
def global_exception_handler(request: Request, exc: Exception):
    """Ensure API always returns JSON so frontend can parse errors."""
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "message": str(exc)},
    )


# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(auth_router.router)
app.include_router(trading_router.router)
app.include_router(stats_router.router)
app.include_router(backtest_router.router)

# ── Static frontend ────────────────────────────────────────────────────────────
# Vue SPA (frontend/dist/) 优先，旧 static/ 作为备用
DIST_DIR   = Path(__file__).parent.parent / "frontend" / "dist"
STATIC_DIR = Path(__file__).parent.parent / "static"

if DIST_DIR.exists():
    # 托管 Vue build 产物（assets/、icons/ 等静态资源）
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")
    app.mount("/icons",  StaticFiles(directory=str(DIST_DIR / "icons")),  name="icons")

    @app.get("/", include_in_schema=False)
    def root():
        return FileResponse(str(DIST_DIR / "index.html"))

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        # SPA 路由：所有非 API 路径都返回 index.html
        if full_path.startswith("api/") or full_path.startswith("ws"):
            raise HTTPException(404)
        static_file = DIST_DIR / full_path
        if static_file.exists() and static_file.is_file():
            return FileResponse(str(static_file))
        return FileResponse(str(DIST_DIR / "index.html"))

elif STATIC_DIR.exists():
    # 回退：旧版静态 HTML
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def root():
        index = STATIC_DIR / "index.html"
        return FileResponse(str(index)) if index.exists() else {"message": "RSI Bot API"}

    @app.get("/{page}.html", include_in_schema=False)
    def serve_page(page: str):
        allowed = {"login", "index", "trades", "stats", "settings", "rsi-scanner", "backtest"}
        if page not in allowed:
            raise HTTPException(404)
        html_file = STATIC_DIR / f"{page}.html"
        if not html_file.exists():
            raise HTTPException(404)
        return FileResponse(str(html_file))


# ── WebSocket ──────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    token = ws.query_params.get("token")
    if not token:
        await ws.close(code=4001)
        return

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            raise ValueError("No sub in token")
        user_id = int(sub) if not isinstance(sub, int) else sub
    except (JWTError, ValueError, TypeError):
        await ws.close(code=4001)
        return

    await ws_manager.connect(user_id, ws)
    try:
        # Send initial RSI cache
        rsi_data = trading_engine.rsi_cache.get(user_id, {})
        if rsi_data:
            await ws.send_text(json.dumps({"type": "rsi_snapshot", "data": rsi_data}))

        # Keep alive — client can send pings
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=30)
                if msg == "ping":
                    await ws.send_text('{"type":"pong"}')
            except asyncio.TimeoutError:
                await ws.send_text('{"type":"heartbeat"}')
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(user_id, ws)


@app.get("/api/debug/scanner", include_in_schema=False)
def debug_scanner():
    """实时查看 RSI 扫描仪状态，无需 auth，方便排查问题。"""
    sample_rsi = dict(list(okx_ws_scanner.rsi_values.items())[:10])
    return {
        "running": okx_ws_scanner._running,
        "bootstrapped": okx_ws_scanner._bootstrapped,
        "task_alive": okx_ws_scanner._task is not None and not okx_ws_scanner._task.done(),
        "pairs_total": okx_ws_scanner.pairs_count(),
        "rsi_ready": okx_ws_scanner.ready_count(),
        "pending_pairs": len(okx_ws_scanner._pending_pairs),
        "sample_rsi": sample_rsi,
        "pairs_list": sorted(list(okx_ws_scanner._pairs))[:20],
    }


@app.websocket("/ws/rsi")
async def websocket_rsi(ws: WebSocket):
    token = ws.query_params.get("token")
    if not token:
        await ws.close(code=4001)
        return
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            raise ValueError("No sub in token")
    except (JWTError, ValueError, TypeError):
        await ws.close(code=4001)
        return

    await public_rsi_ws_manager.connect(ws)
    try:
        # Send initial snapshot immediately
        items = okx_ws_scanner.get_history_snapshot(top_n=100)
        await ws.send_text(json.dumps({"type": "public_rsi_snapshot", "items": items}))

        # Keep alive + allow client-triggered refresh
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=30)
                if msg == "ping":
                    await ws.send_text('{"type":"pong"}')
                elif msg == "refresh":
                    items = okx_ws_scanner.get_history_snapshot(top_n=100)
                    await ws.send_text(json.dumps({"type": "public_rsi_snapshot", "items": items}))
            except asyncio.TimeoutError:
                await ws.send_text('{"type":"heartbeat"}')
    except WebSocketDisconnect:
        pass
    finally:
        public_rsi_ws_manager.disconnect(ws)
