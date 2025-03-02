# Ava Voice Assistant

A voice-activated assistant that listens for the wake phrase "Hi, Ava" and displays a circular window on top of all other windows.

## Features

- Always listens for the wake phrase "Hi, Ava"
- Circular UI with a black border and white background
- Stays on top of all other windows
- Slides up from the bottom of the screen when activated
- Slides down and hides when closed
- Draggable interface

## Installation

1. Make sure you have Node.js installed on your system.
2. Clone this repository.
3. Navigate to the frontend directory:
```
cd frontend
```
4. Install the dependencies:
```
npm install
```

## Usage

1. Start the application:
```
npm start
```
2. The application will run in the background, listening for the wake phrase.
3. Say "Hi, Ava" to activate the assistant.
4. Click the X button or click outside the window to close it.

## Technologies Used

- Electron - For creating the desktop application
- @electron/remote - For window control functionality
- Web Speech API - For voice recognition
- HTML/CSS/JavaScript - For the UI

## Future Enhancements

- Add more voice commands
- Integrate with AI services for intelligent responses
- Add settings to customize appearance and behavior
- Improve voice recognition accuracy
- Add text-to-speech for responses
