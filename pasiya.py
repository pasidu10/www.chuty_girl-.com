#!/usr/bin/env python3
"""
Binance Futures Scalping Bot with AI Analysis
- Scalping strategy: Quick in/out trades
- Fixed SL: 0.8% | TP: 0.5-2.0%
- AI-driven trade decisions
⚠️ WARNING: LIVE TRADING WITH REAL MONEY!
"""

import time
import hmac
import hashlib
import requests
import json
import re
import threading
from datetime import datetime

# ================================
# CONFIGURATION
# ================================
BINANCE_KEY = ""
BINANCE_SECRET = ""
GEMINI_KEY = ""

BASE_URL = "https://fapi.binance.com"

# SCALPING SETTINGS
SL_PERCENTAGE = 0.8  # Fixed 0.8% stop loss
TP_MIN = 0.5  # Minimum 0.5% take profit
TP_MAX = 2.0  # Maximum 2.0% take profit
MIN_INVESTMENT = 0.10
MAX_INVESTMENT = 5.00

# ================================
# GLOBAL VARIABLES
# ================================
running = False
active_trades = {}
trade_history = []
total_pnl = 0.0
TIME_DIFF = 0  # Time difference between local and Binance server


# ================================
# UTILITIES
# ================================
def get_timestamp():
    return int(time.time() * 1000) + TIME_DIFF


def log_info(msg):
    print(f"\033[92m[{datetime.now().strftime('%H:%M:%S')}] {msg}\033[0m")


def log_warn(msg):
    print(f"\033[93m[{datetime.now().strftime('%H:%M:%S')}] {msg}\033[0m")


def log_error(msg):
    print(f"\033[91m[{datetime.now().strftime('%H:%M:%S')}] {msg}\033[0m")


def log_success(msg):
    print(f"\033[96m[{datetime.now().strftime('%H:%M:%S')}] {msg}\033[0m")


# ================================
# BINANCE API
# ================================
def sign(params):
    return hmac.new(BINANCE_SECRET.encode(), params.encode(), hashlib.sha256).hexdigest()


def request_binance(method, endpoint, params=""):
    url = f"{BASE_URL}{endpoint}?{params}" if params else f"{BASE_URL}{endpoint}"
    headers = {"X-MBX-APIKEY": BINANCE_KEY}

    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=10)
        elif method == "POST":
            response = requests.post(url, headers=headers, timeout=10)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers, timeout=10)
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def get_server_time():
    try:
        response = requests.get(f"{BASE_URL}/fapi/v1/time", timeout=10)
        return response.json()['serverTime']
    except Exception as e:
        log_error(f"Failed to get server time: {e}")
        return None


def sync_time():
    global TIME_DIFF
    server_time = get_server_time()
    if server_time:
        # Calculate time difference between server and local time
        TIME_DIFF = server_time - int(time.time() * 1000)
        log_info(f"Time synced. Difference: {TIME_DIFF} ms")
        return True
    log_error("Failed to sync time")
    return False


def get_balance():
    ts = get_timestamp()
    params = f"timestamp={ts}"
    sig = sign(params)
    account = request_binance("GET", "/fapi/v2/account", f"{params}&signature={sig}")
    return float(account.get("availableBalance", 0)) if "availableBalance" in account else 0


def set_leverage(symbol, leverage=15):
    ts = get_timestamp()
    params = f"symbol={symbol}&leverage={leverage}&timestamp={ts}"
    sig = sign(params)
    result = request_binance("POST", "/fapi/v1/leverage", f"{params}&signature={sig}")

    if "code" in result and result["code"] < 0 and leverage > 5:
        return set_leverage(symbol, leverage // 2)
    return result


def get_symbol_filters(symbol):
    exchange_info = request_binance("GET", "/fapi/v1/exchangeInfo")
    for s in exchange_info.get('symbols', []):
        if s['symbol'] == symbol:
            filters = {}
            for f in s.get('filters', []):
                if f['filterType'] == 'PRICE_FILTER':
                    filters['tick_size'] = float(f['tickSize'])
                elif f['filterType'] == 'LOT_SIZE':
                    filters['step_size'] = float(f['stepSize'])
                    filters['min_qty'] = float(f['minQty'])
                elif f['filterType'] == 'MIN_NOTIONAL':
                    filters['min_notional'] = float(f['notional'])
            return filters
    return {}


def round_to_precision(value, precision):
    if precision == 0:
        return int(value)
    precision_str = f"{precision:.10f}".rstrip('0')
    if '.' in precision_str:
        decimal_places = len(precision_str.split('.')[1])
        return round(value, decimal_places)
    return round(value / precision) * precision


def place_order(symbol, side, order_type, qty, price=None):
    filters = get_symbol_filters(symbol)
    step_size = filters.get('step_size', 0.001)
    tick_size = filters.get('tick_size', 0.000001)

    qty = round_to_precision(qty, step_size)
    qty = max(qty, filters.get('min_qty', 0.001))

    ts = get_timestamp()
    params = f"symbol={symbol}&side={side}&type={order_type}&quantity={qty}&positionSide=BOTH&timestamp={ts}"

    if order_type == "LIMIT" and price:
        price = round_to_precision(price, tick_size)
        params += f"&price={price}&timeInForce=GTC"

    sig = sign(params)
    return request_binance("POST", "/fapi/v1/order", f"{params}&signature={sig}")


def place_tp_sl_orders(symbol, side, qty, entry_price, tp_price, sl_price):
    filters = get_symbol_filters(symbol)
    tick_size = filters.get('tick_size', 0.000001)
    step_size = filters.get('step_size', 0.001)

    qty = round_to_precision(qty, step_size)
    tp_price = round_to_precision(tp_price, tick_size)
    sl_price = round_to_precision(sl_price, tick_size)

    tp_side = "SELL" if side == "BUY" else "BUY"
    sl_side = tp_side

    orders = []

    # Take Profit
    ts = get_timestamp()
    tp_params = f"symbol={symbol}&side={tp_side}&type=TAKE_PROFIT_MARKET&quantity={qty}&stopPrice={tp_price}&positionSide=BOTH&timestamp={ts}"
    tp_sig = sign(tp_params)
    tp_order = request_binance("POST", "/fapi/v1/order", f"{tp_params}&signature={tp_sig}")
    if "orderId" in tp_order:
        log_success(f"✅ TP order placed @ ${tp_price}")
        orders.append({'type': 'TP', 'order': tp_order})

    # Stop Loss
    ts = get_timestamp()
    sl_params = f"symbol={symbol}&side={sl_side}&type=STOP_MARKET&quantity={qty}&stopPrice={sl_price}&positionSide=BOTH&timestamp={ts}"
    sl_sig = sign(sl_params)
    sl_order = request_binance("POST", "/fapi/v1/order", f"{sl_params}&signature={sl_sig}")
    if "orderId" in sl_order:
        log_success(f"✅ SL order placed @ ${sl_price}")
        orders.append({'type': 'SL', 'order': sl_order})

    return orders


def get_active_orders():
    ts = get_timestamp()
    params = f"timestamp={ts}"
    sig = sign(params)
    return request_binance("GET", "/fapi/v1/openOrders", f"{params}&signature={sig}")


def cancel_all_orders(symbol):
    ts = get_timestamp()
    params = f"symbol={symbol}&timestamp={ts}"
    sig = sign(params)
    return request_binance("DELETE", "/fapi/v1/allOpenOrders", f"{params}&signature={sig}")


def get_scalping_coins():
    """Get coins suitable for scalping (high volume, high volatility)"""
    try:
        response = requests.get(f"{BASE_URL}/fapi/v1/ticker/24hr", timeout=10)
        tickers = response.json()

        valid_coins = []
        for ticker in tickers:
            symbol = ticker['symbol']
            if not symbol.endswith('USDT'):
                continue

            price = float(ticker['lastPrice'])
            volume = float(ticker['quoteVolume'])
            price_change = abs(float(ticker['priceChangePercent']))

            # Scalping criteria: more relaxed volume and volatility requirements
            if (price > 0.0001 and
                    price < 10.0 and
                    volume > 1000000 and  # Lowered volume requirement
                    price_change > 0.5):  # Lowered volatility requirement

                ticker['volume_usd'] = volume
                ticker['volatility'] = price_change
                valid_coins.append(ticker)

        # Sort by volume and volatility for best scalping opportunities
        return sorted(valid_coins, key=lambda x: x['volume_usd'] * x['volatility'], reverse=True)

    except Exception as e:
        log_error(f"Error getting coins: {e}")
        return []


def get_ohlcv(symbol, interval="5m", limit=50):
    """Get OHLCV data - scalping uses shorter timeframes"""
    try:
        url = f"{BASE_URL}/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
        response = requests.get(url, timeout=10)
        klines = response.json()

        return [{
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5])
        } for k in klines]
    except Exception as e:
        log_error(f"Error getting OHLCV: {e}")
        return []


# ================================
# AI ANALYSIS
# ================================
def analyze_with_ai(data, balance, win_rate):
    """AI analysis for scalping with fixed SL/TP percentages"""
    prompt = f"""
You are a scalping trading AI. Analyze market data for quick trades.

Account: ${balance:.2f} USDT | Win Rate: {win_rate:.1f}%

Market Data (Short Timeframes for Scalping):
5M: {data.get('5m', [])[-15:]}
15M: {data.get('15m', [])[-10:]}
1H: {data.get('1h', [])[-6:]}

24H Stats:
Volume: ${data.get('volume_usd', 0):,.0f}
Price Change: {data.get('price_change', 0)}%

SCALPING RULES:
- SL: Fixed 0.8% loss
- TP: 0.5% to 2.0% gain
- Quick in/out (hold time: minutes to hours)
- Look for momentum signals even in minor trends
- Consider entering on strong breakouts or reversals

Return ONLY valid JSON:
{{
  "signal": "BUY/SELL/HOLD",
  "confidence": "HIGH/MEDIUM/LOW",
  "investment_amount": "Use 100% of balance for HIGH confidence, 50% for MEDIUM, 10% for LOW",
  "leverage": 5 to 15,
  "tp_percentage": 0.5 to 2.0,
  "reasoning": "brief explanation"
}}

HIGH confidence = More investment
MEDIUM/LOW = Less investment
If you see any momentum, even minor, consider it a trading opportunity.
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"

    try:
        response = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30
        )
        result = response.json()

        if "candidates" not in result:
            return {"error": "No AI response"}

        ai_text = result["candidates"][0]["content"]["parts"][0]["text"]
        match = re.search(r"\{.*\}", ai_text, re.DOTALL)
        if not match:
            return {"error": "No JSON in response"}

        parsed = json.loads(match.group(0).strip())

        # Validate and constrain values
        if parsed.get("signal") not in ["BUY", "SELL", "HOLD"]:
            return {"error": "Invalid signal"}

        parsed["investment_amount"] = max(MIN_INVESTMENT,
                                          min(MAX_INVESTMENT, balance * (0.5 if parsed.get("confidence") == "MEDIUM" else 1.0)))
        parsed["leverage"] = max(5, min(15, int(parsed.get("leverage", 10))))
        parsed["tp_percentage"] = max(TP_MIN, min(TP_MAX, float(parsed.get("tp_percentage", 1.0))))

        return parsed

    except Exception as e:
        return {"error": str(e)}


# ================================
# TRADE EXECUTION
# ================================
def execute_scalp_trade(symbol, analysis, current_price):
    """Execute scalping trade with fixed SL and AI TP"""
    try:
        signal = analysis['signal']
        investment = analysis['investment_amount']
        leverage = analysis['leverage']
        tp_percentage = analysis['tp_percentage']

        log_info(f"🎯 Scalping {signal} {symbol} @ ${current_price:.6f}")
        log_info(f"💰 Investment: ${investment:.2f} | Leverage: {leverage}x")

        # Set leverage
        set_leverage(symbol, leverage)

        # Calculate quantity
        position_value = investment * leverage
        qty = position_value / current_price

        filters = get_symbol_filters(symbol)
        step_size = filters.get('step_size', 0.001)
        qty = round_to_precision(qty, step_size)
        qty = max(qty, filters.get('min_qty', 0.001))

        # Calculate TP/SL prices
        if signal == "BUY":
            tp_price = current_price * (1 + tp_percentage / 100)
            sl_price = current_price * (1 - SL_PERCENTAGE / 100)
        else:  # SELL
            tp_price = current_price * (1 - tp_percentage / 100)
            sl_price = current_price * (1 + SL_PERCENTAGE / 100)

        log_info(f"📈 TP: ${tp_price:.6f} (+{tp_percentage:.2f}%)")
        log_info(f"🛡️ SL: ${sl_price:.6f} (-{SL_PERCENTAGE}%)")

        # Place entry order
        entry = place_order(symbol, signal, "MARKET", qty)
        if "orderId" not in entry:
            log_error(f"Entry failed: {entry}")
            return False

        log_success(f"✅ Entry order filled! ID: {entry['orderId']}")

        time.sleep(2)

        # Place TP/SL
        orders = place_tp_sl_orders(symbol, signal, qty, current_price, tp_price, sl_price)

        # Store trade
        active_trades[symbol] = {
            'symbol': symbol,
            'side': signal,
            'investment': investment,
            'leverage': leverage,
            'qty': qty,
            'entry_price': current_price,
            'tp_price': tp_price,
            'sl_price': sl_price,
            'tp_percentage': tp_percentage,
            'orders': orders,
            'start_time': datetime.now()
        }

        log_success("🚀 SCALP TRADE ACTIVE!")
        return True

    except Exception as e:
        log_error(f"Trade execution error: {e}")
        return False


def monitor_trades():
    """Monitor active scalping trades"""
    if not active_trades:
        return

    all_orders = get_active_orders()
    if not isinstance(all_orders, list):
        return

    active_order_ids = {str(o['orderId']) for o in all_orders}
    completed = []

    for symbol, trade in active_trades.items():
        original_count = len(trade.get('orders', []))
        still_active = sum(1 for o in trade.get('orders', [])
                           if str(o['order'].get('orderId', '')) in active_order_ids)

        if still_active < original_count:
            # Trade completed
            cancel_all_orders(symbol)

            # Calculate PnL (simplified)
            pnl = trade['investment'] * (trade['tp_percentage'] / 100) * trade['leverage']
            completed.append((symbol, pnl))

    # Complete trades
    for symbol, pnl in completed:
        trade = active_trades.pop(symbol)
        trade_history.append({**trade, 'pnl': pnl, 'end_time': datetime.now()})

        global total_pnl
        total_pnl += pnl

        log_success(f"✅ Scalp completed: {symbol} | PnL: ${pnl:.2f}")
        log_info(f"💰 Session P&L: ${total_pnl:.2f}")


def find_scalp_opportunity():
    """Find and execute scalping opportunity"""
    log_info("🔍 Scanning for scalp opportunities...")

    balance = get_balance()
    if balance < MIN_INVESTMENT:
        log_warn(f"⚠️ Low balance: ${balance:.2f}")
        return

    win_rate = calculate_win_rate()
    coins = get_scalping_coins()

    if not coins:
        log_warn("⚠️ No suitable coins")
        return

    log_info(f"📊 Analyzing top {min(5, len(coins))} coins...")

    for coin in coins[:5]:
        symbol = coin['symbol']
        price = float(coin['lastPrice'])

        log_info(f"🔍 {symbol} @ ${price:.6f}")

        # Get scalping timeframe data
        data = {
            "5m": get_ohlcv(symbol, "5m", 50),
            "15m": get_ohlcv(symbol, "15m", 30),
            "1h": get_ohlcv(symbol, "1h", 20),
            "volume_usd": coin.get('volume_usd', 0),
            "price_change": coin.get('priceChangePercent', 0)
        }

        if not all(data[tf] for tf in ["5m", "15m", "1h"]):
            continue

        # AI analysis
        analysis = analyze_with_ai(data, balance, win_rate)

        if "error" in analysis:
            log_warn(f"⚠️ AI error: {analysis['error']}")
            continue

        if analysis['signal'] == 'HOLD':
            log_info(f"📊 AI: HOLD {symbol}")
            # Fallback mechanism: Check if market conditions are good enough for a trade
            price_change = abs(float(coin.get('priceChangePercent', 0)))
            volume = float(coin.get('volume_usd', 0))
            
            # If volatility is high enough, create a manual trade signal
            if price_change > 2.0 and volume > 2000000:
                log_info(f"🔄 Fallback: Creating manual trade for {symbol} due to high volatility ({price_change:.2f}%)")
                analysis = {
                    'signal': 'BUY' if float(coin.get('priceChangePercent', 0)) > 0 else 'SELL',
                    'confidence': 'HIGH',
                    'investment_amount': min(MAX_INVESTMENT, max(MIN_INVESTMENT, balance * 0.5)),
                    'leverage': 10,
                    'tp_percentage': 1.0,
                    'reasoning': f"Fallback trade due to high volatility ({price_change:.2f}%)",
                }
            else:
                continue

        # Execute scalp trade
        log_success(f"🎯 AI: {analysis['signal']} | Confidence: {analysis['confidence']}")
        log_info(f"💡 {analysis.get('reasoning', 'No reason')}")

        if execute_scalp_trade(symbol, analysis, price):
            return

    log_warn("⚠️ No scalp opportunities found")


def calculate_win_rate():
    """Calculate win rate from history"""
    if not trade_history:
        return 0
    wins = sum(1 for t in trade_history if t.get('pnl', 0) > 0)
    return (wins / len(trade_history)) * 100


# ================================
# BOT MAIN LOOP
# ================================
def run_bot():
    """Main scalping bot loop"""
    global running
    running = True

    log_success("🚀 SCALPING BOT STARTED!")
    log_info(f"💰 Balance: ${get_balance():.2f} USDT")
    log_info(f"📊 SL: {SL_PERCENTAGE}% | TP: {TP_MIN}%-{TP_MAX}%")

    cycle = 0

    while running:
        try:
            cycle += 1
            log_info(f"🔄 Cycle #{cycle}")

            # Monitor existing trades
            if active_trades:
                monitor_trades()
                log_info(f"📊 Active: {len(active_trades)} trade(s)")

            # Find new scalp if no active trades
            if not active_trades:
                find_scalp_opportunity()

            # Stats every 10 cycles
            if cycle % 10 == 0:
                balance = get_balance()
                win_rate = calculate_win_rate()
                log_success("📈 SESSION STATS:")
                log_info(f"   💰 Balance: ${balance:.2f}")
                log_info(f"   📊 Trades: {len(trade_history)}")
                log_info(f"   🏆 Win Rate: {win_rate:.1f}%")
                log_info(f"   💎 P&L: ${total_pnl:.2f}")

            # Sleep
            time.sleep(20 if active_trades else 40)

        except KeyboardInterrupt:
            break
        except Exception as e:
            log_error(f"Error: {e}")
            time.sleep(10)

    log_warn("🛑 Bot stopping...")

    # Cleanup
    for symbol in list(active_trades.keys()):
        cancel_all_orders(symbol)

    balance = get_balance()
    win_rate = calculate_win_rate()

    log_success("🏁 FINAL STATS:")
    log_info(f"   💰 Balance: ${balance:.2f}")
    log_info(f"   📊 Total Trades: {len(trade_history)}")
    log_info(f"   🏆 Win Rate: {win_rate:.1f}%")
    log_info(f"   💎 Total P&L: ${total_pnl:.2f}")


def stop_bot():
    global running
    running = False


# ================================
# MAIN INTERFACE
# ================================
def print_banner():
    banner = """
╔══════════════════════════════════════════════════╗
║     BINANCE FUTURES SCALPING BOT WITH AI         ║
║              🔴 LIVE TRADING 🔴                   ║
║                                                  ║
║  ⚡ Quick Scalp Trades                           ║
║  🛡️ Fixed SL: 0.8%                              ║
║  🎯 TP Range: 0.5% - 2.0%                       ║
║  🤖 AI-Powered Entry Decisions                   ║
╚══════════════════════════════════════════════════╝
"""
    print(f"\033[96m{banner}\033[0m")


def verify_api():
    # Sync time before verifying API
    if not sync_time():
        log_error("Failed to sync time with Binance server")
        return False
    
    ts = get_timestamp()
    params = f"timestamp={ts}"
    sig = sign(params)
    account = request_binance("GET", "/fapi/v2/account", f"{params}&signature={sig}")

    if "totalWalletBalance" in account:
        log_success("✅ API verified!")
        balance = float(account["totalWalletBalance"])
        log_info(f"💰 Balance: ${balance:.2f} USDT")
        return True
    else:
        log_error(f"❌ API failed: {account}")
        return False


def main():
    print_banner()

    if not verify_api():
        return

    log_success("🔌 Connected to Binance Futures")
    log_info("🤖 Gemini AI ready")

    bot_thread = None

    while True:
        print(f"\n\033[94m[1] Start Bot | [2] Stop Bot | [3] Stats | [4] Exit\033[0m")
        cmd = input(f"\033[95mCommand: \033[0m").strip()

        if cmd == '1':
            if running:
                log_warn("⚠️ Bot already running!")
            else:
                bot_thread = threading.Thread(target=run_bot, daemon=True)
                bot_thread.start()

        elif cmd == '2':
            if running:
                stop_bot()
                log_success("✅ Bot stopped")
            else:
                log_warn("⚠️ Bot not running!")

        elif cmd == '3':
            balance = get_balance()
            win_rate = calculate_win_rate()
            log_info(f"💰 Balance: ${balance:.2f}")
            log_info(f"📊 Trades: {len(trade_history)}")
            log_info(f"🏆 Win Rate: {win_rate:.1f}%")
            log_info(f"💎 P&L: ${total_pnl:.2f}")
            log_info(f"🔄 Active: {len(active_trades)}")

        elif cmd == '4':
            if running:
                stop_bot()
                if bot_thread:
                    bot_thread.join(timeout=5)
            log_success("👋 Goodbye!")
            break


if __name__ == "__main__":
    main()
