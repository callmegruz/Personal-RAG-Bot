import os
import uuid
import config

try:
    import speech_recognition as sr
    HAS_SR = True
except Exception as e:
    import traceback
    print("⚠️ Error importing speech_recognition in services/audio.py:")
    traceback.print_exc()
    HAS_SR = False


def transcribe_audio_file(filepath: str) -> str:
    """
    Transcribes audio file locally using standard Whisper tiny model.
    """
    if not HAS_SR:
        raise RuntimeError("Voice recognition dependencies are not available. Please ensure PyTorch and SpeechRecognition are installed.")
        
    r = sr.Recognizer()
    with sr.AudioFile(filepath) as source:
        audio_data = r.record(source)
        
    # Transcribe locally using Whisper tiny model.
    # Explicitly lock transcription to English to prevent language confusion.
    result = r.recognize_whisper(audio_data, model="tiny", language="english")
    return result.strip()
