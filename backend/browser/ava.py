from langchain_groq import ChatGroq
from browser_use import Agent, Browser, BrowserConfig, Controller
import os
from fastapi.responses import JSONResponse
from fastapi import FastAPI, HTTPException, BackgroundTasks
import uvicorn
from typing import List, Dict, Optional
from pydantic import BaseModel
import asyncio
from dotenv import load_dotenv

load_dotenv()

groq_api_key = os.getenv("GROQ_API_KEY")

app = FastAPI(title="Browser Use API", description="API for using the Browser Use library")

#global variables
browser = None
browser_context = None
task_results = {}
running_tasks = set()

class TaskRequest(BaseModel):
    task: str
    
class TaskResponse(BaseModel):
    task_id: str
    status: str
    
class TaskResult(BaseModel):
    task_id: str
    result: Optional[str] = None
    status: str


groq_api_key = os.getenv("GROQ_API_KEY")
llm = ChatGroq(
    model_name="deepseek-r1-distill-llama-70b",
    api_key=groq_api_key,
    temperature=0.3
)


#Settings for browser
config = BrowserConfig(
    headless=False,
    disable_security=True,
    chrome_instance_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)

# Initialize browser at startup
browser = None
browser_context = None

async def initialize_browser():
    """Initialize the browser if not already initialized"""
    global browser, browser_context
    if browser is None:
        print("Initializing browser...")
        browser = Browser(config=config)
        browser_context = await browser.new_context()
        print("Browser initialized successfully")
    else:
        print("Browser already initialized, reusing existing instance")


async def execute_task(task_id: str, task_description: str):
    """Execute a task with the agent"""
    global browser_context, task_results, running_tasks
    
    try:
        running_tasks.add(task_id)
        task_results[task_id] = {"status": "running", "result": None}
        
        # Initialize browser if needed
        if browser_context is None:
            await initialize_browser()
        else:
            print(f"Reusing existing browser context for task {task_id}")
        
        # Create and run the agent
        agent = Agent(
            task=task_description,
            llm=llm,
            browser_context=browser_context
        )
        
        result = await agent.run()
        
        # Update task status
        task_results[task_id] = {"status": "completed", "result": result}
        running_tasks.remove(task_id)
        
        return result
    except Exception as e:
        task_results[task_id] = {"status": "failed", "result": str(e)}
        if task_id in running_tasks:
            running_tasks.remove(task_id)
        raise e

async def execute_email_task(task_id: str, email_details: dict):
    """Execute an email task with a single agent handling the entire process"""
    global browser_context, task_results, running_tasks
    
    try:
        running_tasks.add(task_id)
        task_results[task_id] = {"status": "running", "result": None}
        
        # Initialize browser if needed
        if browser_context is None:
            await initialize_browser()
        else:
            print(f"Reusing existing browser context for email task {task_id}")
        
        # Validate email details
        required_fields = ["recipient", "subject", "body"]
        missing_fields = [field for field in required_fields if field not in email_details or not email_details[field]]
        
        if missing_fields:
            error_msg = f"Missing required email fields: {', '.join(missing_fields)}"
            task_results[task_id] = {"status": "failed", "result": error_msg}
            running_tasks.remove(task_id)
            return error_msg
        
        # Create a comprehensive task for the entire email process
        print("Executing complete email task with a single agent")
        complete_email_task = f"""
        Your task is to send an email through Gmail. Follow these steps exactly in sequence, completing each step before moving to the next:
        
        STEP 1: NAVIGATE TO GMAIL
        1.1. Navigate to https://mail.google.com/
            - Type the URL in the address bar and press Enter
            - Wait at least 5 seconds for the page to start loading
        
        1.2. Check for login page:
            - If you see a login page with fields for email/password, stop and report: "Gmail requires login. Please log in manually first."
            - If you see a "Choose an account" page, stop and report: "Gmail requires account selection. Please select an account manually first."
            - If you're already logged in, proceed to the next step
        
        1.3. Wait for Gmail to fully load:
            - Look for the Gmail logo in the top-left corner
            - Wait for the inbox to appear with email messages
            - Wait for all loading indicators to disappear
            - Wait at least 10 seconds total to ensure complete loading
        
        STEP 2: COMPOSE NEW EMAIL
        2.1. Find and click the Compose button:
            - Look for a button labeled "Compose" in the left sidebar
            - It may also have a pencil icon or a "+" symbol
            - The button is typically near the top of the left sidebar
            - If you don't see it immediately, scroll the sidebar to find it
            - Click directly on the "Compose" button
        
        2.2. Verify the compose window appears:
            - Wait at least 3 seconds for the compose window to open
            - Look for a popup window with "New Message" or similar text at the top
            - Confirm you can see fields for recipient (To:), subject, and message body
            - If the compose window doesn't appear within 10 seconds, try clicking Compose again
        
        STEP 3: ENTER RECIPIENT
        3.1. Find the recipient field:
            - Look for the field labeled "To" or "Recipients" at the top of the compose window
            - Click on this field to focus it
            - Wait 1 second to ensure the field is active
        
        3.2. Enter the recipient email address:
            - Type exactly: {email_details['recipient']}
            - After typing, wait 1 second
            - Press Enter key to confirm
            - Wait 2 seconds before moving to the next step
        
        STEP 4: ENTER SUBJECT
        4.1. Enter the subject:
            - Click on the subject field
            - Type exactly: {email_details['subject']}
            - After typing, wait 1 second
            - Press Tab key to move to the body field
            - Wait 1 second to ensure focus has moved to the body field
        
        STEP 5: ENTER EMAIL BODY
        5.1. Verify you are in the email body field:
            - Confirm the cursor is in the large text area below the subject field
            - If not, click directly in the body area
        
        5.2. Enter the email body:
            - Type the following message exactly as written:
            {email_details['body']}
            - After typing, wait 2 seconds to ensure all text has been entered
        
        STEP 6: SEND THE EMAIL
        6.1. Find the Send button:
            - Look for a button labeled "Send" at the bottom of the compose window
            - It's typically a blue button with white text
            - If you don't see it, look for a paper airplane icon
        
        6.2. Click the Send button:
            - Click directly on the Send button
            - Wait at least 5 seconds for the email to be sent
        
        STEP 7: REPORT RESULTS
        7.1. If all steps completed successfully:
            - Report: "Email sent successfully to {email_details['recipient']} with subject '{email_details['subject']}'"
        
        7.2. If any step failed:
            - Report exactly which step failed (e.g., "Failed at step 3.2")
            - Describe what you observed that indicates failure
            - Provide any error messages you saw
        
        Be very thorough and patient with each step. Take your time to ensure each action completes fully before moving to the next step. If you encounter any unexpected situations, describe them in detail.
        """
        
        # Create a single agent with increased timeout and iterations
        email_agent = Agent(
            task=complete_email_task,
            llm=llm,
            browser_context=browser_context,
        )
        
        # Run the agent
        print(f"Starting email agent for task {task_id}")
        result = await email_agent.run()
        
        # Process the result
        if result and result.is_done():
            final_result = result.final_result() or "Email task completed"
            print(f"Email task {task_id} completed: {final_result}")
            task_results[task_id] = {"status": "completed", "result": final_result}
        else:
            # Extract error information
            error_details = result.errors() if result else []
            error_msg = "Email task failed or incomplete"
            detailed_error = f"{error_msg}. Details: {'; '.join(error_details)}" if error_details else error_msg
            print(f"Email task {task_id} failed: {detailed_error}")
            task_results[task_id] = {"status": "failed", "result": detailed_error}
        
        running_tasks.remove(task_id)
        return task_results[task_id]["result"]
        
    except Exception as e:
        error_msg = f"Error executing email task: {str(e)}"
        print(error_msg)
        task_results[task_id] = {"status": "failed", "result": error_msg}
        if task_id in running_tasks:
            running_tasks.remove(task_id)
        return error_msg

class EmailRequest(BaseModel):
    recipient: str
    subject: str
    body: str

@app.on_event("startup")
async def startup_event():
    # Initialize on startup
    await initialize_browser()

@app.on_event("shutdown")
async def shutdown_event():
    # Close browser on shutdown
    global browser
    if browser:
        await browser.close()

@app.post("/task/start", response_model=TaskResponse)
async def start_task(task_request: TaskRequest, background_tasks: BackgroundTasks):
    """Start the initial task"""
    task_id = f"task_{len(task_results) + 1}"
    background_tasks.add_task(execute_task, task_id, task_request.task)
    return TaskResponse(task_id=task_id, status="started")

@app.post("/task/{task_id}/add", response_model=TaskResponse)
async def add_task(task_id: str, task_request: TaskRequest, background_tasks: BackgroundTasks):
    """Add a new task that will run after the specified task"""
    if task_id not in task_results:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    # Wait until the previous task is completed before starting this one
    async def wait_and_execute():
        while task_id in running_tasks or task_results[task_id]["status"] == "running":
            await asyncio.sleep(1)
        
        # If the previous task failed, don't execute the next one
        if task_results[task_id]["status"] == "failed":
            new_task_id = f"task_{len(task_results) + 1}"
            task_results[new_task_id] = {
                "status": "failed", 
                "result": f"Previous task {task_id} failed, so this task was not executed"
            }
            return
        
        # Execute the new task
        new_task_id = f"task_{len(task_results) + 1}"
        await execute_task(new_task_id, task_request.task)
    
    new_task_id = f"task_{len(task_results) + 1}"
    background_tasks.add_task(wait_and_execute)
    return TaskResponse(task_id=new_task_id, status="queued")

@app.post("/email/send", response_model=TaskResponse)
async def send_email(email_request: EmailRequest, background_tasks: BackgroundTasks):
    """Send an email using Gmail"""
    task_id = f"email_{len(task_results) + 1}"
    
    email_details = {
        "recipient": email_request.recipient,
        "subject": email_request.subject,
        "body": email_request.body
    }
    
    background_tasks.add_task(execute_email_task, task_id, email_details)
    return TaskResponse(task_id=task_id, status="started")

@app.get("/task/{task_id}", response_model=TaskResult)
async def get_task_result(task_id: str):
    """Get the result of a task"""
    if task_id not in task_results:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    return TaskResult(
        task_id=task_id,
        result=task_results[task_id]["result"],
        status=task_results[task_id]["status"]
    )

@app.get("/tasks", response_model=Dict[str, TaskResult])
async def get_all_tasks():
    """Get all tasks and their results"""
    return {
        task_id: TaskResult(
            task_id=task_id,
            result=task_data["result"],
            status=task_data["status"]
        ) 
        for task_id, task_data in task_results.items()
    }

if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=3000)
