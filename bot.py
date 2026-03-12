{
 "cells": [
  {
   "cell_type": "markdown",
   "id": "md-title",
   "metadata": {},
   "source": [
    "# 📊 Crypto Signal Bot — ETHUSDT\n",
    "\n",
    "Automated trading signal bot using **CCI (60)**, **EMA 7**, and **RSI (14)** on 30-minute candles from Delta Exchange.  \n",
    "Sends Telegram alerts on signal changes and logs them to `signals.csv`.\n",
    "\n",
    "---\n",
    "**Strategy Logic:**\n",
    "- 🟢 **Long Entry** → CCI > CCI_EMA, |Diff_CCI| > 4, Close > EMA7\n",
    "- 🔴 **Short Entry** → CCI < CCI_EMA, |Diff_CCI| > 4, Close < EMA7\n",
    "- ⚪ **No Trade** → Conditions not met\n",
    "\n",
    "Scheduler fires at **HH:00:05** and **HH:30:05** IST every day."
   ]
  },
  {
   "cell_type": "markdown",
   "id": "md-install",
   "metadata": {},
   "source": [
    "## 1. Install Dependencies"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 1,
   "id": "cell-install",
   "metadata": {},
   "outputs": [],
   "source": [
    "# Run once to install required packages\n",
    "!pip install apscheduler pytz requests pandas numpy --quiet"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "md-config",
   "metadata": {},
   "source": [
    "## 2. Configuration & Environment Setup"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 2,
   "id": "cell-config",
   "metadata": {},
   "outputs": [
    {
     "name": "stdout",
     "output_type": "stream",
     "text": [
      "[CONFIG] Symbol: ETHUSDT\n",
      "[CONFIG] Chat IDs loaded: 4\n"
     ]
    }
   ],
   "source": [
    "import os\n",
    "import time\n",
    "import requests\n",
    "import pandas as pd\n",
    "import numpy as np\n",
    "from datetime import datetime\n",
    "import pytz\n",
    "\n",
    "# ── Set your credentials here (or use environment variables) ────\n",
    "# os.environ[\"BOT_TOKEN\"]  = \"your_telegram_bot_token\"\n",
    "# os.environ[\"CHAT_IDS\"]   = \"chat_id_1,chat_id_2\"\n",
    "# os.environ[\"SYMBOL\"]     = \"ETHUSDT\"  # optional, default is ETHUSDT\n",
    "\n",
    "BOT_TOKEN = \"8749089704:AAFq_Xh6_oYk61V4mv8eNVdcX3Yh27AJuuY\"\n",
    "\n",
    "CHAT_IDS = [\n",
    "    \"1070509960\",\n",
    "    \"1937479700\",\n",
    "    \"5034473353\",\n",
    "    \"2037873693\"\n",
    "]\n",
    "\n",
    "\n",
    "SYMBOL     =\"ETHUSDT\"\n",
    "IST        = pytz.timezone(\"Asia/Kolkata\")\n",
    "\n",
    "last_signal = None  # in-memory; resets on restart\n",
    "\n",
    "print(f\"[CONFIG] Symbol: {SYMBOL}\")\n",
    "print(f\"[CONFIG] Chat IDs loaded: {len(CHAT_IDS)}\")"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "md-telegram",
   "metadata": {},
   "source": [
    "## 3. Telegram Messenger"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 3,
   "id": "cell-telegram",
   "metadata": {},
   "outputs": [],
   "source": [
    "def send_message(text):\n",
    "    \"\"\"Send a message to all configured Telegram chat IDs.\"\"\"\n",
    "    url = f\"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage\"\n",
    "    for chat_id in CHAT_IDS:\n",
    "        try:\n",
    "            r = requests.post(\n",
    "                url,\n",
    "                data={\"chat_id\": chat_id.strip(), \"text\": text},\n",
    "                timeout=10\n",
    "            )\n",
    "            r.raise_for_status()\n",
    "            print(f\"[TELEGRAM] Message sent to {chat_id.strip()}\")\n",
    "        except Exception as e:\n",
    "            print(f\"[ERROR] Telegram failed for {chat_id}: {e}\")"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "md-indicators",
   "metadata": {},
   "source": [
    "## 4. Technical Indicators"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 4,
   "id": "cell-indicators",
   "metadata": {},
   "outputs": [],
   "source": [
    "def calculate_rsi(series, length=14):\n",
    "    \"\"\"\n",
    "    Wilder's RSI using EWM (alpha = 1/length).\n",
    "    Returns a Series of RSI values (0–100).\n",
    "    \"\"\"\n",
    "    delta    = series.diff()\n",
    "    gain     = pd.Series(np.where(delta > 0, delta, 0), index=series.index)\n",
    "    loss     = pd.Series(np.where(delta < 0, -delta, 0), index=series.index)\n",
    "    avg_gain = gain.ewm(alpha=1/length, adjust=False).mean()\n",
    "    avg_loss = loss.ewm(alpha=1/length, adjust=False).mean()\n",
    "    rs       = avg_gain / avg_loss\n",
    "    return 100 - (100 / (1 + rs))"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "md-fetch",
   "metadata": {},
   "source": [
    "## 5. Fetch Candle Data from Delta Exchange"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 5,
   "id": "cell-fetch",
   "metadata": {},
   "outputs": [],
   "source": [
    "def fetch_candles(symbol=SYMBOL, resolution=\"30m\", lookback_candles=200):\n",
    "    \"\"\"Fetch OHLCV candles from Delta Exchange API.\"\"\"\n",
    "    end   = int(time.time())\n",
    "    start = end - lookback_candles * 1800\n",
    "\n",
    "    resp = requests.get(\n",
    "        \"https://api.delta.exchange/v2/history/candles\",\n",
    "        params={\"symbol\": symbol, \"resolution\": resolution, \"start\": start, \"end\": end},\n",
    "        timeout=15\n",
    "    )\n",
    "    resp.raise_for_status()\n",
    "    data = resp.json()\n",
    "\n",
    "    if \"result\" not in data or not data[\"result\"]:\n",
    "        raise ValueError(\"No candle data returned from API\")\n",
    "\n",
    "    df = pd.DataFrame(data[\"result\"])\n",
    "    df.rename(columns={\n",
    "        \"time\": \"Open_time\", \"open\": \"Open\", \"high\": \"High\",\n",
    "        \"low\": \"Low\", \"close\": \"Close\", \"volume\": \"Volume\"\n",
    "    }, inplace=True)\n",
    "\n",
    "    df[\"Open_time\"] = (\n",
    "        pd.to_datetime(df[\"Open_time\"], unit='s')\n",
    "        .dt.tz_localize(\"UTC\")\n",
    "        .dt.tz_convert(\"Asia/Kolkata\")\n",
    "        .dt.tz_localize(None)\n",
    "    )\n",
    "    df = df.sort_values(\"Open_time\").reset_index(drop=True)\n",
    "    for col in [\"Open\", \"High\", \"Low\", \"Close\", \"Volume\"]:\n",
    "        df[col] = df[col].astype(float)\n",
    "\n",
    "    print(f\"[FETCH] {len(df)} candles loaded. Latest: {df['Open_time'].iloc[-1]}\")\n",
    "    return df\n",
    "\n",
    "# Test fetch\n",
    "# df = fetch_candles()\n",
    "# df.tail(3)"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "md-signals",
   "metadata": {},
   "source": [
    "## 6. Compute Indicators & Generate Signal"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 6,
   "id": "cell-signals",
   "metadata": {},
   "outputs": [],
   "source": [
    "def compute_signals(df):\n",
    "    \"\"\"Compute CCI(60), EMA7, RSI(14) and derive trading signals.\"\"\"\n",
    "    # CCI (60)\n",
    "    df[\"hlc3\"]     = (df[\"High\"] + df[\"Low\"] + df[\"Close\"]) / 3\n",
    "    df[\"ma\"]       = df[\"hlc3\"].rolling(60).mean()\n",
    "    df[\"mean_dev\"] = df[\"hlc3\"].rolling(60).apply(\n",
    "        lambda x: np.mean(np.abs(x - np.mean(x))), raw=True\n",
    "    )\n",
    "    df[\"CCI_60\"]   = (df[\"hlc3\"] - df[\"ma\"]) / (0.015 * df[\"mean_dev\"])\n",
    "    df[\"CCI_EMA\"]  = df[\"CCI_60\"].ewm(span=7, adjust=False).mean()\n",
    "    df[\"Diff_CCI\"] = df[\"CCI_60\"] - df[\"CCI_EMA\"]\n",
    "\n",
    "    # EMA 7 and RSI 14\n",
    "    df[\"EMA7\"] = df[\"Close\"].ewm(span=7, adjust=False).mean()\n",
    "    df[\"RSI\"]  = calculate_rsi(df[\"Close\"])\n",
    "\n",
    "    # Signal conditions\n",
    "    long_cond  = (df[\"CCI_60\"] > df[\"CCI_EMA\"]) & (abs(df[\"Diff_CCI\"]) > 4) & (df[\"Close\"] > df[\"EMA7\"])\n",
    "    short_cond = (df[\"CCI_60\"] < df[\"CCI_EMA\"]) & (abs(df[\"Diff_CCI\"]) > 4) & (df[\"Close\"] < df[\"EMA7\"])\n",
    "    df[\"Signal\"] = np.where(long_cond, \"Long Entry\", np.where(short_cond, \"Short Entry\", \"No Trade\"))\n",
    "\n",
    "    return df\n",
    "\n",
    "# Quick test (offline — uses random data)\n",
    "# df = compute_signals(df)\n",
    "# df[[\"Open_time\",\"Close\",\"CCI_60\",\"EMA7\",\"RSI\",\"Signal\"]].tail(5)"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "md-job",
   "metadata": {},
   "source": [
    "## 7. Main Signal-Check Job"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 7,
   "id": "cell-job",
   "metadata": {},
   "outputs": [],
   "source": [
    "def run_signal_check():\n",
    "    \"\"\"Fetch data, compute signals, and send Telegram alert on signal change.\"\"\"\n",
    "    global last_signal\n",
    "    print(f\"[INFO] Job triggered at: {datetime.now(IST)}\")\n",
    "\n",
    "    try:\n",
    "        df = fetch_candles()\n",
    "    except Exception as e:\n",
    "        print(f\"[ERROR] API fetch failed: {e}\")\n",
    "        return\n",
    "\n",
    "    df    = compute_signals(df)\n",
    "    row   = df.iloc[-1]\n",
    "\n",
    "    open_time = row[\"Open_time\"].strftime(\"%Y-%m-%d %H:%M\")\n",
    "    close     = row[\"Close\"]\n",
    "    signal    = row[\"Signal\"]\n",
    "    rsi       = round(row[\"RSI\"], 2)\n",
    "\n",
    "    print(f\"[INFO] Signal: {signal} | Close: {close} | RSI: {rsi}\")\n",
    "\n",
    "    if signal != last_signal:\n",
    "        emoji = \"🟢\" if signal == \"Long Entry\" else \"🔴\" if signal == \"Short Entry\" else \"⚪\"\n",
    "        msg = (\n",
    "            f\"{emoji} *{SYMBOL} Signal Alert*\\n\"\n",
    "            f\"🕐 Time  : {open_time} IST\\n\"\n",
    "            f\"💰 Close : {close}\\n\"\n",
    "            f\"📊 Signal: {signal}\\n\"\n",
    "            f\"📈 RSI   : {rsi}\"\n",
    "        )\n",
    "        send_message(msg)\n",
    "\n",
    "        log = pd.DataFrame([{\"Open_time\": open_time, \"Close\": close, \"Signal\": signal, \"RSI\": rsi}])\n",
    "        log.to_csv(\"signals.csv\", mode='a', header=not os.path.exists(\"signals.csv\"), index=False)\n",
    "        print(f\"[LOG] Signal saved to signals.csv\")\n",
    "\n",
    "        last_signal = signal\n",
    "    else:\n",
    "        print(f\"[INFO] Signal unchanged ({signal}), no alert sent.\")"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "md-run-once",
   "metadata": {},
   "source": [
    "## 8. Run Once (Manual Test)\n",
    "> Use this cell to test the bot without the scheduler."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 8,
   "id": "cell-run-once",
   "metadata": {},
   "outputs": [
    {
     "name": "stdout",
     "output_type": "stream",
     "text": [
      "[INFO] Job triggered at: 2026-03-12 15:31:45.674662+05:30\n",
      "[FETCH] 200 candles loaded. Latest: 2026-03-12 15:30:00\n",
      "[INFO] Signal: Long Entry | Close: 2055.0 | RSI: 59.62\n",
      "[TELEGRAM] Message sent to 1070509960\n",
      "[TELEGRAM] Message sent to 1937479700\n",
      "[TELEGRAM] Message sent to 5034473353\n",
      "[TELEGRAM] Message sent to 2037873693\n",
      "[LOG] Signal saved to signals.csv\n"
     ]
    }
   ],
   "source": [
    "# Single test run — fetches live data, computes signal, sends Telegram message\n",
    "run_signal_check()"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "md-scheduler",
   "metadata": {},
   "source": [
    "## 9. Start Scheduler\n",
    "> ⚠️ This cell **blocks** the notebook kernel. Run it last, or deploy to a server/Railway instead."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "id": "cell-scheduler",
   "metadata": {},
   "outputs": [
    {
     "name": "stdout",
     "output_type": "stream",
     "text": [
      "[INFO] Scheduler started for ETHUSDT. Fires at :00:05 and :30:05 IST\n",
      "[TELEGRAM] Message sent to 1070509960\n",
      "[TELEGRAM] Message sent to 1937479700\n",
      "[TELEGRAM] Message sent to 5034473353\n",
      "[TELEGRAM] Message sent to 2037873693\n"
     ]
    }
   ],
   "source": [
    "from apscheduler.schedulers.blocking import BlockingScheduler\n",
    "from apscheduler.triggers.cron import CronTrigger\n",
    "\n",
    "scheduler = BlockingScheduler(timezone=IST)\n",
    "\n",
    "scheduler.add_job(\n",
    "    run_signal_check,\n",
    "    trigger=CronTrigger(minute=\"0,3\", second=\"5\", timezone=IST),\n",
    "    misfire_grace_time=60,\n",
    "    max_instances=1\n",
    ")\n",
    "\n",
    "print(f\"[INFO] Scheduler started for {SYMBOL}. Fires at :00:05 and :30:05 IST\")\n",
    "send_message(f\"✅ Bot started for {SYMBOL} — running every 30 mins\")\n",
    "\n",
    "try:\n",
    "    scheduler.start()\n",
    "except (KeyboardInterrupt, SystemExit):\n",
    "    print(\"[INFO] Scheduler stopped.\")"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "md-logs",
   "metadata": {},
   "source": [
    "## 10. View Signal Log"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "id": "cell-logs",
   "metadata": {},
   "outputs": [],
   "source": [
    "import os\n",
    "if os.path.exists(\"signals.csv\"):\n",
    "    log_df = pd.read_csv(\"signals.csv\")\n",
    "    print(f\"Total signals logged: {len(log_df)}\")\n",
    "    display(log_df.tail(10))\n",
    "else:\n",
    "    print(\"No signals logged yet. Run the bot to generate signals.\")"
   ]
  }
 ],
 "metadata": {
  "kernelspec": {
   "display_name": "Python 3 (ipykernel)",
   "language": "python",
   "name": "python3"
  },
  "language_info": {
   "codemirror_mode": {
    "name": "ipython",
    "version": 3
   },
   "file_extension": ".py",
   "mimetype": "text/x-python",
   "name": "python",
   "nbconvert_exporter": "python",
   "pygments_lexer": "ipython3",
   "version": "3.13.9"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 5
}
