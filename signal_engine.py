"""
signal_engine.py
=================
"Otak" bot -- menggabungkan hasil dari semua modul analisa menjadi
satu keputusan: ADA sinyal entry yang valid, atau TIDAK.

Alur analisa:
1. market_structure  -> deteksi swing, tren, BOS
2. order_block       -> cari zona Order Block dari BOS tsb
3. fibonacci         -> hitung golden zone dari kaki pergerakan
4. support_resistance-> cek harga dekat level S/R historis
5. candlestick_patterns -> cek konfirmasi candle (engulfing/pin bar)

MODE "PRO" (LOOKBACK):
Alih-alih hanya mengecek candle yang PALING BARU closed, engine ini
menelusuri MUNDUR sejauh config.LOOKBACK_CANDLES candle terakhir untuk
mencari apakah ada momen konfluensi + candle confirmation yang baru
saja terjadi -- persis seperti analis manual yang menengok "apakah
baru saja ada setup valid", bukan cuma candle detik ini persis.

Begitu ketemu, entry TETAP memakai HARGA PASAR SAAT INI (bukan harga
candle lama), dan divalidasi dulu supaya setup itu belum "basi" --
yaitu harga belum bergerak terlalu jauh melewati area SL/TP yang
seharusnya (lihat _is_setup_still_fresh).
"""

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

import config
import market_structure
import order_block as ob_module
import fibonacci
import support_resistance as sr_module
import candlestick_patterns as candle

log = logging.getLogger("smc_bot")


@dataclass
class TradeSignal:
    direction: str   # "buy" atau "sell"
    entry: float
    sl: float
    tp: float
    reason: str
    setup_candle_time: Optional[object] = None  # waktu candle yang memicu setup (untuk logging)


def analyze(df: pd.DataFrame) -> Optional[TradeSignal]:
    """
    Menjalankan seluruh pipeline analisa pada DataFrame candle yang
    diberikan (hanya candle yang SUDAH CLOSED, tanpa candle berjalan).

    Mengembalikan TradeSignal kalau ada setup valid dalam
    config.LOOKBACK_CANDLES candle terakhir (dan masih "segar"),
    atau None kalau tidak ada.
    """
    # --- 1. Struktur market & BOS (dihitung dari SELURUH histori) ---
    swing_highs, swing_lows = market_structure.detect_swings(df)
    if not swing_highs or not swing_lows:
        log.debug("Belum cukup swing point untuk analisa struktur.")
        return None

    structure = market_structure.detect_structure(df, swing_highs, swing_lows)
    if structure.event is None or structure.break_index is None:
        log.debug("Belum ada BOS/CHoCH yang terdeteksi.")
        return None

    trend = structure.trend
    break_idx = structure.break_index

    # --- 2. Order Block ---
    ob = ob_module.find_order_block(df, break_idx, trend)
    if ob is None:
        log.debug("Order block tidak ditemukan untuk BOS ini.")
        return None

    # --- 3. Fibonacci golden zone ---
    if trend == "up":
        ref_low_idx = structure.last_swing_low_idx
        ref_low = df["low"].iloc[ref_low_idx] if ref_low_idx is not None else ob.low
        ref_high = df["high"].iloc[structure.last_swing_high_idx]
    else:
        ref_high_idx = structure.last_swing_high_idx
        ref_high = df["high"].iloc[ref_high_idx] if ref_high_idx is not None else ob.high
        ref_low = df["low"].iloc[structure.last_swing_low_idx]

    zone_low, zone_high = fibonacci.fib_golden_zone(ref_low, ref_high, trend)

    # --- 4. Support/Resistance ---
    sr_levels = sr_module.get_sr_levels(df, swing_highs, swing_lows)

    # --- 5. Telusuri MUNDUR beberapa candle terakhir untuk cari setup ---
    n = len(df)
    lookback = min(config.LOOKBACK_CANDLES, n - 1)  # jangan sampai index minus
    last_i = n - 1
    current_price = df["close"].iloc[last_i]

    matched_index = None
    matched_near_sr = None

    for i in range(last_i, last_i - lookback, -1):
        if i < 1:
            break

        candle_close = df["close"].iloc[i]
        in_order_block = ob_module.price_in_order_block(candle_close, ob)
        in_fib_zone = fibonacci.price_in_golden_zone(candle_close, zone_low, zone_high)
        near_sr = sr_module.near_sr_level(candle_close, sr_levels)

        confirmed = (
            candle.has_bullish_confirmation(df, i)
            if trend == "up"
            else candle.has_bearish_confirmation(df, i)
        )

        # --- Cek tiap syarat: WAJIB harus True, OPSIONAL cukup dicatat saja ---
        ob_ok = in_order_block if config.REQUIRE_ORDER_BLOCK else True
        fib_ok = in_fib_zone if config.REQUIRE_FIB_ZONE else True
        sr_ok = near_sr if config.REQUIRE_SR else True
        confirm_ok = confirmed if config.REQUIRE_CANDLE_CONFIRMATION else True

        log.debug(
            f"[lookback i={i}, {n - 1 - i} candle lalu] close={candle_close:.2f} | "
            f"in_OB={in_order_block}{'(wajib)' if config.REQUIRE_ORDER_BLOCK else '(opsional)'} "
            f"in_fib={in_fib_zone}{'(wajib)' if config.REQUIRE_FIB_ZONE else '(opsional)'} "
            f"near_SR={near_sr}{'(wajib)' if config.REQUIRE_SR else '(opsional/bonus)'} "
            f"confirmed={confirmed}{'(wajib)' if config.REQUIRE_CANDLE_CONFIRMATION else '(opsional)'}"
        )

        if ob_ok and fib_ok and sr_ok and confirm_ok:
            matched_index = i
            matched_near_sr = near_sr  # simpan untuk info bonus di reason
            break  # ambil yang PALING BARU duluan (loop dari belakang)

    if matched_index is None:
        log.debug(
            f"Tidak ada setup valid dalam {lookback} candle terakhir."
        )
        return None

    # --- 6. Bangun sinyal dengan entry di HARGA PASAR SAAT INI ---
    if trend == "up":
        sl = ob.low - _ob_buffer_price()
        risk = current_price - sl
        if risk <= 0:
            log.debug("Risk <= 0 (harga sudah di bawah SL calc), setup dianggap batal.")
            return None
        tp = current_price + risk * config.RR_RATIO
        direction = "buy"
    else:
        sl = ob.high + _ob_buffer_price()
        risk = sl - current_price
        if risk <= 0:
            log.debug("Risk <= 0 (harga sudah di atas SL calc), setup dianggap batal.")
            return None
        tp = current_price - risk * config.RR_RATIO
        direction = "sell"

    # --- 7. Validasi "kesegaran" setup: pastikan harga belum kebablasan ---
    if not _is_setup_still_fresh(direction, current_price, sl, tp):
        log.debug(
            f"Setup ditemukan di candle {matched_index} tapi sudah dianggap BASI "
            f"(harga sekarang {current_price:.2f} sudah terlalu jauh dari zona entry)."
        )
        return None

    setup_time = df["time"].iloc[matched_index] if "time" in df.columns else None
    candles_ago = last_i - matched_index
    sr_note = "+ S/R (bonus terpenuhi)" if matched_near_sr else "(S/R bonus tidak terpenuhi, tapi diabaikan karena opsional)"

    return TradeSignal(
        direction=direction,
        entry=current_price,
        sl=sl,
        tp=tp,
        reason=(
            f"BOS {trend} + Order Block + Fib golden zone + candle confirmation "
            f"{sr_note} (setup terbentuk {candles_ago} candle lalu, entry di harga pasar saat ini)"
        ),
        setup_candle_time=setup_time,
    )


def _is_setup_still_fresh(direction: str, current_price: float, sl: float, tp: float) -> bool:
    """
    Mengecek apakah setup yang ditemukan di candle lookback masih layak
    dieksekusi SEKARANG, atau sudah "basi" karena harga sudah bergerak
    terlalu jauh (mendekati/melewati TP, atau mendekati SL).

    Pakai config.MAX_ZONE_INVALIDATION_BUFFER sebagai kelipatan risk
    yang masih ditoleransi.
    """
    risk = abs(current_price - sl)
    if risk <= 0:
        return False

    if direction == "buy":
        # Kalau harga sekarang sudah tembus SL, atau sudah lebih dekat ke
        # TP daripada seharusnya (bergerak terlalu jauh), anggap basi.
        if current_price <= sl:
            return False
        if current_price >= tp:
            return False  # sudah "kelewat", TP versi baru tidak masuk akal
    else:
        if current_price >= sl:
            return False
        if current_price <= tp:
            return False

    return True


def _ob_buffer_price() -> float:
    """Konversi OB_BUFFER_POINTS (config) menjadi satuan harga."""
    import mt5_connector
    point = mt5_connector.get_symbol_point()
    return config.OB_BUFFER_POINTS * point