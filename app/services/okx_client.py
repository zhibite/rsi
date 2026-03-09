"""
OKX exchange wrapper using ccxt async support.
Supports both live trading and paper-trading (test mode).
"""
import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
import math
from typing import Optional
import urllib.parse
import urllib.request

import ccxt.async_support as ccxt

logger = logging.getLogger(__name__)

FEE_RATE = 0.001   # OKX spot taker fee: 0.1%


def floor_to_lot_sz(qty: float, lot_sz: float | None) -> float:
    """Floor qty down to the nearest lot_sz increment.

    e.g. lot_sz=0.01, qty=496.312 → 496.31
         lot_sz=1,    qty=496.9   → 496
    Returns qty unchanged when lot_sz is None/0.
    """
    if not lot_sz or lot_sz <= 0:
        return qty
    factor = round(1 / lot_sz)
    return math.floor(qty * factor) / factor


class OKXClient:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        api_passphrase: str,
        is_test_mode: bool = True,
    ):
        self.is_test_mode = is_test_mode
        self._api_key = api_key
        self._api_secret = api_secret
        self._api_passphrase = api_passphrase
        self._base_url = "https://www.okx.com"
        options = {
            "defaultType": "spot",
            "fetchMarkets": ["spot"],   # only load spot markets; avoids ccxt parse_market crash on OKX futures/options with None base
        }
        if is_test_mode:
            options["sandboxMode"] = True

        self._exchange = ccxt.okx(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "password": api_passphrase,
                "options": options,
                "enableRateLimit": True,
            }
        )

    async def close(self):
        await self._exchange.close()

    # ── OKX REST (signed) helpers ──────────────────────────────────────────────

    def _sign(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        prehash = f"{timestamp}{method.upper()}{request_path}{body}"
        digest = hmac.new(
            self._api_secret.encode("utf-8"),
            prehash.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(digest).decode("utf-8")

    async def _okx_post(self, path: str, body: dict) -> dict:
        body_str = json.dumps(body)
        request_path = path
        url = f"{self._base_url}{request_path}"

        def _fetch():
            ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            sign = self._sign(ts, "POST", request_path, body_str)
            headers = {
                "OK-ACCESS-KEY": self._api_key,
                "OK-ACCESS-SIGN": sign,
                "OK-ACCESS-TIMESTAMP": ts,
                "OK-ACCESS-PASSPHRASE": self._api_passphrase,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "bquant-rsi/1.0 (+fastapi)",
            }
            if self.is_test_mode:
                headers["x-simulated-trading"] = "1"
            req = urllib.request.Request(url, data=body_str.encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read()

        raw = await asyncio.to_thread(_fetch)
        payload = json.loads(raw.decode("utf-8"))
        # Top-level error (auth / request level)
        if str(payload.get("code", "0")) != "0":
            data0 = (payload.get("data") or [{}])[0]
            detail = data0.get("sMsg") or payload.get("msg", "unknown")
            raise RuntimeError(f"OKX order failed [{payload.get('code')}]: {detail}")
        # Per-order error (sCode inside data[0])
        data0 = (payload.get("data") or [{}])[0]
        if str(data0.get("sCode", "0")) != "0":
            raise RuntimeError(f"OKX order rejected [sCode={data0.get('sCode')}]: {data0.get('sMsg')}")
        return payload

    async def _okx_get(self, path: str, params: dict | None = None) -> dict:
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        request_path = f"{path}{query}"
        url = f"{self._base_url}{request_path}"

        def _fetch():
            ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            sign = self._sign(ts, "GET", request_path, "")
            headers = {
                "OK-ACCESS-KEY": self._api_key,
                "OK-ACCESS-SIGN": sign,
                "OK-ACCESS-TIMESTAMP": ts,
                "OK-ACCESS-PASSPHRASE": self._api_passphrase,
                "Accept": "application/json",
                "User-Agent": "bquant-rsi/1.0 (+fastapi)",
            }
            if self.is_test_mode:
                headers["x-simulated-trading"] = "1"
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read()

        raw = await asyncio.to_thread(_fetch)
        payload = json.loads(raw.decode("utf-8"))
        if str(payload.get("code", "0")) != "0":
            raise RuntimeError(f"OKX API error: {payload.get('code')} {payload.get('msg')}")
        return payload

    # ── Market data ────────────────────────────────────────────────────────────

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1m", limit: int = 100
    ) -> list:
        """Return list of [timestamp, open, high, low, close, volume]."""
        bars = await self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        return bars

    async def fetch_ticker(self, symbol: str) -> dict:
        return await self._exchange.fetch_ticker(symbol)

    async def fetch_tickers(self) -> dict:
        return await self._exchange.fetch_tickers()

    async def fetch_last_price(self, symbol: str) -> float:
        ticker = await self.fetch_ticker(symbol)
        return float(ticker["last"])

    async def fetch_top_usdt_pairs(self, top_n: int = 20) -> list[str]:
        """Fetch top N USDT spot pairs by 24h quote volume via OKX public REST API."""
        try:
            payload = await self._public_get("/api/v5/market/tickers", {"instType": "SPOT"})
            rows = payload.get("data") or []
            usdt_pairs = []
            for t in rows:
                inst = t.get("instId", "")
                vol = float(t.get("volCcy24h") or t.get("vol24h") or 0)
                if inst.endswith("-USDT") and vol > 0:
                    usdt_pairs.append((inst.replace("-", "/"), vol))
            usdt_pairs.sort(key=lambda x: x[1], reverse=True)
            return [sym for sym, _ in usdt_pairs[:top_n]]
        except Exception as e:
            logger.warning(f"Failed to fetch top pairs: {e}, using defaults")
            from ..config import DEFAULT_PAIRS
            return DEFAULT_PAIRS

    # ── Account ────────────────────────────────────────────────────────────────

    async def fetch_coin_balance(self, currency: str) -> float:
        """Return available balance of a specific coin (e.g. 'BTC', 'MERL')."""
        payload = await self._okx_get("/api/v5/account/balance", {"ccy": currency})
        items = payload.get("data") or []
        if not items:
            return 0.0
        details = (items[0] or {}).get("details") or []
        for d in details:
            if (d or {}).get("ccy") == currency:
                avail = (d or {}).get("availBal")
                cash = (d or {}).get("cashBal")
                return float(avail or cash or 0.0)
        return 0.0

    async def fetch_usdt_balance(self) -> float:
        """
        Return available USDT in spot account.

        Use OKX signed REST directly to avoid occasional ccxt fetch_balance issues.
        """
        payload = await self._okx_get("/api/v5/account/balance", {"ccy": "USDT"})
        items = payload.get("data") or []
        if not items:
            return 0.0
        details = (items[0] or {}).get("details") or []
        for d in details:
            if (d or {}).get("ccy") == "USDT":
                avail = (d or {}).get("availBal")
                cash = (d or {}).get("cashBal")
                return float(avail or cash or 0.0)
        return 0.0

    async def _public_get(self, path: str, params: dict | None = None) -> dict:
        """Unsigned GET for OKX public endpoints (no API key required)."""
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        url = f"{self._base_url}{path}{query}"

        def _fetch():
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/json", "User-Agent": "bquant-rsi/1.0"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read()

        raw = await asyncio.to_thread(_fetch)
        payload = json.loads(raw.decode("utf-8"))
        if str(payload.get("code", "0")) != "0":
            raise RuntimeError(f"OKX public API error: {payload.get('code')} {payload.get('msg')}")
        return payload

    async def fetch_lot_sz(self, symbol: str) -> float | None:
        """Fetch the lot size (minimum quantity increment) for a spot instrument.

        Returns float e.g. 0.01 for FLOW/USDT, or None if unavailable.
        """
        inst_id = self._symbol_to_inst(symbol)
        try:
            payload = await self._public_get(
                "/api/v5/public/instruments",
                {"instType": "SPOT", "instId": inst_id},
            )
            data = (payload.get("data") or [{}])[0]
            lot_sz_str = data.get("lotSz")
            if lot_sz_str:
                return float(lot_sz_str)
        except Exception as e:
            logger.warning(f"fetch_lot_sz({symbol}) failed: {e}")
        return None

    # ── Orders (direct OKX REST — no ccxt load_markets) ───────────────────────

    @staticmethod
    def _symbol_to_inst(symbol: str) -> str:
        """BTC/USDT → BTC-USDT"""
        return symbol.replace("/", "-")

    async def create_market_buy_order(
        self, symbol: str, amount_usdt: float, hint_price: float | None = None
    ) -> dict:
        """
        Market buy denominated in USDT (sz = USDT amount, tgtCcy = quote_ccy).
        Uses direct OKX REST so ccxt load_markets() is never triggered.
        Works for both live and paper trading (x-simulated-trading header set automatically).
        """
        inst_id = self._symbol_to_inst(symbol)
        payload = await self._okx_post("/api/v5/trade/order", {
            "instId": inst_id,
            "tdMode": "cash",
            "side": "buy",
            "ordType": "market",
            "sz": str(amount_usdt),
            "tgtCcy": "quote_ccy",
        })
        data = (payload.get("data") or [{}])[0]
        return {
            "id": data.get("ordId", ""),
            "symbol": symbol,
            "side": "buy",
            "status": "closed",
            "_raw": data,
        }

    async def create_market_sell_order(
        self, symbol: str, quantity: float, hint_price: float | None = None
    ) -> dict:
        """
        Market sell by base coin quantity.
        Uses direct OKX REST so ccxt load_markets() is never triggered.
        """
        inst_id = self._symbol_to_inst(symbol)
        payload = await self._okx_post("/api/v5/trade/order", {
            "instId": inst_id,
            "tdMode": "cash",
            "side": "sell",
            "ordType": "market",
            "sz": str(quantity),
        })
        data = (payload.get("data") or [{}])[0]
        return {
            "id": data.get("ordId", ""),
            "symbol": symbol,
            "side": "sell",
            "status": "closed",
            "_raw": data,
        }

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def get_order_fill(
        self,
        order: dict,
        symbol: str,
        hint_price: float | None = None,
        hint_qty: float | None = None,
    ) -> tuple[float, float | None]:
        """
        Query OKX for actual fill price and filled quantity (accFillSz).
        Returns (fill_price, fill_qty).
        fill_qty is the coin quantity actually received (already net of buy fee when tgtCcy=quote_ccy).
        Retries up to 3 times (0.5s apart) to ensure accFillSz is populated before falling back.
        Falls back to (hint_price, hint_qty) only if all retries fail.
        """
        order_id = order.get("id") or order.get("ordId")
        if order_id:
            inst_id = self._symbol_to_inst(symbol)
            for attempt in range(3):
                try:
                    payload = await self._okx_get(
                        "/api/v5/trade/order",
                        {"instId": inst_id, "ordId": order_id},
                    )
                    data = (payload.get("data") or [{}])[0]
                    avg = data.get("avgPx") or data.get("fillPx")
                    acc_sz = data.get("accFillSz")
                    price = float(avg) if avg and float(avg) > 0 else None
                    qty = float(acc_sz) if acc_sz and float(acc_sz) > 0 else None
                    if price and qty:
                        return price, qty
                    # price or qty not ready yet — wait and retry
                    logger.debug(
                        f"get_order_fill attempt {attempt + 1}: price={price} qty={qty}, retrying..."
                    )
                except Exception as e:
                    logger.debug(f"get_order_fill attempt {attempt + 1} failed ({e}), retrying...")
                if attempt < 2:
                    await asyncio.sleep(0.5)
            logger.warning(
                f"get_order_fill: accFillSz not available for order {order_id} after 3 attempts, falling back to hint"
            )
        price = hint_price or await self.fetch_last_price(symbol)
        return price, hint_qty

    async def get_order_fill_price(self, order: dict, symbol: str, hint_price: float | None = None) -> float:
        """Backward-compat wrapper — returns fill price only."""
        price, _ = await self.get_order_fill(order, symbol, hint_price=hint_price)
        return price
