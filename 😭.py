# file: forex_signal_bot.py
import os
import time
import json
import logging
from datetime import datetime, timedelta
import threading
import random

from telegram import Bot, ParseMode
from telegram.error import TelegramError

# ============ CONFIG ============
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8067527058:AAFd66Gf3UXUseiGGM725gbZeqwRso2EwBg")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "https://t.me/pasiya_md_signale")  # make bot admin
SEND_INTERVAL_MIN = int(os.environ.get("SEND_INTERVAL_MIN", "30"))  # how often to send signals (minutes)
PRE_ANNOUNCE_SECONDS = int(os.environ.get("PRE_ANNOUNCE_SECONDS", "10"))  # seconds before actual signal to announce
DEMO_MODE = os.environ.get("DEMO_MODE", "1") == "1"  # if True use simulated signals
MONITOR_TP_INTERVAL = 10  # seconds between checks for TP hit in demo (or use broker API)
# ================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Simple storage for active signals (in-memory). Persist if needed.
active_signals = {}  # signal_id -> dict

def is_trading_day(now=None):
    # Monday=0 ... Sunday=6
    if now is None:
        now = datetime.utcnow()
    weekday = now.weekday()
    return weekday <= 4  # Mon-Fri

def utcnow():
    return datetime.utcnow()

def send_message(text):
    try:
        bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode=ParseMode.MARKDOWN)
        logging.info("Sent message to channel.")
    except TelegramError as e:
        logging.exception("Telegram send error: %s", e)

def generate_signal():
    """
    Replace this function with your real signal generator.
    Should return a dict:
    {
      "id": str,
      "pair": "EURUSD",
      "side": "BUY" or "SELL",
      "entry": 1.12345,
      "sl": 1.12000,
      "tp": 1.13000,
      "time": ISO timestamp
    }
    """
    if DEMO_MODE:
        pair = random.choice(["EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD"])
        side = random.choice(["BUY","SELL"])
        base = round(random.uniform(1.00, 1.50), 5)
        tp_dist = round(random.uniform(0.0010, 0.0100), 5)
        sl_dist = round(random.uniform(0.0010, 0.0050), 5)
        if side == "BUY":
            entry = base
            tp = round(entry + tp_dist, 5)
            sl = round(entry - sl_dist, 5)
        else:
            entry = base
            tp = round(entry - tp_dist, 5)
            sl = round(entry + sl_dist, 5)
        return {
            "id": datetime.utcnow().strftime("%Y%m%d%H%M%S") + str(random.randint(100,999)),
            "pair": pair,
            "side": side,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "time": utcnow().isoformat()
        }
    else:
        # integrate your real indicator / broker feed here
        raise NotImplementedError("Replace generate_signal() with real logic")

def format_signal_msg(sig):
    msg = (
        f"*NEW SIGNAL*  `{sig['id']}`\n"
        f"Pair: *{sig['pair']}*\n"
        f"Side: *{sig['side']}*\n"
        f"Entry: `{sig['entry']}`\n"
        f"SL: `{sig['sl']}`\n"
        f"TP: `{sig['tp']}`\n"
        f"Time (UTC): `{sig['time']}`\n\n"
        f"`powered_buy  pasiya-md`"
    )
    return msg

def format_announce_msg():
    return "`All trades now signal time coming soon powered_buy  pasiya-md`"

def post_signal(sig):
    # announce
    send_message(format_announce_msg())
    time.sleep(PRE_ANNOUNCE_SECONDS)
    # actual signal
    send_message(format_signal_msg(sig))
    # add to active signals for monitoring
    active_signals[sig["id"]] = {
        "signal": sig,
        "posted_at": utcnow(),
        "status": "OPEN"
    }

def monitor_signals_thread():
    """
    Demo monitor: in production replace price check with broker API or pricing feed.
    This thread checks active_signals and simulates TP hits (or real check).
    """
    logging.info("Signal monitor thread started.")
    while True:
        now = utcnow()
        to_remove = []
        for sid, info in list(active_signals.items()):
            if info["status"] != "OPEN":
                continue
            sig = info["signal"]
            # Demo: randomly mark TP hit after some time
            # Replace below block with real price check against broker/instrument:
            elapsed = (now - info["posted_at"]).total_seconds()
            # after 120 seconds simulate TP hit with small prob
            if DEMO_MODE and elapsed > 60 and random.random() < 0.08:
                info["status"] = "TP_HIT"
                msg = f"Signal TP HIT — good signal powered_buy  pasiya-md\nSignal `{sid}` pair *{sig['pair']}* TP `{sig['tp']}`"
                send_message(msg)
                to_remove.append(sid)
            # Optionally auto-close after long time
            if elapsed > 3600:  # 1 hour expiry
                info["status"] = "EXPIRED"
                to_remove.append(sid)
        for sid in to_remove:
            try:
                del active_signals[sid]
            except KeyError:
                pass
        time.sleep(MONITOR_TP_INTERVAL)

def scheduler_loop():
    logging.info("Scheduler loop started. Interval %s minutes", SEND_INTERVAL_MIN)
    next_run = utcnow()
    while True:
        now = utcnow()
        if now >= next_run:
            # check trading day
            if is_trading_day(now):
                try:
                    sig = generate_signal()
                    post_signal(sig)
                except Exception as e:
                    logging.exception("Error generating/posting signal: %s", e)
            else:
                logging.info("Today is not trading day (Sat/Sun) — skipping.")
            next_run = now + timedelta(minutes=SEND_INTERVAL_MIN)
        time.sleep(1)

def main():
    # start monitor thread
    t = threading.Thread(target=monitor_signals_thread, daemon=True)
    t.start()
    # start scheduler
    scheduler_loop()

if __name__ == "__main__":
    logging.info("Starting Forex signal bot...")
    main()
