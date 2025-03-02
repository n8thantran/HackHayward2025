from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse
from transcribe import speech_to_text
from sanitization import prompt_perplexity
import os

app = FastAPI()

@app.post("/main")
async def brain(mp3: UploadFile = File(...)):
    mp3_bytes = await mp3.read()

    text = speech_to_text(mp3_bytes)

    sanitized_steps = prompt_perplexity(text)

    url = "http://localhost:3000/task/start"
    payload = {"task": sanitized_steps}
    headers = {"Content-Type": "application/json"}

    return {"final_output": sanitized_steps}