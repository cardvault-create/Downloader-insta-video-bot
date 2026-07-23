#!/bin/bash
echo "========================================"
echo "  INSTAGRAM BOT - SETUP"
echo "========================================"
pip install --upgrade yt-dlp instaloader --quiet
pip install -r requirements.txt --quiet
echo "✅ yt-dlp: $(yt-dlp --version)"
echo "✅ instaloader: $(python3 -c 'import instaloader; print(instaloader.__version__)')"
echo "🚀 Starting Bot..."
python3 bot.py
