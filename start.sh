#!/bin/bash
echo "========================================"
echo "  INSTAGRAM BOT - AUTO SETUP"
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
echo "✅ FFmpeg: $(ffmpeg -version 2>&1 | head -1)"

# Run bot
echo "🚀 Starting Bot..."
python3 bot.py
