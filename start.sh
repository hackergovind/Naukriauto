#!/usr/bin/env bash
# Startup script for Wispbyte / Linux environments

echo "🚀 Installing lightweight dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "🤖 Starting Naukri Auto Bot..."
python main.py