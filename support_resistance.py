"""
support_resistance.py
======================
Modul untuk mengumpulkan level Support & Resistance (S/R) dari
titik-titik swing high/low historis, dan mengecek apakah harga
tertentu berada "dekat" dengan salah satu level tersebut.

S/R di sini murni horizontal, diambil dari swing point yang sudah
dideteksi oleh market_structure.py -- tidak menambah perhitungan baru,
hanya mengumpulkan & mengecek jarak.
"""

import logging
from typing import List

import pandas as pd

import config
import mt5_connector

log = logging.getLogger("smc_bot")


def get_sr_levels(
    df: pd.DataFrame, swing_highs: List[int], swing_lows: List[int]
) -> List[float]:
    """
    Mengumpulkan semua level harga dari swing high & swing low
    menjadi daftar level S/R horizontal.
    """
    levels = [df["high"].iloc[i] for i in swing_highs]
    levels += [df["low"].iloc[i] for i in swing_lows]
    return levels


def near_sr_level(
    price: float, levels: List[float], tolerance_points: float = None
) -> bool:
    """
    Mengecek apakah 'price' berada dalam jarak toleransi (dalam poin
    harga, dikonversi dari config.SR_TOLERANCE_POINTS) dari salah satu
    level S/R yang diberikan.
    """
    tolerance_points = tolerance_points or config.SR_TOLERANCE_POINTS
    point = mt5_connector.get_symbol_point()
    tolerance_price = tolerance_points * point

    return any(abs(price - level) <= tolerance_price for level in levels)