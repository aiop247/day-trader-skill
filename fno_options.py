"""NSE Stock F&O Master Registry and Option Buying Planner Engine.

Provides:
- Official NSE F&O universe with exact market lot sizes
- Strike step calculations & ATM/Slightly ITM strike selection
- Option buying trade plans (Entry, SL, 1:2 TP, Lot Sizing based on ₹ Risk Budget)
- Telegram alert dispatching
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import urllib.request
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADER_DIR = os.path.join(ROOT_DIR, "trader")
FNO_DATA_FILE = os.path.join(TRADER_DIR, "fno_stocks.json")
CONFIG_FILE = os.path.join(TRADER_DIR, "config.json")

# Fallback top liquid F&O stocks with lot sizes in case offline/network failure
FALLBACK_FNO: Dict[str, Dict[str, any]] = {
    "RELIANCE": {"name": "RELIANCE INDUSTRIES LTD", "lot": 250},
    "TCS": {"name": "TATA CONSULTANCY SERVICES", "lot": 175},
    "HDFCBANK": {"name": "HDFC BANK LIMITED", "lot": 550},
    "ICICIBANK": {"name": "ICICI BANK LIMITED", "lot": 700},
    "INFY": {"name": "INFOSYS LIMITED", "lot": 400},
    "SBIN": {"name": "STATE BANK OF INDIA", "lot": 1500},
    "BHARTIARTL": {"name": "BHARTI AIRTEL LIMITED", "lot": 475},
    "ITC": {"name": "ITC LIMITED", "lot": 1600},
    "KOTAKBANK": {"name": "KOTAK MAHINDRA BANK", "lot": 400},
    "LT": {"name": "LARSEN & TOUBRO LTD", "lot": 150},
    "AXISBANK": {"name": "AXIS BANK LIMITED", "lot": 625},
    "BAJFINANCE": {"name": "BAJAJ FINANCE LIMITED", "lot": 125},
    "MARUTI": {"name": "MARUTI SUZUKI INDIA LTD", "lot": 100},
    "TATAMOTORS": {"name": "TATA MOTORS LIMITED", "lot": 1425},
    "TATASTEEL": {"name": "TATA STEEL LIMITED", "lot": 5500},
    "SUNPHARMA": {"name": "SUN PHARMACEUTICAL IND L", "lot": 700},
    "WIPRO": {"name": "WIPRO LIMITED", "lot": 1500},
    "NTPC": {"name": "NTPC LIMITED", "lot": 1500},
    "POWERGRID": {"name": "POWER GRID CORP (I) LTD", "lot": 3600},
    "TITAN": {"name": "TITAN COMPANY LIMITED", "lot": 175},
    "ULTRACEMCO": {"name": "ULTRATECH CEMENT LIMITED", "lot": 100},
    "HEROMOTOCO": {"name": "HERO MOTOCORP LIMITED", "lot": 300},
    "INDUSINDBK": {"name": "INDUSIND BANK LIMITED", "lot": 500},
    "M&M": {"name": "MAHINDRA & MAHINDRA LTD", "lot": 350},
    "TECHM": {"name": "TECH MAHINDRA LIMITED", "lot": 600},
    "HINDALCO": {"name": "HINDALCO INDUSTRIES LTD", "lot": 1400},
    "ADANIENT": {"name": "ADANI ENTERPRISES LIMITED", "lot": 300},
    "ADANIPORTS": {"name": "ADANI PORT & SEZ LTD", "lot": 475},
    "COALINDIA": {"name": "COAL INDIA LIMITED", "lot": 2100},
    "DIVISLAB": {"name": "DIVI'S LABORATORIES LTD", "lot": 200},
    "ASIANPAINT": {"name": "ASIAN PAINTS LIMITED", "lot": 200},
    "BAJAJ-AUTO": {"name": "BAJAJ AUTO LIMITED", "lot": 125},
    "BPCL": {"name": "BHARAT PETROLEUM CORP LT", "lot": 1800},
    "EICHERMOT": {"name": "EICHER MOTORS LIMITED", "lot": 175},
    "GRASIM": {"name": "GRASIM INDUSTRIES LTD", "lot": 250},
    "HCLTECH": {"name": "HCL TECHNOLOGIES LTD", "lot": 700},
    "HINDUNILVR": {"name": "HINDUSTAN UNILEVER LTD", "lot": 300},
    "JSWSTEEL": {"name": "JSW STEEL LIMITED", "lot": 675},
    "NESTLEIND": {"name": "NESTLE INDIA LIMITED", "lot": 250},
    "ONGC": {"name": "OIL & NATURAL GAS CORP", "lot": 3850},
    "VEDL": {"name": "VEDANTA LIMITED", "lot": 2300},
    "ZOMATO": {"name": "ZOMATO LIMITED", "lot": 2000},
    "JIOFIN": {"name": "JIO FINANCIAL SERVICES", "lot": 2400},
}


def load_config() -> dict:
    default_cfg = {
        "market": "NSE",
        "currency_symbol": "₹",
        "budget": 50000,
        "max_loss_per_trade_usd": 3000,
        "max_daily_loss_usd": 6000,
        "telegram_token": "8633439842:AAE4zntv2xMxZf_gYjbHQH5_RZCi_GRn_sQ",
        "telegram_chat_id": "-5195328060"
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                default_cfg.update(saved)
                # Ensure telegram settings fallback to default if empty
                if not default_cfg.get("telegram_token"):
                    default_cfg["telegram_token"] = "8633439842:AAE4zntv2xMxZf_gYjbHQH5_RZCi_GRn_sQ"
                if not default_cfg.get("telegram_chat_id"):
                    default_cfg["telegram_chat_id"] = "-5195328060"
                return default_cfg
        except Exception:
            pass
    return default_cfg


def save_config(cfg: dict) -> None:
    os.makedirs(TRADER_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def fetch_nse_fno_master(force_refresh: bool = False) -> Dict[str, Dict[str, any]]:
    """Fetches the official NSE F&O market lot sizes list from NSE Archives."""
    if not force_refresh and os.path.exists(FNO_DATA_FILE):
        try:
            with open(FNO_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data and len(data) > 50:
                    return data
        except Exception:
            pass

    url = "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
            fno_stocks = {}
            lines = text.splitlines()
            reader = csv.reader(lines)
            headers_row = None
            for row in reader:
                if not row or not any(row):
                    continue
                clean_row = [c.strip() for c in row if c.strip()]
                if not clean_row:
                    continue
                if "SYMBOL" in clean_row:
                    headers_row = [c.strip() for c in row]
                    continue
                if headers_row and len(clean_row) >= 3:
                    name = clean_row[0]
                    sym = clean_row[1]
                    # Filter out indices to get Stock F&O
                    if sym in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"]:
                        continue
                    try:
                        lot = int(clean_row[2])
                        fno_stocks[sym] = {"name": name, "lot": lot}
                    except ValueError:
                        pass
            if fno_stocks:
                os.makedirs(TRADER_DIR, exist_ok=True)
                with open(FNO_DATA_FILE, "w", encoding="utf-8") as f:
                    json.dump(fno_stocks, f, indent=2)
                return fno_stocks
    except Exception:
        pass

    # Fallback if network issue
    return FALLBACK_FNO


def get_strike_step(price: float) -> float:
    """Calculates standard NSE stock option strike interval based on underlying price."""
    if price < 100:
        return 2.5
    elif price < 250:
        return 5.0
    elif price < 500:
        return 10.0
    elif price < 1000:
        return 20.0
    elif price < 2500:
        return 50.0
    elif price < 5000:
        return 100.0
    elif price < 10000:
        return 200.0
    else:
        return 500.0


def plan_option_buy(
    symbol: str,
    stock_price: float,
    direction: str,  # "BULLISH" / "LONG" or "BEARISH" / "SHORT"
    stock_sl: Optional[float] = None,
    stock_target: Optional[float] = None,
    max_loss_budget: float = 3000.0,
    fno_master: Optional[Dict[str, dict]] = None
) -> dict:
    """Generates a complete Option Buying trade plan with Entry, SL, TP (1:2 R:R) and lot-sized quantities."""
    clean_sym = symbol.replace(".NS", "").replace(".BO", "").upper()
    if fno_master is None:
        fno_master = fetch_nse_fno_master()

    lot_info = fno_master.get(clean_sym, FALLBACK_FNO.get(clean_sym, {"name": clean_sym, "lot": 250}))
    lot_size = lot_info.get("lot", 250)

    is_bullish = direction.upper() in ["BULLISH", "LONG", "BUY", "CALL", "CE"]
    opt_type = "CE" if is_bullish else "PE"

    step = get_strike_step(stock_price)
    atm_strike = round(stock_price / step) * step

    # Intraday ATM Option Premium benchmark (~2.5% of underlying price)
    est_premium = round(stock_price * 0.024, 2)
    if est_premium < 2.0:
        est_premium = 2.0

    # Stop Loss on Premium: 28% of premium (leaves breathing room while capping max loss)
    sl_points = round(est_premium * 0.28, 2)
    sl_price = round(max(0.5, est_premium - sl_points), 2)

    # Target: 1:2 Risk to Reward (56% gain on premium)
    target_points = round(sl_points * 2.0, 2)
    target_price = round(est_premium + target_points, 2)

    # Risk per lot in INR
    risk_per_lot = round(sl_points * lot_size, 2)
    
    # Capital required to buy 1 lot
    capital_per_lot = round(est_premium * lot_size, 2)

    # Lot Sizing based on max_loss_budget
    lots = max(1, math.floor(max_loss_budget / risk_per_lot)) if risk_per_lot > 0 else 1
    total_qty = lots * lot_size
    total_risk = round(risk_per_lot * lots, 2)
    total_reward = round(target_points * lot_size * lots, 2)
    total_capital = round(capital_per_lot * lots, 2)

    contract_name = f"{clean_sym} {int(atm_strike) if atm_strike.is_integer() else atm_strike} {opt_type}"

    return {
        "symbol": clean_sym,
        "company": lot_info.get("name", clean_sym),
        "stock_price": stock_price,
        "direction": "CALL BUY (CE)" if is_bullish else "PUT BUY (PE)",
        "opt_type": opt_type,
        "strike": atm_strike,
        "contract": contract_name,
        "lot_size": lot_size,
        "lots": lots,
        "total_qty": total_qty,
        "est_premium": est_premium,
        "sl_price": sl_price,
        "sl_points": sl_points,
        "target_price": target_price,
        "target_points": target_points,
        "rr_ratio": "1 : 2.0",
        "risk_per_lot": risk_per_lot,
        "total_risk": total_risk,
        "total_reward": total_reward,
        "capital_required": total_capital,
        "flat_by": "15:15 IST",
        "stock_sl": stock_sl,
        "stock_target": stock_target
    }


def send_telegram_alert(token: str, chat_id: str, plan: dict) -> Tuple[bool, str]:
    """Sends a formatted Option Buying trade signal to Telegram."""
    if not token or not chat_id:
        return False, "Telegram Bot Token or Chat ID not configured."

    direction_emoji = "🟢 🚀" if "CALL" in plan["direction"] else "🔴 📉"
    
    msg = (
        f"{direction_emoji} *NSE STOCK OPTION SIGNAL*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 *Contract*: `{plan['contract']}`\n"
        f"🏢 *Company*: {plan['company']}\n"
        f"📊 *Action*: *{plan['direction']}*\n"
        f"📈 *Stock LTP*: ₹{plan['stock_price']}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Entry Premium*: ~₹{plan['est_premium']}\n"
        f"🛑 *Stop Loss*: ₹{plan['sl_price']} (-₹{plan['sl_points']})\n"
        f"🎯 *Target (1:2)*: ₹{plan['target_price']} (+₹{plan['target_points']})\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *Lot Size*: {plan['lot_size']} shares\n"
        f"🔢 *Recommended*: {plan['lots']} Lot ({plan['total_qty']} Qty)\n"
        f"💵 *Capital Needed*: ₹{plan['capital_required']:,}\n"
        f"⚠️ *Max Risk (SL)*: ₹{plan['total_risk']:,}\n"
        f"🎁 *Target Gain*: ₹{plan['total_reward']:,}\n"
        f"⏰ *Square-Off*: {plan['flat_by']}\n"
    )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        import ssl
        # Disable strict SSL verification on remote/corporate servers with self-signed proxies
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            if res.get("ok"):
                return True, "Alert sent successfully!"
            return False, str(res)
    except Exception as e:
        return False, f"Telegram API error: {e}"
