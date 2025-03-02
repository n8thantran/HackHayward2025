import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.environ.get('GROQ_API_KEY'))

def speech_to_text(audio_file):
    with open(audio_file, "rb") as file:
        transcription = client.audio.transcriptions.create(
            file=(audio_file, file.read()),
            model="distil-whisper-large-v3-en",
            language="en",
            temperature=0.6
        )

    return transcription.text
