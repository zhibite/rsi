"""
OKX Public WebSocket RSI Scanner
=================================
启动流程：
1. 快速预热：并发拉取种子对（DEFAULT_PAIRS / 策略配置对）的历史 K 线，
   ~5-10 秒内就能看到第一批 RSI 值。
2. 后台扩展：异步拉取 OKX 成交量 top-100 USDT 对并补充进扫描列表。
3. 实时更新：订阅 OKX 公共 WS candle1m 频道，每根 K 线更新后重算 RSI。
"""

import asyncio
import json
import logging
import urllib.parse
import urllib.request
from collections import deque

from .rsi_calculator import calculate_rsi

logger = logging.getLogger(__name__)

OKX_WS_PUBLIC = "wss://ws.okx.com:8443/ws/v5/business"
BUFFER_SIZE = 70        # 每对保留的确认收盘价数量
TOP_N_PAIRS = 100       # 后台扩展最大对数
MAX_CONCURRENT = 10     # 并发 REST 请求数


class OKXWSScanner:
    def __init__(self, rsi_period: int = 14):
        self.rsi_period = rsi_period

        self._closes: dict[str, deque] = {}      # 已确认收盘价
        self._live_close: dict[str, float] = {}  # 未收盘 K 线最新价
        self.rsi_values: dict[str, float] = {}   # 当前 RSI
        self.prices: dict[str, float] = {}       # 最新价格
        self.volume_rank: dict[str, float] = {}  # 24h 交易量排名用

        self.confirmed_rsi_values: dict[str, float] = {}
        self.volume_rank: dict[str, float] = {}

        self._pairs: set[str] = set()
        self._pending_pairs: set[str] = set()  # 新增但还未加载历史+订阅的币
        self._running = False
        self._task: asyncio.Task | None = None
        self._bootstrapped = False

    # ── symbol helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _to_inst(symbol: str) -> str:
        return symbol.replace("/", "-")

    @staticmethod
    def _from_inst(inst_id: str) -> str:
        return inst_id.replace("-", "/")

    # ── 公共 API ───────────────────────────────────────────────────────────────

    def add_pairs(self, pairs: list[str]):
        for p in pairs:
            if p not in self._pairs:
                self._pairs.add(p)
                self._closes.setdefault(p, deque(maxlen=BUFFER_SIZE))
                # 若已完成 bootstrap，标记为待处理（需补加载历史K线+WS订阅）
                if self._bootstrapped:
                    self._pending_pairs.add(p)

    def start(self, initial_pairs: list[str] | None = None):
        if initial_pairs:
            self.add_pairs(initial_pairs)
        if self._task and not self._task.done():
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info(f"WS scanner starting (seed={len(self._pairs)} pairs)")

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        self._task = None

    def pairs_count(self) -> int:
        return len(self._pairs)

    def ready_count(self) -> int:
        return len(self.rsi_values)

    def get_history_snapshot(self, top_n: int | None = None) -> list[dict]:
        """返回 RSI 升序列表（超卖在前），供前端展示。"""
        items: list[dict] = []
        for sym in list(self._pairs):
            rsi = self.rsi_values.get(sym)
            if rsi is None:
                continue
            items.append({
                "symbol": sym,
                "rsi": round(float(rsi), 2),
                "price": float(self.prices.get(sym, 0.0)),
                "volume": float(self.volume_rank.get(sym, 0.0)),
            })
        items.sort(key=lambda x: x["rsi"])
        return items[:top_n] if top_n else items

    # ── RSI 计算 ───────────────────────────────────────────────────────────────

    def _calc_rsi(self, symbol: str, include_live: bool = True) -> float | None:
        buf = list(self._closes.get(symbol, []))
        if include_live and symbol in self._live_close:
            buf.append(self._live_close[symbol])
        if len(buf) < self.rsi_period + 1:
            return None
        return calculate_rsi(buf, self.rsi_period)

    # ── 历史 K 线加载（并发，直接调 OKX 公共 REST） ────────────────────────────

    @staticmethod
    def _fetch_candles_rest(inst_id: str, limit: int) -> list | None:
        """同步调用 OKX 公共 REST 拉取 1m K 线（在线程池中执行）。"""
        url = (
            "https://www.okx.com/api/v5/market/candles?"
            + urllib.parse.urlencode({"instId": inst_id, "bar": "1m", "limit": limit})
        )
        req = urllib.request.Request(
            url, headers={"User-Agent": "bquant-rsi/1.0", "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode())
            data = payload.get("data") or []
            # OKX 返回最新在前，需要反转为时间升序
            return list(reversed(data))
        except Exception as e:
            logger.debug(f"REST candle fetch skip {inst_id}: {e}")
            return None

    async def _load_candles(self, pairs: list[str]):
        """并发加载多个交易对的历史 K 线，预热 RSI buffer。"""
        sem = asyncio.Semaphore(MAX_CONCURRENT)
        limit = BUFFER_SIZE + self.rsi_period + 5

        async def fetch_one(sym: str):
            async with sem:
                inst_id = self._to_inst(sym)
                bars = await asyncio.to_thread(self._fetch_candles_rest, inst_id, limit)
                return sym, bars

        results = await asyncio.gather(*[fetch_one(s) for s in pairs])
        done = 0
        for sym, bars in results:
            if not bars or len(bars) < self.rsi_period + 2:
                continue
            # bars 格式：[ts, o, h, l, close, vol, ...]
            confirmed = [float(b[4]) for b in bars[:-1]]
            buf = self._closes.setdefault(sym, deque(maxlen=BUFFER_SIZE))
            buf.clear()
            buf.extend(confirmed[-BUFFER_SIZE:])
            self._live_close[sym] = float(bars[-1][4])
            self.prices[sym] = float(bars[-1][4])
            confirmed_rsi = self._calc_rsi(sym, include_live=False)
            if confirmed_rsi is not None:
                self.confirmed_rsi_values[sym] = confirmed_rsi
            live_rsi = self._calc_rsi(sym, include_live=True)
            if live_rsi is not None:
                self.rsi_values[sym] = live_rsi
                done += 1
        return done

    # ── Bootstrap ──────────────────────────────────────────────────────────────

    async def _bootstrap(self):
        """
        阶段1：快速预热种子对（5-10s 出数据）
        阶段2：后台扩展 top-100（可选，30-60s 完成）
        """
        # 阶段1：快速预热已有的种子对
        seed_pairs = list(self._pairs)
        if seed_pairs:
            logger.info(f"Bootstrap phase1: loading candles for {len(seed_pairs)} seed pairs...")
            done = await self._load_candles(seed_pairs)
            logger.info(f"Bootstrap phase1 done: {done}/{len(seed_pairs)} pairs have RSI")
        self._bootstrapped = True

        # 阶段2：尝试扩展到 top-100（在后台，失败不影响阶段1结果）
        try:
            logger.info("Bootstrap phase2: fetching top-100 USDT pairs by volume...")
            def _fetch_tickers():
                url = "https://www.okx.com/api/v5/market/tickers?" + urllib.parse.urlencode({"instType": "SPOT"})
                req = urllib.request.Request(
                    url, headers={"User-Agent": "bquant-rsi/1.0", "Accept": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=20) as resp:
                    return json.loads(resp.read().decode())

            payload = await asyncio.wait_for(asyncio.to_thread(_fetch_tickers), timeout=30)
            rows = payload.get("data") or []
            usdt: list[tuple[str, float]] = []
            for t in rows:
                inst = t.get("instId", "")
                if not inst.endswith("-USDT"):
                    continue
                vol = float(t.get("volCcy24h") or 0)
                sym = inst.replace("-", "/")
                usdt.append((sym, vol))
                self.volume_rank[sym] = vol
            usdt.sort(key=lambda x: x[1], reverse=True)

            new_pairs = []
            for sym, _ in usdt[:TOP_N_PAIRS]:
                if sym not in self._pairs:
                    self._pairs.add(sym)
                    self._closes.setdefault(sym, deque(maxlen=BUFFER_SIZE))
                    new_pairs.append(sym)

            if new_pairs:
                logger.info(f"Bootstrap phase2: loading candles for {len(new_pairs)} new pairs...")
                done2 = await self._load_candles(new_pairs)
                logger.info(f"Bootstrap phase2 done: {done2} new pairs have RSI, total={len(self.rsi_values)}")
            else:
                logger.info("Bootstrap phase2: no new pairs beyond seed")
        except asyncio.TimeoutError:
            logger.warning("Bootstrap phase2: tickers fetch timeout (30s), skipping top-100 expansion")
        except Exception as e:
            logger.warning(f"Bootstrap phase2 failed ({e}), keeping seed pairs only")

    # ── WebSocket 主循环 ────────────────────────────────────────────────────────

    async def _run(self):
        try:
            await self._bootstrap()
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"Bootstrap error: {e}")

        while self._running:
            try:
                await self._connect()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning(f"WS disconnected ({e}), reconnecting in 5s...")
                await asyncio.sleep(5)

    async def _connect(self):
        try:
            import websockets as ws_lib
        except ImportError:
            logger.error("websockets not installed — run: pip install websockets>=12.0")
            await asyncio.sleep(60)
            return

        pairs = list(self._pairs)
        if not pairs:
            logger.warning("No pairs to subscribe, waiting...")
            await asyncio.sleep(10)
            return

        try:
            async with ws_lib.connect(
                OKX_WS_PUBLIC,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
                max_size=2 ** 22,
            ) as ws:
                args = [{"channel": "candle1m", "instId": self._to_inst(p)} for p in pairs]
                for i in range(0, len(args), 100):
                    await ws.send(json.dumps({"op": "subscribe", "args": args[i: i + 100]}))
                logger.info(f"OKX WS: subscribed {len(pairs)} candle1m streams")

                # 后台任务：动态追加新币的历史K线加载 + WS订阅
                pending_task = asyncio.create_task(self._handle_pending_subs(ws))
                try:
                    async for raw in ws:
                        if not self._running:
                            break
                        self._handle(raw)
                finally:
                    pending_task.cancel()
        except Exception as e:
            raise e

    async def _handle_pending_subs(self, ws):
        """每 5 秒检查有无新增交易对，有则追加 WS 订阅并后台加载历史 K 线。"""
        while True:
            await asyncio.sleep(5)
            if not self._pending_pairs:
                continue
            new = list(self._pending_pairs)
            self._pending_pairs.clear()
            # 追加 WS 订阅
            args = [{"channel": "candle1m", "instId": self._to_inst(p)} for p in new]
            for i in range(0, len(args), 100):
                try:
                    await ws.send(json.dumps({"op": "subscribe", "args": args[i: i + 100]}))
                except Exception as e:
                    logger.warning(f"Failed to subscribe new pairs: {e}")
            logger.info(f"WS: dynamically subscribed {len(new)} new pairs")
            # 后台加载历史 K 线（不阻塞 WS 消息循环）
            asyncio.create_task(self._load_new_pair_candles(new))

    async def _load_new_pair_candles(self, pairs: list[str]):
        """为新增交易对并发加载历史 K 线，完成后即可计算 RSI。"""
        try:
            done = await self._load_candles(pairs)
            logger.info(f"Dynamically loaded candles: {done}/{len(pairs)} new pairs have RSI")
        except Exception as e:
            logger.warning(f"Dynamic candle load failed: {e}")

    # ── K 线消息处理 ───────────────────────────────────────────────────────────

    def _handle(self, raw: str):
        try:
            msg = json.loads(raw)
        except Exception:
            return

        if "event" in msg:
            if msg.get("event") == "error":
                logger.warning(f"OKX WS error: {msg}")
            return

        arg = msg.get("arg", {})
        if not arg.get("channel", "").startswith("candle"):
            return

        symbol = self._from_inst(arg.get("instId", ""))
        for candle in msg.get("data", []):
            if len(candle) < 6:
                continue
            close = float(candle[4])
            confirmed = len(candle) > 8 and candle[8] == "1"

            self.prices[symbol] = close

            if confirmed:
                buf = self._closes.setdefault(symbol, deque(maxlen=BUFFER_SIZE))
                buf.append(close)
                self._live_close.pop(symbol, None)
                confirmed_rsi = self._calc_rsi(symbol, include_live=False)
                if confirmed_rsi is not None:
                    self.confirmed_rsi_values[symbol] = confirmed_rsi
            else:
                self._live_close[symbol] = close

            live_rsi = self._calc_rsi(symbol, include_live=True)
            if live_rsi is not None:
                self.rsi_values[symbol] = live_rsi


# ── 全局单例 ───────────────────────────────────────────────────────────────────
scanner = OKXWSScanner()
