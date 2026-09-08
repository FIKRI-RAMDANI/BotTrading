"""
risk_management.py
===================
Modul untuk menghitung ukuran lot (position size) berdasarkan:
- Risk % dari balance akun (config.RISK_PERCENT)
- Jarak Stop Loss dari harga entry

Prinsip: berapapun jarak SL-nya, jumlah UANG yang dipertaruhkan per
trade selalu konsisten sesuai RISK_PERCENT, karena lot-nya yang
menyesuaikan.
"""

import logging
from typing import Optional

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

import config

log = logging.getLogger("smc_bot")


def calculate_lot_size(sl_distance_price: float) -> Optional[float]:
    """
    Menghitung lot size yang sesuai supaya kerugian maksimal (kalau SL
    kena) sama dengan RISK_PERCENT dari balance akun saat ini.

    sl_distance_price: jarak antara harga entry dan SL, dalam satuan
                        harga (bukan poin), misal 3.5 untuk XAUUSD.

    Mengembalikan lot size yang sudah dibulatkan sesuai step lot
    broker, atau None kalau gagal menghitung.
    """
    if mt5 is None:
        log.error("MetaTrader5 tidak tersedia, tidak bisa menghitung lot size.")
        return None

    if sl_distance_price <= 0:
        log.warning("Jarak SL harus lebih besar dari 0.")
        return None

    account_info = mt5.account_info()
    symbol_info = mt5.symbol_info(config.SYMBOL)

    if account_info is None or symbol_info is None:
        log.error("Gagal mengambil info akun/symbol untuk hitung lot size.")
        return None

    risk_amount = account_info.balance * (config.RISK_PERCENT / 100.0)

    tick_value = symbol_info.trade_tick_value
    tick_size = symbol_info.trade_tick_size

    if tick_size == 0 or tick_value == 0:
        log.error("tick_size/tick_value dari broker bernilai 0, tidak bisa hitung lot.")
        return None

    # Berapa kerugian (dalam mata uang akun) untuk 1 lot penuh, kalau
    # SL sejauh sl_distance_price tersentuh
    loss_per_lot = (sl_distance_price / tick_size) * tick_value

    if loss_per_lot <= 0:
        log.error("Perhitungan loss_per_lot tidak valid (<= 0).")
        return None

    raw_lot = risk_amount / loss_per_lot

    # Bulatkan sesuai step lot minimum broker (misal 0.01)
    step = symbol_info.volume_step
    lot = round(raw_lot / step) * step
    lot = max(symbol_info.volume_min, lot)
    lot = min(symbol_info.volume_max, lot)

    lot = round(lot, 2)

    log.info(
        f"Risk {config.RISK_PERCENT}% dari balance {account_info.balance} = "
        f"{risk_amount:.2f} {account_info.currency} | SL distance = {sl_distance_price} "
        f"| Lot dihitung = {lot}"
    )

    return lot