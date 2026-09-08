"""
trade_executor.py
==================
Modul untuk mengeksekusi order ke MT5 berdasarkan TradeSignal yang
dihasilkan oleh signal_engine.py.

Tanggung jawab modul ini HANYA seputar eksekusi:
- Menghitung lot (lewat risk_management.py)
- Mengirim order (mt5.order_send)
- Logging hasil eksekusi

Modul ini TIDAK menentukan kapan harus entry -- itu tugas
signal_engine.py.
"""

import logging

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

import config
import risk_management
from signal_engine import TradeSignal  # akan dibuat di file berikutnya

log = logging.getLogger("smc_bot")


def execute(signal: "TradeSignal") -> bool:
    """
    Mengeksekusi TradeSignal menjadi order market di MT5.
    Mengembalikan True kalau order berhasil, False kalau gagal.
    """
    if mt5 is None:
        log.error("MetaTrader5 tidak tersedia, tidak bisa eksekusi order.")
        return False

    sl_distance = abs(signal.entry - signal.sl)
    lot = risk_management.calculate_lot_size(sl_distance)

    if lot is None or lot <= 0:
        log.warning("Lot size tidak valid, order dibatalkan.")
        return False

    tick = mt5.symbol_info_tick(config.SYMBOL)
    if tick is None:
        log.error("Gagal mengambil tick harga terkini, order dibatalkan.")
        return False

    order_type = mt5.ORDER_TYPE_BUY if signal.direction == "buy" else mt5.ORDER_TYPE_SELL
    price = tick.ask if signal.direction == "buy" else tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": config.SYMBOL,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": signal.sl,
        "tp": signal.tp,
        "deviation": config.DEVIATION,
        "magic": config.MAGIC_NUMBER,
        "comment": "SMC-Fib-SR bot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    if result is None:
        log.error(f"order_send() mengembalikan None. Error: {mt5.last_error()}")
        return False

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        log.error(
            f"Order GAGAL | retcode={result.retcode} | comment={result.comment}"
        )
        return False

    log.info(
        f"ORDER SUKSES | {signal.direction.upper()} {lot} lot {config.SYMBOL} @ {price:.2f} "
        f"| SL={signal.sl:.2f} TP={signal.tp:.2f} | Alasan: {signal.reason}"
    )
    return True