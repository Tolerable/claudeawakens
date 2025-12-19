# Claude Query Configuration

## Webcam Setup (Presence Detection)

Presence detection uses a webcam + Ollama llava to determine if a human is sitting at the desk.

### Requirements
1. **Webcam**: Any USB webcam (tested with Logitech C270)
2. **Ollama**: Install from https://ollama.ai
3. **llava model**: Run `ollama pull llava:7b`

### Configuration

Edit the constants at the top of `claude_query.py`:

```python
# Webcam index (0 = first webcam, 1 = second, etc.)
WEBCAM_INDEX = 0

# Ollama API endpoint
OLLAMA_URL = "http://localhost:11434/api/generate"
```

### Finding Your Webcam Index

```python
import cv2
for i in range(5):
    cap = cv2.VideoCapture(i)
    if cap.isOpened():
        print(f"Camera {i}: Available")
        cap.release()
```

## Text-to-Speech (TTS)

By default, uses `pyttsx3` for cross-platform TTS. Falls back to system beep if unavailable.

### Default Setup
```bash
pip install pyttsx3
```

### Advanced TTS Options

For better quality voice, you can modify the voice announcement section to use:

**ElevenLabs** (High quality, requires API key):
```python
from elevenlabs import generate, play
audio = generate(text="Decision needed", voice="Rachel")
play(audio)
```

**Azure Speech** (High quality, requires Azure subscription):
```python
import azure.cognitiveservices.speech as speechsdk
speech_config = speechsdk.SpeechConfig(subscription="key", region="region")
synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)
synthesizer.speak_text("Decision needed")
```

**Google Cloud TTS**:
```python
from google.cloud import texttospeech
client = texttospeech.TextToSpeechClient()
# ... standard Google TTS code
```

## Settings File

All persistent settings stored in `claude_query_settings.json`:

```json
{
    "mute": false,
    "hotbar_row": 0,
    "custom_hotbars": [
        [["YES", "YES"], ["NO", "NO"], ...]
    ]
}
```

## Default Hotbar Rows

```python
DEFAULT_HOTBARS = [
    # Row 1: Quick Answers
    [("YES", "YES"), ("NO", "NO"), ("DUNNO", "DUNNO"), ("YOU DO IT", "YOU DO IT"), ("", ""), ("", "")],
    # Row 2: Development
    [("APPROVED", "APPROVED"), ("REJECTED", "REJECTED"), ("LATER", "LATER"), ("SKIP", "SKIP"), ("", ""), ("", "")],
    # Row 3: Detailed
    [("GOOD", "GOOD - looks correct"), ("BAD", "BAD - fix this"), ("PERFECT", "PERFECT!"), ("MEH", "MEH - not important"), ("", ""), ("", "")],
    # Row 4: Actions
    [("PUSH", "Push to GitHub"), ("TEST", "Run tests first"), ("PAUSE", "Pause and wait"), ("CONTINUE", "Continue working"), ("", ""), ("", "")],
]
```

Customize these in the settings modal or edit `claude_query_settings.json` directly.

## Color Scheme

```python
BG_COLOR = "#1a1a2e"       # Dark blue background
FG_COLOR = "#eaeaea"       # Light text
ACCENT_COLOR = "#4a9eff"   # Blue accent
BUTTON_BG = "#2d2d44"      # Button background
YES_COLOR = "#2d5a2d"      # Green for positive
NO_COLOR = "#5a2d2d"       # Red for negative
```

## Troubleshooting

### Webcam not detected
- Check WEBCAM_INDEX value
- Ensure no other app is using the webcam
- Try running as administrator

### Ollama connection failed
- Ensure Ollama is running: `ollama serve`
- Check OLLAMA_URL matches your setup
- Verify llava model is installed: `ollama list`

### TTS not working
- Install pyttsx3: `pip install pyttsx3`
- On Linux, may need espeak: `sudo apt install espeak`
- Check mute toggle in the panel

### Drag-drop not working
- Install tkinterdnd2: `pip install tkinterdnd2`
- Use the "Browse" or "Paste" buttons as alternatives
