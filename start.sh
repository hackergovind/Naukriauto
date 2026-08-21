#!/usr/bin/env bash
# Startup script for Wispbyte / Linux environments

echo "🚀 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "🌐 Installing Playwright Chromium browser..."
playwright install chromium
playwright install-deps chromium 2>/dev/null || true

echo "🤖 Starting Naukri Auto Bot..."
python main.py
