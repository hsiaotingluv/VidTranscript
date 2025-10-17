import os
import yt_dlp
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

class VideoProcessor:
    """Video processor using yt-dlp to download and convert videos"""
    
    def __init__(self):
        self.ydl_opts = {
            'format': 'bestaudio/best',  # prefer best audio source
            'outtmpl': '%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                # convert to mono 16k at extraction stage (smaller and stable)
                'preferredcodec': 'm4a',
                'preferredquality': '192'
            }],
            # global FFmpeg args: mono + 16k sample rate + faststart
            'postprocessor_args': ['-ac', '1', '-ar', '16000', '-movflags', '+faststart'],
            'prefer_ffmpeg': True,
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,  # force single video, not playlist
        }
    
    async def download_and_convert(self, url: str, output_dir: Path) -> tuple[str, str]:
        """
        Download the video and convert to audio (m4a when possible)
        
        Args:
            url: video URL
            output_dir: output directory
            
        Returns:
            Tuple of (audio_file_path, video_title)
        """
        try:
            # 创建输出目录
            output_dir.mkdir(exist_ok=True)
            
            # 生成唯一的文件名
            import uuid
            unique_id = str(uuid.uuid4())[:8]
            output_template = str(output_dir / f"audio_{unique_id}.%(ext)s")
            
            # 更新yt-dlp选项
            ydl_opts = self.ydl_opts.copy()
            ydl_opts['outtmpl'] = output_template
            
            logger.info(f"Start downloading video: {url}")
            
            # 直接同步执行，不使用线程池
            # 在FastAPI中，IO密集型操作可以直接await
            import asyncio
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Get video info (off main loop)
                info = await asyncio.to_thread(ydl.extract_info, url, False)
                video_title = info.get('title', 'unknown')
                expected_duration = info.get('duration') or 0
                logger.info(f"Video title: {video_title}")
                
                # Download video (off main loop)
                await asyncio.to_thread(ydl.download, [url])
            
            # 查找生成的m4a文件
            audio_file = str(output_dir / f"audio_{unique_id}.m4a")
            
            if not os.path.exists(audio_file):
                # If m4a does not exist, try other audio extensions
                for ext in ['webm', 'mp4', 'mp3', 'wav']:
                    potential_file = str(output_dir / f"audio_{unique_id}.{ext}")
                    if os.path.exists(potential_file):
                        audio_file = potential_file
                        break
                else:
                    raise Exception("Downloaded audio file not found")
            
            # Verify duration; if mismatch is large, try ffmpeg remuxing once
            try:
                import subprocess, shlex
                probe_cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {shlex.quote(audio_file)}"
                out = subprocess.check_output(probe_cmd, shell=True).decode().strip()
                actual_duration = float(out) if out else 0.0
            except Exception as _:
                actual_duration = 0.0
            
            if expected_duration and actual_duration and abs(actual_duration - expected_duration) / expected_duration > 0.1:
                logger.warning(
                    f"Audio duration mismatch, expected {expected_duration}s, actual {actual_duration}s. Trying remux..."
                )
                try:
                    fixed_path = str(output_dir / f"audio_{unique_id}_fixed.m4a")
                    fix_cmd = f"ffmpeg -y -i {shlex.quote(audio_file)} -vn -c:a aac -b:a 160k -movflags +faststart {shlex.quote(fixed_path)}"
                    subprocess.check_call(fix_cmd, shell=True)
                    # 用修复后的文件替换
                    audio_file = fixed_path
                    # 重新探测
                    out2 = subprocess.check_output(probe_cmd.replace(shlex.quote(audio_file.rsplit('.',1)[0]+'.m4a'), shlex.quote(audio_file)), shell=True).decode().strip()
                    actual_duration2 = float(out2) if out2 else 0.0
                    logger.info(f"Remux completed, new duration ≈{actual_duration2:.2f}s")
                except Exception as e:
                    logger.error(f"Remux failed: {e}")
            
            logger.info(f"Audio file saved: {audio_file}")
            return audio_file, video_title
            
        except Exception as e:
            logger.error(f"Video download failed: {str(e)}")
            raise Exception(f"Video download failed: {str(e)}")
    
    
