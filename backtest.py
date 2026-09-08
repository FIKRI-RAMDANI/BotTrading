"""
backtest.py
===========
Menjalankan strategi pada data HISTORIS (bukan live) untuk melihat
seberapa sering sinyal muncul, win rate-nya, DAN bagaimana modal
akan bertumbuh/tergerus kalau strategi ini dipakai konsisten dengan
risk % per trade sesuai config.

Cara pakai: python backtest.py

Alur:
1. Connect ke MT5, ambil balance akun (atau pakai modal simulasi custom)
2. Ambil data candle historis sejauh MONTHS_BACK bulan ke belakang
3. Telusuri candle demi candle secara KRONOLOGIS (bot hanya boleh lihat
   data SAMPAI candle tersebut, tidak boleh "mengintip" masa depan)
4. Setiap sinyal ditemukan, simulasikan SL/TP, lalu update saldo
   simulasi sesuai RISK_PERCENT dari saldo SAAT ITU (compounding)
5. Cetak ringkasan rapi: total sinyal, win, loss, win rate, saldo akhir,
   return %, dan max drawdown

CATATAN:
- Backtest SEDERHANA (event-driven pada candle close, high/low dipakai
  untuk cek SL/TP tersentuh) -- bukan simulasi tick presisi tinggi.
- TIDAK memperhitungkan spread, swap, slippage, atau requote.
- TIDAK mengirim order apapun ke MT5, murni simulasi di atas data historis.
- Hasil masa lalu TIDAK menjamin hasil yang sama di masa depan.
"""

import argparse
import logging
from datetime import datetime, timedelta

import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

import config
import mt5_connector
import signal_engine

log = logging.getLogger("smc_bot_backtest")
logging.basicConfig(level=logging.INFO, format="%(message)s")  # format simpel, tanpa timestamp bertele-tele

# --- Pengaturan khusus backtest ---
MONTHS_BACK = 12
MIN_CANDLES_FOR_ANALYSIS = 60

SEPARATOR = "-" * 78
DOUBLE_SEPARATOR = "=" * 78


def fetch_historical_data(months_back: int = MONTHS_BACK) -> pd.DataFrame:
    """Mengambil data candle historis dari MT5 sejauh 'months_back' bulan."""
    if mt5 is None:
        raise RuntimeError("MetaTrader5 tidak tersedia di environment ini.")

    tf_const = getattr(mt5, config.TIMEFRAME_MAP[config.TIMEFRAME])
    date_to = datetime.now()
    date_from = date_to - timedelta(days=months_back * 30)

    rates = mt5.copy_rates_range(config.SYMBOL, tf_const, date_from, date_to)
    if rates is None or len(rates) == 0:
        raise RuntimeError(
            f"Gagal mengambil data historis untuk {config.SYMBOL} "
            f"{config.TIMEFRAME} dari {date_from} sampai {date_to}."
        )

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    log.info(
        f"Data diambil: {len(df)} candle {config.SYMBOL} {config.TIMEFRAME} "
        f"({df['time'].iloc[0]}  ->  {df['time'].iloc[-1]})"
    )
    return df


def simulate_trade_outcome(df: pd.DataFrame, entry_index: int, signal) -> dict:
    """
    Mensimulasikan apakah SL atau TP tersentuh duluan, menelusuri candle
    setelah entry_index memakai high/low tiap candle.
    """
    direction = signal.direction
    sl = signal.sl
    tp = signal.tp

    for j in range(entry_index + 1, len(df)):
        high = df["high"].iloc[j]
        low = df["low"].iloc[j]

        if direction == "buy":
            hit_sl = low <= sl
            hit_tp = high >= tp
        else:
            hit_sl = high >= sl
            hit_tp = low <= tp

        if hit_sl and hit_tp:
            # Kedua level "kena" di candle yang sama -> asumsikan SL duluan
            # (lebih konservatif untuk keperluan evaluasi)
            return {"outcome": "loss", "exit_index": j, "exit_price": sl, "r_multiple": -1.0}

        if hit_sl:
            return {"outcome": "loss", "exit_index": j, "exit_price": sl, "r_multiple": -1.0}

        if hit_tp:
            return {"outcome": "win", "exit_index": j, "exit_price": tp, "r_multiple": config.RR_RATIO}

    return {"outcome": "open", "exit_index": None, "exit_price": None, "r_multiple": 0.0}


def get_starting_balance(cli_balance: float = None) -> tuple:
    """
    Menentukan modal awal simulasi & mata uangnya, dengan prioritas:
    1. Argumen --balance dari command line (kalau diisi)
    2. config.BACKTEST_STARTING_BALANCE (kalau diisi)
    3. Tanya langsung ke user lewat input() interaktif
    4. Kalau user kosongkan input -> pakai balance akun demo saat ini
    """
    currency = "USD"
    if mt5 is not None:
        acc = mt5.account_info()
        if acc is not None:
            currency = acc.currency

    if cli_balance is not None:
        log.info(f"Modal simulasi diambil dari argumen --balance: {cli_balance:,.2f} {currency}")
        return float(cli_balance), currency

    if config.BACKTEST_STARTING_BALANCE is not None:
        return float(config.BACKTEST_STARTING_BALANCE), currency

    # Tanya interaktif ke user
    demo_balance = None
    if mt5 is not None:
        acc = mt5.account_info()
        if acc is not None:
            demo_balance = acc.balance

    prompt = "Masukkan modal simulasi backtest"
    if demo_balance is not None:
        prompt += f" (kosongkan untuk pakai balance akun demo saat ini: {demo_balance:,.2f} {currency})"
    prompt += ": "

    user_input = input(prompt).strip()

    if user_input == "":
        if demo_balance is None:
            raise RuntimeError("Tidak ada balance akun demo yang bisa dipakai, dan modal tidak diisi.")
        return float(demo_balance), currency

    try:
        return float(user_input.replace(",", "")), currency
    except ValueError:
        log.warning(f"Input '{user_input}' tidak valid, pakai balance akun demo saat ini sebagai fallback.")
        if demo_balance is None:
            raise RuntimeError("Input modal tidak valid dan tidak ada balance akun demo sebagai fallback.")
        return float(demo_balance), currency


def run_backtest(cli_balance: float = None, cli_rr: float = None, cli_risk: float = None):
    if cli_rr is not None:
        config.RR_RATIO = cli_rr
    if cli_risk is not None:
        config.RISK_PERCENT = cli_risk

    log.info(DOUBLE_SEPARATOR)
    log.info(f" BACKTEST {config.SYMBOL} | Timeframe: {config.TIMEFRAME} | Periode: {MONTHS_BACK} bulan terakhir")
    log.info(DOUBLE_SEPARATOR)

    if not mt5_connector.connect():
        log.error("Gagal connect ke MT5. Backtest dibatalkan.")
        return

    df = fetch_historical_data()
    starting_balance, currency = get_starting_balance(cli_balance)
    mt5_connector.disconnect()

    log.info(f"Modal awal simulasi   : {starting_balance:,.2f} {currency}")
    log.info(f"Risk per trade         : {config.RISK_PERCENT}%  |  Risk:Reward = 1:{config.RR_RATIO}")
    log.info(DOUBLE_SEPARATOR)
    log.info(f"{'WAKTU ENTRY':<20}{'ARAH':<6}{'ENTRY':>10}{'SL':>10}{'TP':>10}{'HASIL':>7}{'SALDO SETELAH':>18}")
    log.info(SEPARATOR)

    trades = []
    running_balance = starting_balance
    peak_balance = starting_balance
    max_drawdown_pct = 0.0

    i = MIN_CANDLES_FOR_ANALYSIS

    while i < len(df):
        window = df.iloc[: i + 1].reset_index(drop=True)
        signal = signal_engine.analyze(window)

        if signal:
            entry_index = i
            result = simulate_trade_outcome(df, entry_index, signal)

            # --- Update saldo simulasi (compounding sesuai RISK_PERCENT saat ini) ---
            risk_amount = running_balance * (config.RISK_PERCENT / 100.0)
            pnl = risk_amount * result["r_multiple"]
            running_balance += pnl

            peak_balance = max(peak_balance, running_balance)
            drawdown_pct = ((peak_balance - running_balance) / peak_balance * 100) if peak_balance > 0 else 0.0
            max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)

            entry_time_str = str(df["time"].iloc[entry_index])
            outcome_label = {"win": "WIN", "loss": "LOSS", "open": "OPEN"}[result["outcome"]]

            trade_record = {
                "entry_time": entry_time_str,
                "direction": signal.direction,
                "entry": signal.entry,
                "sl": signal.sl,
                "tp": signal.tp,
                "outcome": result["outcome"],
                "r_multiple": result["r_multiple"],
                "pnl": pnl,
                "balance_after": running_balance,
            }
            trades.append(trade_record)

            log.info(
                f"{entry_time_str:<20}"
                f"{signal.direction.upper():<6}"
                f"{signal.entry:>10.2f}"
                f"{signal.sl:>10.2f}"
                f"{signal.tp:>10.2f}"
                f"{outcome_label:>7}"
                f"{running_balance:>18,.2f}"
            )

            if result["exit_index"] is not None:
                i = result["exit_index"] + 1
            else:
                break
        else:
            i += 1

    log.info(SEPARATOR)
    print_summary(trades, starting_balance, running_balance, max_drawdown_pct, currency)
    return trades


def print_summary(trades: list, starting_balance: float, ending_balance: float,
                   max_drawdown_pct: float, currency: str):
    log.info(DOUBLE_SEPARATOR)
    log.info(" RINGKASAN BACKTEST")
    log.info(DOUBLE_SEPARATOR)

    if not trades:
        log.info("Tidak ada sinyal/trade yang ditemukan dalam periode ini.")
        log.info(DOUBLE_SEPARATOR)
        return

    total = len(trades)
    wins = [t for t in trades if t["outcome"] == "win"]
    losses = [t for t in trades if t["outcome"] == "loss"]
    open_trades = [t for t in trades if t["outcome"] == "open"]

    closed = len(wins) + len(losses)
    win_rate = (len(wins) / closed * 100) if closed > 0 else 0.0
    total_r = sum(t["r_multiple"] for t in trades)
    total_return_pct = ((ending_balance - starting_balance) / starting_balance * 100) if starting_balance > 0 else 0.0

    def line(label, value):
        log.info(f"  {label:<28}: {value}")

    line("Total sinyal / trade", f"{total}")
    line("Win", f"{len(wins)}")
    line("Loss", f"{len(losses)}")
    line("Masih terbuka di akhir data", f"{len(open_trades)}")
    line("Win rate (dari yang closed)", f"{win_rate:.1f}%")
    line("Total R multiple", f"{total_r:+.2f} R")
    log.info(SEPARATOR)
    line("Modal awal", f"{starting_balance:,.2f} {currency}")
    line("Modal akhir", f"{ending_balance:,.2f} {currency}")
    line("Total return", f"{total_return_pct:+.2f}%")
    line("Max drawdown", f"{max_drawdown_pct:.2f}%")
    log.info(DOUBLE_SEPARATOR)
    log.info(
        "  Catatan: simulasi ini BELUM memperhitungkan spread, swap, slippage,\n"
        "  atau requote broker -- hasil real akan sedikit lebih rendah dari ini.\n"
        "  Hasil masa lalu tidak menjamin hasil yang sama di masa depan."
    )
    log.info(DOUBLE_SEPARATOR)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest XAUUSD SMC Bot")
    parser.add_argument(
        "--balance",
        type=float,
        default=None,
        help="Modal simulasi awal (contoh: --balance 10000). Kalau tidak diisi, akan ditanya interaktif.",
    )
    parser.add_argument(
        "--rr", type=float, default=None,
        help="Override Risk:Reward ratio untuk sesi ini (contoh: --rr 3.0 untuk 1:3).",
    )
    parser.add_argument(
        "--risk", type=float, default=None,
        help="Override risk %% per trade untuk sesi ini (contoh: --risk 0.5 untuk 0.5%%).",
    )
    args = parser.parse_args()

    run_backtest(cli_balance=args.balance, cli_rr=args.rr, cli_risk=args.risk)