class VideoTranscriber {
    constructor() {
        this.currentTaskId = null;
        this.eventSource = null;
        // Default: use relative /api so Netlify (or local server) can proxy
        this.apiBase = '/api';
        // i18n removed: fixed English UI
        
        // Smart progress simulation
        this.smartProgress = {
            enabled: false,
            current: 0,           // current displayed progress
            target: 0,            // target progress
            lastServerUpdate: 0,  // last server-reported progress
            interval: null,       // timer
            estimatedDuration: 0, // estimated total duration (seconds)
            startTime: null,      // task start time
            stage: 'preparing'    // current stage
        };
        
        this.msg = {
            start_transcription: "Transcribe",
            processing_progress: "Processing Progress",
            preparing: "Preparing...",
            download_transcript: "Download Transcript",
            transcript_text: "Transcript Text",
            processing: "Processing...",
            downloading_video: "Downloading video...",
            parsing_video: "Parsing video info...",
            transcribing_audio: "Transcribing audio...",
            completed: "Processing completed!",
            error_invalid_url: "Please enter a valid video URL",
            error_processing_failed: "Processing failed: ",
            error_task_not_found: "Task not found",
            error_task_not_completed: "Task not completed yet",
            error_invalid_file_type: "Invalid file type",
            error_file_not_found: "File not found",
            error_download_failed: "Download failed: ",
            error_no_file_to_download: "No file available for download"
        };
        
        this.initializeElements();
        // Allow runtime API override via query param: ?api=https://host[:port][/api]
        try {
            const url = new URL(window.location.href);
            const apiOverride = url.searchParams.get('api');
            if (apiOverride) {
                let base = apiOverride.trim();
                // Normalize: ensure it includes /api at the end
                if (!/\/api\/?$/.test(base)) base = base.replace(/\/$/, '') + '/api';
                this.apiBase = base;
                console.log('[DEBUG] 🔧 API base overridden to:', this.apiBase);
            }
        } catch (_) { /* ignore */ }
        this.bindEvents();
        // i18n removed
    }
    
    initializeElements() {
        // Form elements
        this.form = document.getElementById('videoForm');
        this.videoUrlInput = document.getElementById('videoUrl');
        this.summaryLanguageSelect = document.getElementById('summaryLanguage');
        this.submitBtn = document.getElementById('submitBtn');
        
        // Progress elements
        this.progressSection = document.getElementById('progressSection');
        this.progressStatus = document.getElementById('progressStatus');
        this.progressFill = document.getElementById('progressFill');
        this.progressMessage = document.getElementById('progressMessage');
        
        // Error alert
        this.errorAlert = document.getElementById('errorAlert');
        this.errorMessage = document.getElementById('errorMessage');
        
        // Results elements
        this.resultsSection = document.getElementById('resultsSection');
        this.scriptContent = document.getElementById('scriptContent');
        this.downloadScriptBtn = document.getElementById('downloadScript');
        
        // Debug: check element initialization
        console.log('[DEBUG] 🔧 Init check:');
        
        // Tabs
        this.tabButtons = document.querySelectorAll('.tab-button');
        this.tabContents = document.querySelectorAll('.tab-content');
        
        // No language toggle
    }
    
    bindEvents() {
        // Form submit
        this.form.addEventListener('submit', (e) => {
            e.preventDefault();
            this.startTranscription();
        });
        
        // Tab switching
        this.tabButtons.forEach(button => {
            button.addEventListener('click', () => {
                this.switchTab(button.dataset.tab);
            });
        });
        
        // Download buttons
        if (this.downloadScriptBtn) {
            this.downloadScriptBtn.addEventListener('click', () => {
                this.downloadFile('script');
            });
        }
        // Copy to clipboard
        const copyBtn = document.getElementById('copyScript');
        if (copyBtn) {
            copyBtn.addEventListener('click', async () => {
                const text = (this.scriptContent?.textContent || '').trim();
                if (!text) return;
                const ok = await this.copyToClipboard(text);
                if (ok) {
                    const original = copyBtn.innerHTML;
                    copyBtn.innerHTML = '<i class="fas fa-check"></i>';
                    copyBtn.title = 'Copied!';
                    setTimeout(() => {
                        copyBtn.innerHTML = '<i class="fas fa-copy"></i>';
                        copyBtn.title = 'Copy transcript';
                    }, 1200);
                } else {
                    this.showError('Failed to copy to clipboard');
                }
            });
        }
        
        // Only transcript download supported
        
        // No language toggle
    }
    
    // i18n removed: use fixed English strings
    t(key) { return (this.msg && this.msg[key]) || key; }
    
    async startTranscription() {
        // Disable button immediately to prevent double submit
        if (this.submitBtn.disabled) {
            return; // If already disabled, do nothing
        }
        
        const videoUrl = this.videoUrlInput.value.trim();
        
        if (!videoUrl) {
            this.showError(this.t('error_invalid_url'));
            return;
        }
        
        try {
            // Disable button and hide errors immediately
            this.setLoading(true);
            this.hideError();
            this.hideResults();
            this.showProgress();
            
            // Send transcription request
            const formData = new FormData();
            formData.append('url', videoUrl);
            
            const response = await fetch(`${this.apiBase}/process-video`, {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Request failed');
            }
            
            const data = await response.json();
            this.currentTaskId = data.task_id;
            
            console.log('[DEBUG] ✅ Task created, Task ID:', this.currentTaskId);
            
            // Start smart progress simulation
            this.initializeSmartProgress();
            this.updateProgress(5, this.msg.preparing, true);
            
            // Start SSE to receive realtime updates
            this.startSSE();
            
        } catch (error) {
            console.error('Failed to start transcription:', error);
            this.showError(this.t('error_processing_failed') + error.message);
            this.setLoading(false);
            this.hideProgress();
        }
    }

    async copyToClipboard(text) {
        try {
            if (navigator.clipboard && window.isSecureContext) {
                await navigator.clipboard.writeText(text);
                return true;
            }
        } catch (err) {
            console.warn('[DEBUG] navigator.clipboard failed, falling back:', err);
        }
        try {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.setAttribute('readonly', '');
            ta.style.position = 'fixed';
            ta.style.top = '-1000px';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.select();
            ta.setSelectionRange(0, ta.value.length);
            const ok = document.execCommand('copy');
            document.body.removeChild(ta);
            return !!ok;
        } catch (e) {
            console.error('Fallback copy failed:', e);
            return false;
        }
    }
    
    startSSE() {
        if (!this.currentTaskId) return;
        
        console.log('[DEBUG] 🔄 Start SSE connection, Task ID:', this.currentTaskId);
        
        // Create EventSource connection
        this.eventSource = new EventSource(`${this.apiBase}/task-stream/${this.currentTaskId}`);
        
        this.eventSource.onmessage = (event) => {
            try {
                const task = JSON.parse(event.data);
                
                // Ignore heartbeat messages
                if (task.type === 'heartbeat') {
                    console.log('[DEBUG] 💓 Heartbeat received');
                    return;
                }
                
                console.log('[DEBUG] 📊 SSE task status received:', {
                    status: task.status,
                    progress: task.progress,
                    message: task.message
                });
                
                // Update progress (server-pushed)
                console.log('[DEBUG] 📈 Update progress bar:', `${task.progress}% - ${task.message}`);
                this.updateProgress(task.progress, task.message, true);
                
                if (task.status === 'completed') {
                    console.log('[DEBUG] ✅ Task completed, showing results');
                    this.stopSmartProgress(); // stop smart progress
                    this.stopSSE();
                    this.setLoading(false);
                    this.hideProgress();
                    this.showResults(task.script, task.video_title);
                } else if (task.status === 'error') {
                    console.log('[DEBUG] ❌ Task failed:', task.error);
                    this.stopSmartProgress(); // stop smart progress
                    this.stopSSE();
                    this.setLoading(false);
                    this.hideProgress();
                    this.showError(task.error || 'An error occurred during processing');
                }
            } catch (error) {
                console.error('[DEBUG] Failed to parse SSE data:', error);
            }
        };
        
        this.eventSource.onerror = async (error) => {
            console.error('[DEBUG] SSE connection error:', error);
            this.stopSSE();

            // Fallback: fetch final status; if completed, render results
            try {
                if (this.currentTaskId) {
                    const resp = await fetch(`${this.apiBase}/task-status/${this.currentTaskId}`);
                    if (resp.ok) {
                        const task = await resp.json();
                        if (task && task.status === 'completed') {
                            console.log('[DEBUG] 🔁 SSE disconnected, task completed. Rendering results');
                            this.stopSmartProgress();
                            this.setLoading(false);
                            this.hideProgress();
                            this.showResults(task.script, task.video_title);
                            return;
                        }
                    }
                }
            } catch (e) {
                console.error('[DEBUG] Fallback status check failed:', e);
            }

            // If not completed, notify and keep state (user can retry or reconnect)
            this.showError(this.t('error_processing_failed') + 'SSE connection disconnected');
            this.setLoading(false);
        };
        
        this.eventSource.onopen = () => {
            console.log('[DEBUG] 🔗 SSE connection established');
        };
    }
    
    stopSSE() {
        if (this.eventSource) {
            console.log('[DEBUG] 🔌 Close SSE connection');
            this.eventSource.close();
            this.eventSource = null;
        }
    }
    

    
    updateProgress(progress, message, fromServer = false) {
        console.log('[DEBUG] 🎯 updateProgress called:', { progress, message, fromServer });
        
        if (fromServer) {
            // Server-pushed real progress
            this.handleServerProgress(progress, message);
        } else {
            // Local simulated progress
            this.updateProgressDisplay(progress, message);
        }
    }
    
    handleServerProgress(serverProgress, message) {
        console.log('[DEBUG] 📡 Handle server progress:', serverProgress);
        
        // Stop current simulated progress
        this.stopSmartProgress();
        
        // Update last server progress
        this.smartProgress.lastServerUpdate = serverProgress;
        this.smartProgress.current = serverProgress;
        
        // Immediately update UI with server progress
        this.updateProgressDisplay(serverProgress, message);
        
        // Determine stage and target
        this.updateProgressStage(serverProgress, message);
        
        // Restart smart progress simulation
        this.startSmartProgress();
    }
    
    updateProgressStage(progress, message) {
        // Determine stage based on progress and message
        if (message.includes('parsing')) {
            this.smartProgress.stage = 'parsing';
            this.smartProgress.target = 60;
        } else if (message.includes('downloading')) {
            this.smartProgress.stage = 'downloading';
            this.smartProgress.target = 60;
        } else if (message.includes('transcrib')) {
            this.smartProgress.stage = 'transcribing';
            this.smartProgress.target = 80;
        } else if (message.includes('completed')) {
            this.smartProgress.stage = 'completed';
            this.smartProgress.target = 100;
        }
        
        // If current progress exceeds target, adjust target
        if (progress >= this.smartProgress.target) {
            this.smartProgress.target = Math.min(progress + 10, 100);
        }
        
        console.log('[DEBUG] 🎯 Stage updated:', {
            stage: this.smartProgress.stage,
            target: this.smartProgress.target,
            current: progress
        });
    }
    
    initializeSmartProgress() {
        // Initialize smart progress state
        this.smartProgress.enabled = false;
        this.smartProgress.current = 0;
        this.smartProgress.target = 15;
        this.smartProgress.lastServerUpdate = 0;
        this.smartProgress.startTime = Date.now();
        this.smartProgress.stage = 'preparing';
        
        console.log('[DEBUG] 🔧 Smart progress initialized');
    }
    
    startSmartProgress() {
        // Start smart progress simulation
        if (this.smartProgress.interval) {
            clearInterval(this.smartProgress.interval);
        }
        
        this.smartProgress.enabled = true;
        this.smartProgress.startTime = this.smartProgress.startTime || Date.now();
        
        // Update simulated progress every 500ms
        this.smartProgress.interval = setInterval(() => {
            this.simulateProgress();
        }, 500);
        
        console.log('[DEBUG] 🚀 Smart progress started');
    }
    
    stopSmartProgress() {
        if (this.smartProgress.interval) {
            clearInterval(this.smartProgress.interval);
            this.smartProgress.interval = null;
        }
        this.smartProgress.enabled = false;
        console.log('[DEBUG] ⏹️ Smart progress stopped');
    }
    
    simulateProgress() {
        if (!this.smartProgress.enabled) return;
        
        const current = this.smartProgress.current;
        const target = this.smartProgress.target;
        
        // Pause simulation if target reached
        if (current >= target) return;
        
        // Compute progress increment based on stage
        let increment = this.calculateProgressIncrement();
        
        // Ensure not exceeding target
        const newProgress = Math.min(current + increment, target);
        
        if (newProgress > current) {
            this.smartProgress.current = newProgress;
            this.updateProgressDisplay(newProgress, this.getCurrentStageMessage());
        }
    }
    
    calculateProgressIncrement() {
        const elapsedTime = (Date.now() - this.smartProgress.startTime) / 1000; // seconds
        
        // Stage-based speed config
        const stageConfig = {
            'parsing': { speed: 0.3, maxTime: 30 },      // parsing stage: to 25% within 30s
            'downloading': { speed: 0.2, maxTime: 120 }, // downloading: to 60% within 2min
            'transcribing': { speed: 0.15, maxTime: 180 } // transcribing: to 80% within 3min
        };
        
        const config = stageConfig[this.smartProgress.stage] || { speed: 0.2, maxTime: 60 };
        
        // Base increment per 500ms
        let baseIncrement = config.speed;
        
        // Time factor: speed up if taking too long
        if (elapsedTime > config.maxTime) {
            baseIncrement *= 1.5;
        }
        
        // Distance factor: slow down near target
        const remaining = this.smartProgress.target - this.smartProgress.current;
        if (remaining < 5) {
            baseIncrement *= 0.3; // slow down when near target
        }
        
        return baseIncrement;
    }
    
    getCurrentStageMessage() {
        const stageMessages = {
            'parsing': this.msg.parsing_video,
            'downloading': this.msg.downloading_video,
            'transcribing': this.msg.transcribing_audio,
            'completed': this.msg.completed
        };
        
        return stageMessages[this.smartProgress.stage] || this.t('processing');
    }
    
    updateProgressDisplay(progress, message) {
        // Update UI display
        const roundedProgress = Math.round(progress * 10) / 10; // keep 1 decimal
        this.progressStatus.textContent = `${roundedProgress}%`;
        this.progressFill.style.width = `${roundedProgress}%`;
        console.log('[DEBUG] 📏 Progress bar updated:', this.progressFill.style.width);
        
        // Normalize common progress messages
        let normalized = message;
        if (message.includes('downloading') || message.includes('Downloading')) {
            normalized = this.msg.downloading_video;
        } else if (message.includes('parsing') || message.includes('Parsing')) {
            normalized = this.msg.parsing_video;
        } else if (message.includes('transcrib') || message.includes('Transcrib')) {
            normalized = this.msg.transcribing_audio;
        } else if (message.includes('complet') || message.includes('Complet')) {
            normalized = this.msg.completed;
        } else if (message.includes('prepar') || message.includes('Prepar')) {
            normalized = this.msg.preparing;
        }
        this.progressMessage.textContent = normalized;
    }
    
    showProgress() {
        this.progressSection.style.display = 'block';
    }
    
    hideProgress() {
        this.progressSection.style.display = 'none';
    }
    
    showResults(script, videoTitle = null) {
        const safeScript = script || '';
        const titleEl = document.getElementById('videoTitle');
        if (titleEl) {
            titleEl.textContent = videoTitle || '';
        }
        // Clean legacy headings/timestamps and render as plain paragraph
        const cleanParagraph = (text) => {
            const lines = (text || '').split(/\r?\n/);
            const filtered = lines.filter((l) =>
                !/^\s*#/.test(l) &&
                !/Detected Language/i.test(l) &&
                !/Language Probability/i.test(l) &&
                !/Transcription Content/i.test(l) &&
                !/^\s*source:/i.test(l)
            );
            let joined = filtered.join(' ');
            // Remove asterisks and excessive markdown remnants
            joined = joined.replace(/\*/g, '');
            // Remove timestamp blocks like [00:00 - 00:03] or [0:12 - 0:15]
            joined = joined.replace(/\[\s*\d{1,2}:\d{2}(?::\d{2})?\s*-\s*\d{1,2}:\d{2}(?::\d{2})?\s*\]/g, '');
            return joined.replace(/\s+/g, ' ').trim();
        };
        const paragraph = cleanParagraph(safeScript);
        this.scriptContent.textContent = paragraph;
        
        // Show results section
        this.resultsSection.style.display = 'block';
        
        // Scroll to results
        this.resultsSection.scrollIntoView({ behavior: 'smooth' });
        
        // Syntax highlight
        if (window.Prism) {
            Prism.highlightAll();
        }
    }
    
    hideResults() {
        this.resultsSection.style.display = 'none';
    }
    
    switchTab(tabName) {
        // Remove all active states
        this.tabButtons.forEach(btn => btn.classList.remove('active'));
        this.tabContents.forEach(content => content.classList.remove('active'));
        
        // Activate selected tab
        const activeButton = document.querySelector(`[data-tab="${tabName}"]`);
        const activeContent = document.getElementById(`${tabName}Tab`);
        
        if (activeButton && activeContent) {
            activeButton.classList.add('active');
            activeContent.classList.add('active');
        }
    }
    
    async downloadFile(fileType) {
        if (!this.currentTaskId) {
            this.showError(this.msg.error_no_file_to_download);
            return;
        }
        
        try {
            // First, fetch task status to get actual filenames
            const taskResponse = await fetch(`${this.apiBase}/task-status/${this.currentTaskId}`);
            if (!taskResponse.ok) {
                throw new Error('Failed to fetch task status');
            }
            
            const taskData = await taskResponse.json();
            let filename;
            
            // Only transcript downloads are supported
            if (fileType !== 'script') {
                throw new Error('Unknown file type');
            }
            // Prefer server-side .txt; otherwise build clean .txt locally
            const titleText = (document.getElementById('videoTitle')?.textContent || '').trim() || 'Video';
            const contentText = (this.scriptContent?.textContent || '').trim();
            const localTxt = `${titleText}\n\n${contentText}\n`;

            if (taskData.script_path && taskData.script_path.endsWith('.txt')) {
                filename = taskData.script_path.split('/').pop();
                // Direct download .txt from server
                const encodedFilename = encodeURIComponent(filename);
                const link = document.createElement('a');
                link.href = `${this.apiBase}/download/${encodedFilename}`;
                link.download = filename;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            } else {
                // Generate .txt client-side to avoid legacy .md downloads
                filename = `${taskData.safe_title || 'untitled'}.txt`;
                const blob = new Blob([localTxt], { type: 'text/plain;charset=utf-8' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }
            
        } catch (error) {
            console.error('File download failed:', error);
            this.showError(this.msg.error_download_failed + error.message);
        }
    }
    
    setLoading(loading) {
        this.submitBtn.disabled = loading;
        
        if (loading) {
            this.submitBtn.innerHTML = `<div class="loading-spinner"></div> ${this.msg.processing}`;
        } else {
            this.submitBtn.innerHTML = `<i class="fas fa-play"></i> ${this.msg.start_transcription}`;
        }
    }
    
    showError(message) {
        this.errorMessage.textContent = message;
        this.errorAlert.style.display = 'block';
        
        // Scroll to error alert
        this.errorAlert.scrollIntoView({ behavior: 'smooth' });
        
        // Auto-hide after 5s
        setTimeout(() => {
            this.hideError();
        }, 5000);
    }
    
    hideError() {
        this.errorAlert.style.display = 'none';
    }
}

// Init app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.transcriber = new VideoTranscriber();
    
    // Add example URL hints
    const urlInput = document.getElementById('videoUrl');
    urlInput.addEventListener('focus', () => {
        if (!urlInput.value) {
            urlInput.placeholder = 'e.g.: https://www.youtube.com/watch?v=...';
        }
    });
    
    urlInput.addEventListener('blur', () => {
        if (!urlInput.value) {
            urlInput.placeholder = 'Enter YouTube, TikTok, or other platform video URL...';
        }
    });
    
    // Render supported platforms logos marquee (Top 20 requested)
    const SUPPORTED_PLATFORMS = [
        // Major Video Platforms
        { name: 'YouTube', slug: 'youtube' },
        { name: 'Vimeo', slug: 'vimeo' },
        { name: 'Dailymotion', slug: 'dailymotion' },
        { name: 'TikTok', slug: 'tiktok' },
        // Social Media
        { name: 'Instagram', slug: 'instagram' },
        { name: 'X (Twitter)', slug: 'x' },
        { name: 'Facebook', slug: 'facebook' },
        { name: 'Reddit', slug: 'reddit' },
        // Streaming & Live
        { name: 'Twitch', slug: 'twitch' },
        { name: 'Kick', slug: 'kick' },
        // Audio Platforms
        { name: 'SoundCloud', slug: 'soundcloud' },
        { name: 'Bandcamp', slug: 'bandcamp' },
        { name: 'Spotify', slug: 'spotify' },
        // Asian Platforms
        { name: 'BiliBili', slug: 'bilibili' },
        { name: 'Douyin', slug: 'douyin' },
        // News & Media
        { name: 'BBC iPlayer', slug: 'bbciplayer' },
        { name: 'CNN', slug: 'cnn' },
        // Educational
        { name: 'Coursera', slug: 'coursera' },
        { name: 'Khan Academy', slug: 'khanacademy' },
        { name: 'TED', slug: 'ted' }
    ];
    
    const buildLogoNode = (p) => {
        const src = `https://cdn.simpleicons.org/${p.slug}/B9BCD6`;
        const img = new Image();
        img.alt = `${p.name} logo`;
        img.loading = 'lazy';
        img.decoding = 'async';
        img.src = src;
        img.onerror = () => {
            const span = document.createElement('span');
            span.className = 'logo-fallback';
            span.textContent = p.name;
            img.replaceWith(span);
        };
        const wrapper = document.createElement('span');
        wrapper.className = 'logo-item';
        wrapper.appendChild(img);
        return wrapper;
    };
    
    const trackA = document.getElementById('logosTrackA');
    const trackB = document.getElementById('logosTrackB');
    if (trackA && trackB) {
        SUPPORTED_PLATFORMS.forEach(p => trackA.appendChild(buildLogoNode(p)));
        SUPPORTED_PLATFORMS.forEach(p => trackB.appendChild(buildLogoNode(p)));
        
        const marquee = document.querySelector('.logo-marquee');
        const applyMarqueeMetrics = () => {
            if (!marquee) return;
            // Measure full width of track A (includes gaps)
            const distance = trackA.scrollWidth;
            // Set loop distance CSS var (used by keyframes and track B offset)
            marquee.style.setProperty('--loop-distance', `${distance}px`);
            // Compute duration based on distance for steady speed (~80px/s)
            const pxPerSec = 80;
            const duration = Math.max(20, Math.round((distance / pxPerSec) * 100) / 100);
            trackA.style.animationDuration = `${duration}s`;
            trackB.style.animationDuration = `${duration}s`;
        };
        // Initial compute (wait a tick for layout)
        requestAnimationFrame(applyMarqueeMetrics);
        // Recompute on resize
        let marqueeResizeTimer;
        window.addEventListener('resize', () => {
            clearTimeout(marqueeResizeTimer);
            marqueeResizeTimer = setTimeout(applyMarqueeMetrics, 150);
        });
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (window.transcriber && window.transcriber.eventSource) {
        window.transcriber.stopSSE();
    }
});
