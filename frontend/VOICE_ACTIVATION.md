# Alexa-Like Voice Activation System

This VTuber application includes an Alexa-like voice command system that responds to wake words.

## How It Works

1. The application continuously listens for your voice in the background.
2. When you say "Hey Ava" (or variations like "Hi Eva"), the VTuber character will:
   - Grow larger to indicate it heard you (like Alexa's blue ring)
   - Listen for your command (what you say after "Hey Ava")
   - Save both the wake word and your command as MP3 files

## Alexa-Like Features

- **Wake Word Detection**: Similar to Alexa's "Hey Alexa" wake word
- **Command Following**: After saying "Hey Ava", it listens for your complete command
- **MP3 Recording**: Saves high-quality MP3 files (if pydub is installed)
- **Metadata Storage**: Keeps track of all interactions with timestamps
- **Microphone Calibration**: Automatically adjusts to ambient noise levels
- **Flexible Recognition**: Understands variations and slightly misheard commands

## Installation Requirements

To make the system work properly, you need:

```
pip install SpeechRecognition sounddevice pydub
```

For MP3 conversion, you also need FFmpeg installed on your system:
- Windows: Install from https://ffmpeg.org/download.html and add to PATH
- Mac: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg`

## Running the Application

Simply run the application with:
```
python main.py
```

## Recorded Files

The system saves several files in the `temp/` directory:

- `wake_[timestamp].mp3` - The "Hey Ava" wake word audio
- `command_[timestamp].mp3` - Your command after the wake word
- `metadata_[timestamp].json` - Data about the interaction

## Tips for Better Recognition

- Speak clearly and at a normal volume
- Wait for the VTuber to grow in size before saying your command
- Maintain consistent distance from your microphone
- Best wake words: "Hey Ava", "Hi Ava", "Hey Eva" (most reliable)
- The system will recalibrate periodically to adjust to noise

## Manual Activation

If voice recognition doesn't work, you can still press the **SPACEBAR** to simulate the "Hey Ava" command for testing.

## Troubleshooting

### No Sound Detected
- Check if your microphone is working in other applications
- Check Windows privacy settings to ensure the application can access your microphone
- Try speaking more clearly or adjusting your microphone volume
- When the app starts, it will calibrate to ambient noise - stay quiet during calibration

### General Notes
- Internet connection is required for the speech recognition to function
- The wake word detection uses Google's Speech Recognition API
- The application will automatically use manual mode (spacebar) if voice recognition fails 