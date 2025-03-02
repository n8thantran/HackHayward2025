import os
from typing import List, Dict, Optional, Tuple, Any
from dotenv import load_dotenv
import uvicorn
import json
import time  # Import the time module for measuring elapsed time
from openai import OpenAI
import requests
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime

load_dotenv()

perplexity_key = os.getenv("perplexity_Key")

client = OpenAI(api_key=perplexity_key, base_url="https://api.perplexity.ai")

# Initialize FastAPI app
app = FastAPI(title="Voice Command API", description="API for processing voice commands")

class CommandResponse(BaseModel):
    status: str
    message: str
    command_text: str
    processed_data: Dict[str, Any]

def prompt_perplexity(task: str) -> Tuple[str, Any]:
    content = """
    You are a classification AI that categorizes user requests into specific types. Your ONLY job is to determine if a request is an email request or a flight request, then extract the relevant information.

    STRICT OUTPUT FORMAT:
    You must respond with a valid JSON object containing exactly these fields:
    {
        "request_type": "email" OR "flight",
        "data": {
            // For email requests only:
            "recipient": "email address",
            "subject": "email subject line",
            "body": "email body content",
            "senders_name": "name of the sender",
            
            // For flight requests only:
            "from_city": "city name",
            "to_city": "city name",
            "departure_date": "date of departure",
            "num_passengers": "number of passengers"
        }
    }

    CLASSIFICATION RULES:
    - Email request: Any request asking to send, compose, or draft an email to someone
    - Flight request: Any request to search for flights or book a flight

    CRITICAL INSTRUCTIONS:
    - Your ENTIRE response must be ONLY the JSON object - no other text
    - Do not include any explanations, notes, or text outside the JSON object
    - Do not include markdown formatting (```json) around the JSON
    - Ensure the JSON is properly formatted with no trailing commas
    - For flight requests, convert city codes (like SFO) to full city names (San Francisco)
    - For num_passengers, convert text numbers ("two") to digits (2)
    """

    messages = [
        {"role": "system", "content": content},
        {"role": "user", "content": task}
    ]

    start_time = time.time()

    try:
        response = client.chat.completions.create(
            model="sonar-reasoning-pro",
            messages=messages
        )

        # End the timer after the response
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"Query time: {elapsed_time:.4f} seconds")
        
        # Parse the response content to extract the JSON
        response_content = response.choices[0].message.content
        print(f"Raw response from Perplexity:\n{response_content}")
        
        try:
            # First try direct JSON parsing
            try:
                parsed_response = json.loads(response_content)
                print("Successfully parsed JSON directly")
            except json.JSONDecodeError:
                # If direct parsing fails, try to extract JSON from text
                print("Direct JSON parsing failed, trying to extract JSON from text")
                json_start = response_content.find('{')
                json_end = response_content.rfind('}') + 1
                
                if json_start >= 0 and json_end > json_start:
                    clean_json = response_content[json_start:json_end]
                    print(f"Extracted JSON:\n{clean_json}")
                    parsed_response = json.loads(clean_json)
                    print("Successfully parsed extracted JSON")
                else:
                    print("No JSON object found in the response")
                    return "unknown", {}
            
            # Validate the response structure
            request_type = parsed_response.get("request_type", "").lower()
            if request_type not in ["email", "flight"]:
                request_type = "unknown"
            
            data = parsed_response.get("data", {})
            
            # Validate data fields based on request type
            if request_type == "email" and not all(k in data for k in ["recipient", "subject", "body"]):
                print("Warning: Email data missing required fields")
            
            if request_type == "flight" and not all(k in data for k in ["from_city", "to_city", "departure_date", "num_passengers"]):
                print("Warning: Flight data missing required fields")
            
            return request_type, data
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON response: {e}")
            print(f"Raw response: {response_content}")
            return "unknown", {}

    except Exception as e:
        print(f"An error occurred: {e}")
        return "error", {"error_message": str(e)}

def handle_request(task: str):
    """
    Handle the user request by classifying it and taking appropriate action
    """
    request_type, data = prompt_perplexity(task)
    
    if request_type == "email":
        # Make a POST request to your email endpoint
        try:
            email_endpoint = "http://localhost:3000/email/send"
            response = requests.post(
                email_endpoint,
                json=data,
                headers={"Content-Type": "application/json"}
            )
            return {
                "status": "success" if response.status_code == 200 else "error",
                "message": "Email sent successfully" if response.status_code == 200 else "Failed to send email",
                "data": data
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error sending email: {str(e)}",
                "data": data
            }
    
    elif request_type == "flight":
        # Make a POST request to your flight search endpoint
        try:
            flight_endpoint = "http://localhost:3000/flight/search"
            response = requests.post(
                flight_endpoint,
                json=data,
                headers={"Content-Type": "application/json"}
            )
            return {
                "status": "success" if response.status_code == 200 else "error",
                "message": "Flight search completed" if response.status_code == 200 else "Failed to search flights",
                "data": data
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error searching flights: {str(e)}",
                "data": data
            }
    else:
        return {
            "status": "error",
            "message": "Unknown request type",
            "data": data
        }

# Run the FastAPI app if this file is executed directly
if __name__ == "__main__":
    import uvicorn
    print("Starting voice command API server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)

@app.post("/voice/command", response_model=CommandResponse)
async def process_voice_command(request: Request):
    """
    Process a voice command from the voice assistant
    
    Extracts the command text from the request JSON and processes it
    using the existing handle_request function.
    """
    # Get the raw JSON data
    data = await request.json()
    
    # Extract just the command text from the complex structure
    try:
        command_text = data["interaction"]["command"]["text"].strip()
        print(f"Received voice command: {command_text}")
    except (KeyError, TypeError) as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid request format. Could not extract command text: {str(e)}"
        )
    
    # Process the command using the existing handle_request function
    result = handle_request(command_text)
    
    # Return a response
    return CommandResponse(
        status=result["status"],
        message=result["message"],
        command_text=command_text,
        processed_data=result["data"]
    )

@app.get("/health")
async def health_check():
    """
    Simple health check endpoint
    """
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "service": "Voice Command API"
    }
