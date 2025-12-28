"""
CLAUDE QUERY - Quick decision panel for Claude to get human input
==================================================================
Popup panel with quick answer buttons, image preview, and file links.
Includes presence detection via webcam + Ollama llava.

Usage:
    from claude_query import ask_human, ClaudeQuery, check_human_present

    # Simple yes/no question
    answer = ask_human("Deploy to production?")

    # With image preview
    answer = ask_human("Is this UI correct?", image="screenshot.png")

    # With file links
    answer = ask_human("Review these files?", links={
        "Main code": "C:/path/to/file.py",
        "Config": "C:/path/to/config.json"
    })

    # Wait for human to be at desk before showing panel
    answer = ask_human("Need your input", wait_for_presence=True)

    # Check presence without panel
    if check_human_present():
        print("Human is at desk!")

    # Full options
    answer = ask_human(
        "Should I refactor this module?",
        image="diagram.png",
        links={"Source": "module.py"},
        voice=True,  # Announce via TTS
        buttons=["YES", "NO", "LATER", "YOU DO IT"],
        wait_for_presence=True,  # Wait for human first
        show_webcam=True  # Show webcam capture in panel
    )

Returns: The button text clicked (e.g., "YES", "NO", "DUNNO", "YOU DO IT")
         or None if window closed without selection
"""

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import os
import subprocess
import sys
import time
import base64
import requests
import cv2
from pathlib import Path
from datetime import datetime

# Try to import TkinterDnD2 for drag-drop support
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False

# Default buttons
DEFAULT_BUTTONS = ["YES", "NO", "DUNNO", "YOU DO IT"]

# Hotbar rows - WoW-style button bars
# Each row is a list of (label, response) tuples
# Empty slots use ("", "") - configurable by user
DEFAULT_HOTBARS = [
    # Row 1: Quick Answers + 2 empty slots
    [("YES", "YES"), ("NO", "NO"), ("DUNNO", "DUNNO"), ("YOU DO IT", "YOU DO IT"), ("", ""), ("", "")],
    # Row 2: Development + 2 empty slots
    [("APPROVED", "APPROVED"), ("REJECTED", "REJECTED"), ("LATER", "LATER"), ("SKIP", "SKIP"), ("", ""), ("", "")],
    # Row 3: Detailed + 2 empty slots
    [("GOOD", "GOOD - looks correct"), ("BAD", "BAD - fix this"), ("PERFECT", "PERFECT!"), ("MEH", "MEH - not important"), ("", ""), ("", "")],
    # Row 4: Actions + 2 empty slots
    [("PUSH", "Push to GitHub"), ("TEST", "Run tests first"), ("PAUSE", "Pause and wait"), ("CONTINUE", "Continue working"), ("", ""), ("", "")],
]

# Settings file for persistent state
SETTINGS_FILE = Path(__file__).parent / "claude_query_settings.json"

def get_mute_state():
    """Load mute state from settings file."""
    import json
    if SETTINGS_FILE.exists():
        try:
            settings = json.loads(SETTINGS_FILE.read_text())
            return settings.get("mute", False)
        except:
            pass
    return False

def set_mute_state(muted):
    """Save mute state to settings file."""
    import json
    settings = {}
    if SETTINGS_FILE.exists():
        try:
            settings = json.loads(SETTINGS_FILE.read_text())
        except:
            pass
    settings["mute"] = muted
    SETTINGS_FILE.write_text(json.dumps(settings))


def get_listen_state():
    """Load voice-to-text listen state from settings file."""
    import json
    if SETTINGS_FILE.exists():
        try:
            settings = json.loads(SETTINGS_FILE.read_text())
            return settings.get("listen", False)  # Disabled by default
        except:
            pass
    return False


def set_listen_state(enabled):
    """Save voice-to-text listen state to settings file."""
    import json
    settings = {}
    if SETTINGS_FILE.exists():
        try:
            settings = json.loads(SETTINGS_FILE.read_text())
        except:
            pass
    settings["listen"] = enabled
    SETTINGS_FILE.write_text(json.dumps(settings))


def get_hotbar_row():
    """Get current hotbar row from settings."""
    import json
    if SETTINGS_FILE.exists():
        try:
            settings = json.loads(SETTINGS_FILE.read_text())
            return settings.get("hotbar_row", 0)
        except:
            pass
    return 0


def set_hotbar_row(row):
    """Save current hotbar row to settings."""
    import json
    settings = {}
    if SETTINGS_FILE.exists():
        try:
            settings = json.loads(SETTINGS_FILE.read_text())
        except:
            pass
    settings["hotbar_row"] = row
    SETTINGS_FILE.write_text(json.dumps(settings))


def get_custom_hotbars():
    """Get custom hotbar configurations from settings."""
    import json
    if SETTINGS_FILE.exists():
        try:
            settings = json.loads(SETTINGS_FILE.read_text())
            custom = settings.get("custom_hotbars", None)
            if custom:
                # Convert list of lists back to list of list of tuples
                return [[tuple(btn) for btn in row] for row in custom]
        except:
            pass
    return None


def save_custom_hotbars(hotbars):
    """Save custom hotbar configurations to settings."""
    import json
    settings = {}
    if SETTINGS_FILE.exists():
        try:
            settings = json.loads(SETTINGS_FILE.read_text())
        except:
            pass
    # Convert list of tuples to list of lists for JSON
    settings["custom_hotbars"] = [[list(btn) for btn in row] for row in hotbars]
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))

# Colors
BG_COLOR = "#1a1a2e"
FG_COLOR = "#eaeaea"
ACCENT_COLOR = "#4a9eff"
BUTTON_BG = "#2d2d44"
BUTTON_HOVER = "#3d3d5c"
YES_COLOR = "#2d5a2d"
NO_COLOR = "#5a2d2d"

# Presence detection config
WEBCAM_INDEX = 0  # C270 #1
OLLAMA_URL = "http://localhost:11434/api/generate"
SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"
SNAPSHOTS_DIR.mkdir(exist_ok=True)

# Pasted content storage (accessible to Claude)
PASTED_TEXT_FILE = Path(__file__).parent / "claude_query_pasted_content.txt"
PASTED_IMAGE_FILE = Path(__file__).parent / "claude_query_pasted_image.png"


# === PRESENCE DETECTION ===

def capture_webcam(camera_index=WEBCAM_INDEX, save=True):
    """Capture frame from webcam. Returns (image_path, base64) or (None, None) on error."""
    try:
        cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            return None, None

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        # Warmup frames
        for _ in range(10):
            cap.read()
            time.sleep(0.05)

        ret, frame = cap.read()
        cap.release()

        if not ret:
            return None, None

        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = SNAPSHOTS_DIR / f"presence_{timestamp}.jpg"
        cv2.imwrite(str(filename), frame)

        # Also encode to base64
        _, buffer = cv2.imencode('.jpg', frame)
        b64 = base64.b64encode(buffer).decode('utf-8')

        return str(filename), b64

    except Exception as e:
        print(f"[ClaudeQuery] Webcam capture error: {e}")
        return None, None


def check_presence_ollama(image_b64):
    """Ask Ollama llava if a person is present. Returns True/False."""
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": "llava:7b",
            "prompt": "Is there a person sitting at the desk in this image? Answer only YES or NO.",
            "images": [image_b64],
            "stream": False
        }, timeout=60)

        if response.status_code == 200:
            result = response.json().get("response", "").strip().upper()
            return "YES" in result
    except Exception as e:
        print(f"[ClaudeQuery] Ollama presence check error: {e}")

    return False


def check_human_present(camera_index=WEBCAM_INDEX):
    """
    Check if human is at desk using webcam + Ollama llava.

    Returns:
        tuple: (is_present: bool, image_path: str or None)
    """
    image_path, b64 = capture_webcam(camera_index)
    if not b64:
        return False, None

    is_present = check_presence_ollama(b64)
    return is_present, image_path


def analyze_human_state(image_b64):
    """
    Deep analysis of human's emotional state and activity.
    Separate call from presence check to avoid bias.

    Returns:
        dict: {emotion, activity, holding, posture, notes}
    """
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": "llava:7b",
            "prompt": """Analyze this image. If a person is visible, describe:
1. EMOTION: What emotion do they seem to be expressing? (happy, sad, frustrated, focused, tired, neutral, stressed, relaxed)
2. ACTIVITY: What are they doing? (working, eating, drinking, smoking, talking, idle, sleeping)
3. HOLDING: What are they holding or interacting with? (phone, food, drink, cigarette, nothing, keyboard/mouse)
4. POSTURE: How are they sitting? (upright, slouched, leaning, turned away)
5. CONCERN: Anything concerning? (distress, confusion, needs help)

Be brief and direct. One word or short phrase per item.""",
            "images": [image_b64],
            "stream": False
        }, timeout=90)

        if response.status_code == 200:
            result = response.json().get("response", "").strip()
            return {"raw": result, "success": True}
    except Exception as e:
        print(f"[ClaudeQuery] State analysis error: {e}")

    return {"raw": "", "success": False}


def full_human_check(camera_index=WEBCAM_INDEX):
    """
    Two-pass human check:
    1. Simple presence (fast, reliable)
    2. Deep state analysis (emotional read, activity)

    Uses same image for both to ensure consistency.

    Returns:
        dict: {
            present: bool,
            state: dict (emotion, activity, etc),
            image_path: str
        }
    """
    # Capture once
    image_path, b64 = capture_webcam(camera_index)
    if not b64:
        return {"present": False, "state": None, "image_path": None}

    # Pass 1: Simple presence
    is_present = check_presence_ollama(b64)

    # Pass 2: Deep state (only if present)
    state = None
    if is_present:
        state = analyze_human_state(b64)

    return {
        "present": is_present,
        "state": state,
        "image_path": image_path
    }


def wait_for_human(check_interval=10, timeout=300, camera_index=WEBCAM_INDEX):
    """
    Wait until human is detected at desk.

    Args:
        check_interval: Seconds between checks
        timeout: Max seconds to wait (0 = forever)
        camera_index: Webcam to use

    Returns:
        tuple: (found: bool, image_path: str or None)
    """
    start = time.time()
    print("[ClaudeQuery] Waiting for human at desk...")

    while True:
        is_present, image_path = check_human_present(camera_index)
        if is_present:
            print("[ClaudeQuery] Human detected!")
            return True, image_path

        elapsed = time.time() - start
        if timeout > 0 and elapsed >= timeout:
            print("[ClaudeQuery] Timeout waiting for human")
            return False, image_path

        print(f"[ClaudeQuery] Not at desk, checking again in {check_interval}s...")
        time.sleep(check_interval)


class ImagePopup(tk.Toplevel):
    """Fullsize image popup - click anywhere to close."""

    def __init__(self, parent, image_path):
        super().__init__(parent)
        self.title("Image Preview")
        self.configure(bg="#000000")

        # Load and display image at full size (or screen-fitted)
        img = Image.open(image_path)

        # Get screen dimensions
        screen_w = self.winfo_screenwidth() - 100
        screen_h = self.winfo_screenheight() - 100

        # Scale if needed
        img_w, img_h = img.size
        if img_w > screen_w or img_h > screen_h:
            ratio = min(screen_w / img_w, screen_h / img_h)
            new_size = (int(img_w * ratio), int(img_h * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        self.photo = ImageTk.PhotoImage(img)

        label = tk.Label(self, image=self.photo, bg="#000000")
        label.pack(fill=tk.BOTH, expand=True)

        # Click anywhere to close
        label.bind("<Button-1>", lambda e: self.destroy())
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Button-1>", lambda e: self.destroy())

        # Center on screen
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"+{x}+{y}")

        # Make it modal-ish
        self.transient(parent)
        self.grab_set()
        self.focus_set()


# Use TkinterDnD.Tk if available, otherwise fallback to tk.Tk
_BaseClass = TkinterDnD.Tk if HAS_DND else tk.Tk


class ClaudeQuery(_BaseClass):
    """Main query panel window with text input, image carousel, and links."""

    def __init__(self, question, image=None, images=None, links=None, urls=None,
                 buttons=None, allow_text_input=True, info_text=None, auto_speak=True,
                 listen_mode=False, silence_timeout=3):
        """
        Args:
            question: The question to ask
            image: Single image path (legacy support)
            images: List of image paths for carousel
            links: Dict of {name: filepath} for file links
            urls: Dict of {name: url} for web links
            buttons: List of button labels
            allow_text_input: Show text input field
            info_text: Additional info to display
            auto_speak: Speak question text via TTS on open (default True)
            listen_mode: Enable voice-to-text listening (default False)
            silence_timeout: Seconds of silence before submitting voice input (default 3)
        """
        super().__init__()

        self.question = question
        # Support both single image and image list
        if images:
            self.images = [img for img in images if img and os.path.exists(img)]
        elif image and os.path.exists(image):
            self.images = [image]
        else:
            self.images = []
        self.current_image_idx = 0
        self.links = links or {}
        self.urls = urls or {}
        self.buttons = buttons or DEFAULT_BUTTONS
        self.allow_text_input = allow_text_input
        self.info_text = info_text
        self.auto_speak = auto_speak
        self.listen_mode = listen_mode
        self.silence_timeout = silence_timeout
        self.listening = False
        self.submit_countdown = -1  # -1 = no countdown active, 0 = submit, >0 = counting
        self.result = None
        self.text_result = None
        self.attachments = []  # List of attached file paths

        self._setup_window()
        self._create_widgets()

        # Auto-speak question if enabled and not muted
        # Check if listening should be enabled (from param OR settings checkbox)
        should_listen = self.listen_mode or get_listen_state()

        if self.auto_speak and not get_mute_state():
            self.after(100, self._speak_question)
            # Start listening after TTS finishes (estimate with buffer for slower rate)
            if should_listen:
                # ~100ms per char at rate 160, plus 2s buffer
                delay = max(3000, len(question) * 100 + 2000)
                self.after(delay, self._start_listening)
        elif should_listen:
            # No TTS, start listening immediately
            self.after(500, self._start_listening)

    def _setup_window(self):
        """Configure the main window."""
        self.title("CLAUDE QUERY")
        self.configure(bg=BG_COLOR)

        # Always on top
        self.attributes("-topmost", True)

        # Calculate window size based on content
        width = 650
        height = 350  # Base height (increased for scrollable question)

        # Add height for question text (now scrollable, so cap the extra height)
        question_lines = len(self.question) // 55 + self.question.count('\n') + 1
        extra_q_height = min(200, max(0, (question_lines - 3) * 22))  # Cap at 200px extra
        height += extra_q_height

        if self.images:
            height += 180  # Image area
        if self.links or self.urls:
            height += 30 + max(len(self.links), len(self.urls)) * 22
        if self.allow_text_input:
            height += 60
        if self.info_text:
            height += 60

        height = min(height, 900)  # Cap max height

        # Center on screen
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda e: self._on_close())
        self.bind("<Return>", lambda e: self._submit_text())

    def _create_widgets(self):
        """Build the UI."""
        # Main container with padding
        main = tk.Frame(self, bg=BG_COLOR, padx=20, pady=15)
        main.pack(fill=tk.BOTH, expand=True)

        # === CLAUDE'S CONTENT FRAME (visually separated) ===
        content_frame = tk.Frame(main, bg="#1f1f35", relief=tk.RIDGE, bd=2, padx=12, pady=10)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        # Header row with title and mute toggle
        header_frame = tk.Frame(content_frame, bg="#1f1f35")
        header_frame.pack(fill=tk.X)

        header = tk.Label(
            header_frame,
            text="CLAUDE NEEDS INPUT",
            font=("Segoe UI", 10, "bold"),
            fg=ACCENT_COLOR,
            bg="#1f1f35"
        )
        header.pack(side=tk.LEFT)

        # PING button - notify Claude that user is waiting
        self.ping_btn = tk.Button(
            header_frame,
            text="🔔 PING",
            font=("Segoe UI", 9, "bold"),
            fg="#ffaa00",  # Orange/yellow to stand out
            bg="#1f1f35",
            activebackground="#1f1f35",
            activeforeground="#ffcc44",
            relief=tk.FLAT,
            cursor="hand2",
            command=self._ping_claude
        )
        self.ping_btn.pack(side=tk.RIGHT, padx=(0, 10))

        # History button
        history_btn = tk.Button(
            header_frame,
            text="📜 History",
            font=("Segoe UI", 9),
            fg="#888888",
            bg="#1f1f35",
            activebackground="#1f1f35",
            activeforeground="#aaaaaa",
            relief=tk.FLAT,
            cursor="hand2",
            command=self._show_history_popup
        )
        history_btn.pack(side=tk.RIGHT, padx=(0, 5))

        # Browse button (opens file dialog for images)
        browse_btn = tk.Button(
            header_frame,
            text="📂 Browse",
            font=("Segoe UI", 9),
            fg="#cc66cc",
            bg="#1f1f35",
            activebackground="#1f1f35",
            activeforeground="#ee88ee",
            relief=tk.FLAT,
            cursor="hand2",
            command=self._browse_file
        )
        browse_btn.pack(side=tk.RIGHT, padx=(0, 5))

        # Paste from clipboard button
        paste_btn = tk.Button(
            header_frame,
            text="📋 Paste",
            font=("Segoe UI", 9),
            fg="#66cc66",
            bg="#1f1f35",
            activebackground="#1f1f35",
            activeforeground="#88ee88",
            relief=tk.FLAT,
            cursor="hand2",
            command=self._paste_from_clipboard
        )
        paste_btn.pack(side=tk.RIGHT, padx=(0, 5))

        # Listen toggle (voice-to-text)
        self.listen_var = tk.BooleanVar(value=get_listen_state())
        listen_cb = tk.Checkbutton(
            header_frame,
            text="🎤 Listen",
            variable=self.listen_var,
            command=self._toggle_listen,
            font=("Segoe UI", 9),
            fg="#888888",
            bg="#1f1f35",
            selectcolor="#1f1f35",
            activebackground="#1f1f35",
            activeforeground="#888888"
        )
        listen_cb.pack(side=tk.RIGHT, padx=(0, 10))

        # Mute toggle
        self.mute_var = tk.BooleanVar(value=get_mute_state())
        mute_cb = tk.Checkbutton(
            header_frame,
            text="🔇 Mute",
            variable=self.mute_var,
            command=self._toggle_mute,
            font=("Segoe UI", 9),
            fg="#888888",
            bg="#1f1f35",
            selectcolor="#1f1f35",
            activebackground="#1f1f35",
            activeforeground="#888888"
        )
        mute_cb.pack(side=tk.RIGHT)

        # Listen status - simple indicator, not pushing content down
        # Will be shown to the LEFT of the title, not overlapping checkboxes
        self.listen_indicator = tk.Label(
            header_frame,
            text="",
            font=("Segoe UI", 14, "bold"),
            fg="#ff6b6b",  # Red to stand out
            bg="#1f1f35"
        )
        # Don't pack yet - will show when listening starts

        # Question text - use scrollable Text widget for long questions
        question_frame = tk.Frame(content_frame, bg="#1f1f35")
        question_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 10))

        # Calculate needed height based on text length (approx 55 chars per line)
        num_lines = max(3, min(15, len(self.question) // 55 + self.question.count('\n') + 2))

        q_text = tk.Text(
            question_frame,
            font=("Segoe UI", 12),
            fg=FG_COLOR,
            bg="#1f1f35",
            wrap=tk.WORD,
            height=num_lines,
            relief=tk.FLAT,
            padx=5,
            pady=5,
            cursor="arrow"
        )
        q_text.insert("1.0", self.question)
        q_text.config(state=tk.DISABLED)  # Read-only

        # Add scrollbar if text is long
        if len(self.question) > 300 or self.question.count('\n') > 5:
            scrollbar = tk.Scrollbar(question_frame, command=q_text.yview)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            q_text.config(yscrollcommand=scrollbar.set)

        q_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Info text (if provided)
        if self.info_text:
            info_frame = tk.Frame(content_frame, bg="#252540", padx=10, pady=8)
            info_frame.pack(fill=tk.X, pady=(0, 10))
            info_label = tk.Label(
                info_frame,
                text=self.info_text,
                font=("Consolas", 9),
                fg="#aaaaaa",
                bg="#252540",
                wraplength=530,
                justify=tk.LEFT
            )
            info_label.pack(anchor="w")

        # Image carousel (if images provided)
        if self.images:
            self._create_image_carousel(content_frame)

        # Links sections
        if self.links or self.urls:
            self._create_links_section(content_frame)

        # Attachments bar (for paste/drop files)
        self._create_attachments_bar(content_frame)

        # === INPUT SECTION (below the content frame) ===
        # Text input (if enabled)
        if self.allow_text_input:
            self._create_text_input(main)

        # Buttons
        self._create_buttons(main)

    def _create_image_carousel(self, parent):
        """Create image carousel with prev/next buttons."""
        parent_bg = parent.cget("bg")
        carousel_frame = tk.Frame(parent, bg=parent_bg)
        carousel_frame.pack(fill=tk.X, pady=(0, 10))

        # Navigation buttons and image display
        nav_frame = tk.Frame(carousel_frame, bg=parent_bg)
        nav_frame.pack(fill=tk.X)

        # Prev button
        self.prev_btn = tk.Button(
            nav_frame,
            text="<",
            font=("Segoe UI", 12, "bold"),
            fg=FG_COLOR,
            bg=BUTTON_BG,
            width=3,
            command=self._prev_image,
            state=tk.DISABLED if len(self.images) <= 1 else tk.NORMAL
        )
        self.prev_btn.pack(side=tk.LEFT, padx=(0, 10))

        # Image container
        self.img_container = tk.Frame(nav_frame, bg=parent_bg)
        self.img_container.pack(side=tk.LEFT, expand=True)
        self._carousel_bg = parent_bg  # Store for image loading

        # Next button
        self.next_btn = tk.Button(
            nav_frame,
            text=">",
            font=("Segoe UI", 12, "bold"),
            fg=FG_COLOR,
            bg=BUTTON_BG,
            width=3,
            command=self._next_image,
            state=tk.DISABLED if len(self.images) <= 1 else tk.NORMAL
        )
        self.next_btn.pack(side=tk.RIGHT, padx=(10, 0))

        # Image counter
        self.img_counter = tk.Label(
            carousel_frame,
            text=f"1/{len(self.images)}",
            font=("Segoe UI", 9),
            fg="#888888",
            bg=parent_bg
        )
        self.img_counter.pack(pady=(5, 0))

        # Load first image
        self._load_current_image()

    def _load_current_image(self):
        """Load and display the current image in carousel."""
        # Clear previous
        for widget in self.img_container.winfo_children():
            widget.destroy()

        if not self.images:
            return

        img_path = self.images[self.current_image_idx]
        bg = getattr(self, '_carousel_bg', BG_COLOR)

        try:
            img = Image.open(img_path)
            # Thumbnail size for carousel
            img.thumbnail((350, 150), Image.Resampling.LANCZOS)
            self.current_photo = ImageTk.PhotoImage(img)

            img_label = tk.Label(
                self.img_container,
                image=self.current_photo,
                bg=bg,
                cursor="hand2",
                relief=tk.RIDGE,
                borderwidth=2
            )
            img_label.pack()
            img_label.bind("<Button-1>", lambda e: ImagePopup(self, img_path))

            # Update counter
            self.img_counter.config(text=f"{self.current_image_idx + 1}/{len(self.images)}")

            # Show filename
            filename = os.path.basename(img_path)
            name_label = tk.Label(
                self.img_container,
                text=filename[:40] + "..." if len(filename) > 40 else filename,
                font=("Consolas", 8),
                fg="#666666",
                bg=bg
            )
            name_label.pack()

        except Exception as e:
            err_label = tk.Label(
                self.img_container,
                text=f"[Error loading image: {e}]",
                fg="#ff6666",
                bg=bg
            )
            err_label.pack()

    def _prev_image(self):
        """Show previous image in carousel."""
        if self.current_image_idx > 0:
            self.current_image_idx -= 1
            self._load_current_image()

    def _next_image(self):
        """Show next image in carousel."""
        if self.current_image_idx < len(self.images) - 1:
            self.current_image_idx += 1
            self._load_current_image()

    def _create_links_section(self, parent):
        """Create file links and URL links sections."""
        parent_bg = parent.cget("bg")
        links_frame = tk.Frame(parent, bg=parent_bg)
        links_frame.pack(fill=tk.X, pady=(0, 10))

        # File links
        if self.links:
            files_header = tk.Label(
                links_frame,
                text="Files:",
                font=("Segoe UI", 9, "bold"),
                fg="#aaaaaa",
                bg=parent_bg
            )
            files_header.pack(anchor="w")

            for name, path in self.links.items():
                link = tk.Label(
                    links_frame,
                    text=f"  {name}: {path}",
                    font=("Consolas", 9),
                    fg=ACCENT_COLOR,
                    bg=parent_bg,
                    cursor="hand2"
                )
                link.pack(anchor="w")
                link.bind("<Button-1>", lambda e, p=path: self._open_file(p))
                link.bind("<Enter>", lambda e, l=link: l.configure(fg="#7fbfff"))
                link.bind("<Leave>", lambda e, l=link: l.configure(fg=ACCENT_COLOR))

        # URL links
        if self.urls:
            if self.links:
                tk.Label(links_frame, text="", bg=parent_bg).pack()  # Spacer

            urls_header = tk.Label(
                links_frame,
                text="Links:",
                font=("Segoe UI", 9, "bold"),
                fg="#aaaaaa",
                bg=parent_bg
            )
            urls_header.pack(anchor="w")

            for name, url in self.urls.items():
                link = tk.Label(
                    links_frame,
                    text=f"  {name}: {url[:50]}{'...' if len(url) > 50 else ''}",
                    font=("Consolas", 9),
                    fg="#66ccff",
                    bg=parent_bg,
                    cursor="hand2"
                )
                link.pack(anchor="w")
                link.bind("<Button-1>", lambda e, u=url: self._open_url(u))
                link.bind("<Enter>", lambda e, l=link: l.configure(fg="#99ddff"))
                link.bind("<Leave>", lambda e, l=link: l.configure(fg="#66ccff"))

    def _create_text_input(self, parent):
        """Create text input field with SEND button for custom answers."""
        input_frame = tk.Frame(parent, bg=BG_COLOR)
        input_frame.pack(fill=tk.X, pady=(0, 10))

        input_label = tk.Label(
            input_frame,
            text="Or type response:",
            font=("Segoe UI", 9),
            fg="#888888",
            bg=BG_COLOR
        )
        input_label.pack(anchor="w")

        # Row with entry + send button
        entry_row = tk.Frame(input_frame, bg=BG_COLOR)
        entry_row.pack(fill=tk.X, pady=(5, 0))

        self.text_entry = tk.Entry(
            entry_row,
            font=("Segoe UI", 11),
            fg=FG_COLOR,
            bg="#2d2d44",
            insertbackground=FG_COLOR,
            relief=tk.FLAT
        )
        self.text_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, padx=(0, 5))
        self.text_entry.bind("<Return>", lambda e: self._submit_text())
        # Stop listening if user starts typing
        self.text_entry.bind("<KeyRelease>", lambda e: self._on_user_typing())

        # SEND button - blue, rounded corners style
        self.send_btn = tk.Button(
            entry_row,
            text="SEND",
            font=("Segoe UI", 10, "bold"),
            fg="#ffffff",
            bg=ACCENT_COLOR,
            activeforeground="#ffffff",
            activebackground="#3a8aef",
            relief=tk.FLAT,
            padx=15,
            pady=5,
            cursor="hand2",
            command=self._submit_text
        )
        self.send_btn.pack(side=tk.LEFT, padx=(8, 0), ipady=2)

        # Hover effects
        self.send_btn.bind("<Enter>", lambda e: self.send_btn.configure(bg="#5ab0ff"))
        self.send_btn.bind("<Leave>", lambda e: self.send_btn.configure(bg=ACCENT_COLOR))

    def _on_user_typing(self):
        """Called when user types - stop listening and cancel any pending submit."""
        if hasattr(self, 'text_entry') and self.text_entry.get().strip():
            # Only cancel if actually listening or countdown active
            if self.listening or self.submit_countdown > 0:
                self._cancel_listening()

    def _cancel_listening(self):
        """Cancel listening and any pending submit countdown."""
        print("[ClaudeQuery] Cancelling listen mode")
        self.listening = False
        self.submit_countdown = -1  # Use -1 to indicate cancelled (0 means complete)
        self.title("CLAUDE QUERY")
        try:
            self.listen_indicator.pack_forget()
        except:
            pass
        # Update checkbox to unchecked
        if hasattr(self, 'listen_var'):
            self.listen_var.set(False)
        set_listen_state(False)

    def _submit_text(self):
        """Submit text input as result."""
        if hasattr(self, 'text_entry') and self.text_entry.get().strip():
            self.result = self.text_entry.get().strip()
            self.text_result = self.result
            self.destroy()

    def _speak_question(self):
        """Speak the question text via TTS in background thread."""
        import threading

        def speak():
            try:
                import pyttsx3
                engine = pyttsx3.init()
                # Slow down speech rate slightly (default ~200, use 160)
                engine.setProperty('rate', 160)
                # Speak the question text
                engine.say(self.question)
                engine.runAndWait()
            except Exception as e:
                # Fallback to beep if TTS fails
                try:
                    import winsound
                    winsound.MessageBeep()
                except:
                    pass

        # Run in background thread so it doesn't block UI
        thread = threading.Thread(target=speak, daemon=True)
        thread.start()

    def _start_listening(self):
        """Start voice-to-text listening in background thread."""
        import threading

        if self.listening:
            return

        # Check if listening is still enabled (user may have unchecked during TTS)
        if hasattr(self, 'listen_var') and not self.listen_var.get():
            print("[ClaudeQuery] Listen disabled, skipping auto-listen")
            return

        # Don't start listening if user is already typing
        if hasattr(self, 'text_entry') and self.text_entry.get().strip():
            print("[ClaudeQuery] User is typing, skipping auto-listen")
            return

        self.listening = True
        self.listen_paused = False
        self.listen_seconds = 0

        # Show simple indicator (asterisk for listening)
        self.listen_indicator.config(text="*")
        self.listen_indicator.pack(side=tk.LEFT, padx=(10, 0))

        # Update window title to show listening
        self.title("CLAUDE QUERY - 🎤 Listening...")

        def listen():
            try:
                import speech_recognition as sr
                recognizer = sr.Recognizer()

                # Set pause threshold - how long silence before phrase ends
                recognizer.pause_threshold = self.silence_timeout
                recognizer.non_speaking_duration = self.silence_timeout

                with sr.Microphone() as source:
                    # Adjust for ambient noise - show asterisk
                    self.after(0, lambda: self.listen_indicator.config(text="*"))
                    recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    self.after(0, lambda: self.listen_indicator.config(text="●"))

                    # Listen until silence is detected
                    try:
                        print(f"[ClaudeQuery] Listening... (waiting for {self.silence_timeout}s silence)")
                        audio = recognizer.listen(source, timeout=30)

                        # Check if cancelled BEFORE processing (user unchecked Listen)
                        if not self.listening:
                            print("[ClaudeQuery] Listening was cancelled, ignoring audio")
                            return

                        print("[ClaudeQuery] Processing speech...")
                        text = recognizer.recognize_google(audio)

                        # Check AGAIN after recognition (could have been cancelled during API call)
                        if not self.listening:
                            print("[ClaudeQuery] Listening was cancelled, ignoring result")
                            return

                        if text and text.strip():
                            recognized_text = text.strip()
                            print(f"[ClaudeQuery] Recognized: {recognized_text}")
                            # Show recognized text in input box
                            self.after(0, lambda t=recognized_text: self._show_voice_result(t))
                            return
                    except sr.WaitTimeoutError:
                        print("[ClaudeQuery] No speech detected within timeout")
                        self.after(0, lambda: self.listen_indicator.config(text="⏱"))
                    except sr.UnknownValueError:
                        print("[ClaudeQuery] Could not understand audio")
                        self.after(0, lambda: self.listen_indicator.config(text="?"))

            except Exception as e:
                print(f"[ClaudeQuery] Voice recognition error: {e}")
                self.after(0, lambda: self.listen_indicator.config(text="❌"))

            # Reset state if listening failed/ended without result
            self.after(0, self._stop_listening_ui)

        thread = threading.Thread(target=listen, daemon=True)
        thread.start()

    def _show_voice_result(self, text):
        """Show recognized text in input box with countdown before submit."""
        # Stop the listening counter
        self.listening = False
        self.title("CLAUDE QUERY")

        # Put text in the input box if it exists
        if hasattr(self, 'text_entry'):
            self.text_entry.delete(0, tk.END)
            self.text_entry.insert(0, text)

        # Start 3 second countdown - just show numbers (shorter since silence detection already waited)
        self.voice_submit_text = text
        self.submit_countdown = 3
        self._voice_submit_countdown()

    def _voice_submit_countdown(self):
        """Countdown before submitting voice result - just show numbers."""
        # Check if countdown was cancelled (negative means cancelled)
        if self.submit_countdown < 0:
            return  # Cancelled by user typing or unchecking Listen
        if self.submit_countdown > 0:
            self.listen_indicator.config(text=f"{self.submit_countdown}")
            self.submit_countdown -= 1
            self.after(1000, self._voice_submit_countdown)
        else:
            # countdown == 0, natural completion - submit!
            self.listen_indicator.config(text="✓")
            self.after(200, lambda: self._submit_voice_result(self.voice_submit_text))

    def _submit_voice_result(self, text):
        """Submit voice-transcribed text as result."""
        self.result = text
        self.text_result = text
        self.destroy()

    def _update_listen_countdown(self):
        """Keep listening state active (no visual counter during recording)."""
        if self.listening and not self.listen_paused:
            # Don't show count-up during listening per Rev's feedback
            # Just keep the timer running to maintain state
            self.after(1000, self._update_listen_countdown)

    def _pause_listening(self):
        """Pause/resume listening (for future use)."""
        self.listen_paused = not self.listen_paused
        if self.listen_paused:
            self.listen_indicator.config(text="⏸")
        else:
            self.listen_indicator.config(text="●")

    def _stop_listening_ui(self):
        """Reset listening UI state."""
        self.listening = False
        self.title("CLAUDE QUERY")
        # Hide indicator after a moment
        self.after(2000, lambda: self.listen_indicator.pack_forget())

    def _open_url(self, url):
        """Open URL in default browser."""
        import webbrowser
        webbrowser.open(url)

    def _create_image_preview(self, parent):
        """Legacy method - redirects to carousel."""
        self._create_image_carousel(parent)

    # Keep old methods for file links
    def _open_file(self, path):
        """Open file in default editor/viewer."""
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
        except Exception as e:
            print(f"Error opening {path}: {e}")

    def _show_full_image(self, event):
        """Open fullsize image popup."""
        if self.images:
            ImagePopup(self, self.images[self.current_image_idx])

    # Rest of links section removed - now in _create_links_section

    def _create_buttons(self, parent):
        """Create hotbar-style buttons with row navigation."""
        self.current_hotbar = get_hotbar_row()
        # Load custom hotbars if they exist, otherwise use defaults
        custom = get_custom_hotbars()
        self.hotbars = custom if custom else [list(row) for row in DEFAULT_HOTBARS]

        # Fixed lower panel container
        self.hotbar_container = tk.Frame(parent, bg=BG_COLOR)
        self.hotbar_container.pack(fill=tk.X, pady=(10, 0))

        # Centered hotbar row
        hotbar_row = tk.Frame(self.hotbar_container, bg=BG_COLOR)
        hotbar_row.pack(anchor="center")

        # LEFT: Up/Down arrows stacked with row number
        nav_frame = tk.Frame(hotbar_row, bg=BG_COLOR)
        nav_frame.pack(side=tk.LEFT, padx=(0, 10))

        self.prev_row_btn = tk.Button(
            nav_frame,
            text="▲",
            font=("Segoe UI", 7, "bold"),
            fg=ACCENT_COLOR,
            bg=BUTTON_BG,
            relief=tk.FLAT,
            width=2,
            height=1,
            cursor="hand2",
            command=self._prev_hotbar
        )
        self.prev_row_btn.pack()

        self.hotbar_label = tk.Label(
            nav_frame,
            text=str(self.current_hotbar + 1),
            font=("Segoe UI", 9, "bold"),
            fg="#888888",
            bg=BG_COLOR,
            width=2
        )
        self.hotbar_label.pack()

        self.next_row_btn = tk.Button(
            nav_frame,
            text="▼",
            font=("Segoe UI", 7, "bold"),
            fg=ACCENT_COLOR,
            bg=BUTTON_BG,
            relief=tk.FLAT,
            width=2,
            height=1,
            cursor="hand2",
            command=self._next_hotbar
        )
        self.next_row_btn.pack()

        # CENTER: Hotbar buttons frame
        self.btn_frame = tk.Frame(hotbar_row, bg=BG_COLOR)
        self.btn_frame.pack(side=tk.LEFT)

        # RIGHT: Gear icon for settings
        gear_btn = tk.Button(
            hotbar_row,
            text="⚙️",
            font=("Segoe UI", 10),
            fg="#888888",
            bg=BG_COLOR,
            relief=tk.FLAT,
            cursor="hand2",
            command=self._show_hotbar_settings
        )
        gear_btn.pack(side=tk.LEFT, padx=(10, 0))

        # Render current hotbar row
        self._render_hotbar()

    def _configure_button(self, button_idx):
        """Open config modal for a specific button slot."""
        self._open_button_editor(button_idx)

    def _open_button_editor(self, button_idx=None, return_to_settings=False):
        """Open editor modal for a button. If button_idx is None, show full row editor."""
        popup = tk.Toplevel(self)
        popup.title("Configure Button")
        popup.configure(bg=BG_COLOR)
        popup.geometry("400x200")
        popup.attributes("-topmost", True)
        popup.transient(self)
        popup.grab_set()

        row = self.hotbars[self.current_hotbar]
        current_label, current_response = row[button_idx] if button_idx is not None else ("", "")

        # Header
        tk.Label(
            popup,
            text=f"Configure Button (Row {self.current_hotbar + 1}, Slot {button_idx + 1})",
            font=("Segoe UI", 11, "bold"),
            fg=ACCENT_COLOR,
            bg=BG_COLOR
        ).pack(pady=(15, 10))

        # Label entry
        label_frame = tk.Frame(popup, bg=BG_COLOR)
        label_frame.pack(fill=tk.X, padx=20, pady=5)
        tk.Label(label_frame, text="Button Label:", font=("Segoe UI", 10), fg=FG_COLOR, bg=BG_COLOR).pack(side=tk.LEFT)
        label_entry = tk.Entry(label_frame, font=("Segoe UI", 10), fg=FG_COLOR, bg="#2d2d44", insertbackground=FG_COLOR, width=25)
        label_entry.pack(side=tk.RIGHT, padx=(10, 0))
        label_entry.insert(0, current_label)

        # Response entry
        resp_frame = tk.Frame(popup, bg=BG_COLOR)
        resp_frame.pack(fill=tk.X, padx=20, pady=5)
        tk.Label(resp_frame, text="Response Text:", font=("Segoe UI", 10), fg=FG_COLOR, bg=BG_COLOR).pack(side=tk.LEFT)
        resp_entry = tk.Entry(resp_frame, font=("Segoe UI", 10), fg=FG_COLOR, bg="#2d2d44", insertbackground=FG_COLOR, width=25)
        resp_entry.pack(side=tk.RIGHT, padx=(10, 0))
        resp_entry.insert(0, current_response)

        def save_button():
            new_label = label_entry.get().strip()
            new_response = resp_entry.get().strip()
            # Update hotbar
            self.hotbars[self.current_hotbar][button_idx] = (new_label, new_response)
            # Save to settings
            save_custom_hotbars(self.hotbars)
            # Re-render
            self._render_hotbar()
            popup.destroy()
            if return_to_settings:
                self._show_hotbar_settings()

        def clear_button():
            # Clear this slot
            self.hotbars[self.current_hotbar][button_idx] = ("", "")
            save_custom_hotbars(self.hotbars)
            self._render_hotbar()
            popup.destroy()
            if return_to_settings:
                self._show_hotbar_settings()

        def cancel_button():
            popup.destroy()
            if return_to_settings:
                self._show_hotbar_settings()

        # Buttons row
        btn_frame = tk.Frame(popup, bg=BG_COLOR)
        btn_frame.pack(pady=20)

        tk.Button(
            btn_frame, text="Save", font=("Segoe UI", 10, "bold"),
            fg="#ffffff", bg=ACCENT_COLOR, relief=tk.FLAT, padx=20, command=save_button
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            btn_frame, text="Clear", font=("Segoe UI", 10),
            fg=FG_COLOR, bg=NO_COLOR, relief=tk.FLAT, padx=15, command=clear_button
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            btn_frame, text="Cancel", font=("Segoe UI", 10),
            fg=FG_COLOR, bg=BUTTON_BG, relief=tk.FLAT, padx=15, command=cancel_button
        ).pack(side=tk.LEFT, padx=5)

        # Enter to save
        popup.bind("<Return>", lambda e: save_button())
        label_entry.focus_set()

    def _show_hotbar_settings(self):
        """Show full hotbar configuration modal with reordering."""
        popup = tk.Toplevel(self)
        popup.title("Hotbar Settings")
        popup.configure(bg=BG_COLOR)
        popup.geometry("500x400")
        popup.attributes("-topmost", True)
        popup.transient(self)

        # Header
        tk.Label(
            popup,
            text=f"Edit Row {self.current_hotbar + 1}",
            font=("Segoe UI", 12, "bold"),
            fg=ACCENT_COLOR,
            bg=BG_COLOR
        ).pack(pady=(15, 10))

        # Scrollable button list
        list_frame = tk.Frame(popup, bg=BG_COLOR)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20)

        row = self.hotbars[self.current_hotbar]

        def refresh_list():
            for widget in list_frame.winfo_children():
                widget.destroy()

            for idx, (label, response) in enumerate(row):
                item_frame = tk.Frame(list_frame, bg="#252540", pady=5, padx=10)
                item_frame.pack(fill=tk.X, pady=2)

                # Position number
                tk.Label(item_frame, text=f"{idx+1}.", font=("Segoe UI", 10, "bold"),
                        fg="#888888", bg="#252540", width=3).pack(side=tk.LEFT)

                # Button name (or empty indicator)
                display_text = label if label else "[empty]"
                display_color = FG_COLOR if label else "#666666"
                tk.Label(item_frame, text=display_text, font=("Segoe UI", 10),
                        fg=display_color, bg="#252540", width=15, anchor="w").pack(side=tk.LEFT, padx=5)

                # Edit button
                tk.Button(
                    item_frame, text="Edit", font=("Segoe UI", 9),
                    fg=ACCENT_COLOR, bg="#353560", relief=tk.FLAT, padx=8,
                    command=lambda i=idx: [popup.destroy(), self._open_button_editor(i, return_to_settings=True)]
                ).pack(side=tk.LEFT, padx=2)

                # Move up button
                if idx > 0:
                    tk.Button(
                        item_frame, text="▲", font=("Segoe UI", 8),
                        fg="#888888", bg="#353560", relief=tk.FLAT, width=2,
                        command=lambda i=idx: move_up(i)
                    ).pack(side=tk.LEFT, padx=2)

                # Move down button
                if idx < len(row) - 1:
                    tk.Button(
                        item_frame, text="▼", font=("Segoe UI", 8),
                        fg="#888888", bg="#353560", relief=tk.FLAT, width=2,
                        command=lambda i=idx: move_down(i)
                    ).pack(side=tk.LEFT, padx=2)

        def move_up(idx):
            if idx > 0:
                row[idx], row[idx-1] = row[idx-1], row[idx]
                save_custom_hotbars(self.hotbars)
                refresh_list()

        def move_down(idx):
            if idx < len(row) - 1:
                row[idx], row[idx+1] = row[idx+1], row[idx]
                save_custom_hotbars(self.hotbars)
                refresh_list()

        refresh_list()

        # Bottom buttons
        bottom_frame = tk.Frame(popup, bg=BG_COLOR)
        bottom_frame.pack(pady=15)

        def reset_row():
            # Reset this row to defaults
            self.hotbars[self.current_hotbar] = list(DEFAULT_HOTBARS[self.current_hotbar])
            save_custom_hotbars(self.hotbars)
            self._render_hotbar()
            popup.destroy()

        tk.Button(
            bottom_frame, text="Reset to Default", font=("Segoe UI", 10),
            fg="#ff8888", bg=BUTTON_BG, relief=tk.FLAT, padx=15, command=reset_row
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            bottom_frame, text="Done", font=("Segoe UI", 10, "bold"),
            fg="#ffffff", bg=ACCENT_COLOR, relief=tk.FLAT, padx=20,
            command=lambda: [self._render_hotbar(), popup.destroy()]
        ).pack(side=tk.LEFT, padx=5)

    def _render_hotbar(self):
        """Render the current hotbar row's buttons."""
        # Clear existing buttons
        for widget in self.btn_frame.winfo_children():
            widget.destroy()

        # Get current row
        row = self.hotbars[self.current_hotbar]

        for idx, (label, response) in enumerate(row):
            # Empty slot - show as "+" button for configuration
            if not label and not response:
                btn = tk.Button(
                    self.btn_frame,
                    text="+",
                    font=("Segoe UI", 12, "bold"),
                    fg="#666666",
                    bg="#252540",
                    activeforeground="#888888",
                    activebackground="#353560",
                    relief=tk.FLAT,
                    width=3,
                    pady=8,
                    cursor="hand2",
                    command=lambda i=idx: self._configure_button(i)
                )
                btn.pack(side=tk.LEFT, padx=(0, 10))
                # Hover effects
                btn.bind("<Enter>", lambda e, b=btn: b.configure(bg="#353560", fg="#888888"))
                btn.bind("<Leave>", lambda e, b=btn: b.configure(bg="#252540", fg="#666666"))
            else:
                # Color coding for YES/NO
                if label.upper() == "YES" or label.upper() == "APPROVED" or label.upper() == "GOOD":
                    bg = YES_COLOR
                elif label.upper() == "NO" or label.upper() == "REJECTED" or label.upper() == "BAD":
                    bg = NO_COLOR
                else:
                    bg = BUTTON_BG

                btn = tk.Button(
                    self.btn_frame,
                    text=label,
                    font=("Segoe UI", 10, "bold"),
                    fg=FG_COLOR,
                    bg=bg,
                    activeforeground=FG_COLOR,
                    activebackground=BUTTON_HOVER,
                    relief=tk.FLAT,
                    padx=15,
                    pady=8,
                    cursor="hand2",
                    command=lambda r=response: self._select(r)
                )
                btn.pack(side=tk.LEFT, padx=(0, 10))

                # Hover effects
                btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=BUTTON_HOVER))
                btn.bind("<Leave>", lambda e, b=btn, orig=bg: b.configure(bg=orig))

        # Update label (just the number)
        self.hotbar_label.config(text=str(self.current_hotbar + 1))

    def _prev_hotbar(self):
        """Switch to previous hotbar row."""
        self.current_hotbar = (self.current_hotbar - 1) % len(self.hotbars)
        set_hotbar_row(self.current_hotbar)
        self._render_hotbar()

    def _next_hotbar(self):
        """Switch to next hotbar row."""
        self.current_hotbar = (self.current_hotbar + 1) % len(self.hotbars)
        set_hotbar_row(self.current_hotbar)
        self._render_hotbar()

    def _toggle_mute(self):
        """Toggle and save mute state."""
        set_mute_state(self.mute_var.get())

    def _ping_claude(self):
        """
        User wants Claude's attention NOW.
        Grabs any text from input, writes to ping file for Claude to check.
        No beeps (user already knows they pinged - Claude needs to see it).
        Has 3-minute cooldown since bots take time to check messages.
        """
        # Check cooldown (3 minutes)
        cooldown_file = Path(__file__).parent / "claude_query_ping_cooldown.txt"
        if cooldown_file.exists():
            try:
                last_ping = datetime.fromisoformat(cooldown_file.read_text().strip())
                elapsed = (datetime.now() - last_ping).total_seconds()
                remaining = 180 - elapsed  # 3 minute cooldown
                if remaining > 0:
                    mins = int(remaining // 60)
                    secs = int(remaining % 60)
                    self.title(f"⏳ Wait {mins}:{secs:02d}")
                    self.after(1500, lambda: self.title("CLAUDE QUERY"))
                    print(f"[ClaudeQuery] PING cooldown - {mins}:{secs:02d} remaining")
                    return
            except:
                pass

        # Grab any text from input field
        message = ""
        if hasattr(self, 'text_entry'):
            message = self.text_entry.get().strip()

        # Write to ping file so Claude can detect it during heartbeat
        ping_file = Path(__file__).parent / "claude_query_ping.txt"
        ping_content = f"PING from user at {datetime.now().isoformat()}\n"
        if message:
            ping_content += f"MESSAGE: {message}\n"
        ping_file.write_text(ping_content)

        # Save cooldown timestamp
        cooldown_file.write_text(datetime.now().isoformat())

        # Visual feedback - pulse the PING button
        self._pulse_ping_button()

        # Flash the window title
        self.title("🔔 PING SENT!")
        self.after(1500, lambda: self.title("CLAUDE QUERY"))

        # Log to history with message if present
        log_history("[PING]", f"User pinged: {message}" if message else "User pinged for attention")

        print(f"[ClaudeQuery] PING sent - user wants attention! Message: {message or '(none)'}")

        # DON'T close window - user still needs it to respond
        # DON'T beep at user - they clicked it, they know. Claude checks the file.

    def _pulse_ping_button(self):
        """Animate the PING button with a soft pulse effect."""
        if not hasattr(self, 'ping_btn'):
            return

        # Store original colors
        orig_fg = "#ffaa00"
        orig_bg = "#1f1f35"

        # Pulse sequence - bright flash then fade
        def pulse_step(step):
            if step == 0:
                self.ping_btn.config(fg="#ffffff", bg="#ff6600")
            elif step == 1:
                self.ping_btn.config(fg="#ffdd00", bg="#cc5500")
            elif step == 2:
                self.ping_btn.config(fg="#ffcc00", bg="#aa4400")
            elif step == 3:
                self.ping_btn.config(fg="#ffbb00", bg="#883300")
            elif step == 4:
                self.ping_btn.config(fg="#ffaa00", bg="#552200")
            else:
                # Back to original but with subtle "sent" indicator
                self.ping_btn.config(fg="#88ff88", bg=orig_bg, text="✓ SENT")
                # Reset to normal after 2 seconds
                self.after(2000, lambda: self.ping_btn.config(fg=orig_fg, text="🔔 PING"))
                return

            self.after(100, lambda s=step+1: pulse_step(s))

        pulse_step(0)

    def _toggle_listen(self):
        """Toggle and save listen state. Start/stop listening accordingly."""
        enabled = self.listen_var.get()
        set_listen_state(enabled)
        if enabled and not self.listening:
            # Start listening when enabled
            self._start_listening()
        elif not enabled:
            # Stop listening AND cancel any pending submit countdown
            self._cancel_listening()

    def _create_attachments_bar(self, parent):
        """Create a bar showing attached files and a drop zone."""
        parent_bg = parent.cget("bg")

        # Container for attachments and drop zone
        attach_container = tk.Frame(parent, bg=parent_bg)
        attach_container.pack(fill=tk.X, pady=(5, 5))

        # Attachments row
        self.attach_frame = tk.Frame(attach_container, bg=parent_bg)
        self.attach_frame.pack(fill=tk.X)

        # Hidden by default, shown when files attached
        self.attach_label = tk.Label(
            self.attach_frame,
            text="📎 Attached:",
            font=("Segoe UI", 9, "bold"),
            fg="#888888",
            bg=parent_bg
        )

        # Frame for file links
        self.attach_files_frame = tk.Frame(self.attach_frame, bg=parent_bg)

        # Drop zone (for drag-and-drop)
        self._create_drop_zone(attach_container)

    def _create_drop_zone(self, parent):
        """Create a clickable drop zone to grab clipboard images."""
        parent_bg = parent.cget("bg")

        self.drop_zone = tk.Frame(
            parent,
            bg="#2d2d2d",
            relief=tk.RIDGE,
            bd=1,
            height=40
        )
        self.drop_zone.pack(fill=tk.X, pady=(5, 0))
        self.drop_zone.pack_propagate(False)  # Keep fixed height

        self.drop_label = tk.Label(
            self.drop_zone,
            text="📥 DROP",
            font=("Arial", 9, "bold"),
            fg="#00d4ff",
            bg="#2d2d2d",
            cursor="hand2"
        )
        self.drop_label.pack(expand=True, fill=tk.BOTH)

        # LEFT CLICK = grab clipboard image (like clipboard_drop.py)
        self.drop_label.bind("<Button-1>", self._grab_clipboard_image)
        self.drop_zone.bind("<Button-1>", self._grab_clipboard_image)

        # Also support drag-drop if available
        if HAS_DND:
            self.drop_zone.drop_target_register(DND_FILES)
            self.drop_zone.dnd_bind('<<Drop>>', self._on_drop)
            self.drop_zone.dnd_bind('<<DragEnter>>', self._on_drag_enter)
            self.drop_zone.dnd_bind('<<DragLeave>>', self._on_drag_leave)
            self.drop_label.drop_target_register(DND_FILES)
            self.drop_label.dnd_bind('<<Drop>>', self._on_drop)
            self.drop_label.dnd_bind('<<DragEnter>>', self._on_drag_enter)
            self.drop_label.dnd_bind('<<DragLeave>>', self._on_drag_leave)

    def _grab_clipboard_image(self, event=None):
        """Grab image from clipboard (like clipboard_drop.py)."""
        from PIL import ImageGrab

        try:
            img = ImageGrab.grabclipboard()
            if isinstance(img, Image.Image):
                # Save the image
                img.save(str(PASTED_IMAGE_FILE), "PNG")
                self._add_attachment(str(PASTED_IMAGE_FILE))

                # Visual feedback - green flash
                self.drop_zone.config(bg="#00ff00")
                self.drop_label.config(bg="#00ff00", fg="#000000")
                self.after(1000, self._reset_drop_zone)
            else:
                # No image - red flash
                self.drop_zone.config(bg="#ff4444")
                self.drop_label.config(bg="#ff4444", fg="#ffffff", text="No image!")
                self.after(1000, self._reset_drop_zone)
        except Exception as e:
            print(f"[ClaudeQuery] Clipboard grab error: {e}")
            self.drop_zone.config(bg="#ff4444")
            self.drop_label.config(bg="#ff4444", fg="#ffffff", text="Error!")
            self.after(1000, self._reset_drop_zone)

    def _reset_drop_zone(self):
        """Reset drop zone to default appearance."""
        self.drop_zone.config(bg="#2d2d2d")
        self.drop_label.config(bg="#2d2d2d", fg="#00d4ff", text="📥 DROP")

    def _on_drag_enter(self, event):
        """Visual feedback when dragging over drop zone."""
        self.drop_zone.config(bg="#3d3d5c")
        self.drop_label.config(bg="#3d3d5c", fg="#66cc66", text="📥 Drop now!")

    def _on_drag_leave(self, event):
        """Reset visual when drag leaves."""
        self.drop_zone.config(bg="#252540")
        self.drop_label.config(bg="#252540", fg="#666666", text="📥 Drop files here")

    def _on_drop(self, event):
        """Handle dropped files."""
        import shutil

        # Reset visual
        self.drop_zone.config(bg="#252540")
        self.drop_label.config(bg="#252540", fg="#666666", text="📥 Drop files here")

        # Parse dropped files (may be wrapped in braces on Windows)
        files = event.data
        if files.startswith('{') and files.endswith('}'):
            files = files[1:-1]

        # Split by space (files with spaces are in braces)
        file_list = []
        current = ""
        in_braces = False
        for char in files:
            if char == '{':
                in_braces = True
            elif char == '}':
                in_braces = False
            elif char == ' ' and not in_braces:
                if current:
                    file_list.append(current)
                current = ""
                continue
            current += char
        if current:
            file_list.append(current)

        # Process each file
        for filepath in file_list:
            filepath = filepath.strip()
            if filepath and os.path.exists(filepath):
                try:
                    # Copy to pasted location
                    shutil.copy2(filepath, str(PASTED_IMAGE_FILE))
                    self._add_attachment(str(PASTED_IMAGE_FILE))
                except Exception as e:
                    print(f"[ClaudeQuery] Drop error: {e}")

    def _add_attachment(self, filepath):
        """Add a file to attachments and update display."""
        if filepath not in self.attachments:
            self.attachments.append(filepath)
        self._update_attachments_display()

        # Insert indicator in text entry if available
        if hasattr(self, 'text_entry'):
            filename = os.path.basename(filepath)
            indicator = f"[pasted: {filename}] "
            current = self.text_entry.get()
            # Only add if not already there
            if indicator not in current:
                self.text_entry.insert(0, indicator)

    def _update_attachments_display(self):
        """Update the attachments bar with current files."""
        if not self.attachments:
            self.attach_label.pack_forget()
            self.attach_files_frame.pack_forget()
            return

        # Show the label
        self.attach_label.pack(side=tk.LEFT, padx=(0, 5))

        # Clear old file links
        for widget in self.attach_files_frame.winfo_children():
            widget.destroy()

        # Add file links
        parent_bg = self.attach_frame.cget("bg")
        for filepath in self.attachments:
            filename = os.path.basename(filepath)
            link = tk.Label(
                self.attach_files_frame,
                text=filename,
                font=("Consolas", 9),
                fg="#66ccff",
                bg=parent_bg,
                cursor="hand2"
            )
            link.pack(side=tk.LEFT, padx=(0, 10))
            link.bind("<Button-1>", lambda e, p=filepath: self._open_file(p))
            link.bind("<Enter>", lambda e, l=link: l.configure(fg="#99ddff"))
            link.bind("<Leave>", lambda e, l=link: l.configure(fg="#66ccff"))

        self.attach_files_frame.pack(side=tk.LEFT)

    def _paste_from_clipboard(self):
        """
        Paste content from clipboard (text or image).
        Saves to file for Claude to access.
        """
        from PIL import ImageGrab

        pasted_file = None

        # Try to get image from clipboard first (more specific)
        try:
            img = ImageGrab.grabclipboard()
            if img is not None:
                # Save the image
                img.save(str(PASTED_IMAGE_FILE), "PNG")
                pasted_file = str(PASTED_IMAGE_FILE)
        except Exception as e:
            print(f"[ClaudeQuery] Image paste failed: {e}")

        # Try text if no image
        if not pasted_file:
            try:
                text = self.clipboard_get()
                if text and text.strip():
                    # Save the text
                    PASTED_TEXT_FILE.write_text(text, encoding='utf-8')
                    pasted_file = str(PASTED_TEXT_FILE)
            except tk.TclError:
                # No text in clipboard
                pass
            except Exception as e:
                print(f"[ClaudeQuery] Text paste failed: {e}")

        # Add to attachments bar
        if pasted_file:
            self._add_attachment(pasted_file)
        else:
            self._show_paste_feedback(None, "Nothing to paste")

    def _browse_file(self):
        """
        Open file dialog to select an image to attach.
        Copies the selected image to the pasted location.
        """
        from tkinter import filedialog
        import shutil

        filetypes = [
            ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
            ("All files", "*.*")
        ]

        filepath = filedialog.askopenfilename(
            title="Select file to attach",
            filetypes=filetypes,
            parent=self
        )

        if filepath:
            try:
                # Copy the file to pasted location
                shutil.copy2(filepath, str(PASTED_IMAGE_FILE))
                self._add_attachment(str(PASTED_IMAGE_FILE))
            except Exception as e:
                self._show_paste_feedback(None, f"Error: {e}")

    def _show_paste_feedback(self, paste_type, message):
        """Show a brief feedback popup for paste action."""
        popup = tk.Toplevel(self)
        popup.title("Pasted")
        popup.configure(bg="#1f1f35")
        popup.attributes("-topmost", True)
        popup.overrideredirect(True)  # No window chrome

        # Position near paste button
        popup.geometry(f"+{self.winfo_x() + 400}+{self.winfo_y() + 50}")

        # Frame with border
        frame = tk.Frame(popup, bg="#1f1f35", relief=tk.RIDGE, bd=2, padx=10, pady=8)
        frame.pack()

        # Icon based on type
        if paste_type == "image":
            icon = "🖼️"
            color = "#66cc66"
        elif paste_type == "text":
            icon = "📄"
            color = "#66cc66"
        else:
            icon = "❌"
            color = "#cc6666"

        label = tk.Label(
            frame,
            text=f"{icon} {message}",
            font=("Segoe UI", 10),
            fg=color,
            bg="#1f1f35",
            wraplength=350
        )
        label.pack()

        # Auto-close after 2 seconds
        popup.after(2000, popup.destroy)

    def _show_history_popup(self):
        """Show history in a popup window."""
        history = get_history(limit=20)
        if not history:
            return

        popup = tk.Toplevel(self)
        popup.title("Query History")
        popup.configure(bg=BG_COLOR)
        popup.geometry("600x450")
        popup.attributes("-topmost", True)
        popup.resizable(True, True)  # Allow resize

        # Scrollable frame
        canvas = tk.Canvas(popup, bg=BG_COLOR, highlightthickness=0)
        scrollbar = tk.Scrollbar(popup, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=BG_COLOR)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        popup.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>"))

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Add history items
        for h in history:
            ts = h.get("timestamp", "")[:16].replace("T", " ")
            q = h.get("question", "")[:80]
            a = h.get("answer", "?")

            item_frame = tk.Frame(scroll_frame, bg="#252540", padx=8, pady=6)
            item_frame.pack(fill=tk.X, pady=3)

            ts_label = tk.Label(
                item_frame,
                text=ts,
                font=("Consolas", 8),
                fg="#666666",
                bg="#252540"
            )
            ts_label.pack(anchor="w")

            q_label = tk.Label(
                item_frame,
                text=f"Q: {q}",
                font=("Segoe UI", 10),
                fg=FG_COLOR,
                bg="#252540",
                wraplength=550,
                justify=tk.LEFT
            )
            q_label.pack(anchor="w")

            a_label = tk.Label(
                item_frame,
                text=f"A: {a}",
                font=("Segoe UI", 10, "bold"),
                fg=ACCENT_COLOR,
                bg="#252540",
                wraplength=550,
                justify=tk.LEFT
            )
            a_label.pack(anchor="w")

        # Resize grip at bottom
        grip = tk.ttk.Sizegrip(popup)
        grip.pack(side=tk.RIGHT, anchor=tk.SE)

        popup.transient(self)
        # Don't grab_set - allows typing in main window

    def _select(self, choice):
        """Handle button click - also capture any typed text."""
        # Check if there's text in the entry field
        typed_text = ""
        if hasattr(self, 'text_entry'):
            typed_text = self.text_entry.get().strip()

        # Combine button choice with typed text if both present
        if typed_text:
            self.result = f"{choice}: {typed_text}"
            self.text_result = typed_text
        else:
            self.result = choice
            self.text_result = None
        self.destroy()

    def _on_close(self):
        """Handle window close without selection."""
        self.result = None
        self.destroy()

    def get_result(self):
        """Run the dialog and return result."""
        self.mainloop()
        return self.result


def ask_human(question, image=None, images=None, links=None, urls=None, buttons=None,
              voice=True, allow_text_input=True, info_text=None,
              wait_for_presence=False, show_webcam=False, presence_timeout=300,
              listen_mode=False, silence_timeout=3):
    """
    Show query panel and get human's answer.

    Args:
        question: The question to ask
        image: Single image path (legacy)
        images: List of image paths for carousel
        links: Dict of {name: filepath} for file links
        urls: Dict of {name: url} for web links
        buttons: List of button labels (default: YES/NO/DUNNO/YOU DO IT)
        voice: Announce via TTS (default True)
        allow_text_input: Show text input field (default True)
        info_text: Additional context text to display
        wait_for_presence: Wait for human to be at desk
        show_webcam: Capture and show webcam in panel
        presence_timeout: Max seconds to wait for presence
        listen_mode: Enable voice-to-text listening (default False)
        silence_timeout: Seconds of silence before submitting voice input (default 3)

    Returns:
        The button/text result, or None if closed without selection
    """
    webcam_image = None
    all_images = list(images) if images else []

    # Wait for presence if requested
    if wait_for_presence:
        found, webcam_image = wait_for_human(timeout=presence_timeout)
        if not found:
            print("[ClaudeQuery] Human not found, showing panel anyway")

    # Capture webcam for display if requested
    if show_webcam and not webcam_image:
        webcam_image, _ = capture_webcam()

    # Add webcam image to list if captured
    if webcam_image and webcam_image not in all_images:
        all_images.insert(0, webcam_image)

    # Add single image to list if provided
    if image and image not in all_images:
        all_images.insert(0, image)

    # Show the panel with auto-speak of question (replaces generic "decision needed")
    panel = ClaudeQuery(
        question,
        images=all_images if all_images else None,
        links=links,
        urls=urls,
        buttons=buttons,
        allow_text_input=allow_text_input,
        info_text=info_text,
        auto_speak=voice,
        listen_mode=listen_mode,
        silence_timeout=silence_timeout
    )
    result = panel.get_result()

    # Log to history
    log_history(question, result, image=all_images[0] if all_images else None, links=links)

    return result


# === HISTORY & QUEUE ===

QUEUE_FILE = Path(__file__).parent / "claude_query_queue.json"
HISTORY_FILE = Path(__file__).parent / "claude_query_history.json"
MAX_HISTORY = 100  # Keep last N items


def log_history(question, answer, image=None, links=None):
    """Log a Q&A to history file for persistence across context compacts."""
    import json

    history = []
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text())
        except:
            history = []

    entry = {
        "question": question,
        "answer": answer,
        "image": image,
        "links": links,
        "timestamp": datetime.now().isoformat()
    }
    history.append(entry)

    # Trim to max size
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]

    HISTORY_FILE.write_text(json.dumps(history, indent=2))


def get_history(limit=20, search=None):
    """
    Get recent history entries.

    Args:
        limit: Max entries to return
        search: Optional search term to filter questions

    Returns:
        List of history entries (newest first)
    """
    import json

    if not HISTORY_FILE.exists():
        return []

    try:
        history = json.loads(HISTORY_FILE.read_text())
    except:
        return []

    # Filter by search term
    if search:
        search = search.lower()
        history = [h for h in history if search in h.get("question", "").lower()]

    # Return newest first
    return list(reversed(history[-limit:]))


def show_history(limit=10, search=None):
    """Print formatted history."""
    history = get_history(limit=limit, search=search)

    if not history:
        print("No history found")
        return

    print(f"\n=== CLAUDE QUERY HISTORY ({len(history)} items) ===\n")
    for h in history:
        ts = h.get("timestamp", "")[:16].replace("T", " ")
        q = h.get("question", "")[:50]
        a = h.get("answer", "?")
        print(f"[{ts}] Q: {q}...")
        print(f"           A: {a}\n")


def queue_question(question, image=None, links=None, buttons=None, priority=0):
    """
    Add a question to the queue for batch answering.

    Args:
        question: The question text
        image: Optional image path
        links: Optional dict of {name: filepath}
        buttons: Optional button labels
        priority: Higher = asked first (default 0)

    Returns:
        Queue position
    """
    import json

    queue = []
    if QUEUE_FILE.exists():
        try:
            queue = json.loads(QUEUE_FILE.read_text())
        except:
            queue = []

    item = {
        "question": question,
        "image": image,
        "links": links,
        "buttons": buttons,
        "priority": priority,
        "added": datetime.now().isoformat()
    }
    queue.append(item)

    # Sort by priority (highest first)
    queue.sort(key=lambda x: -x.get("priority", 0))

    QUEUE_FILE.write_text(json.dumps(queue, indent=2))
    print(f"[ClaudeQuery] Queued: {question[:50]}... (position {len(queue)})")
    return len(queue)


def get_queue():
    """Get current queue contents."""
    import json
    if QUEUE_FILE.exists():
        try:
            return json.loads(QUEUE_FILE.read_text())
        except:
            return []
    return []


def clear_queue():
    """Clear the queue."""
    if QUEUE_FILE.exists():
        QUEUE_FILE.unlink()
    print("[ClaudeQuery] Queue cleared")


def process_queue(voice=True, wait_for_presence=False):
    """
    Process all queued questions in one session.
    Shows each question, collects answer, moves to next.

    Args:
        voice: Announce via TTS
        wait_for_presence: Wait for human before starting

    Returns:
        dict: {question: answer} for all questions
    """
    import json

    queue = get_queue()
    if not queue:
        print("[ClaudeQuery] Queue is empty")
        return {}

    print(f"[ClaudeQuery] Processing {len(queue)} queued questions...")

    # Wait for presence if requested
    if wait_for_presence:
        found, _ = wait_for_human(timeout=300)
        if not found:
            print("[ClaudeQuery] Human not found, proceeding anyway")

    # Voice announcement (check mute state)
    if voice and not get_mute_state():
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.say(f"I have {len(queue)} questions queued.")
            engine.runAndWait()
        except:
            pass

    results = {}

    for i, item in enumerate(queue):
        question = item.get("question", "")
        print(f"\n[{i+1}/{len(queue)}] {question[:60]}...")

        # Show panel for this question
        panel = ClaudeQuery(
            f"[{i+1}/{len(queue)}] {question}",
            image=item.get("image"),
            links=item.get("links"),
            buttons=item.get("buttons")
        )
        answer = panel.get_result()

        results[question] = answer
        print(f"Answer: {answer}")

        # Log to history
        log_history(question, answer, image=item.get("image"), links=item.get("links"))

        if answer is None:
            # User closed window, stop processing
            print("[ClaudeQuery] Queue processing cancelled")
            break

    # Clear processed items
    clear_queue()

    return results


# === PING CHECK (for Claude's heartbeat) ===

PING_FILE = Path(__file__).parent / "claude_query_ping.txt"


def check_ping():
    """
    Check if user has pinged. Call this in your heartbeat loop.
    Returns: (has_ping: bool, message: str or None)
    Clears the ping file after reading.
    """
    if not PING_FILE.exists():
        return False, None

    try:
        content = PING_FILE.read_text().strip()
        # Clear the ping file
        PING_FILE.unlink()

        # Extract message if present
        message = None
        for line in content.split('\n'):
            if line.startswith('MESSAGE:'):
                message = line[8:].strip()
                break

        return True, message
    except Exception as e:
        print(f"[ClaudeQuery] Error checking ping: {e}")
        return False, None


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CLAUDE QUERY - Quick decision panel")
    parser.add_argument("question", nargs="?", default=None, help="Question to ask")
    parser.add_argument("--image", "-i", help="Path to image to display")
    parser.add_argument("--link", "-l", action="append", nargs=2, metavar=("NAME", "PATH"),
                        help="Add a named link (can use multiple times)")
    parser.add_argument("--no-voice", action="store_true", help="Skip voice announcement")
    parser.add_argument("--webcam", "-w", action="store_true", help="Capture and show webcam")
    parser.add_argument("--wait", action="store_true", help="Wait for human to be at desk")
    parser.add_argument("--queue", "-q", action="store_true", help="Add to queue instead of showing now")
    parser.add_argument("--process", "-p", action="store_true", help="Process all queued questions")
    parser.add_argument("--show-queue", action="store_true", help="Show current queue")
    parser.add_argument("--clear-queue", action="store_true", help="Clear the queue")
    parser.add_argument("--check-presence", action="store_true", help="Just check if human is at desk")
    parser.add_argument("--check-state", action="store_true", help="Full check: presence + emotional state")
    parser.add_argument("--history", "-H", nargs="?", const=10, type=int, metavar="N",
                        help="Show last N history entries (default 10)")
    parser.add_argument("--search", "-s", help="Search history for term")
    parser.add_argument("--listen", action="store_true", help="Enable voice-to-text listening")
    parser.add_argument("--silence", type=int, default=3, help="Silence timeout in seconds for voice input (default 3)")
    parser.add_argument("--check-ping", action="store_true", help="Check if user has pinged (for Claude's heartbeat)")

    args = parser.parse_args()

    # Build links dict
    links = {}
    if args.link:
        for name, path in args.link:
            links[name] = path

    # Handle commands
    if args.check_ping:
        has_ping, message = check_ping()
        if has_ping:
            print(f"PING received! Message: {message or '(none)'}")
        else:
            print("No ping")
    elif args.history is not None:
        show_history(limit=args.history, search=args.search)
    elif args.clear_queue:
        clear_queue()
    elif args.show_queue:
        queue = get_queue()
        if queue:
            print(f"Queue ({len(queue)} items):")
            for i, item in enumerate(queue):
                print(f"  {i+1}. {item['question'][:60]}...")
        else:
            print("Queue is empty")
    elif args.process:
        results = process_queue(voice=not args.no_voice, wait_for_presence=args.wait)
        print(f"\nResults: {results}")
    elif args.check_state:
        result = full_human_check()
        print(f"Person present: {result['present']}")
        if result['state']:
            print(f"State analysis:\n{result['state'].get('raw', 'No data')}")
        if result['image_path']:
            print(f"Image: {result['image_path']}")
    elif args.check_presence:
        is_present, img_path = check_human_present()
        print(f"Person at desk: {is_present}")
        if img_path:
            print(f"Image: {img_path}")
    elif args.queue and args.question:
        queue_question(args.question, image=args.image, links=links if links else None)
    elif args.question:
        # Direct query
        result = ask_human(
            args.question,
            image=args.image,
            links=links if links else None,
            voice=not args.no_voice,
            wait_for_presence=args.wait,
            show_webcam=args.webcam,
            listen_mode=args.listen,
            silence_timeout=args.silence
        )
        print(f"\nResult: {result}")
    else:
        # Default test
        result = ask_human(
            "Test question - does this panel work?",
            voice=not args.no_voice,
            show_webcam=args.webcam,
            listen_mode=args.listen,
            silence_timeout=args.silence
        )
        print(f"\nResult: {result}")
