# Chunked Voice Recognition with Groq Whisper

This VTuber application includes an advanced voice recognition system that continuously processes audio in chunks and uses Groq's Whisper API for transcription.

## How It Works

1. The application continuously records audio in small chunks (~256ms).
2. Multiple chunks are combined into ~1 second segments for processing.
3. Each segment is sent to Groq's Whisper API for high-quality transcription.
4. When wake words like "Hey Ava" are detected, the VTuber character activates.
5. Audio is saved in the temp/ directory as MP3 files (if possible).

## Key Features

- **Continuous Chunked Processing**: No waiting for silence or specific phrases
- **High Quality Transcription**: Uses Groq's Whisper API for accurate speech recognition
- **Fallback Mode**: Falls back to energy-based detection if no API key is provided
- **MP3 Recording**: Saves recordings as MP3 files when pydub is available
- **Queue-Based Architecture**: Thread-safe queue ensures no audio is lost
- **Buffer Overlap**: Prevents missing words that span chunk boundaries

## Installation Requirements

The system requires the following Python packages:
```
pip install sounddevice soundfile pydub requests
```

For MP3 conversion, you also need FFmpeg installed on your system:
- Windows: Install from https://ffmpeg.org/download.html and add to PATH
- Mac: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg`

## Using Groq's Whisper API

For optimal performance, you need a Groq API key:

1. Sign up at https://console.groq.com/ to get an API key
2. Set the API key as an environment variable:
   ```
   # Windows
   set GROQ_API_KEY=your_api_key
   
   # Linux/Mac
   export GROQ_API_KEY=your_api_key
   ```
3. The application will automatically use the key for transcription

If no API key is provided, the system will fall back to a simple energy-based detection method, which is less accurate but requires no external services.

## Running the Application

Simply run the application with:
```
python main.py
```

## Recorded Files

The system saves audio files in the `temp/` directory:
- `wake_[timestamp].mp3` - Audio containing the wake word
- `command_[timestamp].mp3` - Audio after the wake word
- `metadata_[timestamp].json` - Data about the interaction

## Advanced Configuration

The chunking system can be tuned by modifying these parameters in the code:
- `CHUNK_SIZE`: Size of each audio buffer (default: 4096 samples)
- `cooldown_period`: Time in seconds between activations (default: 2.0)
- Command listening duration (default: 5.0 seconds)

## Manual Activation

If voice recognition doesn't work, you can still press the **SPACEBAR** to simulate the "Hey Ava" command.

## Troubleshooting

### No Sound Detected
- Check if your microphone is working in other applications
- Check if the GROQ_API_KEY environment variable is set correctly
- Try speaking more clearly or adjusting your microphone volume

### High CPU Usage
- If experiencing high CPU usage, you can adjust the chunk size or processing frequency
- Larger chunks reduce processing frequency but may delay response

### API Errors
- Check your internet connection
- Verify your Groq API key is valid
- Check the Groq API status at https://status.groq.com/ 