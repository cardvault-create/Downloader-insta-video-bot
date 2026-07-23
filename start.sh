#!/bin/bash
echo "========================================"
echo "  INSTAGRAM BOT - SETUP"
echo "========================================"

# Update yt-dlp
echo "📦 Updating yt-dlp..."
pip install --upgrade yt-dlp --quiet

# Install requirements
echo "📦 Installing requirements..."
pip install -r requirements.txt --quiet

# Show versions
echo "✅ yt-dlp: $(yt-dlp --version)"
echo "✅ Python: $(python3 --version)"

# Run bot
echo "🚀 Starting Bot..."
python3 bot.py
