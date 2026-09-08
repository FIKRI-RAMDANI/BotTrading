"""
candlestick_patterns.py
========================
Modul untuk mendeteksi pola candlestick sebagai konfirmasi entry.

CATATAN PENTING:
Chart pattern klasik (head & shoulders, triangle, double top/bottom,
dsb) sangat sulit dideteksi otomatis secara akurat oleh kode
sederhana -- butuh pengenalan bentuk geometris yang kompleks dan
rawan false positive. Sebagai pendekatan praktis, modul ini memakai
CANDLESTICK CONFIRMATION PATTERN (engulfing & pin bar) yang jauh lebih
reliable untuk dikodekan, sambil tetap sejalan dengan filosofi
price-action: konfirmasi momentum sesaat sebelum entry.
"""

import pandas as pd


def is_bullish_engulfing(df: pd.DataFrame, i: int) -> bool:
    """
    Candle ke-i menelan penuh body candle sebelumnya (i-1), dengan arah
    candle sebelumnya bearish dan candle ke-i bullish.
    """
    if i < 1:
        return False

    prev_open, prev_close = df["open"].iloc[i - 1], df["close"].iloc[i - 1]
    open_, close_ = df["open"].iloc[i], df["close"].iloc[i]

    prev_is_bearish = prev_close < prev_open
    curr_is_bullish = close_ > open_
    engulfs = close_ >= prev_open and open_ <= prev_close

    return prev_is_bearish and curr_is_bullish and engulfs


def is_bearish_engulfing(df: pd.DataFrame, i: int) -> bool:
    """Kebalikan dari bullish engulfing."""
    if i < 1:
        return False

    prev_open, prev_close = df["open"].iloc[i - 1], df["close"].iloc[i - 1]
    open_, close_ = df["open"].iloc[i], df["close"].iloc[i]

    prev_is_bullish = prev_close > prev_open
    curr_is_bearish = close_ < open_
    engulfs = open_ >= prev_close and close_ <= prev_open

    return prev_is_bullish and curr_is_bearish and engulfs


def is_bullish_pin_bar(df: pd.DataFrame, i: int) -> bool:
    """
    Pin bar bullish: body kecil di bagian atas candle, ekor bawah
    (lower wick) panjang minimal 2x body -> menandakan penolakan harga
    dari bawah (rejection), sinyal potensi naik.
    """
    o, h, l, c = df["open"].iloc[i], df["high"].iloc[i], df["low"].iloc[i], df["close"].iloc[i]
    body = abs(c - o)
    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)

    if body == 0:
        return False

    return lower_wick >= body * 2 and upper_wick <= body * 0.5


def is_bearish_pin_bar(df: pd.DataFrame, i: int) -> bool:
    """Kebalikan dari bullish pin bar: ekor atas panjang -> rejection dari atas."""
    o, h, l, c = df["open"].iloc[i], df["high"].iloc[i], df["low"].iloc[i], df["close"].iloc[i]
    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l

    if body == 0:
        return False

    return upper_wick >= body * 2 and lower_wick <= body * 0.5


def has_bullish_confirmation(df: pd.DataFrame, i: int) -> bool:
    """Gabungan pengecekan: engulfing ATAU pin bar bullish."""
    return is_bullish_engulfing(df, i) or is_bullish_pin_bar(df, i)


def has_bearish_confirmation(df: pd.DataFrame, i: int) -> bool:
    """Gabungan pengecekan: engulfing ATAU pin bar bearish."""
    return is_bearish_engulfing(df, i) or is_bearish_pin_bar(df, i)