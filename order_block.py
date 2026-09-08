"""
order_block.py
===============
Modul untuk mengidentifikasi Order Block (OB) dari hasil BOS/CHoCH
yang ditemukan oleh market_structure.py.

Definisi Order Block yang dipakai di sini:
- Untuk BOS bullish (trend='up'): candle BEARISH (close < open) TERAKHIR
  sebelum rangkaian candle yang menembus swing high (impulsive move up).
  Zona (low - high) candle ini jadi area demand/support versi SMC.
- Untuk BOS bearish (trend='down'): candle BULLISH (close > open) TERAKHIR
  sebelum rangkaian candle yang menembus swing low (impulsive move down).
  Zona (low - high) candle ini jadi area supply/resistance versi SMC.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

import config

log = logging.getLogger("smc_bot")


@dataclass
class OrderBlock:
    direction: str   # "bullish" atau "bearish"
    low: float
    high: float
    index: int       # index candle order block di DataFrame


def find_order_block(
    df: pd.DataFrame, break_index: int, trend: str, max_lookback: int = None
) -> Optional[OrderBlock]:
    """
    Mencari candle order block dengan menelusuri MUNDUR dari candle
    yang memicu break (break_index), maksimal sejauh 'max_lookback'
    candle ke belakang.

    trend == 'up'   -> cari candle BEARISH terakhir (close < open)
    trend == 'down' -> cari candle BULLISH terakhir (close > open)

    Mengembalikan None kalau tidak ditemukan dalam batas lookback.
    """
    max_lookback = max_lookback or config.OB_MAX_LOOKBACK

    opens = df["open"].values
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values

    search_start = max(0, break_index - max_lookback)

    for i in range(break_index, search_start, -1):
        is_bearish = closes[i] < opens[i]
        is_bullish = closes[i] > opens[i]

        if trend == "up" and is_bearish:
            return OrderBlock(
                direction="bullish", low=lows[i], high=highs[i], index=i
            )

        if trend == "down" and is_bullish:
            return OrderBlock(
                direction="bearish", low=lows[i], high=highs[i], index=i
            )

    log.debug(
        f"Order block tidak ditemukan dalam {max_lookback} candle ke belakang "
        f"dari break_index={break_index}, trend={trend}."
    )
    return None


def price_in_order_block(price: float, ob: OrderBlock) -> bool:
    """Mengecek apakah harga tertentu berada di dalam zona Order Block."""
    return ob.low <= price <= ob.high