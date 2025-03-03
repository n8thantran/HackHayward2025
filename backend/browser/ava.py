from browser_use import Agent, Browser, BrowserConfig, Controller
import os
from fastapi.responses import JSONResponse
from fastapi import FastAPI, HTTPException, BackgroundTasks
import uvicorn
from typing import List, Dict, Optional, Union
from pydantic import BaseModel
from langchain_groq import ChatGroq
import asyncio
from dotenv import load_dotenv
import logging
import platform

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

llm = ChatGroq(
    model_name="deepseek-r1-distill-llama-70b-specdec",
    api_key=groq_api_key,
    temperature=0.6
)

def get_browser_path():
    if platform.system() == "Windows":
        return "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    elif platform.system() == "Darwin":
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    elif platform.system() == "Linux":
        return "/usr/bin/google-chrome"
    else:
        raise Exception(f"Unsupported platform: {platform.system()}")

# Settings for browser
config = BrowserConfig(
    headless=False,
    disable_security=True,
    # Use platform-specific Chrome path
    chrome_instance_path=get_browser_path(),  # Let Playwright auto-detect Chrome location
)

# Initialize browser at startup
browser = None
browser_context = None

async def initialize_browser():
    """Initialize the browser if not already initialized"""
    global browser, browser_context
    
    # Initialize browser if needed
    if browser is None:
        print("Initializing browser...")
        try:
            browser = Browser(config=config)
            print("Browser initialized successfully")
        except Exception as e:
            print(f"Failed to initialize browser: {e}")
            # Provide helpful error message about Chrome installation
            print("\nTROUBLESHOOTING:")
            print("1. Make sure Google Chrome is installed on your system")
            print("2. On Windows: Check if Chrome is in 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'")
            print("3. Try running: playwright install chromium")
            raise
    else:
        print("Browser already initialized, reusing existing instance")
    
    # Initialize browser context if needed
    if browser_context is None:
        print("Creating new browser context...")
        browser_context = await browser.new_context()
        print("Browser context created successfully")
    else:
        print("Browser context already exists, reusing existing context")


async def execute_task(task_id: str, task_description: str):
    """Execute a task with the agent"""
    global browser, browser_context, task_results, running_tasks
    
    try:
        running_tasks.add(task_id)
        task_results[task_id] = {"status": "running", "result": None}
        
        # Initialize browser if needed
        if browser is None or browser_context is None:
            await initialize_browser()
        else:
            print(f"Reusing existing browser context for task {task_id}")
        
        # Create and run the agent
        agent = Agent(
            task=task_description,
            llm=llm,
            browser_context=browser_context
        )
        
        # Run with max_steps to prevent infinite loops
        result = await agent.run(max_steps=40)
        
        # Check if the task completed successfully
        if result.is_done():
            task_results[task_id] = {"status": "completed", "result": result}
        else:
            task_results[task_id] = {"status": "failed", "result": "Failed to complete task: " + str(result.errors())}
        
        running_tasks.remove(task_id)
        
        return task_results[task_id]["result"]
    except Exception as e:
        error_msg = f"Error executing task: {str(e)}"
        print(error_msg)
        task_results[task_id] = {"status": "failed", "result": error_msg}
        if task_id in running_tasks:
            running_tasks.remove(task_id)
        return error_msg

async def execute_email_task(task_id: str, email_details: dict):
    """Execute an email task with a single agent and clear instructions"""
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
        
        # Step 1: Navigate and compose
        navigate_compose_task = """
        1. Navigate to gmail.com and wait for the page to fully load
        2. Click the Compose button to start a new email
        """
        
        navigate_agent = Agent(
            task=navigate_compose_task,
            llm=llm,
            browser_context=browser_context
        )
        await navigate_agent.run()
        
        # Step 2: Fill recipient and subject
        recipient_subject_task = f"""
        Complete these steps in order:
        1. Click the 'To' field and type: {email_details['recipient']}
        2. Press Tab to confirm the recipient and move to the Subject field
        3. Type: {email_details['subject']} in the Subject field
        4. wait 1 second
        5. Press Tab to move to the email body
        6. Type: {email_details['body']} in the email body
        7. wait 1 second
        8. Press Tab to move to the Send button
        9. Press Enter to send the email
        """
        
        email_agent = Agent(
            task=recipient_subject_task,
            llm=llm,
            browser_context=browser_context
        )
        await email_agent.run()
        
        # Update task status
        task_results[task_id] = {"status": "completed", "result": "Email sent successfully"}
        running_tasks.remove(task_id)
        
        return "Email sent successfully"
    except Exception as e:
        error_msg = f"Error sending email: {str(e)}"
        print(error_msg)
        task_results[task_id] = {"status": "failed", "result": error_msg}
        if task_id in running_tasks:
            running_tasks.remove(task_id)
        raise e


class EmailRequest(BaseModel):
    recipient: str
    subject: str
    body: str
    senders_name: str
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

class FlightSearchRequest(BaseModel):
    from_city: str
    to_city: str
    departure_date: str
    num_passengers: int

async def execute_flight_search_task(task_id: str, flight_details: dict):
    """Execute a flight search task using an agent"""
    global browser, browser_context, task_results, running_tasks

    try:
        running_tasks.add(task_id)
        task_results[task_id] = {"status": "running", "result": None}
        logger.info(f"Starting flight search task {task_id}")

        # Initialize browser if needed
        if browser is None or browser_context is None:
            await initialize_browser()
        else:
            logger.info(f"Reusing existing browser context for flight search task {task_id}")

        # Validate required fields
        required_fields = ["from_city", "to_city", "departure_date", "num_passengers"]
        missing_fields = [field for field in required_fields if field not in flight_details or not flight_details[field]]

        if missing_fields:
            error_msg = f"Missing required flight search fields: {', '.join(missing_fields)}"
            task_results[task_id] = {"status": "failed", "result": error_msg}
            running_tasks.remove(task_id)
            return error_msg

        # Create a single comprehensive flight search task
        comprehensive_flight_task = f"""
        DIRECT INSTRUCTION: NAVIGATE TO KAYAK.COM - NOT GOOGLE FLIGHTS
        
        GLOBAL TEXT INPUT RULE:
        - After typing ANY text in ANY field (origin, destination, dates, etc.)
        - ALWAYS press the Enter key immediately after typing
        - Wait 2 seconds to see if a suggestion dropdown appears
        - If it does, the Enter key will select the top suggestion
        - This applies to ALL text fields without exception
        
        Complete these exact steps in order:
        
        STEP 1: Open a new browser window and type "https://www.kayak.com/flights" in the address bar
        - DO NOT search for "Google Flights" or go to Google
        - Type the FULL URL: https://www.kayak.com/flights
        - Press Enter and wait for Kayak to load
        - Verify the URL contains "kayak.com" - if it shows "google.com", you are on the WRONG site
        - Close any popups or cookie notices
        
        STEP 2: Search for a flight with these details:
        - From: {flight_details['from_city']}
          * Click on the origin field
          * Type the city name SLOWLY
          * Press Enter immediately after typing
          * Wait 2 seconds to see if a suggestion is selected
        
        - To: {flight_details['to_city']} 
          * Click on the destination field
          * Type the city name SLOWLY 
          * Press Enter immediately after typing
          * Wait 2 seconds to see if a suggestion is selected
        
        - Date: {flight_details['departure_date']}
          * Click on the date field
          * Type or select the date
          * If typing, press Enter after entering
        
        - Passengers: {flight_details['num_passengers']}
          * Adjust the passenger count as needed
        
        - Click the search button
        
        STEP 3: Review flight results on Kayak
        - Wait for search results to load completely
        - Identify the top 3 flight options
        
        STEP 4: Select the first (or best value) flight option
        - Click on the "View Deal", "Select", or similar button
        - You may be redirected to a booking page (either on Kayak or a partner site)
        - If redirected away from Kayak, that's okay as long as you're proceeding to booking
        
        STEP 5: Proceed to checkout/payment page
        - Fill out any required passenger information if prompted
        - For ANY text field (including name, address, phone):
          * Click the field
          * Type the required information SLOWLY
          * Press Enter key immediately after typing
          * Wait 2 seconds to see if the input is accepted
        
        - If asked for an email address:
          * Click the email field
          * Type the email carefully
          * Press Enter key immediately after typing
          * Wait 3 seconds to see if the field validates
          * Look for any validation messages or color changes
        
        - Continue until you reach the payment information page
        - STOP when you reach the payment/checkout page
        - DO NOT enter any payment information
        
        IMPORTANT REMINDERS:
        - After EVERY action, check if you're on Kayak or a legitimate booking site
        - If you find yourself on Google Flights, go back and type "https://www.kayak.com/flights"
        - NEVER enter payment information or complete a purchase
        - Stop at the checkout page where payment would normally be entered
        
        TEXT INPUT TROUBLESHOOTING:
        - If pressing Enter causes unexpected behavior, try Tab key instead
        - If a dropdown appears but Enter doesn't select an option, try clicking the option directly
        - If a field turns red after pressing Enter, the input may be invalid - check and retry
        - Some fields may require Tab to move to the next field instead of Enter - adjust accordingly
        - Always verify your input was accepted before moving to the next field
        
        FINAL REPORT:
        - Describe the flight you selected (airline, times, price)
        - Confirm you reached the checkout/payment page
        - List what information would be needed to complete the booking (but do not enter it)
        """

        # Create a single agent for the entire flight search process
        logger.info(f"Creating flight search agent for task {task_id}")
        flight_agent = Agent(
            task=comprehensive_flight_task,
            llm=llm,
            browser_context=browser_context
        )

        # Run the agent
        logger.info(f"Running flight search for task {task_id}")
        try:
            result = await flight_agent.run(max_steps=40)
            logger.info(f"Flight search agent run completed for task {task_id}")
        except Exception as e:
            logger.error(f"Error during flight search agent run: {str(e)}")
            raise

        # Check if the task completed successfully
        if hasattr(result, 'is_done') and result.is_done():
            task_results[task_id] = {"status": "completed", "result": "Flight search completed successfully"}
        else:
            task_results[task_id] = {"status": "failed", "result": "Failed to complete flight search: " + str(result.errors())}

        running_tasks.remove(task_id)
        return task_results[task_id]["result"]

    except Exception as e:
        error_msg = f"Error searching for flights: {str(e)}"
        logger.error(error_msg)
        task_results[task_id] = {"status": "failed", "result": error_msg}
        if task_id in running_tasks:
            running_tasks.remove(task_id)
        return error_msg

@app.post("/flight/search", response_model=TaskResponse)
async def search_flight(flight_request: FlightSearchRequest, background_tasks: BackgroundTasks):
    """Search for flights using Kayak"""
    task_id = f"flight_{len(task_results) + 1}"
    
    flight_details = {
        "from_city": flight_request.from_city,
        "to_city": flight_request.to_city,
        "departure_date": flight_request.departure_date,
        "num_passengers": flight_request.num_passengers
    }
    
    background_tasks.add_task(execute_flight_search_task, task_id, flight_details)
    return TaskResponse(task_id=task_id, status="started")

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
