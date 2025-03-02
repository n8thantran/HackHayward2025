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
import queue

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

# Speech queue to ensure one speech plays at a time
speech_queue = queue.Queue()
speech_thread_running = False

# Function to process the speech queue
def speech_worker(tts_client, voice_id="FGY2WhTYpPnrIDTdsKH5"):
    """Worker thread that processes speech requests from the queue"""
    global speech_thread_running
    
    while speech_thread_running:
        try:
            # Get the next text to speak (block for 0.5 seconds, then check if thread should be running)
            try:
                text = speech_queue.get(timeout=0.5)
            except queue.Empty:
                continue
                
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
            
            # Mark this item as done
            speech_queue.task_done()
            
        except Exception as e:
            print(f"Error in TTS playback: {e}")
            # Mark the task as done even if there was an error
            if not speech_queue.empty():
                speech_queue.task_done()

# Function to play text using TTS
def speak_text(tts_client, text, voice_id="FGY2WhTYpPnrIDTdsKH5"):
    """Add text to the speech queue to be spoken"""
    global speech_thread_running, speech_queue
    
    if not TTS_AVAILABLE or not tts_client:
        return
    
    # Add the text to the speech queue
    speech_queue.put(text)
    
    # Start the worker thread if it's not already running
    if not speech_thread_running:
        speech_thread_running = True
        thread = threading.Thread(target=speech_worker, args=(tts_client, voice_id), daemon=True)
        thread.start()
        return thread
    
    return None

# Main rendering loop
def main():
    try:
        # Initialize TTS
        tts_client = initialize_tts()
        
        # Initialize voice recognition if available
        voice_recognizer = None
        if VOICE_RECOGNITION_AVAILABLE:
            try:
                # Create temp directory if it doesn't exist
                os.makedirs("temp", exist_ok=True)
                
                # Initialize with simpler wake word for easier activation
                wake_words = ["hey", "hi"]
                voice_recognizer = VoiceRecognizer(wake_words=wake_words, temp_dir="temp")
                voice_recognizer.start_listening()
                print("Voice recognition initialized successfully.")
                if hasattr(voice_recognizer, 'use_groq') and voice_recognizer.use_groq:
                    print("Using Groq Whisper for enhanced wake word detection.")
                else:
                    print("Using Google Speech Recognition for wake word detection.")
                print("Say 'Hey' to activate!")
            except Exception as e:
                print(f"ERROR initializing voice recognition: {e}")
                print("The application will run without voice activation features.")
                voice_recognizer = None
        
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
        activation_duration = 5.0  # Duration in seconds to stay activated
        
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
            
            # If we receive a command but we're already activated, just store the command without reactivating
            if activated and command and is_activated:
                # Just store the command without repeating the activation sequence
                last_command = command
                print(f"Command detected: {command}")
                return
            
            if activated:
                is_activated = True
                activation_timer = 0  # Reset timer on activation
                
                # Set response message - updated to match user requirement
                current_message = "Okay, I am now recording"
                message_timer = 0
                show_message = True
                print("Voice activated! Listening for command...")
                
                # Speak the response using TTS
                if tts_client:
                    speak_text(tts_client, current_message)
                
                # If a command was captured, store it
                if command:
                    last_command = command
                    print(f"Command detected: {command}")
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
                        current_message = "Okay, I am now recording"
                        message_timer = 0
                        show_message = True
                        # For testing - simulate a command after 2 seconds
                        last_command = "open browser and search for cats"
                        print("Manual activation! Listening for command.")
                        
                        # Speak the response using TTS
                        if tts_client:
                            speak_text(tts_client, current_message)
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
                    
                    # If we have a command, show it
                    if last_command:
                        current_message = f"I heard: {last_command}"
                        message_timer = 0
                        show_message = True
                        
                        # Speak the response using TTS
                        if tts_client:
                            speak_text(tts_client, current_message)
                            
                        # Reset last_command after displaying
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
        # Make sure to stop the speech thread when done
        global speech_thread_running
        speech_thread_running = False
        
        # Make sure to stop the voice recognizer when done
        if 'voice_recognizer' in locals() and voice_recognizer:
            voice_recognizer.stop_listening()
        pygame.quit()

if __name__ == "__main__":
    main() 