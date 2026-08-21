# 🚀 Naukri Auto Profile Updater (Telegram Controlled)

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![Playwright](https://img.shields.io/badge/Engine-Playwright-green.svg)](https://playwright.dev)
[![Telegram Bot](https://img.shields.io/badge/Interface-Telegram_Bot-2CA5E0.svg)](https://core.telegram.org/bots)
[![License](https://img.shields.io/badge/License-MIT-orange.svg)](#)

An intelligent automation tool that automatically edits your **Naukri profile headline** every day at **9:00 AM IST** (or on-demand) by toggling a trailing period (.). 

This marks your profile as freshly updated on Naukri's recruiter search algorithm, ensuring your profile stays in the **top search results when recruiters start sourcing candidates in the morning**.

---

## ✨ Features

- ⏰ **Daily 9:00 AM IST Scheduler**: Built-in cron engine (APScheduler) configured to update every morning.
- 📱 **Interactive Telegram Bot**: Control everything from Telegram with interactive inline buttons and commands.
- 🔄 **Smart Dot Toggler**: Toggles a . at the end of your headline ("Developer" ⇄ "Developer.") so your headline stays clean while refreshing your timestamp.
- 📸 **Live Screenshot Verification**: Sends photo proof directly to Telegram after every update.
- 🔐 **Session Persistence**: Stores cookies/session state securely after first login to avoid repeated authentications or security alerts.
- 🛡️ **Access Control**: Restricts bot usage strictly to your Telegram User ID (ALLOWED_TELEGRAM_USER_IDS).
- ☁️ **100% Free Hosting Ready**: Optimized for **Wispbyte**, Render, Railway, Docker, or any Linux VPS.

---

## 🤖 Telegram Commands

| Command | Description |
|---|---|
| /start | Open the interactive dashboard with action buttons |
| /update_now or /update | Manually trigger profile headline update immediately |
| /status | Check scheduler status, account, and next run time |
| /headline | Fetch and view your current headline from Naukri |
| /set_time <HH:MM> | Change daily scheduled update time (24-hr format) |
| /logs | View the latest 20 log entries |
| /help | Display command usage and guide |

---

## 🛠️ Step 1: Telegram Bot Setup

1. Open Telegram and search for [@BotFather](https://t.me/BotFather).
2. Send /newbot, choose a name and username (e.g. MyNaukriAutoBot).
3. Copy the generated **HTTP API Bot Token** (e.g. 1234567890:ABCdefGHI...).
4. Search for [@userinfobot](https://t.me/userinfobot) on Telegram, click Start, and copy your **User ID** (e.g. 987654321).

---

## 🌐 Step 2: Free Hosting on Wispbyte

[Wispbyte](https://wispbyte.com) provides free Python / bot hosting containers:

1. **Sign up / Log in** to your [Wispbyte Panel](https://wispbyte.com).
2. **Create a New Server**:
   - Choose **Python** (Python 3.10+ / Debian egg).
   - Allocate the free resources.
3. **Upload Files**:
   - In the Wispbyte File Manager, upload this repository (or clone it using Git if Git egg is selected).
4. **Configure Environment Variables**:
   - Create a file named .env in the root directory (or copy from .env.example):
     `ini
     NAUKRI_EMAIL=your_email@example.com
     NAUKRI_PASSWORD=your_naukri_password
     TELEGRAM_BOT_TOKEN=your_telegram_bot_token_from_botfather
     ALLOWED_TELEGRAM_USER_IDS=your_telegram_user_id
     DAILY_UPDATE_TIME=09:00
     TIMEZONE=Asia/Kolkata
     HEADLESS=true
     `
5. **Set Startup Command**:
   - Set the startup command to:
     `ash
     bash start.sh
     `
     *(Or: pip install -r requirements.txt && playwright install chromium && python main.py)*
6. **Start the Server**:
   - Click **Start**. The bot will initialize, install Chromium dependencies, connect to Telegram, and schedule daily 9 AM updates!

---

## 💻 Step 3: Local Setup / VPS / Docker

### Option A: Local / Virtualenv

1. **Clone the repository**:
   `ash
   git clone https://github.com/hackergovind/Naukriauto.git
   cd Naukriauto
   `

2. **Create & activate virtual environment**:
   `ash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On Linux/macOS:
   source venv/bin/activate
   `

3. **Install dependencies**:
   `ash
   pip install -r requirements.txt
   playwright install chromium
   `

4. **Setup .env file**:
   `ash
   cp .env.example .env
   # Edit .env with your credentials
   `

5. **Run the bot**:
   `ash
   python main.py
   `

### Option B: Docker / Docker Compose

`ash
docker-compose up -d --build
`

---

## 📁 Project Structure

`
Naukriauto/
├── src/
│   ├── __init__.py
│   ├── config.py             # Settings, loguru logger & env parser
│   ├── naukri_client.py      # Playwright browser automation engine
│   ├── scheduler.py          # APScheduler daily cron manager
│   └── bot.py                # Telegram bot handlers & UI
├── data/                     # Saved sessions, screenshots & logs (.gitignored)
├── Dockerfile                # Container definition with Chromium
├── docker-compose.yml        # Docker compose setup
├── requirements.txt          # Python dependencies
├── start.sh                  # Wispbyte / Linux startup script
├── .env.example              # Configuration template
├── .gitignore                # Protect sensitive data
├── main.py                   # Main entry point
└── README.md                 # Complete documentation
`

---

## 🔒 Security & Privacy

- All credentials remain on your private host / server and are never logged or transmitted elsewhere.
- ALLOWED_TELEGRAM_USER_IDS guarantees that no unauthorized person can access or trigger commands on your bot.
- .gitignore prevents your .env and data/session.json from ever being committed to Git.

---

## 📄 License
This project is licensed under the MIT License.
