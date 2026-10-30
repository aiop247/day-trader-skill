"""Automated Live NSE F&O Scanner Daemon for Telegram Alerts.

Monitors NSE sectors & stock breakouts in real-time during market hours (09:30 - 15:00 IST),
calculates ATM CE / PE option buying plans, and dispatches instant Telegram alerts.
"""
from __future__ import annotations

import datetime
import os
import sys
import time

import app_fno_gui
import fno_options

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def is_market_open() -> bool:
    """Checks whether NSE market is currently in active intraday trading window (09:30 - 15:00 IST, Mon-Fri)."""
    # Calculate IST time (UTC+5:30)
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    ist_now = utc_now + datetime.timedelta(hours=5, minutes=30)
    
    # 0 = Monday, 4 = Friday, 5 = Saturday, 6 = Sunday
    if ist_now.weekday() > 4:
        return False
        
    hour = ist_now.hour
    minute = ist_now.minute
    total_mins = hour * 60 + minute
    
    # 09:30 IST to 15:00 IST
    return (9 * 60 + 30) <= total_mins < (15 * 60)


def run_scanner_loop(interval_seconds: int = 60):
    print("=" * 60)
    print("🚀 NSE Stock F&O Auto-Scanner & Telegram Daemon Started")
    print(f"⏱️ Scan Interval: Every {interval_seconds} seconds")
    print("⏰ Active Hours: 09:30 to 15:00 IST (Monday - Friday)")
    print("=" * 60)
    
    cfg = fno_options.load_config()
    token = cfg.get("telegram_token")
    chat_id = cfg.get("telegram_chat_id")
    
    if not token or not chat_id:
        print("❌ Error: Telegram token or chat_id not configured in config.json")
        return

    print(f"📡 Telegram Channel: {chat_id}")
    sent_today: set[str] = set()
    last_reset_day = -1

    while True:
        try:
            utc_now = datetime.datetime.now(datetime.timezone.utc)
            ist_now = utc_now + datetime.timedelta(hours=5, minutes=30)
            
            # Reset sent_today cache each new morning
            if ist_now.day != last_reset_day:
                sent_today.clear()
                last_reset_day = ist_now.day
                print(f"📅 New trading day reset: {ist_now.strftime('%Y-%m-%d')}")

            if not is_market_open():
                print(f"[{ist_now.strftime('%H:%M:%S')} IST] ⏸️ Market closed / outside trading window. Waiting...")
                time.sleep(interval_seconds)
                continue

            print(f"[{ist_now.strftime('%H:%M:%S')} IST] 🔍 Scanning NSE Sectors & F&O stocks...")
            sectors = app_fno_gui.get_sectors()
            if not sectors:
                time.sleep(interval_seconds)
                continue

            top_sector = sectors[0]
            weakest_sector = sectors[-1]

            # 1. Bullish CE Check: Top Sector avg change >= +0.40%
            if top_sector.get("avg_change", 0.0) >= 0.40:
                sec_name = top_sector["name"]
                stocks = app_fno_gui.get_sector_stocks(sec_name)
                if stocks:
                    leader = stocks[0]
                    sym = leader["symbol"]
                    # Stock must be showing real breakout (>= +1.2%) and not already alerted today
                    if leader.get("change", 0.0) >= 1.20 and sym not in sent_today:
                        print(f"🔥 Found Bullish Setup: {sym} in {sec_name} (+{leader['change']}%)")
                        plan = fno_options.plan_option_buy(
                            symbol=sym,
                            stock_price=leader["price"],
                            direction="LONG",
                            max_loss_budget=cfg.get("max_loss_per_trade_usd", 3000.0)
                        )
                        ok, msg = fno_options.send_telegram_alert(token, chat_id, plan)
                        if ok:
                            sent_today.add(sym)
                            print(f"✅ Telegram CE alert sent for {sym}!")
                        else:
                            print(f"❌ Failed to send alert: {msg}")

            # 2. Bearish PE Check: Weakest Sector avg change <= -0.40%
            if weakest_sector.get("avg_change", 0.0) <= -0.40:
                sec_name = weakest_sector["name"]
                stocks = app_fno_gui.get_sector_stocks(sec_name)
                if stocks:
                    laggard = stocks[-1]
                    sym = laggard["symbol"]
                    # Stock must be under heavy selling (<= -1.2%) and not already alerted today
                    if laggard.get("change", 0.0) <= -1.20 and sym not in sent_today:
                        print(f"❄️ Found Bearish Setup: {sym} in {sec_name} ({laggard['change']}%)")
                        plan = fno_options.plan_option_buy(
                            symbol=sym,
                            stock_price=laggard["price"],
                            direction="SHORT",
                            max_loss_budget=cfg.get("max_loss_per_trade_usd", 3000.0)
                        )
                        ok, msg = fno_options.send_telegram_alert(token, chat_id, plan)
                        if ok:
                            sent_today.add(sym)
                            print(f"✅ Telegram PE alert sent for {sym}!")
                        else:
                            print(f"❌ Failed to send alert: {msg}")

        except Exception as e:
            print(f"⚠️ Scanner loop error: {e}")

        time.sleep(interval_seconds)


if __name__ == "__main__":
    run_scanner_loop()
