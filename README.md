# Ava Voice Assistant

A voice-activated assistant that listens for the wake phrase "Hey, Ava" and displays AVA, on the top right of your screen.

## Features

- Always listens for the wake phrase "Hey, Ava"
- Circular UI with a black border and white background
- Stays on top of all other windows

## Prerequisites

- Python 3.8 or higher
- Node.js (if using web components)
- Git

## Installation

1. Clone the repository.

```bash

```

2. Set up environment variables:

```bash
# Copy the example environment file
cp .env.example .env
```

3. Edit the `.env` file and add your API keys:

```
GROQ_API_KEY=your_api_key_here
perplexity_Key=your_perplexity_key_here
```

4. Set up the backend:

```bash
# Navigate to the backend directory
cd backend

# Create a virtual environment (recommended)
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

5. Set up the frontend:

```bash
# Navigate to the frontend directory from the project root
cd ../frontend

# Create a virtual environment (recommended)
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

1. Start the backend server:

```bash
# Make sure you're in the backend directory with the virtual environment activated
cd backend
python main.py
```

2. In a new terminal, start the frontend application:

```bash
# Make sure you're in the frontend directory with the virtual environment activated
cd frontend
python main.py
```

3. The application will run in the background, listening for the wake phrase.
4. Say "Hi, Ava" to activate the assistant.

## Technologies Used

- PyGame
- Groq API
- Perplexity Sonar Reasoning
- FastAPI
- SpeechRecognition library
- ModernGL
- ElevenLabs

## Future Enhancements

- Add more voice commands
- Integrate with AI services for intelligent responses
- Add settings to customize appearance and behavior
