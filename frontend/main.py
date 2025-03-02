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

# Main rendering loop
def main():
    try:
        # Initialize voice recognition if available
        voice_recognizer = None
        if VOICE_RECOGNITION_AVAILABLE:
            try:
                # Create temp directory if it doesn't exist
                os.makedirs("temp", exist_ok=True)
                
                # Initialize with more wake word variations for better detection
                wake_words = ["hi ava", "hey ava", "hi eva", "hey eva"]
                voice_recognizer = VoiceRecognizer(wake_words=wake_words, temp_dir="temp")
                voice_recognizer.start_listening()
                print("Voice recognition initialized successfully.")
                if hasattr(voice_recognizer, 'use_groq') and voice_recognizer.use_groq:
                    print("Using Groq Whisper for enhanced wake word detection.")
                else:
                    print("Using Google Speech Recognition for wake word detection.")
                print("Say 'Hey Ava' to activate!")
            except Exception as e:
                print(f"ERROR initializing voice recognition: {e}")
                print("The application will run without voice activation features.")
                voice_recognizer = None
        
        # Flag to track wake word activation
        is_activated = False
        
        # Animation settings for smooth scaling
        target_scale = 0.5  # Default scale
        current_scale = 0.5  # Current scale
        scale_speed = 0.015  # Increased for more responsive animation
        
        # Scale multiplier when activated - a bit more noticeable
        activated_scale_multiplier = 1.5  # 50% larger when activated
        
        # Activation timer - longer to match Alexa-like behavior
        activation_timer = 0
        activation_duration = 5.0  # Duration in seconds to stay activated
        
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
        def on_voice_activation(activated):
            nonlocal is_activated, activation_timer
            if activated:
                is_activated = True
                activation_timer = 0  # Reset timer on activation
                print("Voice activated! Model scaling up (listening for command)...")
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
                        print("Manual activation! Model scaling up.")
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
                
                # Set target scale when activated
                target_scale = model_scale * activated_scale_multiplier
                
                # If activation time has expired, deactivate
                if activation_timer >= activation_duration:
                    is_activated = False
                    print("Voice activation ended.")
            else:
                # Return to normal scale when not activated
                target_scale = model_scale
            
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
            
            # Disable scissor test after rendering (set to None or reset to full viewport)
            ctx.scissor = None
            
            pygame.display.flip()
            clock.tick(60)
    
    finally:
        # Make sure to stop the voice recognizer when done
        if 'voice_recognizer' in locals() and voice_recognizer:
            voice_recognizer.stop_listening()
        pygame.quit()

if __name__ == "__main__":
    main() 