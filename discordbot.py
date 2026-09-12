import time
import requests
import pandas as pd
import ta
import yfinance as yf
from datetime import datetime
import pytz

# --- CONFIGURATION ---
DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL_HERE"
SYMBOL = "GC=F"  # Gold Futures (Ya Currency pairs jaise EURUSD=X)
TIMEFRAME = "1m"
EMA_PERIOD = 200
SWING_LENGTH = 5
RR_RATIO = 1.5

# Pakistan Timezone
PKT = pytz.timezone('Asia/Karachi')

def send_discord_alert(message):
    data = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=data)
    except Exception as e:
        print(f"Error sending Discord alert: {e}")

def is_restricted_session(current_time):
    # PKT Session Check (19:30 - 03:00 PKT)
    pkt_time = current_time.astimezone(PKT)
    hour = pkt_time.hour
    minute = pkt_time.minute
    total_minutes = hour * 60 + minute

    start_mins = 19 * 60 + 30  # 19:30
    end_mins = 3 * 60          # 03:00

    if start_mins < end_mins:
        return start_mins <= total_minutes < end_mins
    else:
        return total_minutes >= start_mins or total_minutes < end_mins

def run_bot():
    print("ICT Clean Sweep + MSS Bot Engine Started...")
    swept_low = False
    swept_high = False
    sweep_low_level = None
    sweep_high_level = None

    last_processed_candle = None

    while True:
        try:
            # Data Fetching
            data = yf.download(tickers=SYMBOL, period="2d", interval=TIMEFRAME, progress=False)
            if len(data) < 205:
                time.sleep(15)
                continue

            # Flatten MultiIndex columns if present
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)

            # 200 EMA
            data['EMA200'] = ta.trend.ema_indicator(data['Close'], window=EMA_PERIOD)

            latest_candle_time = data.index[-2] # Last completed bar
            if last_processed_candle == latest_candle_time:
                time.sleep(10)
                continue

            last_processed_candle = latest_candle_time
            df = data.iloc[:-1].copy() # Completed candles only

            curr_close = df['Close'].iloc[-1]
            curr_high  = df['High'].iloc[-1]
            curr_low   = df['Low'].iloc[-1]
            ema200     = df['EMA200'].iloc[-1]

            # Current Timestamp
            now_utc = datetime.now(pytz.utc)
            in_restricted_session = is_restricted_session(now_utc)

            # Swing Points Calculation
            df['pHi'] = df['High'][(df['High'] == df['High'].rolling(SWING_LENGTH * 2 + 1, center=True).max())]
            df['pLo'] = df['Low'][(df['Low'] == df['Low'].rolling(SWING_LENGTH * 2 + 1, center=True).min())]

            last_swing_high = df['pHi'].dropna().iloc[-1] if not df['pHi'].dropna().empty else None
            last_swing_low  = df['pLo'].dropna().iloc[-1] if not df['pLo'].dropna().empty else None

            # 1. Sweep Detection
            if last_swing_low and curr_low < last_swing_low and curr_close > last_swing_low:
                swept_low = True
                sweep_low_level = curr_low
                swept_high = False

            if last_swing_high and curr_high > last_swing_high and curr_close < last_swing_high:
                swept_high = True
                sweep_high_level = curr_high
                swept_low = False

            # 2. MSS Shift Detection
            prev_close = df['Close'].iloc[-2]
            mss_bullish = swept_low and last_swing_high and (curr_close > last_swing_high) and (prev_close <= last_swing_high)
            mss_bearish = swept_high and last_swing_low and (curr_close < last_swing_low) and (prev_close >= last_swing_low)

            if mss_bullish: swept_low = False
            if mss_bearish: swept_high = False

            # Signal & Trend Validation
            is_bullish_trend = curr_close > ema200
            is_bearish_trend = curr_close < ema200

            buy_signal  = mss_bullish and not in_restricted_session and is_bullish_trend
            sell_signal = mss_bearish and not in_restricted_session and is_bearish_trend

            # Trigger Discord Alert
            if buy_signal:
                entry = curr_close
                sl = min(sweep_low_level, curr_low) if sweep_low_level else curr_low
                tp = entry + (abs(entry - sl) * RR_RATIO)
                msg = f"🚨 **ICT BUY SIGNAL DETECTED** 🚨\n**Symbol:** {SYMBOL}\n**Entry:** {entry:.2f}\n**SL:** {sl:.2f}\n**TP:** {tp:.2f}\n**Time:** {now_utc.astimezone(PKT).strftime('%Y-%m-%d %H:%M:%S PKT')}"
                send_discord_alert(msg)

            if sell_signal:
                entry = curr_close
                sl = max(sweep_high_level, curr_high) if sweep_high_level else curr_high
                tp = entry - (abs(sl - entry) * RR_RATIO)
                msg = f"🚨 **ICT SELL SIGNAL DETECTED** 🚨\n**Symbol:** {SYMBOL}\n**Entry:** {entry:.2f}\n**SL:** {sl:.2f}\n**TP:** {tp:.2f}\n**Time:** {now_utc.astimezone(PKT).strftime('%Y-%m-%d %H:%M:%S PKT')}"
                send_discord_alert(msg)

        except Exception as e:
            print(f"Error in execution loop: {e}")

        time.sleep(10)

if __name__ == "__main__":
    run_bot()