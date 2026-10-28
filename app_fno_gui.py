"""FastAPI Local Server & Web GUI Dashboard for NSE Stock Option Buyer.

Run directly via:
    python app_fno_gui.py
Opens automatically on http://localhost:8000
"""
from __future__ import annotations

import json
import os
import urllib.request
import webbrowser
from typing import Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import fno_options

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(ROOT_DIR, "templates")

app = FastAPI(title="NSE Stock F&O Option Buyer")


class ConfigUpdate(BaseModel):
    max_loss_per_trade_usd: float
    max_daily_loss_usd: float
    telegram_token: Optional[str] = ""
    telegram_chat_id: Optional[str] = ""


@app.get("/", response_class=HTMLResponse)
def read_root():
    template_path = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Index template not found.</h1>"


@app.get("/api/fno-stocks")
def get_fno_stocks():
    return fno_options.fetch_nse_fno_master()


@app.get("/api/config")
def get_config():
    return fno_options.load_config()


@app.post("/api/config")
def update_config(cfg: ConfigUpdate):
    current = fno_options.load_config()
    current["max_loss_per_trade_usd"] = cfg.max_loss_per_trade_usd
    current["max_daily_loss_usd"] = cfg.max_daily_loss_usd
    current["telegram_token"] = cfg.telegram_token
    current["telegram_chat_id"] = cfg.telegram_chat_id
    fno_options.save_config(current)
    return {"status": "ok", "config": current}


def fetch_stock_quote(symbol: str) -> dict:
    """Fetches real-time price from Yahoo Finance for NSE ticker."""
    clean_sym = symbol.replace(".NS", "").replace(".BO", "").upper()
    ticker = f"{clean_sym}.NS"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=5m&range=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            meta = data["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice") or meta.get("chartPreviousClose")
            prev_close = meta.get("chartPreviousClose", price)
            change_pct = round(((price - prev_close) / prev_close) * 100, 2) if prev_close else 0.0
            return {"price": price, "change": change_pct}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch market data for {ticker}: {e}")


@app.get("/api/plan-option")
def api_plan_option(
    symbol: str = Query(..., description="Stock symbol, e.g. RELIANCE, SBIN"),
    direction: str = Query("LONG", description="LONG for Call (CE), SHORT for Put (PE)")
):
    cfg = fno_options.load_config()
    max_loss = cfg.get("max_loss_per_trade_usd", 3000.0)
    
    quote = fetch_stock_quote(symbol)
    stock_price = quote["price"]
    
    plan = fno_options.plan_option_buy(
        symbol=symbol,
        stock_price=stock_price,
        direction=direction,
        max_loss_budget=max_loss
    )
    return plan


@app.post("/api/send-telegram")
def api_send_telegram(plan: dict):
    cfg = fno_options.load_config()
    token = cfg.get("telegram_token", "")
    chat_id = cfg.get("telegram_chat_id", "")
    
    if not token or not chat_id:
        return {"success": False, "message": "Telegram Bot Token or Chat ID not configured in Settings."}
    
    success, msg = fno_options.send_telegram_alert(token, chat_id, plan)
    return {"success": success, "message": msg}


SECTOR_MAP = {
    "Banking": [
        ("HDFCBANK", "HDFC Bank Ltd", 650),
        ("ICICIBANK", "ICICI Bank Ltd", 700),
        ("SBIN", "State Bank of India", 750),
        ("AXISBANK", "Axis Bank Ltd", 625),
        ("KOTAKBANK", "Kotak Mahindra Bank", 2000),
        ("INDUSINDBK", "IndusInd Bank Ltd", 700),
        ("BANKBARODA", "Bank of Baroda", 2925),
        ("PNB", "Punjab National Bank", 8000),
        ("CANBK", "Canara Bank", 6750),
        ("FEDERALBNK", "Federal Bank Ltd", 2500),
        ("IDFCFIRSTB", "IDFC First Bank Ltd", 9275),
        ("AUBANK", "AU Small Finance Bank", 500),
        ("BANDHANBNK", "Bandhan Bank Ltd", 3600)
    ],
    "IT & Software": [
        ("TCS", "Tata Consultancy Services", 225),
        ("INFY", "Infosys Ltd", 400),
        ("HCLTECH", "HCL Technologies Ltd", 400),
        ("WIPRO", "Wipro Ltd", 3000),
        ("TECHM", "Tech Mahindra Ltd", 600),
        ("LTIM", "LTIMindtree Ltd", 150),
        ("COFORGE", "Coforge Ltd", 475),
        ("PERSISTENT", "Persistent Systems Ltd", 125),
        ("MPHASIS", "Mphasis Ltd", 275),
        ("LTTS", "L&T Technology Services", 100),
        ("TATAELXSI", "Tata Elxsi Ltd", 125)
    ],
    "Auto": [
        ("TATAMOTORS", "Tata Motors Ltd", 1425),
        ("MARUTI", "Maruti Suzuki India Ltd", 50),
        ("M&M", "Mahindra & Mahindra Ltd", 200),
        ("BAJAJ-AUTO", "Bajaj Auto Ltd", 75),
        ("HEROMOTOCO", "Hero MotoCorp Ltd", 150),
        ("EICHERMOT", "Eicher Motors Ltd", 100),
        ("TVSMOTOR", "TVS Motor Company Ltd", 175),
        ("BHARATFORG", "Bharat Forge Ltd", 500),
        ("ASHOKLEY", "Ashok Leyland Ltd", 5000),
        ("BALKRISIND", "Balkrishna Industries", 300),
        ("MOTHERSON", "Samvardhana Motherson", 6150),
        ("BOSCHLTD", "Bosch Ltd", 25),
        ("MRF", "MRF Ltd", 5)
    ],
    "Energy & Oil": [
        ("RELIANCE", "Reliance Industries Ltd", 500),
        ("ONGC", "Oil & Natural Gas Corp", 2250),
        ("BPCL", "Bharat Petroleum Corp", 1975),
        ("IOC", "Indian Oil Corporation", 4875),
        ("GAIL", "GAIL (India) Ltd", 3550),
        ("NTPC", "NTPC Ltd", 1500),
        ("POWERGRID", "Power Grid Corp of India", 1900),
        ("TATAPOWER", "Tata Power Co Ltd", 1450),
        ("ADANIPOWER", "Adani Power Ltd", 3550),
        ("ADANIENSOL", "Adani Energy Solutions", 675),
        ("PETRONET", "Petronet LNG Ltd", 1900),
        ("IGL", "Indraprastha Gas Ltd", 1375),
        ("MGL", "Mahanagar Gas Ltd", 400)
    ],
    "Metals": [
        ("TATASTEEL", "Tata Steel Ltd", 2750),
        ("JSWSTEEL", "JSW Steel Ltd", 675),
        ("HINDALCO", "Hindalco Industries Ltd", 700),
        ("VEDL", "Vedanta Ltd", 1150),
        ("COALINDIA", "Coal India Ltd", 1350),
        ("JINDALSTEL", "Jindal Steel & Power", 625),
        ("NMDC", "NMDC Ltd", 6750),
        ("SAIL", "Steel Authority of India", 4700),
        ("NATIONALUM", "National Aluminium Co", 1875)
    ],
    "Financial & NBFC": [
        ("BAJFINANCE", "Bajaj Finance Ltd", 750),
        ("BAJAJFINSV", "Bajaj Finserv Ltd", 300),
        ("CHOLAFIN", "Cholamandalam Inv & Fin", 625),
        ("SHRIRAMFIN", "Shriram Finance Ltd", 825),
        ("MUTHOOTFIN", "Muthoot Finance Ltd", 275),
        ("PFC", "Power Finance Corp", 1300),
        ("RECLTD", "REC Ltd", 1575),
        ("SBICARD", "SBI Cards & Payment", 800),
        ("HDFCLIFE", "HDFC Life Insurance Co", 1100),
        ("SBILIFE", "SBI Life Insurance Co", 375),
        ("ICICIPRULI", "ICICI Prudential Life", 1500),
        ("ICICIGI", "ICICI Lombard General", 325)
    ],
    "Pharma": [
        ("SUNPHARMA", "Sun Pharmaceutical Ind", 350),
        ("DRREDDY", "Dr. Reddy s Laboratories", 625),
        ("CIPLA", "Cipla Ltd", 425),
        ("DIVISLAB", "Divi s Laboratories Ltd", 100),
        ("APOLLOHOSP", "Apollo Hospitals Ent", 125),
        ("LUPIN", "Lupin Ltd", 425),
        ("TORNTPHARM", "Torrent Pharmaceuticals", 125),
        ("ZYDUSLIFE", "Zydus Lifesciences", 450),
        ("BIOCON", "Biocon Ltd", 2500),
        ("MANKIND", "Mankind Pharma Ltd", 250),
        ("MAXHEALTH", "Max Healthcare Institute", 525)
    ],
    "FMCG": [
        ("ITC", "ITC Ltd", 1725),
        ("HINDUNILVR", "Hindustan Unilever Ltd", 300),
        ("NESTLEIND", "Nestle India Ltd", 500),
        ("BRITANNIA", "Britannia Industries", 125),
        ("TATACONSUM", "Tata Consumer Products", 550),
        ("DABUR", "Dabur India Ltd", 1250),
        ("GODREJCP", "Godrej Consumer Products", 500),
        ("MARICO", "Marico Ltd", 1200),
        ("COLPAL", "Colgate-Palmolive India", 275),
        ("VBL", "Varun Beverages Ltd", 1275)
    ],
    "Infra & Defense": [
        ("LT", "Larsen & Toubro Ltd", 175),
        ("HAL", "Hindustan Aeronautics Ltd", 150),
        ("BEL", "Bharat Electronics Ltd", 1425),
        ("BHEL", "Bharat Heavy Electricals", 2625),
        ("SIEMENS", "Siemens Ltd", 175),
        ("ABB", "ABB India Ltd", 125),
        ("CUMMINSIND", "Cummins India Ltd", 100),
        ("ADANIPORTS", "Adani Ports & SEZ", 475),
        ("GMRINFRA", "GMR Airports Infra", 10000)
    ],
    "Realty & Cement": [
        ("ULTRACEMCO", "UltraTech Cement Ltd", 50),
        ("AMBUJACEM", "Ambuja Cements Ltd", 1200),
        ("SHREECEM", "Shree Cement Ltd", 25),
        ("DLF", "DLF Ltd", 950),
        ("GODREJPROP", "Godrej Properties Ltd", 325),
        ("OBEROIRLTY", "Oberoi Realty Ltd", 350),
        ("BHARTIARTL", "Bharti Airtel Ltd", 475)
    ]
}


@app.get("/api/sectors")
def get_sectors():
    """Returns sector list with average performance for sorting."""
    import concurrent.futures

    fno_master = fno_options.fetch_nse_fno_master()
    
    # Representative tickers to quickly compute sector performance
    rep_map = {
        "Banking": ["HDFCBANK", "ICICIBANK", "SBIN"],
        "IT & Software": ["TCS", "INFY", "HCLTECH"],
        "Auto": ["TATAMOTORS", "MARUTI", "M&M"],
        "Energy & Oil": ["RELIANCE", "ONGC", "NTPC"],
        "Metals": ["TATASTEEL", "JSWSTEEL", "HINDALCO"],
        "Financial & NBFC": ["BAJFINANCE", "CHOLAFIN", "PFC"],
        "Pharma": ["SUNPHARMA", "CIPLA", "DRREDDY"],
        "FMCG": ["ITC", "HINDUNILVR", "TATACONSUM"],
        "Infra & Defense": ["LT", "BEL", "HAL"],
        "Realty & Cement": ["BHARTIARTL", "ULTRACEMCO", "DLF"]
    }

    all_reps = list(set([sym for syms in rep_map.values() for sym in syms]))
    quotes = {}
    
    def fetch_sym(s):
        try:
            return s, fetch_stock_quote(s)
        except Exception:
            return s, {"price": 0.0, "change": 0.0}

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for sym, q in executor.map(fetch_sym, all_reps):
            quotes[sym] = q

    sector_summary = []
    for sector, stock_list in SECTOR_MAP.items():
        reps = rep_map.get(sector, [])
        changes = [quotes[r]["change"] for r in reps if r in quotes and quotes[r]["price"] > 0]
        avg_change = round(sum(changes) / len(changes), 2) if changes else 0.0
        sector_summary.append({
            "name": sector,
            "avg_change": avg_change,
            "stock_count": len(stock_list)
        })

    # Sort sectors: highest positive % on top, most negative % at bottom
    sector_summary.sort(key=lambda x: x["avg_change"], reverse=True)
    return sector_summary


@app.get("/api/sector-stocks")
def get_sector_stocks(sector: str = Query("Banking")):
    """Returns all stocks for a specific sector, sorted descending by % change."""
    import concurrent.futures

    stocks = SECTOR_MAP.get(sector, SECTOR_MAP["Banking"])
    fno_master = fno_options.fetch_nse_fno_master()

    def fetch_stock_data(item):
        sym, default_name, default_lot = item
        lot = fno_master.get(sym, {}).get("lot", default_lot)
        name = fno_master.get(sym, {}).get("name", default_name)
        try:
            q = fetch_stock_quote(sym)
            return {
                "symbol": sym,
                "name": name,
                "lot": lot,
                "price": q["price"],
                "change": q["change"]
            }
        except Exception:
            return {
                "symbol": sym,
                "name": name,
                "lot": lot,
                "price": 0.0,
                "change": 0.0
            }

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(fetch_stock_data, stocks))

    # Auto-sort: Green (+%) on TOP, Red (-%) at BOTTOM
    results.sort(key=lambda x: x["change"], reverse=True)
    return results


def main():
    import sys
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("=" * 60)
    print("Starting NSE Stock Option Buyer GUI...")
    print("Access GUI at: http://localhost:8000")
    print("=" * 60)
    
    # Try opening browser automatically
    try:
        webbrowser.open("http://localhost:8000")
    except Exception:
        pass

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()
