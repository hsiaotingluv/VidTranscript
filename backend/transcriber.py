import os
from faster_whisper import WhisperModel
import logging
from typing import Optional
import unicodedata
import re

logger = logging.getLogger(__name__)

class Transcriber:
    """Audio transcriber using Faster-Whisper for speech-to-text"""
    
    def __init__(self, model_size: str = "base"):
        """
        Initialize the transcriber
        
        Args:
            model_size: Whisper model size (tiny, base, small, medium, large)
        """
        self.model_size = model_size
        self.model = None
        
    def _load_model(self):
        """Lazy-load the Whisper model"""
        if self.model is None:
            logger.info(f"Loading Whisper model: {self.model_size}")
            try:
                self.model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
                logger.info("Model loaded")
            except Exception as e:
                logger.error(f"Model load failed: {str(e)}")
                raise Exception(f"Model load failed: {str(e)}")
    
    async def transcribe(self, audio_path: str, language: Optional[str] = None) -> str:
        """
        Transcribe an audio file
        
        Args:
            audio_path: path to the audio file
            language: explicit language (optional; auto-detected if None)
            
        Returns:
            Transcript text (Markdown format)
        """
        try:
            # Check file existence
            if not os.path.exists(audio_path):
                raise Exception(f"Audio file not found: {audio_path}")
            
            # Load model
            self._load_model()
            
            logger.info(f"Start transcribing audio: {audio_path}")
            
            # Call in a thread to avoid blocking the event loop
            import asyncio
            def _do_transcribe():
                return self.model.transcribe(
                    audio_path,
                    language=language,
                    beam_size=5,
                    best_of=5,
                    temperature=[0.0, 0.2, 0.4],  # temperature ladder
                    # Robust: enable VAD and thresholds to reduce duplicates from silence/noise
                    vad_filter=True,
                    vad_parameters={
                        "min_silence_duration_ms": 900,  # silence detection window
                        "speech_pad_ms": 300  # speech pad
                    },
                    no_speech_threshold=0.7,  # no-speech threshold
                    compression_ratio_threshold=2.3,  # compression ratio threshold
                    log_prob_threshold=-1.0,  # log prob threshold
                    # Avoid error accumulation causing repeating artifacts
                    condition_on_previous_text=False
                )
            segments, info = await asyncio.to_thread(_do_transcribe)
            
            # Build initial paragraph
            texts = []
            for segment in segments:
                t = (segment.text or "").strip()
                if t:
                    texts.append(t)
            paragraph = " ".join(texts)

            # If detected language is Chinese or paragraph contains Chinese characters,
            # re-run in translate mode to produce English
            try:
                lang_code = getattr(info, 'language', None) or ''
            except Exception:
                lang_code = ''
            contains_cjk = bool(re.search(r"[\u4e00-\u9fff]", paragraph))
            if (lang_code.startswith('zh') or lang_code == 'yue' or contains_cjk):
                def _do_translate():
                    return self.model.transcribe(
                        audio_path,
                        language=lang_code or None,
                        task='translate',
                        beam_size=5,
                        best_of=5,
                        temperature=[0.0, 0.2, 0.4],
                        vad_filter=True,
                        vad_parameters={
                            "min_silence_duration_ms": 900,
                            "speech_pad_ms": 300
                        },
                        no_speech_threshold=0.7,
                        compression_ratio_threshold=2.3,
                        log_prob_threshold=-1.0,
                        condition_on_previous_text=False
                    )
                segments_tr, _info_tr = await asyncio.to_thread(_do_translate)
                texts_tr = []
                for seg in segments_tr:
                    tt = (seg.text or "").strip()
                    if tt:
                        texts_tr.append(tt)
                paragraph = " ".join(texts_tr)
            # Sanitize: keep only letters, numbers, punctuation, and spaces; remove asterisks
            cleaned_chars = []
            for ch in paragraph:
                if ch == '*':
                    continue
                cat = unicodedata.category(ch)
                if cat and cat[0] in ('L', 'N', 'P', 'Z'):
                    cleaned_chars.append(ch)
            sanitized = ''.join(cleaned_chars)
            transcript_text = " ".join(sanitized.split())
            logger.info("Transcription completed")
            
            return transcript_text
            
        except Exception as e:
            logger.error(f"Transcription failed: {str(e)}")
            raise Exception(f"Transcription failed: {str(e)}")
