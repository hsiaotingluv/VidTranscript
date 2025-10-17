#!/bin/bash

# AI Video Transcriber installation script

echo "🚀 AI Video Transcriber Installer"
echo "=========================="

# Check Python version
echo "Checking Python environment..."
python_version=$(python3 --version 2>&1 | cut -d' ' -f2)
if [[ -z "$python_version" ]]; then
    echo "❌ Python3 not found. Please install Python 3.8 or higher."
    exit 1
fi
echo "✅ Python version: $python_version"

# Check pip
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 not found. Please install pip."
    exit 1
fi
echo "✅ pip is installed"

# Install Python dependencies
echo ""
echo "Installing Python dependencies..."
pip3 install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✅ Python dependencies installed"
else
    echo "❌ Failed to install Python dependencies"
    exit 1
fi

# Check FFmpeg
echo ""
echo "Checking FFmpeg..."
if command -v ffmpeg &> /dev/null; then
    echo "✅ FFmpeg is installed"
else
    echo "⚠️  FFmpeg not found, attempting to install..."
    
    # Detect OS
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        if command -v apt-get &> /dev/null; then
            sudo apt-get update && sudo apt-get install -y ffmpeg
        elif command -v yum &> /dev/null; then
            sudo yum install -y ffmpeg
        else
            echo "❌ Unable to auto-install FFmpeg. Please install it manually."
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            brew install ffmpeg
        else
            echo "❌ Please install Homebrew first, then run: brew install ffmpeg"
        fi
    else
        echo "❌ Unsupported OS. Please install FFmpeg manually."
    fi
fi

# Create required directories
echo ""
echo "Creating required directories..."
mkdir -p temp static
echo "✅ Directories created"

# Set permissions
chmod +x start.py

echo ""
echo "🎉 Installation complete!"
echo ""
echo "Usage:"
echo "  1) (Optional) Configure OpenAI API key to enable smart summary"
echo "     export OPENAI_API_KEY=your_api_key_here"
echo ""
echo "  2) Start the service:"
echo "     python3 start.py"
echo ""
echo "  3) Open your browser: http://localhost:8000"
echo ""
echo "Supported platforms:"
echo "  - YouTube"
echo "  - Bilibili"
echo "  - Other platforms supported by yt-dlp"