from fastapi import FastAPI
from sanitization import prompt_perplexity
import os

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.post("/main")
async def brain(prompt: str):

    sanitized_steps = prompt_perplexity(prompt)

    url = "http://localhost:3000/task/start"
    payload = {"task": sanitized_steps}
    headers = {"Content-Type": "application/json"}

    return {"final_output": sanitized_steps}