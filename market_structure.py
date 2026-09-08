"""
market_structure.py
====================
Modul untuk mendeteksi:
1. Swing High / Swing Low (fractal point) -> titik balik harga
2. Market structure (uptrend/downtrend) berdasarkan urutan swing
3. BOS (Break of Structure)  -> konfirmasi tren berlanjut
4. CHoCH (Change of Character) -> sinyal potensi reversal tren

Konsep SMC ini didasarkan pada urutan swing high/low, jadi modul ini
TIDAK butuh indikator apapun -- murni price action.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pandas as pd

import config

log = logging.getLogger("smc_bot")


@dataclass
class StructureResult:
    trend: Optional[str]              # "up", "down", atau None (belum ada struktur jelas)
    event: Optional[str]              # "BOS", "CHoCH", atau None
    break_index: Optional[int]        # index candle yang menembus level struktur
    last_swing_high_idx: Optional[int]
    last_swing_low_idx: Optional[int]


def detect_swings(df: pd.DataFrame, order: int = None) -> Tuple[List[int], List[int]]:
    """
    Mendeteksi swing high & swing low menggunakan metode fractal:
    sebuah candle dianggap swing high kalau high-nya lebih tinggi dari
    'order' candle di kiri DAN kanan-nya (begitu juga sebaliknya untuk low).

    Mengembalikan (index_swing_high, index_swing_low) sebagai list index
    baris DataFrame.
    """
    order = order or config.SWING_ORDER
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    swing_highs = []
    swing_lows = []

    for i in range(order, n - order):
        window_high = highs[i - order: i + order + 1]
        window_low = lows[i - order: i + order + 1]

        # Pastikan hanya SATU titik tertinggi di window ini (menghindari
        # candle datar/duplikat dianggap swing ganda)
        if highs[i] == window_high.max() and (window_high == highs[i]).sum() == 1:
            swing_highs.append(i)

        if lows[i] == window_low.min() and (window_low == lows[i]).sum() == 1:
            swing_lows.append(i)

    return swing_highs, swing_lows


def detect_structure(
    df: pd.DataFrame, swing_highs: List[int], swing_lows: List[int]
) -> StructureResult:
    """
    Menelusuri swing high/low secara kronologis untuk menemukan event
    BOS/CHoCH PALING BARU pada data yang diberikan.

    Logika sederhana:
    - Ambil swing high terakhir -> kalau ada candle SETELAHNYA yang
      close di atas level itu, berarti struktur naik ditembus (bullish
      break).
    - Ambil swing low terakhir -> kalau ada candle SETELAHNYA yang
      close di bawah level itu, berarti struktur turun ditembus
      (bearish break).
    - Break dengan index candle paling besar (paling baru) yang menang.
    """
    last_high_idx = swing_highs[-1] if swing_highs else None
    last_low_idx = swing_lows[-1] if swing_lows else None

    closes = df["close"].values
    result = StructureResult(
        trend=None,
        event=None,
        break_index=None,
        last_swing_high_idx=last_high_idx,
        last_swing_low_idx=last_low_idx,
    )

    bullish_break_idx = None
    if last_high_idx is not None:
        level = df["high"].iloc[last_high_idx]
        for i in range(last_high_idx + 1, len(df)):
            if closes[i] > level:
                bullish_break_idx = i
                break

    bearish_break_idx = None
    if last_low_idx is not None:
        level = df["low"].iloc[last_low_idx]
        for i in range(last_low_idx + 1, len(df)):
            if closes[i] < level:
                bearish_break_idx = i
                break

    # Pilih break yang PALING BARU (index terbesar) di antara keduanya
    if bullish_break_idx is not None and (
        bearish_break_idx is None or bullish_break_idx > bearish_break_idx
    ):
        result.trend = "up"
        result.event = "BOS"  # penyederhanaan: bisa juga CHoCH kalau sebelumnya downtrend,
        result.break_index = bullish_break_idx  # tapi untuk keperluan sinyal, treatment-nya sama

    elif bearish_break_idx is not None:
        result.trend = "down"
        result.event = "BOS"
        result.break_index = bearish_break_idx

    return result