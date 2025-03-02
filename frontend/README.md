# Borderless GLTF Model Viewer

This application renders the TokoVT GLTF model in a borderless window using PyGame and ModernGL.

## Features

- Borderless window with no title bar
- 3D rendering of GLTF models
- Window can be dragged by clicking and holding the left mouse button
- Press ESC to close the application

## Installation

1. Ensure you have Python 3.7+ installed
2. Set up a virtual environment (optional but recommended):
   ```
   python -m venv venv
   
   # On Windows
   venv\Scripts\activate
   
   # On macOS/Linux
   source venv/bin/activate
   ```

3. Install required dependencies:
   ```
   pip install -r requirements.txt
   ```

## Usage

Run the application:
```
python main.py
```

## Controls

- Click and drag anywhere in the window to move it
- Press ESC to exit

## Model Credits

The TokoVT model is licensed under CC-BY-NC-4.0:
- Title: TokoVT
- Source: https://sketchfab.com/3d-models/tokovt-9d35f44614c1428eaa32d76e0415d9d2
- Author: Doppel_Kaku (https://sketchfab.com/Doppel_Kaku)

## Troubleshooting

If you encounter OpenGL-related errors, ensure your graphics drivers are up to date. This application requires OpenGL 3.3+ support. 