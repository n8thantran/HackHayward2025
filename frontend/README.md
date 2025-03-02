# TokoVT Frontend with Groq Voice Recognition

This folder contains the frontend application for the TokoVT model viewer with voice recognition capabilities.

## Setup

1. Install the required dependencies:

```bash
pip install -r requirements.txt
```

2. Create a `.env` file in the frontend folder with your Groq API key:

```
GROQ_API_KEY=your_groq_api_key_here
```

You can get a Groq API key by signing up at [https://console.groq.com/](https://console.groq.com/).

## Running the Application

Run the application from the frontend folder:

```bash
python main.py
```

## Using Voice Recognition

The application uses Groq's Whisper model for enhanced wake word detection. To interact with the virtual model:

1. Say "Hey Ava" or "Hi Ava" to activate the model
2. After activation, the model will listen for your command
3. The model will return to idle state after a few seconds

## Features

- Enhanced wake word detection using Groq's Whisper model
- Fallback to Google Speech Recognition if Groq is unavailable
- Natural head movements and responses
- Audio and transcription logging for review

## Troubleshooting

If you encounter issues with voice recognition:

- Ensure your microphone is properly connected and set as the default device
- Check that your Groq API key is correct in the .env file
- Press the SPACE key for manual activation (for testing purposes)
- Press ESC to exit the application 