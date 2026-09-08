"""
paper_trading.py
=================
FORWARD TEST / PAPER TRADING -- kebalikan dari backtest.py.

backtest.py  -> menguji strategi pada data MASA LALU (2 bulan ke belakang)
paper_trading.py -> memantau strategi MULAI SEKARANG ke DEPAN, secara
                     real-time, TAPI tanpa mengirim order asli ke MT5.
                     Semua "trade" murni simulasi & dicatat di sini.

Kenapa ini penting: backtest bisa bias (curve-fitting ke data lama tanpa
disadari). Paper trading membuktikan strategi tetap masuk akal di data
BARU yang belum pernah "dilihat" strategi sebelumnya -- forward-looking,
persis seperti bot akan bekerja kalau live sungguhan.

Cara pakai: python paper_trading.py
Hentikan dengan Ctrl+C kapan saja -- progress otomatis tersimpan.

State (saldo simulasi, posisi terbuka, histori trade) disimpan di file
paper_trading_state.json supaya kalau script di-restart, progress tidak
hilang.
"""

import argparse
import json
import logging
import os
import time
from datetime import datetime

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

import config
import mt5_connector
import signal_engine

log = logging.getLogger("smc_bot_paper")

STATE_FILE = "paper_trading_state.json"
LOG_FILE = "paper_trading.log"

SEPARATOR = "-" * 78
DOUBLE_SEPARATOR = "=" * 78


def setup_logging():
    logger = logging.getLogger("smc_bot_paper")
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(message)s")

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


def load_state(initial_balance: float) -> dict:
    """Muat state dari file JSON kalau ada, atau buat baru."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        log.info(
            f"State lama ditemukan, melanjutkan dari saldo: "
            f"{state['balance']:,.2f} | Total trade sebelumnya: {len(state['history'])}"
        )
        return state

    log.info(f"Tidak ada state lama, mulai paper trading baru dengan modal {initial_balance:,.2f}")
    return {
        "balance": initial_balance,
        "peak_balance": initial_balance,
        "max_drawdown_pct": 0.0,
        "open_trade": None,   # dict kalau ada posisi simulasi terbuka
        "history": [],        # list of closed trades
        "last_closed_bar_time": None,
    }


def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)


def get_initial_balance(cli_balance: float = None) -> float:
    if cli_balance is not None:
        return float(cli_balance)

    if config.BACKTEST_STARTING_BALANCE is not None:
        return float(config.BACKTEST_STARTING_BALANCE)

    demo_balance = mt5_connector.get_account_balance()
    prompt = "Masukkan modal simulasi paper trading"
    if demo_balance is not None:
        prompt += f" (kosongkan untuk pakai balance akun demo saat ini: {demo_balance:,.2f})"
    prompt += ": "

    user_input = input(prompt).strip()
    if user_input == "":
        if demo_balance is None:
            raise RuntimeError("Tidak ada balance demo yang bisa dipakai, dan modal tidak diisi.")
        return float(demo_balance)

    try:
        return float(user_input.replace(",", ""))
    except ValueError:
        log.warning(f"Input '{user_input}' tidak valid, pakai balance demo sebagai fallback.")
        return float(demo_balance) if demo_balance is not None else 0.0


def check_open_trade(state: dict, candle: dict):
    """
    Cek apakah posisi simulasi yang sedang terbuka kena SL/TP di candle
    baru ini. Kalau iya, tutup posisi & update saldo.
    """
    trade = state["open_trade"]
    if trade is None:
        return

    direction = trade["direction"]
    sl = trade["sl"]
    tp = trade["tp"]
    high = candle["high"]
    low = candle["low"]

    hit_sl = (low <= sl) if direction == "buy" else (high >= sl)
    hit_tp = (high >= tp) if direction == "buy" else (low <= tp)

    if not (hit_sl or hit_tp):
        return  # posisi masih terbuka, belum ada keputusan

    # Kalau dua-duanya kena di candle yang sama, asumsikan SL duluan (konservatif)
    outcome = "loss" if hit_sl else "win"
    r_multiple = -1.0 if outcome == "loss" else config.RR_RATIO
    exit_price = sl if outcome == "loss" else tp

    risk_amount = state["balance"] * (config.RISK_PERCENT / 100.0)
    pnl = risk_amount * r_multiple
    state["balance"] += pnl

    state["peak_balance"] = max(state["peak_balance"], state["balance"])
    dd = (
        (state["peak_balance"] - state["balance"]) / state["peak_balance"] * 100
        if state["peak_balance"] > 0
        else 0.0
    )
    state["max_drawdown_pct"] = max(state["max_drawdown_pct"], dd)

    closed_trade = {
        **trade,
        "exit_price": exit_price,
        "outcome": outcome,
        "r_multiple": r_multiple,
        "pnl": pnl,
        "balance_after": state["balance"],
        "closed_at": str(candle["time"]),
    }
    state["history"].append(closed_trade)
    state["open_trade"] = None

    log.info(
        f"[PAPER CLOSE] {trade['direction'].upper()} entry={trade['entry']:.2f} "
        f"-> {outcome.upper()} @ {exit_price:.2f} | PnL={pnl:+,.2f} | "
        f"Saldo sekarang: {state['balance']:,.2f}"
    )


def open_new_trade(state: dict, signal, candle_time):
    state["open_trade"] = {
        "direction": signal.direction,
        "entry": signal.entry,
        "sl": signal.sl,
        "tp": signal.tp,
        "reason": signal.reason,
        "opened_at": str(candle_time),
    }
    log.info(
        f"[PAPER ENTRY] {signal.direction.upper()} @ {signal.entry:.2f} | "
        f"SL={signal.sl:.2f} TP={signal.tp:.2f} | {signal.reason}"
    )


def print_status(state: dict):
    log.info(SEPARATOR)
    total = len(state["history"])
    wins = [t for t in state["history"] if t["outcome"] == "win"]
    losses = [t for t in state["history"] if t["outcome"] == "loss"]
    closed = len(wins) + len(losses)
    win_rate = (len(wins) / closed * 100) if closed > 0 else 0.0

    log.info(
        f"STATUS | Saldo: {state['balance']:,.2f} | Trade selesai: {total} "
        f"(Win {len(wins)} / Loss {len(losses)}, WR {win_rate:.1f}%) | "
        f"Max DD: {state['max_drawdown_pct']:.2f}% | "
        f"Posisi terbuka sekarang: {'ADA' if state['open_trade'] else 'tidak ada'}"
    )
    log.info(SEPARATOR)


def run_paper_trading(cli_balance: float = None, cli_rr: float = None, cli_risk: float = None):
    setup_logging()

    if cli_rr is not None:
        config.RR_RATIO = cli_rr
    if cli_risk is not None:
        config.RISK_PERCENT = cli_risk

    log.info(DOUBLE_SEPARATOR)
    log.info(" PAPER TRADING / FORWARD TEST -- mulai dari SEKARANG ke DEPAN")
    log.info(" (simulasi murni, TIDAK ada order asli yang dikirim ke MT5)")
    log.info(DOUBLE_SEPARATOR)

    if not mt5_connector.connect():
        log.error("Gagal connect ke MT5. Paper trading dibatalkan.")
        return

    initial_balance = get_initial_balance(cli_balance)
    state = load_state(initial_balance)

    log.info(
        f"Symbol={config.SYMBOL} | Timeframe={config.TIMEFRAME} | "
        f"Risk={config.RISK_PERCENT}% | RR=1:{config.RR_RATIO}"
    )
    print_status(state)

    try:
        while True:
            df = mt5_connector.get_candles()

            if df is None or len(df) < (config.SWING_ORDER * 2 + 10):
                time.sleep(config.LOOP_SLEEP_SECONDS)
                continue

            closed_df = df.iloc[:-1].reset_index(drop=True)
            current_bar_time = str(closed_df["time"].iloc[-1])

            if current_bar_time != state["last_closed_bar_time"]:
                state["last_closed_bar_time"] = current_bar_time

                last_candle = {
                    "time": closed_df["time"].iloc[-1],
                    "high": closed_df["high"].iloc[-1],
                    "low": closed_df["low"].iloc[-1],
                }

                log.info(f"Candle baru closed: {current_bar_time}")

                # 1. Cek dulu apakah posisi simulasi yang ada sekarang closed
                check_open_trade(state, last_candle)

                # 2. Kalau tidak ada posisi terbuka, cari sinyal baru
                if state["open_trade"] is None:
                    signal = signal_engine.analyze(closed_df)
                    if signal:
                        open_new_trade(state, signal, closed_df["time"].iloc[-1])
                    else:
                        log.info("Belum ada sinyal valid pada candle ini.")
                else:
                    log.info("Masih ada posisi simulasi terbuka, menunggu closed.")

                save_state(state)
                print_status(state)

            time.sleep(config.LOOP_SLEEP_SECONDS)

    except KeyboardInterrupt:
        log.info("Paper trading dihentikan oleh user (Ctrl+C). Progress sudah tersimpan.")

    except Exception as e:
        log.exception(f"Terjadi error tak terduga: {e}")

    finally:
        save_state(state)
        mt5_connector.disconnect()
        log.info("Paper trading berhenti dengan aman.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Paper Trading / Forward Test XAUUSD SMC Bot")
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

    run_paper_trading(cli_balance=args.balance, cli_rr=args.rr, cli_risk=args.risk)