"""RSI calculation using Wilder's smoothed moving average (standard method)."""
import numpy as np


def calculate_rsi(closes: list[float], period: int = 14) -> float:
    """
    Calculate RSI for the last candle.

    Parameters
    ----------
    closes : list of close prices (need at least period+1 values)
    period : RSI period (default 14)

    Returns
    -------
    RSI value in [0, 100], or -1 if insufficient data.
    """
    if len(closes) < period + 1:
        return -1.0

    prices = np.array(closes, dtype=float)
    deltas = np.diff(prices)

    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    # Seed with simple average of first `period` changes
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))

    # Wilder's smoothing for subsequent values
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def calculate_rsi_series(closes: list[float], period: int = 14) -> list[float | None]:
    """
    Calculate RSI series aligned with closes.

    Returns a list of length len(closes) with None for indices < period.
    """
    n = len(closes)
    if n < period + 1:
        return [None] * n

    prices = np.array(closes, dtype=float)
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    # Seed with simple average of first `period` changes
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))

    out: list[float | None] = [None] * n

    def rsi_from(avg_g: float, avg_l: float) -> float:
        if avg_l == 0:
            return 100.0
        rs = avg_g / avg_l
        return round(100.0 - (100.0 / (1.0 + rs)), 2)

    # RSI for candle at index `period` (uses deltas up to period-1)
    out[period] = rsi_from(avg_gain, avg_loss)

    # Wilder smoothing for subsequent values
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + float(gains[i])) / period
        avg_loss = (avg_loss * (period - 1) + float(losses[i])) / period
        out[i + 1] = rsi_from(avg_gain, avg_loss)

    return out
