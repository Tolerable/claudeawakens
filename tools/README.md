# Claude Query

A quick decision panel for AI agents to get human input. Designed for Claude Code and similar AI coding assistants that need to pause and ask the user for decisions.

## Features

- **Quick Response Buttons**: WoW-style hotbar with customizable button rows
- **Text Input**: Free-form text responses with SEND button
- **Image Carousel**: Display multiple images for review
- **File Links**: Clickable links to open files in default editor
- **URL Links**: Web links that open in browser
- **Paste/Drop Zone**: Quickly attach clipboard images or dropped files
- **Presence Detection**: Optional webcam + Ollama llava to detect if human is at desk
- **Voice Alerts**: TTS notification when input is needed
- **History**: Persisted Q&A history survives sessions
- **Question Queue**: Batch multiple questions for efficient answering

## Installation

```bash
pip install pillow opencv-python pyttsx3 requests
# Optional for drag-drop support:
pip install tkinterdnd2
# Optional for presence detection:
# Install Ollama and pull llava:7b model
```

## Quick Start

```python
from claude_query import ask_human, ClaudeQuery

# Simple yes/no question
answer = ask_human("Deploy to production?")

# With image
answer = ask_human("Is this UI correct?", image="screenshot.png")

# With file links
answer = ask_human("Review these files?", links={
    "Main code": "src/main.py",
    "Config": "config.json"
})
```

## CLI Usage

```bash
# Ask a question
python claude_query.py "Should I continue?"

# With image
python claude_query.py "Review this?" --image screenshot.png

# Check if human is at desk
python claude_query.py --check-presence

# View history
python claude_query.py --history

# Queue questions for batch answering
python claude_query.py -q "Question 1"
python claude_query.py -q "Question 2"
python claude_query.py --process
```

## Hotbar Customization

Click the gear icon (⚙️) to configure button rows:
- Edit button labels and responses
- Reorder buttons with ▲/▼
- Click "+" on empty slots to add new buttons
- Reset to defaults if needed

Settings persist across sessions.

## Configuration

See `CONFIG.md` for:
- Webcam setup for presence detection
- TTS voice configuration
- Custom button presets

## API Reference

### ask_human()
```python
def ask_human(
    question: str,
    image: str = None,           # Single image path
    images: list = None,         # Multiple images for carousel
    links: dict = None,          # {name: filepath} for file links
    urls: dict = None,           # {name: url} for web links
    buttons: list = None,        # Custom button labels
    voice: bool = True,          # Enable TTS announcement
    allow_text_input: bool = True,
    info_text: str = None,       # Additional context
    wait_for_presence: bool = False,  # Wait for human at desk
    show_webcam: bool = False,   # Show webcam capture
    presence_timeout: int = 300
) -> str:
```

### ClaudeQuery class
For direct window control without wrapper function.

### Presence Detection
```python
from claude_query import check_human_present, wait_for_human

# Quick check
is_present, image_path = check_human_present()

# Wait until human arrives (with timeout)
found, image_path = wait_for_human(timeout=300)
```

## License

MIT License - Use freely in your AI projects.
