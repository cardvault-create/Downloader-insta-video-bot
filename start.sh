#!/bin/bash
echo "========================================"
echo "  INSTAGRAM BOT - SETUP"
echo "========================================"
pip install --upgrade yt-dlp --quiet
pip install -r requirements.txt --quiet
echo "✅ yt-dlp: $(yt-dlp --version)"
echo "🚀 Starting Bot..."
python3 bot.py
