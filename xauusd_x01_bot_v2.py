"""
╔══════════════════════════════════════════════════════════════╗
║          X SYSTEM X.01 — TELEGRAM BOT v2.0            ║
║          Integrated: X.01 + Gold Alpha Fase 0 & 1           ║
╠══════════════════════════════════════════════════════════════╣
║  3 Pilar  : Macro + Technical + Eksekusi                     ║
║  3 Strategi: Liquidity Sweep / Macro Trigger / Breakout      ║
║  Research : Gold Alpha (DXY -0.98, VIX -0.98, DML)          ║
║  Broker   : Valetax MT5 | Modal $125.49 | Leverage 1:2000   ║
╚══════════════════════════════════════════════════════════════╝

INSTALL:
  pip install python-telegram-bot==20.7 MetaTrader5 yfinance requests schedule pytz

CARA DAPAT TOKEN & CHAT_ID:
  Token  : @BotFather → /newbot
  Chat ID: @userinfobot → /start

RUN:
  python xauusd_x01_bot_v2.py
"""

import asyncio
import os
import schedule
import time
import threading
import json
import csv
from datetime import datetime, date, timezone
from pathlib import Path

import pytz
import requests

try:
    from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
    TELEGRAM_OK = True
except ImportError:
    print("Install: pip install python-telegram-bot==20.7")
    TELEGRAM_OK = False

try:
    import MetaTrader5 as mt5
    MT5_OK = True
except ImportError:
    MT5_OK = False

try:
    import yfinance as yf
    YF_OK = True
except ImportError:
    YF_OK = False

# ══════════════════════════════════════════════════════════════════════════════
# ⚙️  CONFIG
# ══════════════════════════════════════════════════════════════════════════════

CONFIG = {
    # ── WAJIB DIISI ──────────────────────────────────────────
    "TOKEN"          : os.environ.get("TOKEN", "8694963924:AAHIuF3Xkw-EBnnWM3OziSRbONlrFIQRSWQ"),
    "CHAT_ID"        : os.environ.get("CHAT_ID", "6806030764"),

    # ── PROFIL VALETAX ───────────────────────────────────────
    "BROKER"         : "Valetax",
    "SYMBOL"         : "XAUUSD",
    "BALANCE"        : 125.49,
    "LEVERAGE"       : 2000,
    "MIN_LOT"        : 0.01,

    # ── RISK MANAGEMENT ──────────────────────────────────────
    "RISK_SCALP"     : 1.0,    # % per trade scalping
    "RISK_SWING"     : 2.0,    # % per trade swing
    "PARTIAL_SCALP"  : 70,     # % close di TP1 scalping
    "PARTIAL_SWING"  : 50,     # % close di TP1 swing
    "MAX_DD_DAILY"   : 3.0,    # % max drawdown harian
    "MAX_TRADES_DAY" : 3,      # max trade per hari

    # ── X.01 RULES ───────────────────────────────────────────
    "SIGNAL_THRESHOLD": 0.65,  # min confidence Gold Alpha
    "ADX_SCALP"      : 20,
    "ADX_TREND"      : 25,
    "SPREAD_MAX"     : 50,

    # ── KILL ZONE (WIB) ──────────────────────────────────────
    "KZ_LONDON_START": 14,
    "KZ_LONDON_END"  : 16,
    "KZ_NY_START"    : 19,
    "KZ_NY_END"      : 22,

    # ── TIMEZONE ─────────────────────────────────────────────
    "TZ"             : "Asia/Jakarta",

    # ── AUTO REPORT SCHEDULE (WIB) ───────────────────────────
    "REPORT_MORNING" : "07:30",
    "ALERT_LONDON"   : "14:00",
    "ALERT_NY"       : "19:30",
    "REPORT_EOD"     : "21:00",

    # ── FILES ────────────────────────────────────────────────
    "LOG_FILE"       : "dca_log.json",
    "PRED_LOG"       : "prediction_log.csv",
    "JOURNAL_FILE"   : "trade_journal.csv",
}

WIB = pytz.timezone(CONFIG["TZ"])

# ══════════════════════════════════════════════════════════════════════════════
# 📊 X.01 SYSTEM DATA
# ══════════════════════════════════════════════════════════════════════════════

X01 = {
    "strategies": {
        "LIQUIDITY_SWEEP": {
            "name"   : "LIQUIDITY SWEEP ⭐ PRIORITAS",
            "filters": 6,
            "items"  : [
                "Sweep terjadi di Kill Zone",
                "CHoCH konfirmasi setelah sweep",
                "OB atau FVG valid",
                "Target likuiditas jelas",
                "Volume spike saat sweep",
                "Tidak ada news <30 menit",
            ],
        },
        "MACRO_TRIGGER": {
            "name"   : "MACRO TRIGGER",
            "filters": 6,
            "items"  : [
                "News surprise teridentifikasi",
                "SMC entry valid (OB/FVG)",
                "Volume konfirmasi",
                "DXY berlawanan",
                "<30 menit setelah news",
                "Kill Zone aktif",
            ],
        },
        "SESSION_BREAKOUT": {
            "name"   : "SESSION BREAKOUT",
            "filters": 7,
            "items"  : [
                "Asia range terbentuk jelas",
                "Body candle CLOSE di luar range",
                "Volume 2x rata-rata",
                "London session aktif",
                "ADX > 20",
                "Arah sesuai bias Daily",
                "FVG / OB di sisi breakout",
            ],
        },
    },
    "no_trade": [
        ("Sabtu & Minggu",        "Pasar tutup",           "MUTLAK"),
        ("±30 menit news HIGH",   "Volatilitas ekstrem",   "MUTLAK"),
        ("3x loss berturut",      "Judgment rusak",        "WAJIB"),
        ("H4 Choppy ADX<20",      "Tidak ada trending",    "WAJIB"),
        ("Spread >50 pip",        "Cost terlalu tinggi",   "WAJIB"),
        ("Mental buruk",          "Ngantuk/stress",        "WAJIB"),
    ],
    "key_levels": [
        ("Strong Resistance", 4800),
        ("Resistance",        4750),
        ("Pivot",             4680),
        ("Support",           4620),
        ("Strong Support",    4579),
    ],
    "economic_calendar": [
        ("Senin 12 Mei",   "CPI April",             "🔴 KRITIS"),
        ("Selasa 13 Mei",  "PPI April",             "🔴 TINGGI"),
        ("Kamis 15 Mei",   "Initial Jobless Claims","🟡 SEDANG"),
        ("Rabu 21 Mei",    "PMI Manufacturing",     "🟡 SEDANG"),
    ],
}

# Gold Alpha Fase 0 findings (confirmed empirically)
GOLD_ALPHA = {
    "correlations": {
        "DXY"      : -0.980,
        "VIX"      : -0.982,
        "RSI"      : +0.921,
        "ATR"      : -0.428,
        "ADX"      : -0.125,
        "Fed Rate" : None,   # Bug — data missing
    },
    "causal_ate"   : -0.000285,   # Fed +1% → gold -0.0285%/hari
    "top_features" : ["gold_lag1", "gold_ma20", "dxy_lag1", "vix_lag1"],
    "insight"      : (
        "DXY & VIX = driver terkuat. "
        "ADX = filter timing bukan arah. "
        "Momentum kemarin > data real-time."
    ),
}

# ══════════════════════════════════════════════════════════════════════════════
# 🕐 HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def now_wib() -> datetime:
    return datetime.now(WIB)

def get_session(hour: int) -> dict:
    """Identifikasi sesi dan Kill Zone aktif."""
    if CONFIG["KZ_LONDON_START"] <= hour < CONFIG["KZ_LONDON_END"]:
        return {"name":"London Kill Zone ⭐", "prime":True,  "icon":"🏦", "kz":True}
    if CONFIG["KZ_NY_START"] <= hour < CONFIG["KZ_NY_END"]:
        return {"name":"NY Kill Zone ⭐",     "prime":True,  "icon":"🗽", "kz":True}
    if 8 <= hour < CONFIG["KZ_LONDON_START"]:
        return {"name":"London Early",        "prime":False, "icon":"🌅", "kz":False}
    if 0 <= hour < 8:
        return {"name":"Asian Session",       "prime":False, "icon":"🌙", "kz":False}
    return     {"name":"NY Afternoon",        "prime":False, "icon":"🌃", "kz":False}

def get_regime(gold: float, gold_ma200: float, vix: float) -> str:
    if gold > gold_ma200 and vix < 20:  return "Bull Low-Vol 📈"
    if gold > gold_ma200 and vix >= 20: return "Bull High-Vol 🌊"
    if gold <= gold_ma200 and vix < 20: return "Bear Low-Vol 📉"
    return                                       "Bear High-Vol 🔴"

def calc_lot(risk_pct: float, sl_pips: float) -> float:
    risk_usd = CONFIG["BALANCE"] * (risk_pct / 100)
    return max(CONFIG["MIN_LOT"], round(risk_usd / (sl_pips * 10), 2))

def is_no_trade_day() -> bool:
    return now_wib().weekday() >= 5  # Sabtu/Minggu

# ══════════════════════════════════════════════════════════════════════════════
# 📡 MARKET DATA
# ══════════════════════════════════════════════════════════════════════════════

def get_price() -> dict:
    """Ambil harga XAUUSD — MT5 → yfinance → fallback."""
    # Try MT5
    if MT5_OK and mt5.initialize():
        tick = mt5.symbol_info_tick(CONFIG["SYMBOL"])
        if tick:
            return {
                "bid"   : round(tick.bid, 2),
                "ask"   : round(tick.ask, 2),
                "spread": round((tick.ask - tick.bid) * 10, 1),
                "time"  : datetime.fromtimestamp(tick.time, tz=timezone.utc).strftime("%H:%M UTC"),
                "source": "MT5",
            }

    # Try yfinance
    if YF_OK:
        try:
            t = yf.Ticker("GC=F")
            p = t.fast_info["last_price"]
            return {
                "bid"   : round(p - 0.3, 2),
                "ask"   : round(p + 0.3, 2),
                "spread": 0.6,
                "time"  : now_wib().strftime("%H:%M WIB"),
                "source": "yfinance",
            }
        except:
            pass

    # Fallback REST
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/GC=F",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=5
        )
        p = r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        return {
            "bid": round(p-0.3, 2), "ask": round(p+0.3, 2),
            "spread": 0.6, "time": now_wib().strftime("%H:%M WIB"),
            "source": "Yahoo REST",
        }
    except:
        return {"bid":0, "ask":0, "spread":0, "time":"N/A", "source":"Error"}

def get_macro() -> dict:
    """Ambil DXY dan VIX."""
    result = {"dxy": None, "vix": None, "spx": None}
    if not YF_OK:
        return result
    try:
        result["dxy"] = round(yf.Ticker("DX-Y.NYB").fast_info["last_price"], 3)
        result["vix"] = round(yf.Ticker("^VIX").fast_info["last_price"], 2)
        result["spx"] = round(yf.Ticker("^GSPC").fast_info["last_price"], 2)
    except:
        pass
    return result

def get_gold_alpha_signal() -> dict:
    """Baca signal terbaru dari prediction_log.csv."""
    path = Path(CONFIG["PRED_LOG"])
    if not path.exists():
        return {"signal":"N/A", "confidence":0, "grade":"?", "valid":False, "date":"—"}

    try:
        rows = []
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

        if not rows:
            return {"signal":"N/A", "confidence":0, "grade":"?", "valid":False, "date":"—"}

        last = rows[-1]
        conf = float(last.get("confidence", 0))
        grade = "A" if conf >= 0.75 else ("B" if conf >= 0.65 else "C")
        return {
            "signal"    : last.get("signal", "N/A"),
            "confidence": conf,
            "grade"     : grade,
            "valid"     : conf >= CONFIG["SIGNAL_THRESHOLD"],
            "date"      : last.get("date", "—"),
            "regime"    : last.get("regime", "Unknown"),
            "vix"       : last.get("vix", "—"),
        }
    except:
        return {"signal":"N/A", "confidence":0, "grade":"?", "valid":False, "date":"—"}

def get_mt5_positions() -> list:
    if not MT5_OK or not mt5.initialize():
        return []
    positions = mt5.positions_get(symbol=CONFIG["SYMBOL"])
    if not positions:
        return []
    result = []
    for p in positions:
        result.append({
            "ticket": p.ticket,
            "type"  : "BUY 📈" if p.type == 0 else "SELL 📉",
            "volume": p.volume,
            "open"  : round(p.price_open, 2),
            "sl"    : round(p.sl, 2),
            "tp"    : round(p.tp, 2),
            "profit": round(p.profit, 2),
            "pips"  : round((p.price_current - p.price_open) * 10
                            if p.type == 0
                            else (p.price_open - p.price_current) * 10, 1),
        })
    return result

# ══════════════════════════════════════════════════════════════════════════════
# 📨 MESSAGE BUILDERS
# ══════════════════════════════════════════════════════════════════════════════

def build_morning_brief() -> str:
    t      = now_wib()
    price  = get_price()
    macro  = get_macro()
    sig    = get_gold_alpha_signal()
    hour   = t.hour
    sesh   = get_session(hour)

    mid    = (price["bid"] + price["ask"]) / 2
    nearest = min(X01["key_levels"], key=lambda x: abs(x[1] - mid))
    dist   = round(mid - nearest[1], 1)

    # Regime
    regime = "—"
    if macro["vix"] and mid > 0:
        regime = get_regime(mid, mid * 0.97, macro["vix"])  # approx ma200

    # Signal icon
    sig_icon = "✅" if sig["valid"] else "⚠️"
    sig_action = sig["signal"] if sig["valid"] else f"SKIP (Grade {sig['grade']} < threshold)"

    msg = f"""
🌅 *X.01 MORNING BRIEF*
📅 {t.strftime("%A, %d %B %Y")} | {t.strftime("%H:%M")} WIB

💰 *XAUUSD*
├ Bid    : `${price['bid']:,.2f}`
├ Ask    : `${price['ask']:,.2f}`
├ Spread : `{price['spread']} pip`
└ Level  : *{nearest[0]}* `${nearest[1]:,.0f}` ({'+' if dist > 0 else ''}{dist})

🌍 *MACRO*
├ DXY   : `{macro['dxy'] or '—'}`
├ VIX   : `{macro['vix'] or '—'}`
├ SPX   : `{macro['spx'] or '—'}`
└ Regime: _{regime}_

🤖 *GOLD ALPHA SIGNAL* _{sig['date']}_
├ Signal : `{sig['signal']}` | Grade `{sig['grade']}`
├ Confidence: `{sig['confidence']:.1%}`
└ Action : {sig_icon} _{sig_action}_

📊 *GOLD ALPHA INSIGHTS*
├ DXY vs Gold  : `-0.980` (terkuat)
├ VIX vs Gold  : `-0.982` (terkuat)
└ Fed Rate ATE : `-0.0285%/hari`

🕐 *SESI*: {sesh['icon']} {sesh['name']}
{'⭐ KILL ZONE AKTIF — siap cari setup' if sesh['kz'] else '→ Tunggu Kill Zone: London 14:00 / NY 19:30 WIB'}

{'🚨 *HARI INI NON-TRADING (Weekend)* — Pasar tutup' if is_no_trade_day() else ''}

📅 *KALENDER EKONOMI MINGGU INI*
"""
    for event_date, event, impact in X01["economic_calendar"]:
        msg += f"{impact} {event_date}: {event}\n"

    msg += f"""
⚠️ *RULES HARI INI*
├ Risk/trade : Scalp {CONFIG['RISK_SCALP']}% | Swing {CONFIG['RISK_SWING']}%
├ Max trades : {CONFIG['MAX_TRADES_DAY']}x
└ Stop di    : -{CONFIG['MAX_DD_DAILY']}% DD harian

_"Disiplin + Data + Waktu = Edge yang tidak bisa dicopy siapapun."_
🤖 _X.01 Bot v2.0 | Valetax MT5_
"""
    return msg

def build_signal_msg() -> str:
    sig   = get_gold_alpha_signal()
    price = get_price()
    macro = get_macro()
    t     = now_wib()

    icon  = "✅" if sig["valid"] else "🚫"
    conf_bar = "█" * int(sig["confidence"] * 10) + "░" * (10 - int(sig["confidence"] * 10))

    return f"""
🤖 *GOLD ALPHA ML SIGNAL*
📅 {sig['date']} | Update: {t.strftime('%H:%M')} WIB

📊 *Signal*    : `{sig['signal']}`
📈 *Confidence*: `{sig['confidence']:.1%}` [{conf_bar}]
🏷️ *Grade*     : `{sig['grade']}`
🌡️ *VIX*       : `{sig.get('vix', '—')}`
🌐 *Regime*    : _{sig.get('regime', '—')}_

*Status X.01* : {icon} `{'VALID — pertimbangkan entry' if sig['valid'] else f"SKIP — confidence < {CONFIG['SIGNAL_THRESHOLD']:.0%}"}`

*Threshold grades:*
├ A: ≥75% → Strong, pertimbangkan entry
├ B: 65–74% → Butuh 1+ konfirmasi SMC
├ C+: 60–64% → Butuh semua filter X.01
└ C: <60% → SKIP, terlalu banyak noise

⚠️ _Signal ML hanya konfirmasi tambahan._
_Tetap jalankan checklist X.01 sebelum entry._
"""

def build_scorecard_msg(strategy_key: str) -> str:
    strat = X01["strategies"].get(strategy_key)
    if not strat:
        return "❌ Strategi tidak ditemukan. Gunakan: LIQUIDITY\\_SWEEP, MACRO\\_TRIGGER, SESSION\\_BREAKOUT"

    t   = now_wib()
    sesh= get_session(t.hour)

    msg = f"""
🎯 *SCORECARD — {strat['name']}*
{t.strftime('%H:%M')} WIB | {sesh['icon']} {sesh['name']}

*Checklist {strat['filters']}/{strat['filters']} filter wajib:*
"""
    for i, item in enumerate(strat["items"], 1):
        msg += f"{i}. ☐ {item}\n"

    msg += f"""
*Cara pakai:*
Centang semua filter di chart kamu.
Jika semua ✅ → *GO*
Jika ada yang ❌ → *NO GO*, tunggu setup lebih baik.

💡 _{strat['name'].split()[0]}: {'PRIORITAS UTAMA' if 'PRIORITAS' in strat['name'] else 'Setup valid kalau semua terpenuhi'}_
"""
    return msg

def build_notrade_msg() -> str:
    t    = now_wib()
    hour = t.hour
    dow  = t.weekday()

    active = []
    if dow >= 5:
        active.append("🔴 SABTU/MINGGU — pasar tutup")

    msg = f"""
🚫 *NO TRADE ZONE CHECK*
{t.strftime('%H:%M')} WIB

*6 Kondisi WAJIB dihindari:*
"""
    for cond, why, level in X01["no_trade"]:
        icon = "🔴" if level == "MUTLAK" else "🟡"
        msg += f"{icon} *{cond}*\n   _{why}_ — `{level}`\n"

    if active:
        msg += f"\n*⚠️ AKTIF SEKARANG:*\n"
        for a in active:
            msg += f"  {a}\n"
        msg += "\n🚫 *JANGAN BUKA POSISI APAPUN*"
    else:
        msg += "\n✅ *Tidak ada No Trade Zone aktif saat ini.*\nCek tetap manual sebelum entry."

    return msg

def build_levels_msg() -> str:
    price = get_price()
    mid   = (price["bid"] + price["ask"]) / 2

    msg = f"""
🎯 *KEY LEVELS XAUUSD*
💰 Harga sekarang: `${mid:,.2f}`

"""
    for label, level in reversed(X01["key_levels"]):
        dist = round(mid - level, 1)
        icon = "🔴" if "Resistance" in label else ("🟢" if "Support" in label else "🟡")
        pos  = "▲" if dist > 0 else "▼"
        msg += f"{icon} *{label}* : `${level:,.0f}` {pos}{abs(dist):.1f}\n"

    msg += """
*Zone Mapping MT5:*
🔴 Merah → Resistance, OB Bearish, PDH
🟢 Hijau → Support, OB Bullish, PDL
🟡 Kuning → EQ 50%, Liquidity cluster
🔵 Biru → CHoCH / BOS level
🟠 Orange → FVG zone
"""
    return msg

def build_lot_msg(sl_pips: float, mode: str = "SCALPING") -> str:
    risk_pct  = CONFIG["RISK_SCALP"] if mode == "SCALPING" else CONFIG["RISK_SWING"]
    lot       = calc_lot(risk_pct, sl_pips)
    risk_usd  = CONFIG["BALANCE"] * risk_pct / 100
    partial   = CONFIG["PARTIAL_SCALP"] if mode == "SCALPING" else CONFIG["PARTIAL_SWING"]
    hold      = "Max 2 jam" if mode == "SCALPING" else "24-72 jam"

    return f"""
🧮 *LOT SIZE CALCULATOR*
Mode: `{mode}`

💰 Modal     : `${CONFIG['BALANCE']:.2f}` (Valetax)
⚠️ Risk      : `{risk_pct}%` = `${risk_usd:.2f}`
📏 SL        : `{sl_pips} pip`
⚖️ Leverage  : `1:{CONFIG['LEVERAGE']}`

✅ *LOT OPTIMAL : `{lot} lot`*

📊 Setup:
├ Partial TP1 : {partial}% dari posisi
├ Max hold    : {hold}
└ Min lot     : {CONFIG['MIN_LOT']} (Valetax)

_Nilai pip XAUUSD = $10/lot/pip_
"""

def build_fre_msg() -> str:
    """FRE — AI Initiated Analysis."""
    price = get_price()
    macro = get_macro()
    sig   = get_gold_alpha_signal()
    t     = now_wib()
    sesh  = get_session(t.hour)
    mid   = (price["bid"] + price["ask"]) / 2

    regime = "—"
    if macro["vix"] and mid > 0:
        regime = get_regime(mid, mid * 0.97, macro["vix"])

    # Simple bias logic from Gold Alpha findings
    dxy_bearish = macro["dxy"] and macro["dxy"] > 104
    vix_risk_on = macro["vix"] and macro["vix"] < 18

    bull_count = sum([not dxy_bearish, not vix_risk_on, mid > 4700])
    bias = "🟢 Bullish" if bull_count >= 2 else ("🔴 Bearish" if bull_count == 0 else "🟡 Netral")

    return f"""
📡 *FRE — AI INITIATED ANALYSIS*
_{t.strftime('%H:%M')} WIB | {sesh['icon']} {sesh['name']}_

━━━━━━━━━━━━━━━━━━━━━
*FUNDAMENTAL*
├ Bias       : {bias}
├ DXY        : `{macro['dxy'] or '—'}` {'(bearish gold)' if dxy_bearish else '(neutral/bullish)'}
├ VIX        : `{macro['vix'] or '—'}` {'(risk-on)' if vix_risk_on else '(risk-off/elevated)'}
└ Regime     : _{regime}_

*TECHNICAL*
├ Harga      : `${mid:,.2f}`
├ Nearest    : {min(X01['key_levels'], key=lambda x: abs(x[1]-mid))[0]}
└ Kill Zone  : {'✅ AKTIF' if sesh['kz'] else f"❌ Next: London 14:00 / NY 19:30 WIB"}

*GOLD ALPHA SIGNAL*
├ Signal     : `{sig['signal']}` Grade `{sig['grade']}`
├ Confidence : `{sig['confidence']:.1%}`
└ Valid       : {'✅' if sig['valid'] else '⚠️ SKIP'}

*GOLD ALPHA INSIGHTS*
├ DXY driver : -0.980 correlation
├ VIX driver : -0.982 correlation
└ Fed ATE    : -0.0285%/hari

━━━━━━━━━━━━━━━━━━━━━
*KEPUTUSAN KAMU:*
/go → Lanjut cari entry
/no → Skip sesi ini
/tahan → Tunggu konfirmasi

_Balas dengan setup kamu untuk TIE evaluation._
"""

def build_eod_msg() -> str:
    positions = get_mt5_positions()
    price     = get_price()
    sig       = get_gold_alpha_signal()
    t         = now_wib()
    total_pnl = sum(p["profit"] for p in positions)

    msg = f"""
🌃 *X.01 END OF DAY REPORT*
📅 {t.strftime('%d %B %Y')}

💰 *PENUTUPAN*
└ XAUUSD : `${price['bid']:,.2f}`

📊 *POSISI TERBUKA*
└ {len(positions)} posisi | P/L: `${total_pnl:+.2f}`

🤖 *SIGNAL BESOK (Gold Alpha)*
└ {sig['signal']} | {sig['confidence']:.1%} | Grade {sig['grade']}

📅 *EVENT BESOK*
"""
    for event_date, event, impact in X01["economic_calendar"][:2]:
        msg += f"  {impact} {event_date}: {event}\n"

    msg += f"""
✍️ *JURNAL CHECKLIST*
├ ☐ Berapa trade hari ini?
├ ☐ Win / Loss / BE?
├ ☐ Pakai strategi mana?
├ ☐ Semua filter terpenuhi?
├ ☐ Emosi terkontrol?
└ ☐ Pelajaran hari ini?

🎯 *PREP BESOK*
├ Tandai PDH & PDL
├ Identifikasi zone D1 & H4
└ Set alarm Kill Zone 14:00 WIB

_"Bukan siapa yang paling pintar —_
_tapi siapa yang paling lama diam."_
🤖 _X.01 Bot v2.0_
"""
    return msg

def build_positions_msg() -> str:
    positions = get_mt5_positions()
    price     = get_price()
    t         = now_wib()

    if not positions:
        return f"""
📋 *POSISI AKTIF*
{t.strftime('%H:%M')} WIB

✅ Tidak ada posisi terbuka.
💰 XAUUSD: `${price['bid']:,.2f}`
"""

    total = sum(p["profit"] for p in positions)
    msg   = f"📋 *POSISI AKTIF — {t.strftime('%H:%M')} WIB*\n\n"

    for i, p in enumerate(positions, 1):
        icon = "✅" if p["profit"] >= 0 else "❌"
        msg += f"""*#{i} — {p['type']}*
├ Volume : `{p['volume']} lot`
├ Open   : `${p['open']:,.2f}`
├ SL/TP  : `${p['sl']:,.2f}` / `${p['tp']:,.2f}`
├ Pips   : `{p['pips']:+.1f}`
└ P/L    : {icon} `${p['profit']:+.2f}`\n\n"""

    pnl_icon = "📈" if total >= 0 else "📉"
    msg += f"{pnl_icon} *TOTAL P/L: `${total:+.2f}`*"
    return msg

def build_macro_insight_msg() -> str:
    macro = get_macro()
    price = get_price()
    mid   = (price["bid"] + price["ask"]) / 2

    return f"""
🌍 *MACRO + GOLD ALPHA INSIGHTS*

*Live Data:*
├ XAUUSD : `${mid:,.2f}`
├ DXY    : `{macro['dxy'] or '—'}`
├ VIX    : `{macro['vix'] or '—'}`
└ SPX    : `{macro['spx'] or '—'}`

*Korelasi Empiris (Fase 0, n=3.700+ hari):*
├ DXY vs Gold  : `-0.980` 🔴 SANGAT KUAT
├ VIX vs Gold  : `-0.982` 🔴 SANGAT KUAT
├ RSI vs Gold  : `+0.921` 🟢 KUAT
├ ATR vs Gold  : `-0.428` 🟡 SEDANG
└ ADX vs Gold  : `-0.125` ⬜ LEMAH

*Causal Analysis (DML):*
└ Fed +1% → Gold Return `-0.0285%/hari`

*Interpretasi sekarang:*
├ DXY `{macro['dxy'] or '?'}` → {'⬇️ Bearish gold' if macro['dxy'] and macro['dxy'] > 104 else '✅ Neutral/Bullish gold'}
├ VIX `{macro['vix'] or '?'}` → {'🔴 Risk-off → safe haven demand' if macro['vix'] and macro['vix'] > 20 else '✅ Risk-on, kurangi bias BUY'}
└ Regime → _{'Identifikasi di Gold Alpha Fase 1'}_

*Top Predictors (Gold Alpha RF):*
gold\\_lag1 → gold\\_ma20 → dxy\\_lag1 → vix\\_lag1

_Fase 1 notebook sudah siap — jalankan di Colab._
"""

# ══════════════════════════════════════════════════════════════════════════════
# 🤖 TELEGRAM HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"""
🥇 *XAU/USD SYSTEM X.01 — BOT v2.0*
_Integrated: X.01 + Gold Alpha Fase 0 & 1_

*COMMANDS:*
/brief   — Morning brief lengkap
/harga   — Harga XAUUSD live
/signal  — Gold Alpha ML signal
/macro   — Macro insights (DXY, VIX, korelasi)
/posisi  — Posisi open MT5
/level   — Key levels XAUUSD
/sesi    — Status sesi & Kill Zone
/fre     — FRE analysis (AI-initiated)
/notrade — Cek No Trade Zone
/kalender— Kalender ekonomi minggu ini

/lot [pips] [mode] — Kalkulator lot
  Contoh: /lot 20 SCALPING
  Contoh: /lot 50 SWING

/checklist [strategi] — Scorecard entry
  /checklist SWEEP   → Liquidity Sweep
  /checklist MACRO   → Macro Trigger
  /checklist BREAKOUT→ Session Breakout

/eod     — End of day report
/help    — Menu ini

*SISTEM:*
3 Pilar: Macro + Technical + Eksekusi
3 Strategi: Sweep ⭐ / Macro / Breakout
Research: Gold Alpha (DXY -0.98, VIX -0.98)
Broker: Valetax MT5 | Leverage 1:{CONFIG['LEVERAGE']}

_"Disiplin + Data + Waktu = Edge."_
""", parse_mode="Markdown")

async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Menyiapkan brief...")
    await update.message.reply_text(build_morning_brief(), parse_mode="Markdown")

async def cmd_harga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price = get_price()
    sesh  = get_session(now_wib().hour)
    await update.message.reply_text(f"""
💰 *XAUUSD LIVE*
├ Bid    : `${price['bid']:,.2f}`
├ Ask    : `${price['ask']:,.2f}`
└ Spread : `{price['spread']} pip`

{sesh['icon']} {sesh['name']}
{'⭐ Kill Zone aktif!' if sesh['kz'] else ''}
📡 _{price['source']} | {price['time']}_
""", parse_mode="Markdown")

async def cmd_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_signal_msg(), parse_mode="Markdown")

async def cmd_macro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Fetching data...")
    await update.message.reply_text(build_macro_insight_msg(), parse_mode="Markdown")

async def cmd_posisi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_positions_msg(), parse_mode="Markdown")

async def cmd_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_levels_msg(), parse_mode="Markdown")

async def cmd_sesi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t    = now_wib()
    sesh = get_session(t.hour)
    await update.message.reply_text(f"""
🕐 *STATUS SESI*
{t.strftime('%H:%M')} WIB

📍 *{sesh['icon']} {sesh['name']}*
{'⭐ KILL ZONE AKTIF — cari setup sekarang!' if sesh['kz'] else '→ Bukan Kill Zone, volatilitas lebih rendah'}

*Jadwal Kill Zone (WIB):*
🏦 London KZ : 14:00 – 16:00
🗽 NY KZ     : 19:30 – 22:00

*Sesi lain:*
🌙 Asian     : 00:00 – 08:00 (konsolidasi)
🌅 London    : 08:00 – 14:00
🌃 NY Late   : 22:00 – 00:00

_Kill Zone = waktu prioritas entry X.01._
_Di luar KZ: hindari entry baru._
""", parse_mode="Markdown")

async def cmd_fre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Menjalankan FRE analysis...")
    await update.message.reply_text(build_fre_msg(), parse_mode="Markdown")

async def cmd_notrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_notrade_msg(), parse_mode="Markdown")

async def cmd_kalender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "📅 *KALENDER EKONOMI MINGGU INI*\n\n"
    for event_date, event, impact in X01["economic_calendar"]:
        msg += f"{impact} *{event_date}*\n   {event}\n\n"
    msg += "_Hindari entry ±30 menit sebelum/sesudah HIGH impact._"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_lot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ Contoh: `/lot 20 SCALPING` atau `/lot 50 SWING`",
            parse_mode="Markdown"
        )
        return
    try:
        sl_pips = float(args[0])
        mode    = args[1].upper() if len(args) > 1 else "SCALPING"
        if mode not in ("SCALPING", "SWING"):
            mode = "SCALPING"
        await update.message.reply_text(build_lot_msg(sl_pips, mode), parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("⚠️ Format: `/lot [pips] [SCALPING/SWING]`", parse_mode="Markdown")

async def cmd_checklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ Pilih strategi:\n/checklist SWEEP\n/checklist MACRO\n/checklist BREAKOUT",
            parse_mode="Markdown"
        )
        return

    key_map = {
        "SWEEP"    : "LIQUIDITY_SWEEP",
        "LIQUIDITY": "LIQUIDITY_SWEEP",
        "MACRO"    : "MACRO_TRIGGER",
        "BREAKOUT" : "SESSION_BREAKOUT",
        "SESSION"  : "SESSION_BREAKOUT",
    }
    key = key_map.get(args[0].upper(), args[0].upper())
    await update.message.reply_text(build_scorecard_msg(key), parse_mode="Markdown")

async def cmd_eod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_eod_msg(), parse_mode="Markdown")

async def cmd_go(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t    = now_wib()
    sesh = get_session(t.hour)
    sig  = get_gold_alpha_signal()
    await update.message.reply_text(f"""
✅ *GO — LANJUT CARI ENTRY*
{t.strftime('%H:%M')} WIB

*Checklist sebelum eksekusi:*
☐ Kill Zone aktif? ({sesh['name']})
☐ Pilih strategi (Sweep/Macro/Breakout)
☐ Semua filter 6/6 atau 7/7 terpenuhi?
☐ SL jelas di bawah/atas struktur
☐ TP minimal 1:2 dari SL
☐ Lot size sudah dihitung? /lot [pips]
☐ Spread < {CONFIG['SPREAD_MAX']} pip?
☐ Gold Alpha signal: {sig['signal']} {sig['confidence']:.1%} ({'✅' if sig['valid'] else '⚠️'})

_Setelah entry, catat di jurnal._
""", parse_mode="Markdown")

async def cmd_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
🚫 *NO — SKIP SESI INI*

Keputusan bagus. Pasar selalu ada besok.

*Lakukan sekarang:*
→ Tutup chart
→ Catat kenapa skip di jurnal
→ Set alarm Kill Zone berikutnya

_"Tidak masuk trade yang ragu-ragu_
_adalah salah satu keputusan terbaik."_
""", parse_mode="Markdown")

async def cmd_tahan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t    = now_wib()
    await update.message.reply_text(f"""
⏳ *TAHAN — TUNGGU KONFIRMASI*
{t.strftime('%H:%M')} WIB

*Yang perlu kamu tunggu:*
☐ BOS atau CHoCH terkonfirmasi di H1
☐ Harga retrace ke OB atau FVG
☐ Kill Zone masih aktif
☐ Volume konfirmasi

*Set alert di MT5:*
→ Pasang price alert di level kritis
→ Jangan stare at chart

_Patience adalah edge terbesar._
""", parse_mode="Markdown")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)

# ══════════════════════════════════════════════════════════════════════════════
# ⏰ SCHEDULER
# ══════════════════════════════════════════════════════════════════════════════

async def send_msg(token: str, chat_id: str, msg: str):
    bot = Bot(token=token)
    await bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

def run_scheduler(token: str, chat_id: str):
    def job_morning():
        asyncio.run(send_msg(token, chat_id, build_morning_brief()))

    def job_london():
        sig  = get_gold_alpha_signal()
        price= get_price()
        asyncio.run(send_msg(token, chat_id, f"""
🏦 *LONDON KILL ZONE OPEN*
💰 XAUUSD: `${price['bid']:,.2f}`
🤖 Signal: `{sig['signal']}` | {sig['confidence']:.1%} | Grade `{sig['grade']}`

⭐ Waktu terbaik cari setup.
Prioritaskan: *Liquidity Sweep* → *Macro Trigger*

_Jalankan /fre untuk analisis lengkap._
"""))

    def job_ny():
        sig  = get_gold_alpha_signal()
        price= get_price()
        asyncio.run(send_msg(token, chat_id, f"""
🗽 *NY KILL ZONE OPEN*
💰 XAUUSD: `${price['bid']:,.2f}`
🤖 Signal: `{sig['signal']}` | {sig['confidence']:.1%} | Grade `{sig['grade']}`

⭐ Volatilitas tertinggi dimulai.
Konfirmasi atau reverse dari London.

_/level untuk key levels | /fre untuk analisis_
"""))

    def job_eod():
        asyncio.run(send_msg(token, chat_id, build_eod_msg()))

    schedule.every().day.at(CONFIG["REPORT_MORNING"]).do(job_morning)
    schedule.every().day.at(CONFIG["ALERT_LONDON"]).do(job_london)
    schedule.every().day.at(CONFIG["ALERT_NY"]).do(job_ny)
    schedule.every().day.at(CONFIG["REPORT_EOD"]).do(job_eod)

    print(f"⏰ Scheduler aktif:")
    print(f"   {CONFIG['REPORT_MORNING']} WIB — Morning Brief")
    print(f"   {CONFIG['ALERT_LONDON']} WIB — London KZ Alert")
    print(f"   {CONFIG['ALERT_NY']} WIB — NY KZ Alert")
    print(f"   {CONFIG['REPORT_EOD']} WIB — EOD Report")

    while True:
        schedule.run_pending()
        time.sleep(30)

# ══════════════════════════════════════════════════════════════════════════════
# 🚀 MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    if not TELEGRAM_OK:
        print("❌ Install: pip install python-telegram-bot==20.7")
        return
    if CONFIG["TOKEN"] == "MASUKKAN_BOT_TOKEN_DISINI":
        print("❌ Isi TOKEN di CONFIG")
        return
    if CONFIG["CHAT_ID"] == "MASUKKAN_CHAT_ID_DISINI":
        print("❌ Isi CHAT_ID di CONFIG")
        return

    print("╔══════════════════════════════════════════════╗")
    print("║   XAU/USD SYSTEM X.01 — BOT v2.0 STARTING   ║")
    print("╚══════════════════════════════════════════════╝")
    print(f"💰 Balance  : ${CONFIG['BALANCE']:.2f} (Valetax)")
    print(f"⚖️  Leverage : 1:{CONFIG['LEVERAGE']}")
    print(f"⚠️  Risk     : Scalp {CONFIG['RISK_SCALP']}% | Swing {CONFIG['RISK_SWING']}%")
    print(f"📡 Signal   : Min {CONFIG['SIGNAL_THRESHOLD']:.0%} confidence")
    print()

    # Scheduler thread
    threading.Thread(
        target=run_scheduler,
        args=(CONFIG["TOKEN"], CONFIG["CHAT_ID"]),
        daemon=True
    ).start()

    # Bot
    app = Application.builder().token(CONFIG["TOKEN"]).build()
    handlers = [
        ("start",      cmd_start),
        ("brief",      cmd_brief),
        ("harga",      cmd_harga),
        ("signal",     cmd_signal),
        ("macro",      cmd_macro),
        ("posisi",     cmd_posisi),
        ("level",      cmd_level),
        ("sesi",       cmd_sesi),
        ("fre",        cmd_fre),
        ("notrade",    cmd_notrade),
        ("kalender",   cmd_kalender),
        ("lot",        cmd_lot),
        ("checklist",  cmd_checklist),
        ("eod",        cmd_eod),
        ("go",         cmd_go),
        ("no",         cmd_no),
        ("tahan",      cmd_tahan),
        ("help",       cmd_help),
    ]
    for cmd, handler in handlers:
        app.add_handler(CommandHandler(cmd, handler))

    print("✅ Bot aktif! Buka Telegram → /start")
    print("   Ctrl+C untuk berhenti\n")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
