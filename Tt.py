# file: forex_signal_bot_menu.py
import os, time, random, logging, threading
from datetime import datetime, timedelta
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext

# ================= CONFIG =================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8067527058:AAFd66Gf3UXUseiGGM725gbZeqwRso2EwBg")
CHANNEL_ID = "@pasiya_md_signale"   # Public Channel
SEND_INTERVAL_MIN = 30              # minutes
PRE_ANNOUNCE_SECONDS = 10
# ===========================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

running = False   # signal status
active_signals = {}

# ---------- BASIC HELPERS ----------
def utcnow(): return datetime.utcnow()
def is_trading_day(): return datetime.utcnow().weekday() <= 4  # Mon-Fri

# ---------- MENU ----------
def menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("📈 Start Signals", callback_data="start_signals")],
        [InlineKeyboardButton("🛑 Stop Signals", callback_data="stop_signals")],
        [InlineKeyboardButton("ℹ️ Bot Info", callback_data="bot_info")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(
        text="👋 *Welcome to PASIYA-MD Forex Auto Signal Bot!*\n\n"
             "Select an option below:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

def button(update: Update, context: CallbackContext):
    global running
    query = update.callback_query
    query.answer()

    if query.data == "start_signals":
        running = True
        query.edit_message_text("✅ *Signal system started.*\nBot will send signals automatically.\n\n`powered_buy pasiya-md`",
                                parse_mode=ParseMode.MARKDOWN)
    elif query.data == "stop_signals":
        running = False
        query.edit_message_text("🛑 *Signal system stopped.*\nNo new signals will be sent.",
                                parse_mode=ParseMode.MARKDOWN)
    elif query.data == "bot_info":
        info = (
            "🤖 *Bot Name:* PASIYA-MD Forex Auto Signal\n"
            "📢 *Channel:* @pasiya_md_signale\n"
            "⚙️ *Developer:* FULSTRK Developer\n"
            "🔋 *Powered by:* PASIYA-MD"
        )
        query.edit_message_text(info, parse_mode=ParseMode.MARKDOWN)

# ---------- SIGNAL SYSTEM ----------
def send_signal(bot: Bot):
    pair = random.choice(["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"])
    side = random.choice(["BUY", "SELL"])
    entry = round(random.uniform(1.00, 1.50), 5)
    tp = round(entry + (0.005 if side == "BUY" else -0.005), 5)
    sl = round(entry - (0.003 if side == "BUY" else -0.003), 5)

    msg_pre = "`All trades now signal time coming soon powered_buy pasiya-md`"
    msg_sig = (f"*NEW SIGNAL*\nPair: *{pair}*\nSide: *{side}*\nEntry: `{entry}`\n"
               f"SL: `{sl}`\nTP: `{tp}`\n\n`powered_buy pasiya-md`")

    try:
        bot.send_message(chat_id=CHANNEL_ID, text=msg_pre, parse_mode=ParseMode.MARKDOWN)
        time.sleep(PRE_ANNOUNCE_SECONDS)
        bot.send_message(chat_id=CHANNEL_ID, text=msg_sig, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logging.error(f"Send error: {e}")

def auto_loop(bot: Bot):
    global running
    while True:
        if running and is_trading_day():
            send_signal(bot)
            time.sleep(SEND_INTERVAL_MIN * 60)
        else:
            time.sleep(5)

# ---------- MAIN ----------
def main():
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("menu", menu))
    dp.add_handler(CallbackQueryHandler(button))

    bot = updater.bot
    threading.Thread(target=auto_loop, args=(bot,), daemon=True).start()

    logging.info("Bot running with /menu command.")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
