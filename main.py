"""
main.py
=======
Entry point bot. Jalankan file ini dengan: python main.py

Alur kerja:
1. Setup logging (ke file & konsol)
2. Connect ke MT5
3. Loop selamanya:
   a. Ambil data candle terbaru
   b. Cek apakah ada candle baru yang SUDAH CLOSED (bukan candle
      yang sedang berjalan)
   c. Kalau ada candle baru:
      - Cek apakah sudah ada posisi terbuka (mode Netting -> skip
        kalau masih ada posisi)
      - Kalau tidak ada posisi terbuka, jalankan signal_engine.analyze()
      - Kalau ada sinyal valid, eksekusi lewat trade_executor.execute()
   d. Sleep sebentar, ulangi
4. Tangani Ctrl+C dengan graceful shutdown (tutup koneksi MT5 dengan rapi)
"""

import argparse
import logging
import time

import config
import mt5_connector
import signal_engine
import trade_executor


def setup_logging() -> logging.Logger:
    """Konfigurasi logging ke file DAN konsol sekaligus."""
    logger = logging.getLogger("smc_bot")
    logger.setLevel(logging.DEBUG)  # sementara DEBUG untuk diagnosa, nanti bisa dikembalikan ke INFO

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def main(rr_override: float = None, risk_override: float = None):
    log = setup_logging()

    if rr_override is not None:
        config.RR_RATIO = rr_override
    if risk_override is not None:
        config.RISK_PERCENT = risk_override

    log.info("=" * 70)
    log.info("Memulai XAUUSD SMC Bot...")
    log.info(
        f"Symbol={config.SYMBOL} | Timeframe={config.TIMEFRAME} | "
        f"Risk={config.RISK_PERCENT}% | RR=1:{config.RR_RATIO}"
    )
    log.info("=" * 70)

    if not mt5_connector.connect():
        log.error("Gagal terhubung ke MT5. Bot dihentikan.")
        return

    last_closed_bar_time = None

    try:
        while True:
            df = mt5_connector.get_candles()

            if df is None or len(df) < (config.SWING_ORDER * 2 + 10):
                log.warning("Data candle belum cukup, menunggu...")
                time.sleep(config.LOOP_SLEEP_SECONDS)
                continue

            # Buang candle TERAKHIR karena itu candle yang masih berjalan
            # (belum closed), kita hanya analisa candle yang sudah pasti.
            closed_df = df.iloc[:-1].reset_index(drop=True)
            current_bar_time = closed_df["time"].iloc[-1]

            # Hanya proses kalau ini candle closed yang BELUM pernah
            # dianalisa sebelumnya (menghindari analisa berulang pada
            # candle yang sama selama masih berjalan)
            if current_bar_time != last_closed_bar_time:
                last_closed_bar_time = current_bar_time
                log.info(f"Candle baru closed: {current_bar_time}")

                if mt5_connector.has_open_position():
                    log.info(
                        "Masih ada posisi terbuka (mode Netting) -> "
                        "lewati analisa entry baru."
                    )
                else:
                    signal = signal_engine.analyze(closed_df)

                    if signal:
                        log.info(f"SINYAL DITEMUKAN: {signal}")
                        trade_executor.execute(signal)
                    else:
                        log.info("Belum ada sinyal valid pada candle ini.")

            time.sleep(config.LOOP_SLEEP_SECONDS)

    except KeyboardInterrupt:
        log.info("Bot dihentikan oleh user (Ctrl+C).")

    except Exception as e:
        log.exception(f"Terjadi error tak terduga: {e}")

    finally:
        mt5_connector.disconnect()
        log.info("Bot berhenti dengan aman.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="XAUUSD SMC Bot - LIVE trading (kirim order asli ke MT5)")
    parser.add_argument(
        "--rr", type=float, default=None,
        help="Override Risk:Reward ratio untuk sesi ini (contoh: --rr 3.0 untuk 1:3). "
             "Tidak mengubah config.py secara permanen.",
    )
    parser.add_argument(
        "--risk", type=float, default=None,
        help="Override risk %% per trade untuk sesi ini (contoh: --risk 0.5 untuk 0.5%%). "
             "Tidak mengubah config.py secara permanen.",
    )
    args = parser.parse_args()

    main(rr_override=args.rr, risk_override=args.risk)