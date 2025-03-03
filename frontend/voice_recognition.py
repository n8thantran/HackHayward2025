import os
import time
import threading
import queue
import wave
import numpy as np
from collections import deque
import datetime
import json
import requests

# Try to import dotenv
try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
    load_dotenv()
except ImportError:
    print("WARNING: python-dotenv module could not be imported.")
    print("The application will run without environment variable loading.")
    DOTENV_AVAILABLE = False

# Check for distutils which is required by some dependencies
try:
    import distutils
except ImportError:
    print("ERROR: distutils module is missing.")
    print("This is required by some dependencies. Please install it with:")
    print("pip install setuptools")
    # Continue execution as other error handlers will catch specific module issues

# Import required libraries with error handling
try:
    import speech_recognition as sr
    import sounddevice as sd
    VOICE_RECOGNITION_AVAILABLE = True
except ImportError:
    print("WARNING: Required voice recognition libraries not available.")
    print("Try installing them with: pip install SpeechRecognition sounddevice")
    VOICE_RECOGNITION_AVAILABLE = False

# Import pydub for MP3 conversion (more like Alexa)
try:
    from pydub import AudioSegment
    MP3_AVAILABLE = True
except ImportError:
    print("WARNING: pydub library not available, will save as WAV instead of MP3.")
    print("Try installing it with: pip install pydub")
    MP3_AVAILABLE = False

class VoiceRecognizer:
    def __init__(self, wake_words=None, temp_dir="temp", callback=None):
        # Create temp directory if it doesn't exist
        self.temp_dir = temp_dir
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Check if required libraries are available
        if not VOICE_RECOGNITION_AVAILABLE:
            print("Voice recognition is disabled due to missing libraries.")
            return
        
        # Initialize Groq API settings (without using the client library)
        self.use_groq = False
        self.groq_api_key = os.environ.get('GROQ_API_KEY')
        if self.groq_api_key:
            # Test the API key
            self.use_groq = self._test_groq_api_key()
            if self.use_groq:
                print("Groq API key validated. Will use Groq Whisper for transcription.")
            else:
                print("Groq API key failed validation. Falling back to Google Speech Recognition.")
        else:
            print("No Groq API key found. Using Google Speech Recognition.")
            self.use_groq = False
        
        # Audio parameters (optimized for speech recognition)
        self.RATE = 16000  # Sample rate
        self.CHANNELS = 1  # Mono
        self.CHUNK = 1024  # Buffer size
        self.FORMAT = np.int16  # 16-bit audio
        
        # Customize wake words with additional variations for better detection
        self.base_wake_words = wake_words or ["hi ava", "hey ava"]
        self.wake_words = self._expand_wake_words(self.base_wake_words)
        self.callback = callback
        
        # Recording state
        self.is_listening = False
        self.is_recording = False
        self.audio_queue = queue.Queue()
        self.recording_thread = None
        self.detection_thread = None
        self.current_recording = []
        
        # Improve Alexa-like behavior with continuous listening
        self.continuous_listening = True
        self.last_activation_time = 0
        self.cooldown_period = 2.0  # seconds to wait between activations
        
        # File management settings
        self.max_recordings = 100  # Maximum number of recordings to keep
        self.cleanup_interval = 3600  # Clean up old files every hour (in seconds)
        self.last_cleanup_time = time.time()
        
        # Create recognizer with optimized settings
        self.recognizer = sr.Recognizer()
        # Lower energy threshold for better sensitivity
        self.recognizer.energy_threshold = 250  
        self.recognizer.dynamic_energy_threshold = True
        # More aggressive settings for faster response
        self.recognizer.pause_threshold = 0.5
        # Adjust non-speaking duration for better phrase detection
        self.recognizer.non_speaking_duration = 0.3
        # Increase phrase threshold for better detection
        self.recognizer.phrase_threshold = 0.3
        
        # Run initial cleanup of old files
        self._cleanup_old_files()
        
    def _expand_wake_words(self, base_words):
        """Expand wake words with common variations to improve detection"""
        expanded = []
        for word in base_words:
            expanded.append(word)
            # Add common variations and misspellings
            if "ava" in word:
                expanded.append(word.replace("ava", "eva"))
                expanded.append(word.replace("ava", "ava please"))
                expanded.append(word.replace("ava", "ava can you"))
            if "hi" in word:
                expanded.append(word.replace("hi", "hey"))
                expanded.append(word.replace("hi", "hello"))
            if "hey" in word:
                expanded.append(word.replace("hey", "hi"))
                expanded.append(word.replace("hey", "hello"))
                expanded.append(word.replace("hey", "hay"))
        
        print(f"Using wake words: {expanded}")
        return expanded
        
    def start_listening(self):
        """Start listening for the wake words in the background"""
        if not VOICE_RECOGNITION_AVAILABLE:
            print("Cannot start listening: Required libraries not available")
            return
            
        if self.is_listening:
            return
            
        # Start listening thread
        try:
            self.is_listening = True
            self.detection_thread = threading.Thread(target=self._listen_and_detect, daemon=True)
            self.detection_thread.start()
            print("Voice recognition started. Listening for wake words...")
        except Exception as e:
            self.is_listening = False
            print(f"Error starting voice recognition: {e}")
        
    def stop_listening(self):
        """Stop listening for wake words"""
        if not self.is_listening:
            return
            
        self.is_listening = False
        if self.detection_thread:
            self.detection_thread.join(timeout=1.0)
            
    def _listen_and_detect(self):
        """Background thread that listens for wake words using microphone"""
        try:
            # Get list of available microphones to help with troubleshooting
            print("Available microphones:")
            for i, mic_name in enumerate(sr.Microphone.list_microphone_names()):
                print(f"  {i}: {mic_name}")
                
            # Setup microphone with default device
            with sr.Microphone(sample_rate=self.RATE) as source:
                # Initial calibration
                print("Calibrating microphone for ambient noise (please be quiet)...")
                self.recognizer.adjust_for_ambient_noise(source, duration=2)
                print("Microphone calibrated, listening for wake words...")
                
                # Periodically recalibrate to adjust to changing environments
                last_calibration = time.time()
                calibration_interval = 300  # recalibrate every 5 minutes
                
                # For Groq API error tracking
                groq_errors_count = 0
                max_groq_errors = 3  # After this many errors, fall back to Google permanently
                
                while self.is_listening:
                    # Periodic recalibration
                    current_time = time.time()
                    if current_time - last_calibration > calibration_interval:
                        print("Recalibrating microphone...")
                        self.recognizer.adjust_for_ambient_noise(source, duration=1)
                        last_calibration = current_time
                        print("Recalibration complete")
                        
                    # Periodically clean up old files
                    if current_time - self.last_cleanup_time > self.cleanup_interval:
                        self._cleanup_old_files()
                        self.last_cleanup_time = current_time
                    
                    try:
                        # Listen for phrases with a shorter timeout and phrase time limit
                        # This makes it more responsive, like Alexa
                        audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=5)
                        
                        # Save the audio to a temporary file for Groq transcription
                        temp_audio_path = os.path.join(self.temp_dir, "temp_listen.wav")
                        with open(temp_audio_path, "wb") as f:
                            f.write(audio.get_wav_data())
                        
                        # Try to recognize speech with Groq Whisper or fall back to Google
                        try:
                            if self.use_groq and groq_errors_count < max_groq_errors:
                                try:
                                    text = self._transcribe_with_groq(temp_audio_path).lower()
                                except Exception as e:
                                    # Count Groq errors
                                    groq_errors_count += 1
                                    if groq_errors_count >= max_groq_errors:
                                        print(f"Too many Groq API errors ({groq_errors_count}). Permanently falling back to Google Speech Recognition.")
                                        self.use_groq = False
                                    # Fall back to Google for this attempt
                                    text = self.recognizer.recognize_google(audio).lower()
                            else:
                                text = self.recognizer.recognize_google(audio).lower()
                            
                            # Only print if it's not just background noise
                            if len(text) > 2:  # Filter out very short recognitions
                                print(f"Detected: {text}")
                            
                            # Check for wake words with more flexibility
                            detected = False
                            detected_word = None
                            
                            # Check exact matches first (faster)
                            for wake_word in self.wake_words:
                                if wake_word in text:
                                    detected = True
                                    detected_word = wake_word
                                    break
                            
                            # If not found, try partial matching for more flexibility
                            if not detected:
                                # For wake words with multiple parts (e.g., "hey ava")
                                for wake_word in self.base_wake_words:
                                    parts = wake_word.split()
                                    if len(parts) > 1 and all(part in text for part in parts):
                                        detected = True
                                        detected_word = wake_word
                                        break
                            
                            # Check cooldown period before activation
                            if detected and (time.time() - self.last_activation_time) > self.cooldown_period:
                                print(f"Wake word detected: {detected_word} in '{text}'")
                                
                                # Save the audio and any following speech
                                self._save_audio_and_listen_for_command(audio, text, source, temp_audio_path)
                                
                                # Update last activation time
                                self.last_activation_time = time.time()
                            else:
                                # Clean up temp file if not used
                                if os.path.exists(temp_audio_path):
                                    os.remove(temp_audio_path)
                            
                        except sr.UnknownValueError:
                            # Clean up temp file
                            if os.path.exists(temp_audio_path):
                                os.remove(temp_audio_path)
                            pass  # Speech was not understood
                        except sr.RequestError as e:
                            # Clean up temp file
                            if os.path.exists(temp_audio_path):
                                os.remove(temp_audio_path)
                            print(f"Could not request results from speech recognition service: {e}")
                    except sr.WaitTimeoutError:
                        pass  # Timeout is normal, just continue listening
                    except Exception as e:
                        if "IOError" in str(e) and "Input overflowed" in str(e):
                            # Common PyAudio buffer overrun, just continue
                            pass
                        else:
                            print(f"Error during listening: {e}")
                    
                    # Brief pause to prevent high CPU usage
                    time.sleep(0.05)
        except Exception as e:
            print(f"Fatal error in speech recognition thread: {e}")
            self.is_listening = False
    
    def _transcribe_with_groq(self, audio_file):
        """Transcribe audio using Groq's Whisper model via direct API access"""
        try:
            headers = {
                "Authorization": f"Bearer {self.groq_api_key}",
            }
            
            with open(audio_file, "rb") as file:
                files = {"file": (os.path.basename(audio_file), file, "audio/wav")}
                data = {
                    "model": "distil-whisper-large-v3-en",
                    "language": "en"
                }
                
                response = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=5  # Add timeout to prevent hanging
                )
                
                if response.status_code == 200:
                    return response.json()["text"]
                else:
                    print(f"Groq API error ({response.status_code}): {response.text[:100]}...")
                    raise Exception(f"API error: {response.status_code}")
                    
        except Exception as e:
            print(f"Error with Groq transcription: {e}")
            # Fall back to Google - but note that this is handled in the calling function
            raise
            
    def _save_audio_and_listen_for_command(self, wake_word_audio, wake_word_text, source, temp_audio_path=None):
        """Save the wake word audio and listen for a follow-up command (like Alexa)"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # First save the wake word audio
        wake_word_filename = self._save_audio(wake_word_audio, f"wake_{timestamp}", temp_audio_path)
        
        # Activate VTuber
        if self.callback:
            self.callback(True)  # Activate callback
        
        try:
            # Now listen for the command (what comes after "Hey Ava")
            print("Listening for command...")
            
            # Use a longer timeout for command to give user more time to start speaking
            command_audio = self.recognizer.listen(source, timeout=5.0, phrase_time_limit=7)
            
            try:
                # Save the command audio to temporary file for Groq
                temp_command_path = os.path.join(self.temp_dir, "temp_command.wav")
                with open(temp_command_path, "wb") as f:
                    f.write(command_audio.get_wav_data())
                
                # Try to recognize the command with Groq or fallback
                if self.use_groq:
                    command_text = self._transcribe_with_groq(temp_command_path).lower()
                else:
                    command_text = self.recognizer.recognize_google(command_audio).lower()
                
                print(f"Command detected: {command_text}")
                
                # Save the command audio
                command_filename = self._save_audio(command_audio, f"command_{timestamp}", temp_command_path)
                
                # Save metadata about the interaction
                self._save_metadata(timestamp, wake_word_text, command_text, 
                                   wake_word_filename, command_filename)
                
                # Pass the command text back to the callback
                if self.callback:
                    self.callback(True, command_text)
                    
                    # Wait for a potential confirmation response
                    # This is handled by the main application's confirmation flow
                    # No need to deactivate immediately, as we'll wait for confirmation
                    return
                
            except sr.UnknownValueError:
                print("Command not understood")
                # Still save the audio even if not understood
                self._save_audio(command_audio, f"unknown_command_{timestamp}")
                # Inform callback that command wasn't understood
                if self.callback:
                    self.callback(True, "I couldn't understand that")
                
            except sr.RequestError as e:
                print(f"Could not request results for command: {e}")
                # Inform callback about the request error
                if self.callback:
                    self.callback(True, "Sorry, I had trouble connecting")
                
            # Clean up temp file
            if os.path.exists(temp_command_path):
                os.remove(temp_command_path)
                
        except Exception as e:
            print(f"Error while listening for command: {e}")
            # Inform callback about the error
            if self.callback:
                self.callback(True, "Sorry, I encountered an error")
        
        # Set a timer to deactivate after a few seconds - only if we're not in confirmation flow
        # This will be managed by the main application for confirmation scenarios
        threading.Timer(3.0, lambda: self.callback(False) if self.callback else None).start()
    
    def _save_audio(self, audio_data, prefix, temp_path=None):
        """Save the recorded audio to a file (MP3 if possible, otherwise WAV)"""
        try:
            # Create timestamp for filename
            wav_filename = os.path.join(self.temp_dir, f"{prefix}.wav")
            mp3_filename = os.path.join(self.temp_dir, f"{prefix}.mp3")
            
            # Use existing temp file if provided, otherwise create from audio_data
            if temp_path and os.path.exists(temp_path):
                # Rename temp file instead of creating a new one
                os.rename(temp_path, wav_filename)
            else:
                # First save as WAV
                with open(wav_filename, "wb") as f:
                    f.write(audio_data.get_wav_data())
            
            # Convert to MP3 if pydub is available (Alexa-like)
            if MP3_AVAILABLE:
                try:
                    audio = AudioSegment.from_wav(wav_filename)
                    audio.export(mp3_filename, format="mp3")
                    
                    # Remove the WAV file after successful conversion
                    os.remove(wav_filename)
                    print(f"Saved recording to {mp3_filename}")
                    return mp3_filename
                except Exception as e:
                    print(f"Error converting to MP3, keeping WAV: {e}")
                    return wav_filename
            else:
                print(f"Saved recording to {wav_filename}")
                return wav_filename
                
        except Exception as e:
            print(f"Error saving audio: {e}")
            return None
            
    def _save_metadata(self, timestamp, wake_word_text, command_text, wake_filename, command_filename):
        """Save detailed metadata about the voice interaction"""
        try:
            # Get system info for better debugging
            system_info = {
                "platform": os.name,
                "python_version": os.sys.version.split()[0],
                "audio_rate": self.RATE,
                "audio_channels": self.CHANNELS,
            }
            
            # Get audio file stats if available
            wake_file_stats = None
            command_file_stats = None
            
            if wake_filename and os.path.exists(wake_filename):
                wake_file_stats = {
                    "size_bytes": os.path.getsize(wake_filename),
                    "created": datetime.datetime.fromtimestamp(os.path.getctime(wake_filename)).isoformat(),
                }
                
            if command_filename and os.path.exists(command_filename):
                command_file_stats = {
                    "size_bytes": os.path.getsize(command_filename),
                    "created": datetime.datetime.fromtimestamp(os.path.getctime(command_filename)).isoformat(),
                }
            
            # Create comprehensive metadata
            metadata = {
                "interaction": {
                    "timestamp": timestamp,
                    "iso_time": datetime.datetime.now().isoformat(),
                    "unix_time": time.time(),
                    "wake_word": {
                        "text": wake_word_text,
                        "file": os.path.basename(wake_filename) if wake_filename else None,
                        "file_stats": wake_file_stats
                    },
                    "command": {
                        "text": command_text,
                        "file": os.path.basename(command_filename) if command_filename else None,
                        "file_stats": command_file_stats
                    }
                },
                "system": system_info,
                "recognition": {
                    "method": "groq" if self.use_groq else "google",
                    "energy_threshold": self.recognizer.energy_threshold,
                    "dynamic_threshold": self.recognizer.dynamic_energy_threshold,
                }
            }
            
            # Save as pretty-formatted JSON
            metadata_file = os.path.join(self.temp_dir, f"metadata_{timestamp}.json")
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
                
            print(f"Saved detailed interaction metadata to {metadata_file}")
            
            # Send the metadata to the voice command API endpoint
            try:
                api_url = "http://localhost:8000/voice/command"
                print(f"Sending command to API: {command_text}")
                
                response = requests.post(
                    api_url,
                    json=metadata,
                    headers={"Content-Type": "application/json"},
                    timeout=5  # Add timeout to prevent hanging
                )
                
                if response.status_code == 200:
                    print(f"Successfully sent command to API. Response: {response.json()}")
                else:
                    print(f"API request failed with status code {response.status_code}: {response.text[:100]}...")
            except Exception as e:
                print(f"Error sending command to API: {e}")
                
            return metadata_file
        except Exception as e:
            print(f"Error saving metadata: {e}")
            return None

    def _cleanup_old_files(self):
        """Clean up old recording files to prevent disk space issues"""
        try:
            print("Cleaning up old recording files...")
            
            # Get all files in the temp directory
            all_files = []
            for file in os.listdir(self.temp_dir):
                file_path = os.path.join(self.temp_dir, file)
                if os.path.isfile(file_path):
                    # Get file creation time and add to list
                    creation_time = os.path.getctime(file_path)
                    all_files.append((file_path, creation_time))
            
            # Skip if there aren't many files
            if len(all_files) <= self.max_recordings:
                print(f"Only {len(all_files)} files found, no cleanup needed (limit: {self.max_recordings})")
                return
                
            # Sort by creation time (oldest first)
            all_files.sort(key=lambda x: x[1])
            
            # Calculate how many files to delete
            files_to_delete = len(all_files) - self.max_recordings
            
            # Delete oldest files
            deleted_count = 0
            for file_path, _ in all_files[:files_to_delete]:
                try:
                    os.remove(file_path)
                    deleted_count += 1
                except Exception as e:
                    print(f"Error deleting {file_path}: {e}")
            
            print(f"Cleanup complete: Deleted {deleted_count} old files, keeping {self.max_recordings} newest recordings")
        except Exception as e:
            print(f"Error during file cleanup: {e}")

    def _test_groq_api_key(self):
        """Test if the Groq API key is valid"""
        try:
            # Make a simple request to test the API key
            headers = {
                "Authorization": f"Bearer {self.groq_api_key}",
                "Content-Type": "application/json"
            }
            response = requests.get(
                "https://api.groq.com/openai/v1/models",
                headers=headers,
                timeout=5
            )
            
            if response.status_code == 200:
                print("✓ Groq API key is valid")
                return True
            else:
                print(f"✗ Groq API key validation failed: {response.status_code}")
                print(f"  Error: {response.text[:100]}...")
                return False
        except Exception as e:
            print(f"✗ Error validating Groq API key: {e}")
            return False

    def listen_for_confirmation(self, source):
        """Listen specifically for a yes/no confirmation response"""
        try:
            print("Listening for confirmation (yes/no)...")
            
            # Use a shorter timeout for confirmation as it's typically a short response
            confirmation_audio = self.recognizer.listen(source, timeout=3.0, phrase_time_limit=2.0)
            
            try:
                # Save the confirmation audio to temporary file
                temp_confirm_path = os.path.join(self.temp_dir, "temp_confirm.wav")
                with open(temp_confirm_path, "wb") as f:
                    f.write(confirmation_audio.get_wav_data())
                
                # Try to recognize the confirmation response
                if self.use_groq:
                    confirmation_text = self._transcribe_with_groq(temp_confirm_path).lower()
                else:
                    confirmation_text = self.recognizer.recognize_google(confirmation_audio).lower()
                
                print(f"Confirmation response: {confirmation_text}")
                
                # Check if it's a yes or no
                is_confirmed = any(word in confirmation_text for word in ["yes.", "yeah.", "yep.", "correct.", "sure.", "ok.", "okay."])
                is_denied = any(word in confirmation_text for word in ["no.", "nope.", "don't.", "not.", "cancel.", "incorrect."])
                
                # Clean up temp file
                if os.path.exists(temp_confirm_path):
                    os.remove(temp_confirm_path)
                
                if is_confirmed:
                    return True, confirmation_text
                elif is_denied:
                    return False, confirmation_text
                else:
                    # Unclear response
                    return None, confirmation_text
                
            except sr.UnknownValueError:
                print("Confirmation not understood")
                if os.path.exists(temp_confirm_path):
                    os.remove(temp_confirm_path)
                return None, "I couldn't understand that"
                
            except sr.RequestError as e:
                print(f"Could not request results for confirmation: {e}")
                if os.path.exists(temp_confirm_path):
                    os.remove(temp_confirm_path)
                return None, f"Request error: {e}"
                
        except Exception as e:
            print(f"Error while listening for confirmation: {e}")
            return None, f"Error: {e}" 