from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import os
import tempfile
import asyncio
import logging
from pathlib import Path
from typing import Optional
import aiofiles
import uuid
import json
import re
import shutil

from video_processor import VideoProcessor
from transcriber import Transcriber

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Video Transcriber", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Project root
PROJECT_ROOT = Path(__file__).parent.parent

# Mount static files
app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "static")), name="static")

# Create temp directory
TEMP_DIR = PROJECT_ROOT / "temp"
TEMP_DIR.mkdir(exist_ok=True)

# Initialize processors
video_processor = VideoProcessor()
transcriber = Transcriber()

# Persist tasks state to file
import json
import threading

TASKS_FILE = TEMP_DIR / "tasks.json"
tasks_lock = threading.Lock()

def load_tasks():
    """Load tasks state"""
    try:
        if TASKS_FILE.exists():
            with open(TASKS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {}

def save_tasks(tasks_data):
    """Save tasks state"""
    try:
        with tasks_lock:
            with open(TASKS_FILE, 'w', encoding='utf-8') as f:
                json.dump(tasks_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save tasks: {e}")

def cleanup_temp_dir_if_idle():
    """
    Delete prior session temp files immediately when no task is active.
    Keeps tasks.json; removes everything else under TEMP_DIR.
    """
    try:
        if active_tasks:
            # Do not clean if something is running
            return
        for p in TEMP_DIR.iterdir():
            if p.name == 'tasks.json':
                continue
            try:
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Temp cleanup skipped {p.name}: {e}")
        logger.info("Temp directory cleaned (idle)")
    except Exception as e:
        logger.error(f"Temp cleanup failed: {e}")

async def broadcast_task_update(task_id: str, task_data: dict):
    """Broadcast task update to all SSE clients"""
    logger.info(f"Broadcast task update: {task_id}, status: {task_data.get('status')}, connections: {len(sse_connections.get(task_id, []))}")
    if task_id in sse_connections:
        connections_to_remove = []
        for queue in sse_connections[task_id]:
            try:
                await queue.put(json.dumps(task_data, ensure_ascii=False))
                logger.debug(f"Message sent to queue: {task_id}")
            except Exception as e:
                logger.warning(f"Failed to send message to queue: {e}")
                connections_to_remove.append(queue)
        
        # Remove broken connections
        for queue in connections_to_remove:
            sse_connections[task_id].remove(queue)
        
        # If no connections left, cleanup list
        if not sse_connections[task_id]:
            del sse_connections[task_id]

# Load tasks on startup
tasks = load_tasks()
# Track URLs being processed to avoid duplicates
processing_urls = set()
# Track active task objects for control/cancel
active_tasks = {}
# Track SSE connections for live updates
sse_connections = {}

def _sanitize_title_for_filename(title: str) -> str:
    """Sanitize video title for a safe filename snippet."""
    if not title:
        return "untitled"
    # Keep only alphanumeric, underscore, hyphen and space
    safe = re.sub(r"[^\w\-\s]", "", title)
    # Compress whitespace and convert to underscore
    safe = re.sub(r"\s+", "_", safe).strip("._-")
    # Limit length to avoid overly long filenames
    return safe[:80] or "untitled"

@app.get("/")
async def read_root():
    """Return frontend page"""
    return FileResponse(str(PROJECT_ROOT / "static" / "index.html"))

@app.get("/robots.txt")
async def robots_txt():
    return FileResponse(str(PROJECT_ROOT / "static" / "robots.txt"))

@app.get("/sitemap.xml")
async def sitemap_xml():
    return FileResponse(str(PROJECT_ROOT / "static" / "sitemap.xml"))

@app.post("/api/process-video")
async def process_video(
    url: str = Form(...)
):
    """
    Process video URL and return a task ID
    """
    try:
        # Immediate cleanup of previous session files when idle
        cleanup_temp_dir_if_idle()
        # Check if the same URL is already being processed
        if url in processing_urls:
            # Find existing task
            for tid, task in tasks.items():
                if task.get("url") == url:
                    return {"task_id": tid, "message": "This video is already being processed. Please wait..."}
        
        # Generate a unique task ID
        task_id = str(uuid.uuid4())
        
        # Mark URL as in processing
        processing_urls.add(url)
        
        # Initialize task state
        tasks[task_id] = {
            "status": "processing",
            "progress": 0,
            "message": "Starting processing...",
            "script": None,
            "error": None,
            "url": url  # Save URL for deduplication
        }
        save_tasks(tasks)
        
        # Create and track async task
        task = asyncio.create_task(process_video_task(task_id, url))
        active_tasks[task_id] = task
        
        return {"task_id": task_id, "message": "Task created. Processing..."}
        
    except Exception as e:
        logger.error(f"Error processing video: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

async def process_video_task(task_id: str, url: str):
    """
    Async task to process video
    """
    try:
        # Update state: start downloading video
        tasks[task_id].update({
            "status": "processing",
            "progress": 10,
            "message": "Downloading video..."
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        
        # Add short delay to ensure state is pushed
        import asyncio
        await asyncio.sleep(0.1)
        
        # Update state: parsing video info
        tasks[task_id].update({
            "progress": 15,
            "message": "Parsing video info..."
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        
        # Download and convert video
        audio_path, video_title = await video_processor.download_and_convert(url, TEMP_DIR)
        
        # Download completed, update state
        tasks[task_id].update({
            "progress": 35,
            "message": "Video downloaded, preparing transcription..."
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        
        # Update state: transcribing
        tasks[task_id].update({
            "progress": 40,
            "message": "Transcribing audio..."
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        
        # Transcribe audio -> returns a single paragraph string
        raw_script = await transcriber.transcribe(audio_path)
        short_id = task_id.replace("-", "")[:6]
        safe_title = _sanitize_title_for_filename(video_title)
        
        # Prepare transcript (use raw transcript directly)
        tasks[task_id].update({
            "progress": 55,
            "message": "Preparing transcript..."
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])

        script = raw_script or ""
        # Use raw single-paragraph transcript as-is (title shown separately in UI)
        script_with_title = script
        
        # Finalization state before completion
        tasks[task_id].update({
            "progress": 85,
            "message": "Finalizing results..."
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        
        # Save final downloadable transcript as .txt, with title on first line
        download_text = f"{video_title}\n\n{script}\n"
        script_filename = f"{safe_title}.txt"
        script_path = TEMP_DIR / script_filename
        async with aiofiles.open(script_path, "w", encoding="utf-8") as f:
            await f.write(download_text)

        # Delete audio source immediately to minimize storage
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
        except Exception as e:
            logger.warning(f"Audio cleanup skipped: {e}")

        # Update state: completed
        task_result = {
            "status": "completed",
            "progress": 100,
            "message": "Processing completed!",
            "video_title": video_title,
            "script": script_with_title,
            "script_path": str(script_path),
            "short_id": short_id,
            "safe_title": safe_title
        }
        
        tasks[task_id].update(task_result)
        save_tasks(tasks)
        logger.info(f"Task completed, broadcasting final state: {task_id}")
        await broadcast_task_update(task_id, tasks[task_id])
        logger.info(f"Final state broadcast: {task_id}")
        
        # Remove URL from processing set
        processing_urls.discard(url)
        
        # Remove from active tasks list
        if task_id in active_tasks:
            del active_tasks[task_id]
        
        # Keep files for this session; they will be deleted automatically
        # at the start of the next session when the service is idle.
        
    except Exception as e:
        logger.error(f"Task {task_id} failed: {str(e)}")
        # Remove URL from processing set
        processing_urls.discard(url)
        
        # Remove from active tasks list
        if task_id in active_tasks:
            del active_tasks[task_id]
            
        tasks[task_id].update({
            "status": "error",
            "error": str(e),
            "message": f"Processing failed: {str(e)}"
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])

@app.get("/api/task-status/{task_id}")
async def get_task_status(task_id: str):
    """
    Get task status
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return tasks[task_id]

@app.get("/api/task-stream/{task_id}")
async def task_stream(task_id: str):
    """
    SSE live task status stream
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    async def event_generator():
        # Create queue for this task
        queue = asyncio.Queue()
        
        # Add queue to connections list
        if task_id not in sse_connections:
            sse_connections[task_id] = []
        sse_connections[task_id].append(queue)
        
        try:
            # Send current state immediately
            current_task = tasks.get(task_id, {})
            yield f"data: {json.dumps(current_task, ensure_ascii=False)}\n\n"
            
            # Listen for updates
            while True:
                try:
                    # Wait for updates; send heartbeat every 30s
                    data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {data}\n\n"
                    
                    # End stream if task completed or errored
                    task_data = json.loads(data)
                    if task_data.get("status") in ["completed", "error"]:
                        break
                        
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield f"data: {json.dumps({'type': 'heartbeat'}, ensure_ascii=False)}\n\n"
                    
        except asyncio.CancelledError:
            logger.info(f"SSE connection cancelled: {task_id}")
        except Exception as e:
            logger.error(f"SSE stream error: {e}")
        finally:
            # Cleanup connection
            if task_id in sse_connections and queue in sse_connections[task_id]:
                sse_connections[task_id].remove(queue)
                if not sse_connections[task_id]:
                    del sse_connections[task_id]
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """
    Download file directly from temp directory (simplified)
    """
    try:
        # Validate extension (.txt preferred, .md allowed for legacy/raw files)
        if not (filename.endswith('.txt') or filename.endswith('.md')):
            raise HTTPException(status_code=400, detail="Only .txt or .md files can be downloaded")
        
        # Validate filename format (prevent path traversal)
        if '..' in filename or '/' in filename or '\\' in filename:
            raise HTTPException(status_code=400, detail="Invalid filename format")
            
        file_path = TEMP_DIR / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
            
        media_type = "text/plain" if filename.endswith('.txt') else "text/markdown"
        return FileResponse(
            file_path,
            filename=filename,
            media_type=media_type
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File download failed: {e}")
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@app.delete("/api/task/{task_id}")
async def delete_task(task_id: str):
    """
    Cancel and delete task
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # If task is running, cancel it
    if task_id in active_tasks:
        task = active_tasks[task_id]
        if not task.done():
            task.cancel()
            logger.info(f"Task {task_id} cancelled")
        del active_tasks[task_id]
    
    # Remove from processing URL set
    task_url = tasks[task_id].get("url")
    if task_url:
        processing_urls.discard(task_url)
    
    # Delete task record
    del tasks[task_id]
    return {"message": "Task has been canceled and deleted"}

@app.get("/api/tasks/active")
async def get_active_tasks():
    """
    Get current active tasks (for debugging)
    """
    active_count = len(active_tasks)
    processing_count = len(processing_urls)
    return {
        "active_tasks": active_count,
        "processing_urls": processing_count,
        "task_ids": list(active_tasks.keys())
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
