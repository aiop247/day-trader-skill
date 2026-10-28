# NSE Stock F&O Option Buying System - Server Setup & Deployment Guide

This step-by-step guide explains how to deploy and run the **NSE Stock F&O Option Buying System** (Local GUI, Strategy Engine, and Automated Telegram Alerts) on any Windows or Linux VPS/Cloud Server.

---

## 1. Prerequisites & System Requirements

- **Operating System**: Windows Server / Windows 10/11 OR Linux (Ubuntu 20.04 / 22.04 LTS).
- **Python**: Version `3.10` or `3.11` (with `pip`).
- **RAM**: Minimum 2 GB (4 GB recommended).
- **Telegram Bot**: HTTP API Token & Chat ID (Already configured with `@dpmarket1_bot`).

---

## 2. Windows Server / Local Setup (Quickest)

### Step 1: Clone or Copy Repository
Ensure your repository is placed in your desired directory:
```powershell
cd "D:\Market Gitlab\day-trader-skill"
```

### Step 2: Install Python Dependencies
Run in PowerShell:
```powershell
python -m pip install --upgrade pip
pip install fastapi uvicorn requests
```

### Step 3: Run the Dashboard & Strategy Engine
Launch the server:
```powershell
python app_fno_gui.py
```
- The dashboard will be available at: **`http://localhost:8000`** (or `http://YOUR_SERVER_IP:8000`).

### Step 4: Run the Automated Telegram Scanner (Background Daemon)
To have the scanner automatically monitor the market and fire Telegram alerts every 60 seconds during live market hours:
```powershell
python -c "
import time, datetime, sys, fno_options, app_fno_gui
sys.stdout.reconfigure(encoding='utf-8')

print('Starting NSE F&O Live Alert Daemon...')
cfg = fno_options.load_config()
sent_today = set()

while True:
    now = datetime.datetime.now()
    # Check if NSE Market is open (09:30 - 15:00 IST)
    market_open = (now.hour == 9 and now.minute >= 30) or (10 <= now.hour < 15)
    
    if market_open:
        try:
            sectors = app_fno_gui.get_sectors()
            top_sector = sectors[0]
            weakest_sector = sectors[-1]
            
            # CE Check: Top sector > +0.50%
            if top_sector['avg_change'] >= 0.50:
                top_stocks = app_fno_gui.get_sector_stocks(top_sector['name'])
                leader = top_stocks[0]
                if leader['change'] >= 1.5 and leader['symbol'] not in sent_today:
                    plan = fno_options.plan_option_buy(leader['symbol'], leader['price'], 'LONG')
                    fno_options.send_telegram_alert(cfg['telegram_token'], cfg['telegram_chat_id'], plan)
                    sent_today.add(leader['symbol'])
                    print(f'Sent CE alert for {leader[\"symbol\"]}')
            
            # PE Check: Weakest sector < -0.50%
            if weakest_sector['avg_change'] <= -0.50:
                weak_stocks = app_fno_gui.get_sector_stocks(weakest_sector['name'])
                laggard = weak_stocks[-1]
                if laggard['change'] <= -1.5 and laggard['symbol'] not in sent_today:
                    plan = fno_options.plan_option_buy(laggard['symbol'], laggard['price'], 'SHORT')
                    fno_options.send_telegram_alert(cfg['telegram_token'], cfg['telegram_chat_id'], plan)
                    sent_today.add(laggard['symbol'])
                    print(f'Sent PE alert for {laggard[\"symbol\"]}')
        except Exception as e:
            print('Scan loop error:', e)
            
    time.sleep(60)
"
```

---

## 3. Linux VPS Deployment (Ubuntu / Debian)

If you are hosting this on an AWS EC2, DigitalOcean, Hetzner, or Contabo Ubuntu instance:

### Step 1: Update Server & Install Python
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip git -y
```

### Step 2: Clone Codebase
```bash
git clone https://github.com/aiop247/day-trader-skill.git /opt/day-trader-skill
cd /opt/day-trader-skill
pip3 install fastapi uvicorn requests
```

### Step 3: Run as a Systemd Background Service (24/7 Autostart)
Create a systemd service file:
```bash
sudo nano /etc/systemd/system/fno-trader.service
```

Paste the following configuration:
```ini
[Unit]
Description=NSE Stock F&O Option Dashboard & Alert Engine
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/day-trader-skill
ExecStart=/usr/bin/python3 app_fno_gui.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable fno-trader
sudo systemctl start fno-trader
```

Check status:
```bash
sudo systemctl status fno-trader
```

---

## 4. Configuration & Credentials

The system stores your settings in `trader/config.json`:

```json
{
  "market": "NSE",
  "currency_symbol": "₹",
  "budget": 50000,
  "max_loss_per_trade_usd": 3000,
  "max_daily_loss_usd": 6000,
  "require_stop": true,
  "no_entries_before": "09:30",
  "no_entries_after": "15:00",
  "flat_by": "15:15",
  "telegram_token": "8633439842:AAE4zntv2xMxZf_gYjbHQH5_RZCi_GRn_sQ",
  "telegram_chat_id": "-5195328060"
}
```

- **`max_loss_per_trade_usd`**: Maximum loss in `₹` per trade.
- **`max_daily_loss_usd`**: Maximum account loss in `₹` before the system stops for the day.
- **`telegram_token`**: Bot token from `@BotFather`.
- **`telegram_chat_id`**: Channel/Group numeric ID.

---

## 5. Security & Firewall (Production Cloud Servers)

If running on a public cloud IP:
1. Allow port `8000` on your server firewall:
   ```bash
   sudo ufw allow 8000/tcp
   ```
2. (Optional) Run behind Nginx with SSL (Certbot Let's Encrypt) for secure `https://` access:
   ```nginx
   server {
       server_name yourdomain.com;
       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

---

## 6. Daily Operating Checklist

1. **09:15 – 09:30 IST**: Market opens. Sector Heatmap begins calculating relative performance. No trade signals are sent during this initial 15-minute range building window.
2. **09:30 – 11:30 IST**: **Prime Window**. Monitor Telegram for CE signals (leading green sectors) or PE signals (lagging red sectors).
3. **11:30 – 13:30 IST**: Lunchtime range-bound chop. The system suppresses false breakout signals.
4. **13:30 – 14:45 IST**: **Afternoon Trend Window**. Watch for continuation breakout alerts.
5. **15:15 IST**: Square-off reminder. Close all open intraday positions.
