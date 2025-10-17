#!/usr/bin/env python3
"""
AI Video Transcriber startup script
"""

import os
import sys
import subprocess
from pathlib import Path

def check_dependencies():
    """Check if required dependencies are installed"""
    import sys
    required_packages = {
        "fastapi": "fastapi",
        "uvicorn": "uvicorn", 
        "yt-dlp": "yt_dlp",
        "faster-whisper": "faster_whisper"
    }
    
    missing_packages = []
    for display_name, import_name in required_packages.items():
        try:
            __import__(import_name)
        except ImportError:
            missing_packages.append(display_name)
    
    if missing_packages:
        print("❌ Missing the following dependencies:")
        for package in missing_packages:
            print(f"   - {package}")
        print("\nPlease install dependencies with:")
        print("source venv/bin/activate && pip install -r requirements.txt")
        return False
    
    print("✅ All dependencies are installed")
    return True

def check_ffmpeg():
    """Check if FFmpeg is installed"""
    try:
        subprocess.run(["ffmpeg", "-version"], 
                      stdout=subprocess.DEVNULL, 
                      stderr=subprocess.DEVNULL, 
                      check=True)
        print("✅ FFmpeg is installed")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ FFmpeg not found")
        print("Please install FFmpeg:")
        print("  macOS: brew install ffmpeg")
        print("  Ubuntu: sudo apt install ffmpeg")
        print("  Windows: Download from https://ffmpeg.org/download.html")
        return False

def setup_environment():
    """Setup environment variables"""
    # Defaults
    if not os.getenv("WHISPER_MODEL_SIZE"):
        os.environ["WHISPER_MODEL_SIZE"] = "base"
    return True

def main():
    """Main entrypoint"""
    # Check production mode (disable hot reload)
    production_mode = "--prod" in sys.argv or os.getenv("PRODUCTION_MODE") == "true"
    
    print("🚀 AI Video Transcriber startup check")
    if production_mode:
        print("🔒 Production mode - hot reload disabled")
    else:
        print("🔧 Development mode - hot reload enabled")
    print("=" * 50)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Check FFmpeg
    if not check_ffmpeg():
        print("⚠️  FFmpeg not installed; some formats may be affected")
    
    # Setup environment
    setup_environment()
    
    print("\n🎉 Startup checks complete!")
    print("=" * 50)
    
    # Start server
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    
    print(f"\n🌐 Starting server...")
    print(f"   URL: http://localhost:{port}")
    print(f"   Press Ctrl+C to stop")
    print("=" * 50)
    
    try:
        # Stay at project root and run backend as a package module
        project_root = Path(__file__).parent
        os.chdir(project_root)

        app_path = "backend.main:app"
        cmd = [
            sys.executable, "-m", "uvicorn", app_path,
            "--host", host,
            "--port", str(port)
        ]
        
        # Enable hot reload only in dev mode
        if not production_mode:
            cmd.append("--reload")
        
        subprocess.run(cmd)
        
    except KeyboardInterrupt:
        print("\n\n👋 Service stopped")
    except Exception as e:
        print(f"\n❌ Startup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
