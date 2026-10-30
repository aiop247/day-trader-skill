"""Automated Live NSE F&O Scanner Daemon for Telegram Alerts.

Monitors NSE sectors & stock breakouts in real-time during market hours (09:30 - 15:00 IST),
calculates ATM CE / PE option buying plans, and dispatches instant Telegram alerts.
Includes:
- Morning Market Open / Welcome Alert (09:15 - 09:30 IST)
- Real-time intraday Breakout Alerts (CE & PE)
- End-of-Day (EOD) Market Summary Alert (15:30 IST)
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


def get_ist_now() -> datetime.datetime:
    """Returns current datetime in Indian Standard Time (UTC+5:30)."""
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    return utc_now + datetime.timedelta(hours=5, minutes=30)


def is_weekday(dt: datetime.datetime) -> bool:
    """0 = Monday, 4 = Friday."""
    return dt.weekday() <= 4


def is_market_open(dt: datetime.datetime) -> bool:
    """Checks whether NSE market is currently in active intraday trading window (09:30 - 15:00 IST, Mon-Fri)."""
    if not is_weekday(dt):
        return False
    total_mins = dt.hour * 60 + dt.minute
    return (9 * 60 + 30) <= total_mins < (15 * 60)


def send_morning_welcome(token: str, chat_id: str, dt: datetime.datetime) -> bool:
    """Dispatches 09:15-09:30 morning market opening message."""
    date_str = dt.strftime("%A, %d %B %Y")
    msg = (
        f"🌅 *GOOD MORNING! NSE MARKET IS NOW OPEN*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 *Date*: {date_str}\n"
        f"⏰ *Time*: {dt.strftime('%H:%M')} IST\n"
        f"🎯 *Mode*: Stock Option Buying (1:2 R:R)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *Intraday Schedule*:\n"
        f"• *09:15 - 09:30*: Opening Range Building (No entries)\n"
        f"• *09:30 - 11:30*: 🚀 Prime Breakout Window\n"
        f"• *11:30 - 13:30*: ⏸️ Lunch Consolidation (Strict filters)\n"
        f"• *13:30 - 14:45*: 📈 Afternoon Trend Window\n"
        f"• *15:15 IST*: ⏰ Mandatory Square-off\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ *Scanner Status*: ACTIVE & Monitoring all F&O Sectors.\n"
        f"Good luck and stick to risk management! 📈"
    )
    ok, _ = fno_options.send_telegram_raw(token, chat_id, msg)
    return ok


def send_eod_summary(token: str, chat_id: str, dt: datetime.datetime, alerts_count: int, alerted_stocks: list[str]) -> bool:
    """Dispatches 15:30 IST market close summary message."""
    try:
        sectors = app_fno_gui.get_sectors()
        top_sec = sectors[0] if sectors else {"name": "N/A", "avg_change": 0.0}
        weak_sec = sectors[-1] if sectors else {"name": "N/A", "avg_change": 0.0}
        top_sec_str = f"{top_sec['name']} (+{top_sec['avg_change']}%)"
        weak_sec_str = f"{weak_sec['name']} ({weak_sec['avg_change']}%)"
    except Exception:
        top_sec_str = "N/A"
        weak_sec_str = "N/A"

    stocks_text = ", ".join(alerted_stocks) if alerted_stocks else "None (Choppy market)"

    msg = (
        f"🏁 *NSE MARKET CLOSE - EOD SUMMARY*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 *Date*: {dt.strftime('%A, %d %B %Y')}\n"
        f"⏰ *Time*: 15:30 IST (Market Closed)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 *Top Performing Sector*: {top_sec_str}\n"
        f"📉 *Weakest Sector*: {weak_sec_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 *Today's Alerts Sent*: *{alerts_count}*\n"
        f"🎯 *Triggered Stocks*: `{stocks_text}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔒 *Status*: Intraday square-off complete.\n"
        f"Scanner going into standby until 09:15 AM tomorrow! 🌙"
    )
    ok, _ = fno_options.send_telegram_raw(token, chat_id, msg)
    return ok


def run_scanner_loop(interval_seconds: int = 60):
    print("=" * 60)
    print("🚀 NSE Stock F&O Auto-Scanner & Telegram Daemon Started")
    print(f"⏱️ Scan Interval: Every {interval_seconds} seconds")
    print("⏰ Active Hours: 09:30 to 15:00 IST (Monday - Friday)")
    print("🔔 Morning Alert: 09:15 IST | EOD Summary: 15:30 IST")
    print("=" * 60)
    
    cfg = fno_options.load_config()
    token = cfg.get("telegram_token")
    chat_id = cfg.get("telegram_chat_id")
    
    if not token or not chat_id:
        print("❌ Error: Telegram token or chat_id not configured in config.json")
        return

    print(f"📡 Telegram Channel: {chat_id}")
    sent_today: list[str] = []
    morning_sent_day = -1
    eod_sent_day = -1
    last_reset_day = -1

    while True:
        try:
            ist_now = get_ist_now()
            today_day = ist_now.day
            total_mins = ist_now.hour * 60 + ist_now.minute

            # Reset daily counters at midnight / new day
            if today_day != last_reset_day:
                sent_today.clear()
                last_reset_day = today_day
                print(f"📅 New trading day reset: {ist_now.strftime('%Y-%m-%d')}")

            # 1. MORNING WELCOME ALERT (Between 09:15 and 09:30 IST on weekdays)
            if is_weekday(ist_now) and (9 * 60 + 15) <= total_mins < (9 * 60 + 30):
                if morning_sent_day != today_day:
                    print("🌅 Sending morning market open message...")
                    if send_morning_welcome(token, chat_id, ist_now):
                        morning_sent_day = today_day
                        print("✅ Morning welcome alert delivered to Telegram!")

            # 2. EOD SUMMARY ALERT (Between 15:30 and 15:45 IST on weekdays)
            if is_weekday(ist_now) and (15 * 60 + 30) <= total_mins < (15 * 60 + 45):
                if eod_sent_day != today_day:
                    print("🏁 Sending EOD market summary message...")
                    if send_eod_summary(token, chat_id, ist_now, len(sent_today), sent_today):
                        eod_sent_day = today_day
                        print("✅ EOD summary alert delivered to Telegram!")

            # 3. ACTIVE INTRADAY SCANNING (09:30 - 15:00 IST)
            if not is_market_open(ist_now):
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

            # Bullish CE Check: Top Sector avg change >= +0.40%
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
                            sent_today.append(sym)
                            print(f"✅ Telegram CE alert sent for {sym}!")
                        else:
                            print(f"❌ Failed to send alert: {msg}")

            # Bearish PE Check: Weakest Sector avg change <= -0.40%
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
                            sent_today.append(sym)
                            print(f"✅ Telegram PE alert sent for {sym}!")
                        else:
                            print(f"❌ Failed to send alert: {msg}")

        except Exception as e:
            print(f"⚠️ Scanner loop error: {e}")

        time.sleep(interval_seconds)


if __name__ == "__main__":
    run_scanner_loop()
