"""
config.py
=========
Semua pengaturan/parameter bot dikumpulkan di sini.
Kalau mau tuning strategi, cukup ubah nilai-nilai di file ini saja.
"""

# ---------------------------------------------------------------------------
# INSTRUMEN & TIMEFRAME
# ---------------------------------------------------------------------------
SYMBOL = "XAUUSD"
TIMEFRAME = "M15"          # pilihan: M1, M5, M15, M30, H1, H4
BARS_TO_FETCH = 500        # jumlah candle historis yang diambil tiap kali analisa

# ---------------------------------------------------------------------------
# DETEKSI STRUKTUR MARKET (SWING HIGH/LOW)
# ---------------------------------------------------------------------------
SWING_ORDER = 3            # jumlah candle kiri & kanan untuk validasi swing point
                            # semakin besar -> semakin sedikit swing terdeteksi (lebih signifikan)

# ---------------------------------------------------------------------------
# ORDER BLOCK
# ---------------------------------------------------------------------------
OB_BUFFER_POINTS = 50       # buffer tambahan di luar order block untuk penempatan SL
OB_MAX_LOOKBACK = 20        # maksimal candle ke belakang saat mencari order block

# ---------------------------------------------------------------------------
# FIBONACCI
# ---------------------------------------------------------------------------
FIB_ZONE_MIN = 0.5          # batas atas golden zone (retracement paling dangkal)
FIB_ZONE_MAX = 0.786        # batas bawah golden zone (retracement paling dalam)

# ---------------------------------------------------------------------------
# SUPPORT & RESISTANCE
# ---------------------------------------------------------------------------
SR_TOLERANCE_POINTS = 150   # toleransi jarak harga dianggap "dekat" ke level S/R

# ---------------------------------------------------------------------------
# MODE ANALISA "PRO" - CEK BEBERAPA CANDLE TERAKHIR
# ---------------------------------------------------------------------------
# Alih-alih hanya mengecek candle yang PALING BARU closed, bot akan menengok
# ke belakang sejauh LOOKBACK_CANDLES candle terakhir untuk mencari apakah
# ada momen konfluensi + confirmation yang baru saja terjadi (meski bukan
# tepat di candle detik ini). Ini meniru cara analis manual membaca chart:
# "apakah baru saja ada setup valid, bukan cuma di candle sekarang persis".
#
# Kalau ditemukan, bot tetap entry di HARGA PASAR SAAT INI (bukan harga
# candle lama), dan akan memvalidasi dulu bahwa setup itu belum "basi"
# (harga belum bergerak terlalu jauh melewati level SL/TP yang seharusnya).
LOOKBACK_CANDLES = 5        # jumlah candle terakhir yang ditelusuri tiap loop
MAX_ZONE_INVALIDATION_BUFFER = 1.5  # kelipatan risk yang mentolerir harga
                                     # bergerak sebelum setup dianggap basi

# ---------------------------------------------------------------------------
# SYARAT WAJIB vs OPSIONAL
# ---------------------------------------------------------------------------
# True  = syarat ini WAJIB terpenuhi, kalau tidak -> sinyal ditolak
# False = syarat ini hanya BONUS/opsional -> tetap dicek & dicatat di log,
#         tapi TIDAK menggagalkan sinyal kalau tidak terpenuhi
#
# Default saat ini: Order Block, Fibonacci golden zone, dan candle
# confirmation adalah inti dari strategi SMC -> WAJIB.
# Support/Resistance hanya jadi konfirmasi tambahan -> OPSIONAL.
REQUIRE_ORDER_BLOCK = True
REQUIRE_FIB_ZONE = True
REQUIRE_SR = False
REQUIRE_CANDLE_CONFIRMATION = True

# ---------------------------------------------------------------------------
# SIMULASI MODAL UNTUK BACKTEST
# ---------------------------------------------------------------------------
# None -> backtest pakai balance akun DEMO kamu saat ini secara otomatis
# Angka -> backtest pakai modal simulasi custom (berguna kalau kamu mau
#          lihat hasil dengan modal tertentu, misal 10 juta atau 1000 USD,
#          terlepas dari berapa balance demo kamu sekarang)
BACKTEST_STARTING_BALANCE = None

# ---------------------------------------------------------------------------
# SYARAT WAJIB vs OPSIONAL
# ---------------------------------------------------------------------------
# True  = syarat ini WAJIB terpenuhi, kalau tidak sinyal ditolak
# False = syarat ini OPSIONAL, hanya jadi "bonus poin" di reason log,
#         tidak menggagalkan sinyal kalau tidak terpenuhi
REQUIRE_ORDER_BLOCK = True
REQUIRE_FIB_ZONE = True
REQUIRE_SR = False                  # <-- S/R dijadikan opsional/bonus
REQUIRE_CANDLE_CONFIRMATION = True

# ---------------------------------------------------------------------------
# MONEY MANAGEMENT
# ---------------------------------------------------------------------------
RISK_PERCENT = 1.0          # risiko per trade, dalam % dari balance akun
RR_RATIO = 2.0              # rasio Risk:Reward, contoh: 2.0 berarti 1:2

# ---------------------------------------------------------------------------
# EKSEKUSI ORDER
# ---------------------------------------------------------------------------
MAGIC_NUMBER = 990011       # ID unik untuk membedakan order dari bot ini vs manual
DEVIATION = 20               # toleransi slippage harga (dalam poin)

# ---------------------------------------------------------------------------
# OPERASIONAL BOT
# ---------------------------------------------------------------------------
LOOP_SLEEP_SECONDS = 15      # jeda antar pengecekan candle baru (detik)
LOG_FILE = "xauusd_smc_bot.log"

# ---------------------------------------------------------------------------
# MAPPING TIMEFRAME (jangan diubah, ini teknis untuk komunikasi ke MT5)
# ---------------------------------------------------------------------------
TIMEFRAME_MAP = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
}