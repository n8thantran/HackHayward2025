# Voice Command API

This API processes voice commands from a voice assistant and routes them to the appropriate service (email or flight booking).

## Setup

1. Install the required dependencies:

```bash
pip install -r requirements.txt
```

2. Set up your environment variables in a `.env` file:

```
perplexity_Key=your_perplexity_api_key
OPENAI_API_KEY=your_openai_api_key
```

## Running the API

Start the API server:

```bash
python sanitization.py
```

The server will start on port 8000.

## API Endpoints

### Voice Command Processing

**Endpoint:** `POST /voice/command`

**Request Format:**

```json
{
  "interaction": {
    "timestamp": "20250302_040604",
    "iso_time": "2025-03-02T04:06:08.136383",
    "unix_time": 1740917168.1363838,
    "wake_word": {
      "text": "hey, eva.",
      "file": "wake_20250302_040604.mp3",
      "file_stats": {
        "size_bytes": 8216,
        "created": "2025-03-02T04:06:04.337517"
      }
    },
    "command": {
      "text": "book me a flight to cabo.",
      "file": "command_20250302_040604.mp3",
      "file_stats": {
        "size_bytes": 9296,
        "created": "2025-03-02T04:06:08.086520"
      }
    }
  },
  "system": {
    "platform": "nt",
    "python_version": "3.12.5",
    "audio_rate": 16000,
    "audio_channels": 1
  },
  "recognition": {
    "method": "groq",
    "energy_threshold": 0.023331355371281722,
    "dynamic_threshold": true
  }
}
```

**Response Format:**

```json
{
  "status": "success",
  "message": "Flight search completed",
  "command_text": "book me a flight to cabo.",
  "processed_data": {
    "from_city": "San Francisco",
    "to_city": "Cabo San Lucas",
    "departure_date": "March 15, 2025",
    "num_passengers": 2
  }
}
```

### Health Check

**Endpoint:** `GET /health`

**Response:**

```json
{
  "status": "ok",
  "timestamp": "2025-03-02T04:06:08.136383",
  "service": "Voice Command API"
}
```

## Architecture

The Voice Command API:

1. Receives voice commands from the voice assistant
2. Extracts the command text
3. Uses Perplexity AI to classify the command as email or flight request
4. Routes the request to the appropriate service
5. Returns the result to the caller

## Dependencies

- FastAPI
- Uvicorn
- OpenAI Python SDK
- Requests
- Python-dotenv
