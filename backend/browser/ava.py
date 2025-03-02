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
    """Execute an email task with multiple agents, each handling a specific step"""
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
        
        # Step 1: Navigate to Gmail and click Compose
        print("Step 1: Navigating to Gmail and clicking Compose")
        navigate_task = """
        Follow these steps exactly:
        1. Navigate to https://mail.google.com/
        2. Wait for the page to fully load
        3. Look for a button with text "Compose" and click it
        4. Wait for the compose window to appear
        """
        
        navigate_agent = Agent(
            task=navigate_task,
            llm=llm,
            browser_context=browser_context
        )
        
        navigate_history = await navigate_agent.run()
        if not navigate_history.is_done():
            error_msg = "Failed to navigate to Gmail and open compose window"
            task_results[task_id] = {"status": "failed", "result": error_msg}
            running_tasks.remove(task_id)
            return error_msg
        
        # Step 2: Enter recipient
        print("Step 2: Entering recipient")
        recipient_task = f"""
        Follow these steps exactly:
        1. Find the input field labeled "To" or "Recipients" in the compose window
        2. Click on this field
        3. Type exactly: {email_details['recipient']}
        4. Press Tab key to confirm
        """
        
        recipient_agent = Agent(
            task=recipient_task,
            llm=llm,
            browser_context=browser_context
        )
        
        recipient_history = await recipient_agent.run()
        if not recipient_history.is_done():
            error_msg = "Failed to enter recipient email address"
            task_results[task_id] = {"status": "failed", "result": error_msg}
            running_tasks.remove(task_id)
            return error_msg
        
        # Step 3: Enter subject
        print("Step 3: Entering subject")
        subject_task = f"""
        Follow these steps exactly:
        1. Find the subject field in the compose window (it should be focused after the previous step)
        2. Type exactly: {email_details['subject']}
        3. Press Tab key to move to the body
        """
        
        subject_agent = Agent(
            task=subject_task,
            llm=llm,
            browser_context=browser_context
        )
        
        subject_history = await subject_agent.run()
        if not subject_history.is_done():
            error_msg = "Failed to enter email subject"
            task_results[task_id] = {"status": "failed", "result": error_msg}
            running_tasks.remove(task_id)
            return error_msg
        
        # Step 4: Enter body and send
        print("Step 4: Entering body and sending email")
        body_send_task = f"""
        Follow these steps exactly:
        1. The email body field should now be focused
        2. Type the following message exactly as written:
        {email_details['body']}
        3. Look for a button labeled "Send" at the bottom of the compose window
        4. Click the Send button
        5. Wait for confirmation that the email was sent
        """
        
        body_send_agent = Agent(
            task=body_send_task,
            llm=llm,
            browser_context=browser_context
        )
        
        body_send_history = await body_send_agent.run()
        if not body_send_history.is_done():
            error_msg = "Failed to enter email body or send email"
            task_results[task_id] = {"status": "failed", "result": error_msg}
            running_tasks.remove(task_id)
            return error_msg
        
        # All steps completed successfully
        success_msg = "Email sent successfully"
        print(success_msg)
        task_results[task_id] = {"status": "completed", "result": success_msg}
        running_tasks.remove(task_id)
        return success_msg
        
    except Exception as e:
        error_msg = f"Error sending email: {str(e)}"
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
