import os
from typing import List, Dict, Optional, Tuple, Any
from dotenv import load_dotenv
import uvicorn
import json
import time  # Import the time module for measuring elapsed time
from openai import OpenAI
import requests

load_dotenv()

perplexity_key = os.getenv("perplexity_Key")

client = OpenAI(api_key=perplexity_key, base_url="https://api.perplexity.ai")

def prompt_perplexity(task: str) -> Tuple[str, Any]:
    content = """
    You are a classification AI that categorizes user requests into specific types. Your ONLY job is to determine if a request is an email request or a task request, then extract the relevant information.

    STRICT OUTPUT FORMAT:
    You must respond with a valid JSON object containing exactly these fields:
    {
        "request_type": "email" OR "task",
        "data": {
            // For email requests only:
            "recipient": "email address",
            "subject": "email subject line",
            //For body, reword the body to be more professional and concise. You need to fill out the fields, dont return a template.
            // My info is, name: oliver
            "body": "email body content"
            
            // For task requests only:
            "description": "full task description"
        }
    }

    CLASSIFICATION RULES:
    - Email request: Any request asking to send, compose, or draft an email to someone
    - Task request: Any request to do something that is not sending an email (like reminders, todos, scheduling, etc.)

    IMPORTANT:
    - Do not include any explanations, notes, or text outside the JSON object
    - Ensure the JSON is properly formatted with no trailing commas
    - If you're unsure about the classification, default to "task"
    - Extract as much detail as possible for the data fields
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
        try:
            # Clean the response in case there's any text before or after the JSON
            json_start = response_content.find('{')
            json_end = response_content.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                clean_json = response_content[json_start:json_end]
                parsed_response = json.loads(clean_json)
                
                # Validate the response structure
                request_type = parsed_response.get("request_type", "").lower()
                if request_type not in ["email", "task"]:
                    request_type = "unknown"
                
                data = parsed_response.get("data", {})
                
                # Validate data fields based on request type
                if request_type == "email" and not all(k in data for k in ["recipient", "subject", "body"]):
                    print("Warning: Email data missing required fields")
                
                if request_type == "task" and "description" not in data:
                    print("Warning: Task data missing description field")
                
                return request_type, data
            else:
                print("No valid JSON found in response")
                return "unknown", {}
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
    
    elif request_type == "task":
        # Handle task logic here
        return {
            "status": "success",
            "message": "Task processed",
            "data": data
        }
    
    else:
        return {
            "status": "error",
            "message": "Unknown request type",
            "data": data
        }

# Example usage
if __name__ == "__main__":
    # Example task
    sample_task = "Please send an email to nathan.tran04@sjsu.edu to meet tomorrow to talk about something important"
    result = handle_request(sample_task)
    print(json.dumps(result, indent=2))
