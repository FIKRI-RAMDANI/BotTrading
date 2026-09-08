"""
fibonacci.py
============
Modul untuk menghitung golden zone Fibonacci retracement
(default 0.5 - 0.786) dari sebuah pergerakan (leg) harga.

Golden zone dipakai sebagai salah satu syarat konfluensi entry:
harga diharapkan retrace (pullback) ke zona ini sebelum melanjutkan
arah tren utama.
"""

import logging
from typing import Tuple

import config

log = logging.getLogger("smc_bot")


def fib_golden_zone(swing_low: float, swing_high: float, trend: str) -> Tuple[float, float]:
    """
    Menghitung batas bawah & batas atas golden zone fibonacci.

    trend == 'up'   -> pergerakan naik dari swing_low ke swing_high,
                        golden zone dihitung sebagai area retracement
                        turun dari swing_high.
    trend == 'down' -> pergerakan turun dari swing_high ke swing_low,
                        golden zone dihitung sebagai area retracement
                        naik dari swing_low.

    Mengembalikan (batas_bawah, batas_atas) dari golden zone tersebut.
    """
    diff = swing_high - swing_low

    if diff <= 0:
        log.debug(
            f"fib_golden_zone: swing_high ({swing_high}) harus lebih besar "
            f"dari swing_low ({swing_low}). Mengembalikan zona kosong."
        )
        return swing_low, swing_low

    if trend == "up":
        zone_top = swing_high - diff * config.FIB_ZONE_MIN
        zone_bottom = swing_high - diff * config.FIB_ZONE_MAX
    else:
        zone_bottom = swing_low + diff * config.FIB_ZONE_MIN
        zone_top = swing_low + diff * config.FIB_ZONE_MAX

    return min(zone_bottom, zone_top), max(zone_bottom, zone_top)


def price_in_golden_zone(price: float, zone_low: float, zone_high: float) -> bool:
    """Mengecek apakah harga tertentu berada di dalam golden zone."""
    return zone_low <= price <= zone_high