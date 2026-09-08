"""
mt5_connector.py
================
Modul untuk:
- Menyambungkan Python ke terminal MT5 yang sedang berjalan
- Mengambil data candle (OHLC)
- Mengambil info akun & symbol

Semua fungsi yang berinteraksi LANGSUNG dengan library MetaTrader5
dikumpulkan di sini, supaya modul lain (structure, signal, dsb) tidak
perlu tahu detail teknis MT5.
"""

import logging
from typing import Optional

import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None  # Library ini hanya jalan di Windows dengan MT5 terinstall

import config

log = logging.getLogger("smc_bot")


def connect() -> bool:
    """
    Menyambungkan ke terminal MT5 yang sedang terbuka & login.
    Mengembalikan True kalau berhasil, False kalau gagal.
    """
    if mt5 is None:
        log.error(
            "Library MetaTrader5 tidak tersedia. Pastikan dijalankan di Windows "
            "dan sudah 'pip install MetaTrader5'."
        )
        return False

    if not mt5.initialize():
        log.error(f"mt5.initialize() gagal. Error: {mt5.last_error()}")
        return False

    account_info = mt5.account_info()
    if account_info is None:
        log.error(
            "Tidak bisa mengambil info akun. Pastikan terminal MT5 sudah login."
        )
        return False

    log.info(
        f"Terhubung ke akun {account_info.login} | Server: {account_info.server} | "
        f"Balance: {account_info.balance} {account_info.currency}"
    )

    symbol_info = mt5.symbol_info(config.SYMBOL)
    if symbol_info is None:
        log.error(f"Symbol {config.SYMBOL} tidak ditemukan di broker ini.")
        return False

    if not symbol_info.visible:
        mt5.symbol_select(config.SYMBOL, True)
        log.info(f"Symbol {config.SYMBOL} diaktifkan di Market Watch.")

    return True


def disconnect() -> None:
    """Menutup koneksi ke MT5 dengan rapi."""
    if mt5 is not None:
        mt5.shutdown()
        log.info("Koneksi ke MT5 ditutup.")


def get_candles(n_bars: int = None) -> Optional[pd.DataFrame]:
    """
    Mengambil data candle terbaru untuk SYMBOL & TIMEFRAME yang
    ditentukan di config.py.

    Mengembalikan DataFrame dengan kolom:
    time, open, high, low, close, tick_volume, spread, real_volume

    Mengembalikan None kalau gagal.
    """
    if mt5 is None:
        return None

    n_bars = n_bars or config.BARS_TO_FETCH
    tf_const = getattr(mt5, config.TIMEFRAME_MAP[config.TIMEFRAME])

    rates = mt5.copy_rates_from_pos(config.SYMBOL, tf_const, 0, n_bars)
    if rates is None or len(rates) == 0:
        log.warning("Gagal mengambil data candle dari MT5.")
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def get_account_balance() -> Optional[float]:
    """Mengembalikan balance akun saat ini, atau None kalau gagal."""
    if mt5 is None:
        return None
    account_info = mt5.account_info()
    return account_info.balance if account_info else None


def get_symbol_point() -> float:
    """Mengembalikan nilai 'point' (satuan harga terkecil) untuk SYMBOL."""
    if mt5 is None:
        return 0.01
    info = mt5.symbol_info(config.SYMBOL)
    return info.point if info else 0.01


def get_current_tick():
    """Mengembalikan tick object (bid/ask terkini) untuk SYMBOL."""
    if mt5 is None:
        return None
    return mt5.symbol_info_tick(config.SYMBOL)


def has_open_position() -> bool:
    """Mengecek apakah sudah ada posisi terbuka di SYMBOL (penting untuk akun Netting)."""
    if mt5 is None:
        return False
    positions = mt5.positions_get(symbol=config.SYMBOL)
    return positions is not None and len(positions) > 0