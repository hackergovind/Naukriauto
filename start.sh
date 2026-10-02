#!/usr/bin/env bash
# Basic Linux CLI server startup (512MB VPS friendly, no browser needed)
set -e
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "Starting Naukri Auto Bot (09:00 + 12:30 IST)..."
exec python main.py
