import os
import time
import threading
import queue
import wave
import numpy as np
from collections import deque
import datetime
import json

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
                
                while self.is_listening:
                    # Periodic recalibration
                    current_time = time.time()
                    if current_time - last_calibration > calibration_interval:
                        print("Recalibrating microphone...")
                        self.recognizer.adjust_for_ambient_noise(source, duration=1)
                        last_calibration = current_time
                        print("Recalibration complete")
                    
                    try:
                        # Listen for phrases with a shorter timeout and phrase time limit
                        # This makes it more responsive, like Alexa
                        audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=5)
                        
                        # Try to recognize speech with Google (reliable API like Alexa uses)
                        try:
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
                                self._save_audio_and_listen_for_command(audio, text, source)
                                
                                # Update last activation time
                                self.last_activation_time = time.time()
                            
                        except sr.UnknownValueError:
                            pass  # Speech was not understood
                        except sr.RequestError as e:
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
            
    def _save_audio_and_listen_for_command(self, wake_word_audio, wake_word_text, source):
        """Save the wake word audio and listen for a follow-up command (like Alexa)"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # First save the wake word audio
        wake_word_filename = self._save_audio(wake_word_audio, f"wake_{timestamp}")
        
        # Activate VTuber
        if self.callback:
            self.callback(True)  # Activate callback
        
        try:
            # Now listen for the command (what comes after "Hey Ava")
            print("Listening for command...")
            
            # Use a shorter timeout for command to make it feel responsive
            command_audio = self.recognizer.listen(source, timeout=1.5, phrase_time_limit=7)
            
            try:
                # Try to recognize the command
                command_text = self.recognizer.recognize_google(command_audio).lower()
                print(f"Command detected: {command_text}")
                
                # Save the command audio
                command_filename = self._save_audio(command_audio, f"command_{timestamp}")
                
                # Save metadata about the interaction
                self._save_metadata(timestamp, wake_word_text, command_text, 
                                   wake_word_filename, command_filename)
                
            except sr.UnknownValueError:
                print("Command not understood")
                # Still save the audio even if not understood
                self._save_audio(command_audio, f"unknown_command_{timestamp}")
            except sr.RequestError as e:
                print(f"Could not request results for command: {e}")
        except Exception as e:
            print(f"Error while listening for command: {e}")
        
        # Set a timer to deactivate after a few seconds
        threading.Timer(3.0, lambda: self.callback(False) if self.callback else None).start()
    
    def _save_audio(self, audio_data, prefix):
        """Save the recorded audio to a file (MP3 if possible, otherwise WAV)"""
        try:
            # Create timestamp for filename
            wav_filename = os.path.join(self.temp_dir, f"{prefix}.wav")
            mp3_filename = os.path.join(self.temp_dir, f"{prefix}.mp3")
            
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
        """Save metadata about the voice interaction (like Alexa does)"""
        try:
            metadata = {
                "timestamp": timestamp,
                "wake_word": wake_word_text,
                "command": command_text,
                "wake_file": os.path.basename(wake_filename) if wake_filename else None,
                "command_file": os.path.basename(command_filename) if command_filename else None
            }
            
            metadata_file = os.path.join(self.temp_dir, f"metadata_{timestamp}.json")
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
                
            print(f"Saved interaction metadata to {metadata_file}")
        except Exception as e:
            print(f"Error saving metadata: {e}") 