import pygame
import pygame.locals as pgl
import os
import moderngl
import numpy as np
from pyrr import Matrix44
import gltf_loader
import ctypes
from ctypes import wintypes
import time
import threading
import math
import random
import requests
import json

# Add ElevenLabs imports for text-to-speech
try:
    from dotenv import load_dotenv
    from elevenlabs.client import ElevenLabs
    from elevenlabs import play
    import os
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Check if ElevenLabs API key is available
    if os.getenv("ELEVENLABS_API_KEY"):
        TTS_AVAILABLE = True
    else:
        print("WARNING: ELEVENLABS_API_KEY environment variable not found.")
        print("Create a .env file with your ELEVENLABS_API_KEY or set it in the environment.")
        TTS_AVAILABLE = False
except ImportError as e:
    print(f"WARNING: ElevenLabs TTS module could not be imported: {e}")
    print("The application will run without voice output features.")
    print("Install required packages with: pip install python-dotenv elevenlabs")
    TTS_AVAILABLE = False

# Make imports more reliable with better error handling
try:
    from voice_recognition import VoiceRecognizer, VOICE_RECOGNITION_AVAILABLE
except ImportError as e:
    print(f"WARNING: Voice recognition module could not be imported: {e}")
    print("The application will run without voice activation features.")
    print("Install required packages with: pip install -r requirements.txt")
    VOICE_RECOGNITION_AVAILABLE = False

# Initialize pygame
pygame.init()

# Initialize font system for text rendering
pygame.font.init()

# Configure a borderless window
WIDTH, HEIGHT = 800, 600
os.environ['SDL_VIDEO_WINDOW_POS'] = "0,0"
pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
pygame.display.gl_set_attribute(pygame.GL_CONTEXT_FORWARD_COMPATIBLE_FLAG, True)
pygame.display.gl_set_attribute(pygame.GL_ALPHA_SIZE, 8)  # Request 8 bits for alpha channel

# Create a borderless window
flags = pygame.DOUBLEBUF | pygame.OPENGL | pygame.NOFRAME
screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
pygame.display.set_caption("TokoVT Model Viewer")

# Windows-specific transparency and window style setup
hwnd = pygame.display.get_wm_info()["window"]
user32 = ctypes.WinDLL("user32")

# Configure function argument types and return types
user32.SetWindowLongW.restype = wintypes.LONG
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]

user32.GetWindowLongW.restype = wintypes.LONG
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]

user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD]

user32.SetWindowPos.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, 
                              ctypes.c_int, ctypes.c_int, wintypes.UINT]

user32.ShowWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]

user32.UpdateWindow.restype = wintypes.BOOL
user32.UpdateWindow.argtypes = [wintypes.HWND]

# Define constants for window styling
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020  # Click-through capability
WS_EX_TOPMOST = 0x00000008      # Always on top flag
WS_EX_NOACTIVATE = 0x08000000   # Prevent activation
LWA_COLORKEY = 0x00000001

# Constants for window positioning
HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_FRAMECHANGED = 0x0020

# We'll use pure black as our background color (this will be transparent due to colorkey)
BACKGROUND_COLOR = (0.0, 0.0, 0.0, 1.0)

# Set up the window with transparency and always-on-top
def setup_window():
    # Get current window style
    ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    
    # Set new window style with layered window, transparency, and topmost
    new_ex_style = ex_style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex_style)
    
    # Set the transparent color key (black)
    user32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_COLORKEY)
    
    # Set the window position to topmost
    user32.SetWindowPos(
        hwnd,
        HWND_TOPMOST,
        0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW | SWP_FRAMECHANGED
    )
    
    # Ensure the window is visible
    user32.ShowWindow(hwnd, 5)  # SW_SHOW = 5
    user32.UpdateWindow(hwnd)

# Call the window setup function
setup_window()

# Function to keep the window always on top
def keep_window_topmost():
    while True:
        # Force the window to stay on top periodically
        user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST,
            0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        )
        time.sleep(0.1)  # Check every 100ms

# Start the always-on-top enforcement thread
topmost_thread = threading.Thread(target=keep_window_topmost, daemon=True)
topmost_thread.start()

# Set up ModernGL context
ctx = moderngl.create_context()
ctx.enable(moderngl.DEPTH_TEST)
ctx.enable(moderngl.CULL_FACE)
ctx.enable(moderngl.BLEND)
ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

# Set up the TTS client
def initialize_tts():
    if not TTS_AVAILABLE:
        return None
        
    # Try to initialize ElevenLabs client with API key
    try:
        # Initialize ElevenLabs client
        tts_client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
        
        # Test the connection
        print("ElevenLabs TTS initialized successfully.")
        return tts_client
            
    except Exception as e:
        print(f"Failed to initialize ElevenLabs TTS: {e}")
        return None

# Global flag to track if TTS is currently speaking
is_speaking = False

# Function to play text using TTS
def speak_text(tts_client, text, voice_id="FGY2WhTYpPnrIDTdsKH5"):
    """Generate speech from text and play it using ElevenLabs TTS"""
    global is_speaking
    
    if not TTS_AVAILABLE or not tts_client:
        return
    
    # If already speaking, wait before starting new speech
    if is_speaking:
        print(f"TTS is busy, queuing: '{text}'")
        
        # Define a function to wait and then speak
        def delayed_speak():
            global is_speaking
            # Wait for current speech to finish
            while is_speaking:
                time.sleep(0.1)
            # Now start the new speech
            speak_text(tts_client, text, voice_id)
        
        # Start a thread to handle the delayed speech
        delay_thread = threading.Thread(target=delayed_speak, daemon=True)
        delay_thread.start()
        return delay_thread
        
    # Define a function to be run in a separate thread
    def tts_thread_func():
        global is_speaking
        try:
            # Set speaking flag
            is_speaking = True
            
            # Print debug info
            print(f"Speaking: '{text}'")
            
            # Request speech from ElevenLabs
            audio_data = tts_client.text_to_speech.convert(
                text=text,
                voice_id=voice_id,
                model_id="eleven_turbo_v2",
                output_format="mp3_44100_128",
            )
            
            # Play audio using elevenlabs play function (handles playback automatically)
            play(audio_data)
            
        except Exception as e:
            print(f"Error in TTS playback: {e}")
        finally:
            # Clear speaking flag when done
            is_speaking = False
    
    # Start TTS in a separate thread to avoid blocking the main thread
    tts_thread = threading.Thread(target=tts_thread_func, daemon=True)
    tts_thread.start()
    
    return tts_thread

# Add this function before the main function
def generate_response(command):
    """Generate a confirmation response based on the user's command"""
    command = command.lower()
    
    # Check for email requests
    if "email" in command or "send" in command and ("message" in command or "to" in command):
        # Extract recipient using simple text parsing
        recipient = None
        if "to" in command:
            parts = command.split("to", 1)
            if len(parts) > 1:
                to_part = parts[1].strip()
                # Look for the recipient (assume it's the first few words after "to")
                recipient_words = to_part.split()
                if recipient_words:
                    # If recipient has multiple words, try to find where it ends
                    if len(recipient_words) > 1:
                        # Assume recipient ends at common transition words
                        end_markers = ["saying", "about", "regarding", "with", "subject", "that", "and", "telling"]
                        recipient_end = len(recipient_words)
                        
                        for i, word in enumerate(recipient_words):
                            if i > 0 and (word in end_markers or ":" in word):
                                recipient_end = i
                                break
                        
                        recipient = " ".join(recipient_words[:recipient_end])
                    else:
                        recipient = recipient_words[0]
        
        # Extract subject if mentioned
        subject = None
        subject_indicators = ["about", "regarding", "subject", "titled", "with subject"]
        
        for indicator in subject_indicators:
            if indicator in command:
                indicator_parts = command.split(indicator, 1)
                if len(indicator_parts) > 1:
                    subject_part = indicator_parts[1].strip()
                    # Look for the end of the subject (until next transition)
                    end_markers = ["saying", "that", "containing", "with text", "with message", "with content", "body"]
                    
                    for marker in end_markers:
                        if marker in subject_part:
                            subject = subject_part.split(marker, 1)[0].strip()
                            break
                    
                    # If no end marker found, take a reasonable number of words
                    if not subject:
                        subject_words = subject_part.split()
                        subject = " ".join(subject_words[:min(6, len(subject_words))])
                    
                    break
        
        # Extract message content if available
        content = None
        content_indicators = ["saying", "that says", "containing", "with text", "with message", "with content", "body", "message"]
        
        for indicator in content_indicators:
            if indicator in command:
                content_parts = command.split(indicator, 1)
                if len(content_parts) > 1:
                    content = content_parts[1].strip()
                    # Clean up the content (remove transition words, quotes)
                    content = content.strip('"\'')
                    if content.startswith("that "):
                        content = content[5:]
                    if content.startswith("is "):
                        content = content[3:]
                    break
        
        # Build response with available information
        if recipient:
            response = f"I'll send an email to {recipient}"
            if subject:
                response += f" with subject '{subject}'"
            if content:
                # Truncate long content for the response
                display_content = content if len(content) < 30 else content[:27] + "..."
                response += f" saying '{display_content}'"
            return response + ". Does this sound correct?"
        else:
            return "I can send an email for you. Who would you like to send it to?"
    
    # Check for booking flights
    elif "book" in command and "flight" in command:
        # Extract destination using simple text parsing
        destination = None
        for word in ["to", "for"]:
            if word in command:
                parts = command.split(word, 1)
                if len(parts) > 1:
                    destination_part = parts[1].strip()
                    destination_words = destination_part.split()
                    if destination_words:
                        destination = destination_words[0]
                        break
        
        # Extract date if present
        date = None
        date_indicators = ["on", "for"]
        months = ["january", "february", "march", "april", "may", "june", "july", 
                 "august", "september", "october", "november", "december"]
        
        for indicator in date_indicators:
            if indicator in command:
                after_indicator = command.split(indicator, 1)[1].strip()
                # Look for a month name
                for month in months:
                    if month in after_indicator:
                        month_index = after_indicator.find(month)
                        # Try to find a number near the month
                        number_found = False
                        for i in range(max(0, month_index - 20), min(len(after_indicator), month_index + 20)):
                            if after_indicator[i:i+2].isdigit():
                                date = f"{after_indicator[i:i+2]} {month}"
                                number_found = True
                                break
                        if not number_found and month in after_indicator:
                            date = month
                        break
        
        if destination:
            if date:
                return f"Okay, I'll book you a flight to {destination} for {date}. Does this sound correct?"
            else:
                return f"Okay, I'll book you a flight to {destination}. Does this sound correct?"
    
    # Check for search requests
    elif "search" in command or "look up" in command or "find" in command:
        # Extract what to search for
        search_term = command.replace("search", "").replace("look up", "").replace("find", "").strip()
        if search_term:
            return f"I'll search for {search_term}. Would you like me to proceed?"
    
    # Handle weather requests
    elif "weather" in command:
        location = None
        if "in" in command:
            location = command.split("in", 1)[1].strip()
        
        if location:
            return f"I'll check the weather in {location}. Is that right?"
        else:
            return "I'll check the current weather for your location. Shall I proceed?"
    
    # Generic response for other commands
    else:
        return f"I heard: {command}. Would you like me to proceed with this request?"

# Add this function to process confirmations
def process_confirmation(voice_recognizer, command, is_confirmed):
    """Process the confirmation response from the user"""
    if is_confirmed:
        print(f"Confirmed! Processing command: {command}")
        
        # Check if the API server is available
        def check_api_health():
            try:
                health_url = "http://localhost:8000/health"
                print(f"[DEBUG] Checking API health at: {health_url}")
                health_response = requests.get(health_url, timeout=2)
                print(f"[DEBUG] Health check response status: {health_response.status_code}")
                print(f"[DEBUG] Health check response body: {health_response.text[:100]}")
                if health_response.status_code == 200:
                    print("API server is available")
                    return True
                else:
                    print(f"API server is not available: {health_response.status_code}")
                    return False
            except Exception as e:
                print(f"Error checking API health: {e}")
                print(f"[DEBUG] Exception type: {type(e).__name__}")
                return False
        
        # Check health first
        print("[DEBUG] Starting API health check...")
        api_available = check_api_health()
        print(f"[DEBUG] API available: {api_available}")
        if not api_available:
            return "I'm sorry, I can't process your request right now. The backend service appears to be offline."
        
        # Here we would make the actual API call to process the command
        try:
            # Check if this is an email request
            if "email" in command.lower() or ("send" in command.lower() and ("message" in command.lower() or "to" in command.lower())):
                # Extract email details
                recipient = None
                subject = None
                content = None
                
                # Basic extraction for demonstration - in real use, this would be more robust
                command_lower = command.lower()
                
                # Extract recipient
                if "to" in command_lower:
                    to_parts = command_lower.split("to", 1)
                    if len(to_parts) > 1:
                        recipient_part = to_parts[1].strip()
                        recipient_end = recipient_part.find(" about ")
                        if recipient_end == -1:
                            recipient_end = recipient_part.find(" saying ")
                        if recipient_end == -1:
                            recipient_end = recipient_part.find(" with ")
                        if recipient_end == -1:
                            recipient_end = len(recipient_part)
                        
                        recipient = recipient_part[:recipient_end].strip()
                
                # Extract subject
                if "about" in command_lower or "subject" in command_lower:
                    subject_indicator = "about" if "about" in command_lower else "subject"
                    subject_parts = command_lower.split(subject_indicator, 1)
                    if len(subject_parts) > 1:
                        subject_part = subject_parts[1].strip()
                        subject_end = subject_part.find(" saying ")
                        if subject_end == -1:
                            subject_end = subject_part.find(" containing ")
                        if subject_end == -1:
                            subject_end = len(subject_part)
                        
                        subject = subject_part[:subject_end].strip()
                
                # Extract content
                content_indicators = ["saying", "containing", "with message", "that says"]
                for indicator in content_indicators:
                    if indicator in command_lower:
                        content_parts = command_lower.split(indicator, 1)
                        if len(content_parts) > 1:
                            content = content_parts[1].strip()
                            break
                
                # Basic email validation
                if not recipient:
                    return "I couldn't determine who to send the email to. Can you try again with a clear recipient?"
                
                # Prepare the email payload
                email_payload = {
                    "type": "email",
                    "recipient": recipient,
                    "subject": subject or "No subject",
                    "content": content or "",
                    "timestamp": time.time()
                }
                
                # Send to API endpoint
                api_url = "http://localhost:8000/api/email"  # Updated endpoint
                print(f"[DEBUG] Sending email request to: {api_url}")
                print(f"[DEBUG] Email payload: {email_payload}")
                
                # Make the request in a non-blocking way
                def send_email_request():
                    try:
                        print(f"Sending email request: {email_payload}")
                        print(f"[DEBUG] Email API URL: {api_url}")
                        response = requests.post(
                            api_url,
                            json=email_payload,
                            headers={"Content-Type": "application/json"},
                            timeout=5
                        )
                        
                        print(f"[DEBUG] Email API response status: {response.status_code}")
                        print(f"[DEBUG] Email API response headers: {response.headers}")
                        
                        try:
                            print(f"[DEBUG] Email API response body: {response.text[:200]}")
                        except Exception as text_err:
                            print(f"[DEBUG] Could not get response text: {text_err}")
                        
                        if response.status_code == 200:
                            print(f"Email sent successfully: {response.json()}")
                        else:
                            print(f"Email API request failed: {response.status_code}")
                    except Exception as e:
                        print(f"Error sending email request: {e}")
                        print(f"[DEBUG] Exception type: {type(e).__name__}")
                
                # Start the request in a separate thread
                threading.Thread(target=send_email_request, daemon=True).start()
                
                return f"I'm sending your email to {recipient} now."
            
            # For other types of commands (flight booking, weather, etc.)
            else:
                # Prepare the JSON payload in the format expected by the backend
                api_url = "http://localhost:8000/command"  # Updated to use /command directly
                print(f"[DEBUG] Command API URL: {api_url}")
                
                # Format the payload as expected by the backend
                payload = {
                    "interaction": {
                        "command": {
                            "text": command
                        }
                    },
                    "timestamp": time.time(),
                    "confirmed": True
                }
                
                print(f"[DEBUG] Command payload: {payload}")
                print(f"[DEBUG] Formatted JSON payload: {json.dumps(payload, indent=2)}")
                print(f"[DEBUG] Request will be sent to {api_url} with content-type: application/json")
                
                # Make the request in a non-blocking way
                def make_api_request():
                    try:
                        print(f"[DEBUG] Sending command request to {api_url}")
                        print(f"[DEBUG] Payload: {json.dumps(payload, indent=2)}")
                        print(f"[DEBUG] *** STARTING POST REQUEST to {api_url} at {time.strftime('%H:%M:%S')} ***")
                        response = requests.post(
                            api_url,
                            json=payload,
                            headers={"Content-Type": "application/json"},
                            timeout=5
                        )
                        print(f"[DEBUG] *** POST REQUEST COMPLETED at {time.strftime('%H:%M:%S')} ***")
                        
                        print(f"[DEBUG] Command API response status: {response.status_code}")
                        print(f"[DEBUG] Command API response headers: {response.headers}")
                        
                        try:
                            print(f"[DEBUG] Command API response body: {response.text[:200]}")
                        except Exception as text_err:
                            print(f"[DEBUG] Could not get response text: {text_err}")
                        
                        if response.status_code == 200:
                            print(f"Command processed successfully: {response.json()}")
                            # Here you could update the UI with the response
                        else:
                            print(f"API request failed with status code {response.status_code}, trying fallback endpoint")
                            # Try the fallback endpoint
                            fallback_url = "http://localhost:8000/voice/command"  # Try the /voice/command as fallback
                            print(f"[DEBUG] Trying fallback URL: {fallback_url}")
                            try:
                                print(f"[DEBUG] Sending to fallback with payload: {json.dumps(payload, indent=2)}")
                                print(f"[DEBUG] *** STARTING FALLBACK POST REQUEST to {fallback_url} at {time.strftime('%H:%M:%S')} ***")
                                fallback_response = requests.post(
                                    fallback_url,
                                    json=payload,
                                    headers={"Content-Type": "application/json"},
                                    timeout=5
                                )
                                print(f"[DEBUG] *** FALLBACK POST REQUEST COMPLETED at {time.strftime('%H:%M:%S')} ***")
                                
                                print(f"[DEBUG] Fallback response status: {fallback_response.status_code}")
                                print(f"[DEBUG] Fallback response headers: {fallback_response.headers}")
                                
                                try:
                                    print(f"[DEBUG] Fallback response body: {fallback_response.text[:200]}")
                                except Exception as text_err:
                                    print(f"[DEBUG] Could not get fallback response text: {text_err}")
                                
                                if fallback_response.status_code == 200:
                                    print(f"Command processed successfully with fallback: {fallback_response.json()}")
                                else:
                                    print(f"Fallback API request also failed: {fallback_response.status_code}")
                            except Exception as e:
                                print(f"Error making fallback API request: {e}")
                                print(f"[DEBUG] Fallback exception type: {type(e).__name__}")
                    except Exception as e:
                        print(f"Error making primary API request: {e}")
                        print(f"[DEBUG] Exception type: {type(e).__name__}")
                        # Try the fallback endpoint
                        fallback_url = "http://localhost:8000/voice/command"
                        print(f"[DEBUG] Trying fallback URL after exception: {fallback_url}")
                        try:
                            print(f"[DEBUG] Sending to fallback with payload: {json.dumps(payload, indent=2)}")
                            print(f"[DEBUG] *** STARTING FALLBACK POST REQUEST to {fallback_url} at {time.strftime('%H:%M:%S')} ***")
                            fallback_response = requests.post(
                                fallback_url,
                                json=payload,
                                headers={"Content-Type": "application/json"},
                                timeout=5
                            )
                            print(f"[DEBUG] *** FALLBACK POST REQUEST COMPLETED at {time.strftime('%H:%M:%S')} ***")
                            
                            print(f"[DEBUG] Fallback response status: {fallback_response.status_code}")
                            print(f"[DEBUG] Fallback response headers: {fallback_response.headers}")
                            
                            try:
                                print(f"[DEBUG] Fallback response body: {fallback_response.text[:200]}")
                            except Exception as text_err:
                                print(f"[DEBUG] Could not get fallback response text: {text_err}")
                            
                            if fallback_response.status_code == 200:
                                print(f"Command processed successfully with fallback: {fallback_response.json()}")
                            else:
                                print(f"Fallback API request also failed: {fallback_response.status_code}")
                        except Exception as e:
                            print(f"Error making fallback API request: {e}")
                            print(f"[DEBUG] Fallback exception type: {type(e).__name__}")
                
                # Start the request in a separate thread
                print("[DEBUG] Starting API request thread...")
                thread = threading.Thread(target=make_api_request, daemon=True)
                thread.start()
                print(f"[DEBUG] API request thread started: {thread.name}")
                
                return f"I'm processing your request now."
        except Exception as e:
            print(f"Error processing command: {e}")
            return "I'm sorry, I encountered an error processing your request."
    else:
        print("Command cancelled by user")
        return "Command cancelled. What else can I help you with?"

# Main rendering loop
def main():
    try:
        # Initialize TTS
        tts_client = initialize_tts()
        
        # Create a voice recognizer if the required libraries are available
        voice_recognizer = None
        if VOICE_RECOGNITION_AVAILABLE:
            try:
                # Initialize with wake words ("hey ava" or "hi ava")
                voice_recognizer = VoiceRecognizer(wake_words=["hi.", "hi, hey, hey."])
                
                # Initialize confirmation state 
                voice_recognizer.awaiting_confirmation = False
                voice_recognizer.pending_command = None
                
                # Start listening for wake words (but don't immediately activate)
                voice_recognizer.start_listening()
                print("Voice recognition started successfully.")
            except Exception as e:
                print(f"Error initializing voice recognition: {e}")
                voice_recognizer = None
        else:
            print("Voice recognition is disabled.")
        
        # One-time initialization dialog - only when explicitly requested by user pressing 'g'
        initial_greeting = "Hello, I'm Ava. Say 'Hey Ava' or 'Hi Ava' to activate me."
        show_greeting = False  # Don't show initial greeting by default
        
        # Load fonts for text rendering
        try:
            # Try to load a nice font, fallback to default if not available
            font_size = 18
            speech_font = pygame.font.SysFont("Arial", font_size)
            print("Font loaded successfully.")
        except Exception as e:
            print(f"Error loading font: {e}")
            # Fallback to default font
            speech_font = pygame.font.Font(None, font_size)
        
        # Text rendering settings
        text_color = (255, 255, 255)  # White text
        speech_bubble_color = (0, 0, 0, 180)  # Semi-transparent black
        speech_bubble_padding = 10
        speech_bubble_border_radius = 10
        max_bubble_width = 300
        
        # Speech bubble state
        current_message = "Hello, I'm AVA. Your Personal Browsing Assistant"
        message_timer = 0
        message_display_time = 5.0  # Initial greeting displays for 5 seconds
        show_message = True
        
        # Speak the initial greeting
        if tts_client:
            speak_text(tts_client, current_message)
        
        # Last recognized command
        last_command = ""
        
        # Flag to track wake word activation
        is_activated = False
        
        # Animation settings for smooth scaling
        target_scale = 0.5  # Default scale
        current_scale = 0.5  # Current scale
        scale_speed = 0.015  # Increased for more responsive animation
        
        # Scale multiplier when activated - just a tiny bit larger for subtle indication
        activated_scale_multiplier = 1.1  # Reduced from 1.5 to just 10% larger when activated
        
        # Activation timer - longer to match Alexa-like behavior
        activation_timer = 0
        activation_duration = 10.0  # Increased from 5.0 to 10.0 seconds to give more time for speaking
        
        # Visual indicator for activation - pulsing halo
        halo_alpha = 0.0        # Transparency of the halo (0-1)
        halo_pulse_speed = 2.0  # Speed of pulsing
        halo_radius = 0.0       # Current radius of the halo
        halo_max_radius = 1.5   # Maximum radius when fully expanded
        halo_color = (0.4, 0.8, 1.0, 0.0)  # Light blue color with alpha
        
        # Load the model
        model_path = os.path.join(os.path.dirname(__file__), 'models', 'tokovt', 'scene.gltf')
        model = gltf_loader.load_gltf(ctx, model_path)
        
        # Create projection matrix with slightly wider FOV for better visibility
        projection = Matrix44.perspective_projection(50.0, WIDTH / HEIGHT, 0.1, 100.0)
        
        # Initial camera position - restore original values that worked
        camera_distance = 5.0  # Original distance
        camera_height = 2.5    # Original height
        camera_position = (0, camera_height, camera_distance)
        target_position = (0, 1.5, 0)  # Original target position
        
        # Create view matrix
        view = Matrix44.look_at(
            camera_position,  # eye
            target_position,  # target
            (0, 1, 0),        # up
        )
        
        # Set up model transformation
        # Apply rotation to better show the textured parts
        model_rotation_x = 0  
        model_rotation_y = 0  
        rotation_speed = 0   
        model_scale = 0.5    # Original scale
        
        # Use original position values with only y-offset adjusted
        model_x_offset = -4.5  # Original x offset
        model_y_offset = 5   # Moderate adjustment to show top half
        model_z_offset = 0.0
        
        # Parameters for natural head movement
        head_rot_x = 0.0  # Current head x rotation (up/down tilt)
        head_rot_y = 0.0  # Current head y rotation (left/right)
        
        # Target rotation values (where the head is moving to)
        target_rot_x = 0.0
        target_rot_y = 0.0
        
        # Timers for changing head direction
        direction_change_timer = 0
        direction_change_interval = 4.0  # Longer interval between movements
        
        # Movement speed (how fast the head rotates to target position)
        movement_speed = 0.015  # Even slower for more natural movement
        
        # Return to center parameters
        return_to_center_chance = 0.6  # 60% chance to return to center
        center_bias = 0.7  # Bias toward center position
        
        # Callback function for voice activation
        def on_voice_activation(activated, command=None):
            nonlocal is_activated, activation_timer, current_message, message_timer, show_message, last_command
            
            # Check if we're awaiting confirmation and this is a confirmation response
            if activated and command and voice_recognizer and voice_recognizer.awaiting_confirmation:
                # Check if the command is a confirmation (yes/no)
                command_lower = command.lower()
                is_confirmed = any(word in command_lower for word in ["yes", "yeah", "yep", "correct", "sure", "ok", "okay"])
                is_denied = any(word in command_lower for word in ["no", "nope", "don't", "not", "cancel", "incorrect"])
                
                if is_confirmed or is_denied:
                    # Process the confirmation response
                    response = process_confirmation(voice_recognizer, voice_recognizer.pending_command, is_confirmed)
                    current_message = response
                    message_timer = 0
                    show_message = True
                    
                    # Speak the response
                    if tts_client:
                        speak_text(tts_client, response)
                    
                    # Reset confirmation state
                    voice_recognizer.awaiting_confirmation = False
                    voice_recognizer.pending_command = None
                    return
            
            # If we receive a command but we're already activated, just store the command without reactivating
            if activated and command and is_activated:
                # Just store the command without repeating the activation sequence
                last_command = command
                print(f"Command detected: {command}")
                
                # Process the command and generate a confirmation response
                confirmation_response = generate_response(command)
                if confirmation_response:
                    # Update the display message with the confirmation
                    current_message = confirmation_response
                    message_timer = 0
                    show_message = True
                    
                    # Speak the confirmation response
                    if tts_client:
                        speak_text(tts_client, confirmation_response)
                return
            
            # This is a new activation (wake word detected) with no command yet
            if activated and not command:
                is_activated = True
                activation_timer = 0  # Reset timer on activation
                
                # Set response message for initial activation only
                current_message = "I'm listening. How can I help?"
                message_timer = 0
                show_message = True
                print("Voice activated! Listening for command...")
                
                # Speak the response using TTS only for initial activation
                if tts_client:
                    speak_text(tts_client, current_message)
            
            # This is a new activation with a command already detected
            elif activated and command:
                is_activated = True
                activation_timer = 0  # Reset timer on activation
                
                # Directly process the command without saying "I'm listening"
                last_command = command
                print(f"Command detected: {command}")
                
                # Process the command and generate a confirmation response
                confirmation_response = generate_response(command)
                if confirmation_response:
                    # Update the display message with the confirmation
                    current_message = confirmation_response
                    message_timer = 0
                    show_message = True
                    
                    # Speak the confirmation response
                    if tts_client:
                        speak_text(tts_client, confirmation_response)
                    
                    # Set state to awaiting confirmation
                    if voice_recognizer:
                        voice_recognizer.awaiting_confirmation = True
                        voice_recognizer.pending_command = command
            else:
                # Don't immediately deactivate, let the animation timer handle it
                pass
        
        # Set callback for voice recognition if available
        if voice_recognizer:
            voice_recognizer.callback = on_voice_activation
            
        # For testing: Allow manual activation with spacebar
        manual_activation_key = pygame.K_SPACE
        
        # Main loop
        running = True
        clock = pygame.time.Clock()
        
        # Define the scissor region - increase only the height, keep width and position the same
        scissor_width = 300  # Keep original width
        scissor_height = 500  # Increase height to show more of the model
        scissor_x = -100  # Keep original x position
        scissor_y = HEIGHT - 175  # Adjust y to show more of the model
        
        # Create a quad for the halo effect
        halo_vertices = np.array([
            # x,    y,    z,    u,    v
            -1.0, -1.0, 0.0,  0.0,  0.0,
             1.0, -1.0, 0.0,  1.0,  0.0,
             1.0,  1.0, 0.0,  1.0,  1.0,
            -1.0,  1.0, 0.0,  0.0,  1.0,
        ], dtype='f4')
        
        halo_indices = np.array([0, 1, 2, 0, 2, 3], dtype='i4')
        
        halo_vbo = ctx.buffer(halo_vertices)
        halo_ibo = ctx.buffer(halo_indices)
        
        halo_vao = ctx.vertex_array(
            ctx.program(
                vertex_shader='''
                    #version 330
                    uniform mat4 mvp;
                    uniform float scale;
                    
                    in vec3 in_position;
                    in vec2 in_texcoord;
                    
                    out vec2 v_texcoord;
                    
                    void main() {
                        gl_Position = mvp * vec4(in_position * scale, 1.0);
                        v_texcoord = in_texcoord;
                    }
                ''',
                fragment_shader='''
                    #version 330
                    uniform vec4 color;
                    uniform float alpha;
                    
                    in vec2 v_texcoord;
                    out vec4 f_color;
                    
                    void main() {
                        // Calculate distance from center for circular gradient
                        float dist = distance(v_texcoord, vec2(0.5, 0.5)) * 2.0;
                        // Create a soft circular gradient that fades at the edges
                        float intensity = 1.0 - smoothstep(0.0, 1.0, dist);
                        // Apply color with calculated alpha
                        f_color = vec4(color.rgb, color.a * alpha * intensity);
                    }
                '''
            ),
            [(halo_vbo, '3f 2f', 'in_position', 'in_texcoord')],
            index_buffer=halo_ibo
        )
        
        # Modify the command handling in the main loop
        while running:            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    # Manual activation with spacebar (for testing)
                    elif event.key == manual_activation_key:
                        is_activated = True
                        activation_timer = 0
                        # Simulate a test command for manual activation - updated message
                        test_command = "book me a flight to Cabo for March 10"
                        current_message = generate_response(test_command)
                        message_timer = 0
                        show_message = True
                        # For testing - store the command
                        last_command = test_command
                        print(f"Manual activation with test command: {test_command}")
                        
                        # Set awaiting confirmation state
                        if voice_recognizer:
                            voice_recognizer.awaiting_confirmation = True
                            voice_recognizer.pending_command = test_command
                        
                        # Speak the response using TTS
                        if tts_client:
                            speak_text(tts_client, current_message)
                    # Test email command with E key
                    elif event.key == pygame.K_e:
                        is_activated = True
                        activation_timer = 0
                        # Simulate an email command
                        test_command = "send an email to john@example.com about Meeting Tomorrow saying Can we meet at 2pm in the conference room?"
                        current_message = generate_response(test_command)
                        message_timer = 0
                        show_message = True
                        # For testing - store the command
                        last_command = test_command
                        print(f"Testing email command: {test_command}")
                        
                        # Set awaiting confirmation state
                        if voice_recognizer:
                            voice_recognizer.awaiting_confirmation = True
                            voice_recognizer.pending_command = test_command
                        
                        # Speak the response using TTS
                        if tts_client:
                            speak_text(tts_client, current_message)
                    # Test weather command with W key
                    elif event.key == pygame.K_w:
                        is_activated = True
                        activation_timer = 0
                        # Simulate a weather command
                        test_command = "what's the weather in New York"
                        current_message = generate_response(test_command)
                        message_timer = 0
                        show_message = True
                        # For testing - store the command
                        last_command = test_command
                        print(f"Testing weather command: {test_command}")
                        
                        # Set awaiting confirmation state
                        if voice_recognizer:
                            voice_recognizer.awaiting_confirmation = True
                            voice_recognizer.pending_command = test_command
                        
                        # Speak the response using TTS
                        if tts_client:
                            speak_text(tts_client, current_message)
                    # Add a key for confirming commands (for testing)
                    elif event.key == pygame.K_y and voice_recognizer and voice_recognizer.awaiting_confirmation:
                        # Process "yes" confirmation
                        response = process_confirmation(voice_recognizer, voice_recognizer.pending_command, True)
                        current_message = response
                        message_timer = 0
                        show_message = True
                        # Reset confirmation state
                        voice_recognizer.awaiting_confirmation = False
                        voice_recognizer.pending_command = None
                        # Speak the response
                        if tts_client:
                            speak_text(tts_client, response)
                    # Add a key for cancelling commands (for testing)
                    elif event.key == pygame.K_n and voice_recognizer and voice_recognizer.awaiting_confirmation:
                        # Process "no" confirmation
                        response = process_confirmation(voice_recognizer, voice_recognizer.pending_command, False)
                        current_message = response
                        message_timer = 0
                        show_message = True
                        # Reset confirmation state
                        voice_recognizer.awaiting_confirmation = False
                        voice_recognizer.pending_command = None
                        # Speak the response
                        if tts_client:
                            speak_text(tts_client, response)
                    # Add a key to recalibrate microphone
                    elif event.key == pygame.K_r and voice_recognizer:
                        print("Manually requesting microphone recalibration...")
                        # This will be handled in the voice recognition thread
                        # Just a placeholder for future implementation
            
            # Calculate delta time for smooth animation
            dt = clock.get_time() / 1000.0  # Convert to seconds
            
            # Update the direction change timer
            direction_change_timer += dt
            if direction_change_timer >= direction_change_interval:
                # Return to center position more often to maintain eye contact
                if random.random() < return_to_center_chance:
                    # Return toward center with some variation
                    target_rot_y = random.uniform(-0.02, 0.02)  # Very small range for facing forward
                    target_rot_x = random.uniform(-0.01, 0.01)  # Very small up/down variation
                else:
                    # Look around slightly
                    target_rot_y = random.uniform(-0.06, 0.06)  # Reduced left-right rotation
                    target_rot_x = random.uniform(-0.025, 0.025)  # Very subtle up-down tilt
                
                # Apply center bias - pull values toward center
                target_rot_y *= (1.0 - center_bias * random.random())
                target_rot_x *= (1.0 - center_bias * random.random())
                
                direction_change_timer = 0
            
            # Smoothly interpolate current rotation towards target rotation
            head_rot_x += (target_rot_x - head_rot_x) * movement_speed
            head_rot_y += (target_rot_y - head_rot_y) * movement_speed
            
            # Composite micro-movements for more realistic motion
            # Faster, smaller movements for eye/head micro-adjustments
            micro_x = (math.sin(time.time() * 0.7) * 0.005 + 
                      math.sin(time.time() * 1.3) * 0.003)
            
            micro_y = (math.sin(time.time() * 0.5) * 0.006 + 
                      math.sin(time.time() * 1.1) * 0.004)
            
            # Add subtle breathing motion
            breathing = math.sin(time.time() * 0.8) * 0.004
            
            # Combine all movements
            final_rot_x = head_rot_x + micro_x + breathing
            final_rot_y = head_rot_y + micro_y
            
            # Handle activation state and scale
            if is_activated:
                # Update activation timer
                activation_timer += dt
                
                # Remove scaling animation - keep original scale
                target_scale = model_scale  # Keep original scale instead of scaling up
                
                # Update halo effect - pulsating animation
                halo_alpha = 0.4 + 0.2 * math.sin(time.time() * halo_pulse_speed)
                halo_radius = halo_max_radius * (0.8 + 0.2 * math.sin(time.time() * halo_pulse_speed * 1.5))
                
                # If activation time has expired, deactivate
                if activation_timer >= activation_duration:
                    is_activated = False
                    print("Voice activation ended.")
                    
                    # Reset last_command without repeating it back
                    if last_command:
                        # Just reset the command without repeating it
                        last_command = ""
            else:
                # Return to normal scale when not activated
                target_scale = model_scale
                
                # Fade out halo effect when not activated
                halo_alpha = max(0.0, halo_alpha - dt * 2.0)
                if halo_alpha <= 0.01:
                    halo_alpha = 0.0
            
            # Smoothly interpolate scale - more responsive
            current_scale += (target_scale - current_scale) * scale_speed * 7
            
            # Create model matrix with natural head rotations
            model_matrix = Matrix44.from_y_rotation(final_rot_y) @ Matrix44.from_x_rotation(final_rot_x)
            
            # Apply scaling to make the model smaller or larger depending on activation
            scale_matrix = Matrix44.from_scale((current_scale, current_scale, current_scale))
            
            # Apply translation to move model to position
            translation_matrix = Matrix44.from_translation((model_x_offset, model_y_offset, model_z_offset))
            
            # Combine transformations: first rotate, then scale, then translate
            model_matrix = translation_matrix @ scale_matrix @ model_matrix
            
            # Clear the entire screen first
            ctx.clear(*BACKGROUND_COLOR)
            
            # Enable scissor test to only render in specific area (top half)
            # ModernGL doesn't use SCISSOR_TEST constant, we just set the scissor box directly
            ctx.scissor = (scissor_x, scissor_y, scissor_width, scissor_height)
            
            # Render the model (only visible in scissor region)
            gltf_loader.render_gltf(model, model_matrix, view, projection)
            
            # Render halo effect if activated
            if halo_alpha > 0.0:
                # Set up MVP matrix for the halo (centered on model but slightly behind)
                halo_matrix = translation_matrix @ Matrix44.from_scale((halo_radius, halo_radius, halo_radius))
                
                # Set uniforms for the halo shader
                halo_vao.program['mvp'].write((projection @ view @ halo_matrix).astype('f4').tobytes())
                halo_vao.program['scale'].value = 1.0
                halo_vao.program['color'].value = halo_color[:3] + (halo_alpha,)
                halo_vao.program['alpha'].value = halo_alpha
                
                # Enable blend for transparency
                ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
                
                # Render the halo
                halo_vao.render()
            
            # Disable scissor test after rendering (set to None or reset to full viewport)
            ctx.scissor = None
            
            # Render speech bubble with text if needed
            if show_message and current_message:
                # Get a reference to the screen surface for 2D drawing
                screen_surface = pygame.display.get_surface()
                
                # Function to render text with word wrapping
                def render_text_with_wrap(text, font, color, max_width, pos_x, pos_y):
                    words = text.split(' ')
                    lines = []
                    current_line = []
                    
                    for word in words:
                        test_line = ' '.join(current_line + [word])
                        test_width, _ = font.size(test_line)
                        
                        if test_width <= max_width:
                            current_line.append(word)
                        else:
                            if current_line:  # If the current line has words, add it to lines
                                lines.append(' '.join(current_line))
                                current_line = [word]
                            else:  # If current_line is empty, the word is too long by itself
                                lines.append(word)
                                current_line = []
                    
                    # Add the last line
                    if current_line:
                        lines.append(' '.join(current_line))
                    
                    # Render each line
                    line_surfaces = []
                    max_line_width = 0
                    total_height = 0
                    
                    for line in lines:
                        line_surf = font.render(line, True, color)
                        line_surfaces.append(line_surf)
                        max_line_width = max(max_line_width, line_surf.get_width())
                        total_height += line_surf.get_height()
                    
                    # Calculate bubble size
                    bubble_width = max_line_width + speech_bubble_padding * 2
                    bubble_height = total_height + speech_bubble_padding * 2
                    
                    # Draw speech bubble
                    bubble_rect = pygame.Rect(pos_x - bubble_width // 2, 
                                             pos_y - bubble_height - 10,
                                             bubble_width, bubble_height)
                    
                    # Semi-transparent background (create a surface with per-pixel alpha)
                    bubble_surface = pygame.Surface((bubble_width, bubble_height), pygame.SRCALPHA)
                    bubble_surface.fill((0, 0, 0, 180))  # RGBA: semi-transparent black
                    
                    # Draw rounded rectangle (simulate with multiple circles and rects)
                    pygame.draw.rect(bubble_surface, speech_bubble_color, 
                                    pygame.Rect(0, 0, bubble_width, bubble_height), 
                                    border_radius=speech_bubble_border_radius)
                    
                    # Draw little triangle pointing to character
                    triangle_points = [
                        (bubble_width // 2 - 10, bubble_height),
                        (bubble_width // 2 + 10, bubble_height),
                        (bubble_width // 2, bubble_height + 10)
                    ]
                    pygame.draw.polygon(bubble_surface, speech_bubble_color, triangle_points)
                    
                    # Blit the bubble
                    screen_surface.blit(bubble_surface, bubble_rect)
                    
                    # Draw text onto bubble
                    current_y = pos_y - bubble_height + speech_bubble_padding - 10
                    for line_surf in line_surfaces:
                        screen_surface.blit(line_surf, 
                                         (pos_x - line_surf.get_width() // 2, current_y))
                        current_y += line_surf.get_height()
                
                # Render the speech bubble with text at the top of the model
                bubble_x = WIDTH // 2
                bubble_y = HEIGHT // 2 - 50  # Positioned above the model
                
                # We need to temporarily switch to Pygame rendering for the text
                # Save the OpenGL state first
                ctx.finish()
                
                render_text_with_wrap(current_message, speech_font, text_color, 
                                    max_bubble_width, bubble_x, bubble_y)
            
            # Always flip only once per frame at the end
            pygame.display.flip()
            clock.tick(60)
    
    finally:
        # Make sure to stop the voice recognizer when done
        if 'voice_recognizer' in locals() and voice_recognizer:
            voice_recognizer.stop_listening()
        pygame.quit()

if __name__ == "__main__":
    main() 