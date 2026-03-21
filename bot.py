import os
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime
import pytz

BOT_TOKEN = "8749089704:AAFq_Xh6_oYk61V4mv8eNVdcX3Yh27AJuuY"

CHAT_IDS = [
    "1070509960",
    "1937479700",
    "5034473353"
    # "2037873693"
]

SYMBOL     ="ETHUSDT"
IST        = pytz.timezone("Asia/Kolkata")

last_signal = None  # in-memory; resets on restart

print(f"[CONFIG] Symbol: {SYMBOL}")
print(f"[CONFIG] Chat IDs loaded: {len(CHAT_IDS)}")

def send_message(text):
    """Send a message to all configured Telegram chat IDs."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for chat_id in CHAT_IDS:
        try:
            r = requests.post(
                url,
                data={"chat_id": chat_id.strip(), "text": text},
                timeout=10
            )
            r.raise_for_status()
            print(f"[TELEGRAM] Message sent to {chat_id.strip()}")
        except Exception as e:
            print(f"[ERROR] Telegram failed for {chat_id}: {e}")
            
def calculate_rsi(series, length=14):
    """
    Wilder's RSI using EWM (alpha = 1/length).
    Returns a Series of RSI values (0–100).
    """
    delta    = series.diff()
    gain     = pd.Series(np.where(delta > 0, delta, 0), index=series.index)
    loss     = pd.Series(np.where(delta < 0, -delta, 0), index=series.index)
    avg_gain = gain.ewm(alpha=1/length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/length, adjust=False).mean()
    rs       = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def fetch_candles(symbol=SYMBOL, resolution="30m", lookback_candles=200):
    """Fetch OHLCV candles from Delta Exchange API."""
    end   = int(time.time())
    start = end - lookback_candles * 1800

    resp = requests.get(
        "https://api.delta.exchange/v2/history/candles",
        params={"symbol": symbol, "resolution": resolution, "start": start, "end": end},
        timeout=15
    )
    resp.raise_for_status()
    data = resp.json()

    if "result" not in data or not data["result"]:
        raise ValueError("No candle data returned from API")

    df = pd.DataFrame(data["result"])
    df.rename(columns={
        "time": "Open_time", "open": "Open", "high": "High",
        "low": "Low", "close": "Close", "volume": "Volume"
    }, inplace=True)

    df["Open_time"] = (
        pd.to_datetime(df["Open_time"], unit='s')
        .dt.tz_localize("UTC")
        .dt.tz_convert("Asia/Kolkata")
        .dt.tz_localize(None)
    )
    df = df.sort_values("Open_time").reset_index(drop=True)
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = df[col].astype(float)

    print(f"[FETCH] {len(df)} candles loaded. Latest: {df['Open_time'].iloc[-1]}")
    return df

def compute_new_signal(df):
    df = df.copy()

    # =========================
    # 📊 INDICATORS
    # =========================
    df["hlc3"] = (df["High"] + df["Low"] + df["Close"]) / 3

    df["ma"] = df["hlc3"].rolling(60).mean()

    df["mean_dev"] = df["hlc3"].rolling(60).apply(
        lambda x: np.mean(np.abs(x - np.mean(x))), raw=True
    )

    df["CCI_60"] = (df["hlc3"] - df["ma"]) / (0.015 * df["mean_dev"])

    df["CCI_EMA"] = df["CCI_60"].ewm(span=7, adjust=False).mean()

    df["Diff_CCI"] = df["CCI_60"] - df["CCI_EMA"]

    df["EMA7"] = df["Close"].ewm(span=7, adjust=False).mean()

    df["RSI"] = calculate_rsi(df["Close"])

    # =========================
    # 🎯 FINAL SIGNAL LOGIC
    # =========================

    signals = []
    current_position = None  # 🔥 Tracks ongoing state

    for i in range(len(df)):
        if i == 0:
            signals.append("No Trade")
            continue

        # Current values
        close = df["Close"].iloc[i]
        ema = df["EMA7"].iloc[i]
        cci = df["CCI_60"].iloc[i]
        cci_ema = df["CCI_EMA"].iloc[i]

        # Previous values
        prev_close = df["Close"].iloc[i-1]
        prev_ema = df["EMA7"].iloc[i-1]
        prev_cci = df["CCI_60"].iloc[i-1]
        prev_cci_ema = df["CCI_EMA"].iloc[i-1]

        # =========================
        # 🔄 CONTINUATION LOGIC FIRST
        # =========================

        # Continue LONG
        if current_position == "Long Trade":
            if close > ema and cci > cci_ema:
                signals.append("Long Trade")
                continue
            else:
                current_position = None  # exit

        # Continue SHORT
        elif current_position == "Short Trade":
            if close < ema and cci < cci_ema:
                signals.append("Short Trade")
                continue
            else:
                current_position = None  # exit

        # =========================
        # 🟢 LONG TRADE (NEW ENTRY)
        # =========================
        if (prev_close < prev_ema and prev_cci < prev_cci_ema) and \
           (close > ema and cci > cci_ema):

            signals.append("Long Trade")
            current_position = "Long Trade"

        # =========================
        # 🔴 SHORT TRADE (NEW ENTRY)
        # =========================
        elif (prev_close > prev_ema and prev_cci > prev_cci_ema) and \
             (close < ema and cci < cci_ema):

            signals.append("Short Trade")
            current_position = "Short Trade"

        # =========================
        # 🟢 LONG FAKE TRADE
        # =========================
        elif (close > ema and cci > cci_ema):
            if i >= 3 and all(
                df["CCI_60"].iloc[j] > df["CCI_EMA"].iloc[j]
                for j in range(i-3, i)
            ):
                signals.append("Long Fake Trade")
            else:
                signals.append("No Trade")

        # =========================
        # 🔴 SHORT FAKE TRADE
        # =========================
        elif (close < ema and cci < cci_ema):
            if i >= 3 and all(
                df["CCI_60"].iloc[j] < df["CCI_EMA"].iloc[j]
                for j in range(i-3, i)
            ):
                signals.append("Short Fake Trade")
            else:
                signals.append("No Trade")

        # =========================
        # ❌ NO TRADE
        # =========================
        else:
            signals.append("No Trade")

    df["Final_Signal"] = signals

    return df

def get_telegram_signal(df, symbol):
    """
    Extract latest signal and format Telegram message.
    Returns: (signal, message)
    """

    row = df.iloc[-1]

    open_time = row["Open_time"].strftime("%Y-%m-%d %H:%M")
    close     = row["Close"]
    signal    = row["Final_Signal"]
    rsi       = round(row["RSI"], 2) if "RSI" in df.columns else "N/A"

    # =========================
    # 🎨 Emoji + Label
    # =========================
    if signal == "Long Trade":
        emoji = "🟢"
        label = "LONG TRADE"
    elif signal == "Short Trade":
        emoji = "🔴"
        label = "SHORT TRADE"
    elif signal == "Long Fake Trade":
        emoji = "🟡"
        label = "LONG FAKE ⚠️"
    elif signal == "Short Fake Trade":
        emoji = "🟠"
        label = "SHORT FAKE ⚠️"
    else:
        emoji = "⚪"
        label = "NO TRADE"

    # =========================
    # 📝 Message Format
    # =========================
    message = (
        f"{emoji} *{symbol} Signal Alert*\n"
        f"🕐 Time  : {open_time} IST\n"
        f"💰 Close : {close}\n"
        f"📊 Signal: {label}\n"
        f"📈 RSI   : {rsi}"
    )

    return signal, message

def run_signal_check():
    """Fetch data, compute signals, and send Telegram alert on signal change."""
    global last_signal

    print(f"[INFO] Job triggered at: {datetime.now(IST)}")

    # =========================
    # 📥 Fetch Data
    # =========================
    try:
        df = fetch_candles()
    except Exception as e:
        print(f"[ERROR] API fetch failed: {e}")
        return

    # =========================
    # ⚙️ Compute Indicators + Signals
    # =========================
    df = compute_new_signal(df)

    # =========================
    # 📡 Get Telegram Message
    # =========================
    signal, msg = get_telegram_signal(df, SYMBOL)

    row = df.iloc[-1]
    open_time = row["Open_time"].strftime("%Y-%m-%d %H:%M")
    close     = row["Close"]
    rsi       = round(row["RSI"], 2) if "RSI" in df.columns else "N/A"

    print(f"[INFO] Signal: {signal} | Close: {close} | RSI: {rsi}")

    # =========================
    # 🔔 Send Alert Only on Change
    # =========================
    if signal != last_signal:

        send_message(msg)

        # =========================
        # 💾 Save to CSV (only selected columns)
        # =========================
        log = pd.DataFrame([{
            "Open_time": open_time,
            "Close": close,
            "Signal": signal,
            "RSI": rsi
        }])

        log.to_csv(
            "sff.csv",
            mode='a',
            header=not os.path.exists("signals.csv"),
            index=False
        )

        print("[LOG] Signal saved to signals.csv")

        # Update last signal
        last_signal = signal

    else:
        print(f"[INFO] Signal unchanged ({signal}), no alert sent.")

run_signal_check()

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = BlockingScheduler(timezone=IST)

scheduler.add_job(
    run_signal_check,
    trigger=CronTrigger(minute="0,3", second="5", timezone=IST),
    misfire_grace_time=60,
    max_instances=1
)

print(f"[INFO] Scheduler started for {SYMBOL}. Fires at :00:05 and :30:05 IST")
# send_message(f"✅ Bot started for {SYMBOL} — running every 30 mins")

try:
    scheduler.start()
except (KeyboardInterrupt, SystemExit):
    print("[INFO] Scheduler stopped.")
