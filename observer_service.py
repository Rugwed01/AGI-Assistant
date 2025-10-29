import os
import time
import json
import threading
import queue
import sys
import mss
import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write as write_wav
from pynput import mouse, keyboard

# --- Configuration ---
DATA_DIR = "data/raw"
LOG_FILE = "data/observer_log.jsonl"
REGION_SIZE = 100
KEY_BUFFER_TIMEOUT = 1.5
PUSH_TO_TALK_KEY = keyboard.Key.ctrl_r
AUDIO_SAMPLE_RATE = 16000

# --- Global State for Observer Functionality ---
# These are managed by the start/stop functions
_key_buffer = []
_last_key_time = None
_buffer_flush_timer = None
_screenshot_queue = queue.Queue()
_log_queue = queue.Queue()
_is_recording = False
_audio_frames = []
_stop_recording_flag = threading.Event()

_observer_stop_event = threading.Event() # Event to signal observer shutdown
_mouse_listener = None
_keyboard_listener = None
_log_thread = None
_screenshot_thread = None
_observer_main_thread = None # To monitor the observer's main loop

# --- Callback for logging output (to be set by GUI) ---
_output_callback = print # Default to print if not run from GUI

# --- Setup ---
def setup_directories():
    """Ensures the data directory exists."""
    os.makedirs(DATA_DIR, exist_ok=True)

# --- Logging ---
def _log_event(event_data):
    """Internal log event handler."""
    global _output_callback
    try:
        for key in ["fullscreen_img", "region_img", "audio_file"]:
            if key in event_data and event_data[key] is not None:
                event_data[key] = str(event_data[key]).replace("\\", "/")
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event_data, default=lambda o: f'<unserializable: {type(o).__name__}>') + '\n')
    except Exception as e:
        _output_callback(f"Error logging event: {e}")

def _log_worker():
    """Worker thread for logging."""
    global _log_queue, _observer_stop_event
    while not _observer_stop_event.is_set():
        try:
            event = _log_queue.get(timeout=0.5) # Timeout allows checking stop event
            if event is None: # Explicit stop signal
                break
            _log_event(event)
            _log_queue.task_done()
        except queue.Empty:
            continue # No event, loop back and check stop flag
    _output_callback("Log worker stopping.")

# --- Screenshotting ---
def _safe_grab_region(sct, x, y):
    """Internal safe region grab."""
    global _output_callback
    if len(sct.monitors) < 2:
        _output_callback("Error: Could not detect primary monitor.")
        return None
    monitor = sct.monitors[1]
    half_size = REGION_SIZE // 2
    top = max(monitor["top"], min(y - half_size, monitor["top"] + monitor["height"] - REGION_SIZE))
    left = max(monitor["left"], min(x - half_size, monitor["left"] + monitor["width"] - REGION_SIZE))
    region = {'top': top, 'left': left, 'width': REGION_SIZE, 'height': REGION_SIZE}
    try:
        return sct.grab(region)
    except Exception as e:
        _output_callback(f"Error grabbing region at {region}: {e}")
        return None

def _screenshot_worker():
    """Worker thread for screenshots."""
    global _screenshot_queue, _log_queue, _observer_stop_event, _output_callback
    sct = mss.mss()
    while not _observer_stop_event.is_set():
        try:
            click_data = _screenshot_queue.get(timeout=0.5) # Timeout allows checking stop event
            if click_data is None: break

            timestamp = click_data["timestamp"]
            x, y = click_data["x"], click_data["y"]
            fs_path = os.path.join(DATA_DIR, f"{timestamp}_fullscreen.png").replace("\\", "/")
            region_path = os.path.join(DATA_DIR, f"{timestamp}_region.png").replace("\\", "/")

            try: sct.shot(mon=-1, output=fs_path)
            except Exception as e: _output_callback(f"Error capturing full screen: {e}"); fs_path = None

            region_img = _safe_grab_region(sct, x, y)
            if region_img:
                try: mss.tools.to_png(region_img.rgb, region_img.size, output=region_path)
                except Exception as e: _output_callback(f"Error saving region image: {e}"); region_path = None
            else: region_path = None

            event_data = {"timestamp": timestamp, "event": "click", "button": click_data["button"],
                          "x": x, "y": y, "fullscreen_img": fs_path, "region_img": region_path}
            _log_queue.put(event_data)
            _screenshot_queue.task_done()
        except queue.Empty:
            continue
    _output_callback("Screenshot worker stopping.")


def _on_click(x, y, button, pressed):
    """Internal click handler."""
    global _screenshot_queue
    if pressed:
        click_data = {"timestamp": int(time.time()), "event": "click",
                      "button": str(button), "x": x, "y": y}
        _screenshot_queue.put(click_data)

# --- Keyboard & Buffering ---
def _flush_key_buffer():
    """Internal key buffer flush."""
    global _key_buffer, _buffer_flush_timer, _last_key_time, _log_queue, _output_callback
    if _buffer_flush_timer:
        _buffer_flush_timer.cancel()
        _buffer_flush_timer = None

    if _key_buffer:
        log_timestamp = int(_last_key_time) if _last_key_time else int(time.time())
        typed_string = "".join(_key_buffer)
        _output_callback(f"Logged typing: '{typed_string}'")
        event_data = {"timestamp": log_timestamp, "event": "type", "text": typed_string}
        _log_queue.put(event_data)
        _key_buffer = []

def _on_press(key):
    """Internal key press handler."""
    global _key_buffer, _last_key_time, _buffer_flush_timer, _is_recording, _stop_recording_flag, _log_queue

    _last_key_time = time.time()

    if key == PUSH_TO_TALK_KEY:
        if not _is_recording:
            _flush_key_buffer()
            _is_recording = True
            _stop_recording_flag.clear()
            threading.Thread(target=_record_audio_task, daemon=True).start()
        return

    try:
        char = key.char
        if char is None: # Modifier key
             _flush_key_buffer()
             return
    except AttributeError: # Special key
        _flush_key_buffer()
        special_key_repr = ' ' if key == keyboard.Key.space else f'[{str(key).split(".")[-1]}]'
        # Log special key press
        _log_queue.put({"timestamp": int(_last_key_time), "event": "key_press", "key": special_key_repr})
        # Reset timer
        if _buffer_flush_timer: _buffer_flush_timer.cancel()
        _buffer_flush_timer = threading.Timer(KEY_BUFFER_TIMEOUT, _flush_key_buffer)
        _buffer_flush_timer.start()
        return

    # Append character
    _key_buffer.append(char)
    # Reset timer
    if _buffer_flush_timer: _buffer_flush_timer.cancel()
    _buffer_flush_timer = threading.Timer(KEY_BUFFER_TIMEOUT, _flush_key_buffer)
    _buffer_flush_timer.start()


def _on_release(key):
    """Internal key release handler."""
    global _is_recording, _stop_recording_flag
    if key == PUSH_TO_TALK_KEY and _is_recording:
        _stop_recording_flag.set()
        _is_recording = False
        _output_callback("...recording stopped.")


# --- Audio Recording ---
def _record_audio_task():
    """Internal audio recording task."""
    global _audio_frames, _stop_recording_flag, _log_queue, _output_callback, _is_recording
    _output_callback("Recording audio...")
    _audio_frames = []

    def audio_callback(indata, frames, time_info, status):
        if status: _output_callback(f"Audio Input Status: {status}")
        _audio_frames.append(indata.copy())

    stream = None
    try:
        stream = sd.InputStream(samplerate=AUDIO_SAMPLE_RATE, channels=1,
                            callback=audio_callback, dtype='float32')
        with stream:
            _stop_recording_flag.wait() # Blocks until flag is set

    except sd.PortAudioError as e:
        _output_callback(f"PortAudioError during recording: {e}")
        if "Invalid device" in str(e): _output_callback("Please check microphone connection.")
        _stop_recording_flag.set() # Ensure flag is set anyway
        _is_recording = False # Update state if error occurs
    except Exception as e:
        _output_callback(f"Unexpected error during audio recording: {e}")
        _stop_recording_flag.set()
        _is_recording = False

    if _audio_frames:
        timestamp = int(time.time())
        audio_path = os.path.join(DATA_DIR, f"{timestamp}_audio.wav").replace("\\", "/")
        try:
            recording = np.concatenate(_audio_frames, axis=0)
            write_wav(audio_path, AUDIO_SAMPLE_RATE, recording)
            event_data = {"timestamp": timestamp, "event": "audio_command",
                          "audio_file": audio_path, "duration": round(len(recording) / AUDIO_SAMPLE_RATE, 2)}
            _log_queue.put(event_data)
            _output_callback(f"Saved audio to {audio_path}")
        except Exception as e:
             _output_callback(f"Error saving audio file {audio_path}: {e}")

# --- Main Observer Control Functions ---

def start_observer_func(output_callback=print):
    """Starts the observer listeners and workers in background threads."""
    global _mouse_listener, _keyboard_listener, _log_thread, _screenshot_thread
    global _observer_stop_event, _output_callback, _observer_main_thread

    _output_callback("Starting Observer Service...")
    _output_callback(f" - Log file: {LOG_FILE}")
    _output_callback(f" - Push-to-Talk key: {PUSH_TO_TALK_KEY}")

    setup_directories()
    _observer_stop_event.clear() # Reset stop event
    _output_callback = output_callback # Use the provided callback

    # Start worker threads
    _log_thread = threading.Thread(target=_log_worker, daemon=True, name="LogWorker")
    _screenshot_thread = threading.Thread(target=_screenshot_worker, daemon=True, name="ScreenshotWorker")
    _log_thread.start()
    _screenshot_thread.start()

    # Setup listeners
    _mouse_listener = mouse.Listener(on_click=_on_click)
    _keyboard_listener = keyboard.Listener(on_press=_on_press, on_release=_on_release, suppress=False)

    # Start listeners
    _mouse_listener.start()
    _keyboard_listener.start()

    _output_callback("--- Observer is now running ---")

    # Keep this function's thread alive (but check stop event) - GUI calls this in a thread
    while not _observer_stop_event.is_set():
        # Optional: Add checks here if listeners crashed unexpectedly
        # if not _mouse_listener.is_alive() or not _keyboard_listener.is_alive():
        #    _output_callback("Error: A listener thread stopped unexpectedly.")
        #    stop_observer_func() # Attempt cleanup
        #    break
        time.sleep(1) # Check stop event periodically

    # --- Cleanup initiated by stop_observer_func setting the event ---
    _output_callback("Observer main loop received stop signal.")
    # Stop listeners (important to do this before joining workers)
    if _mouse_listener.is_alive(): _mouse_listener.stop()
    if _keyboard_listener.is_alive(): _keyboard_listener.stop()

    # Signal workers (redundant if already set, but safe)
    _screenshot_queue.put(None)
    _log_queue.put(None)

    # Wait for workers
    _output_callback("Waiting for observer worker threads...")
    if _screenshot_thread.is_alive(): _screenshot_thread.join(timeout=3.0)
    if _log_thread.is_alive(): _log_thread.join(timeout=3.0)

    # Final flush
    _output_callback("Flushing final key buffer...")
    _flush_key_buffer() # Use the internal one

    _output_callback("--- Observer stopped ---")


def stop_observer_func():
    """Signals the observer thread and workers to stop."""
    global _observer_stop_event, _output_callback
    _output_callback("Stop signal received. Initiating observer shutdown...")
    _observer_stop_event.set() # Signal the main loop in start_observer_func


# --- Direct Execution Block (for running standalone if needed) ---
if __name__ == "__main__":
    # This block allows running observer_service.py directly for testing
    # It mimics how the GUI would call start/stop but uses KeyboardInterrupt

    # Use a threading.Event to simulate external stop signal
    main_stop_event = threading.Event()

    def signal_handler(sig, frame):
        print('\nCtrl+C detected! Signaling observer to stop...')
        main_stop_event.set() # Set the event on Ctrl+C

    import signal
    signal.signal(signal.SIGINT, signal_handler)

    print("Running observer directly. Press Ctrl+C to stop.")
    # Start the observer in a separate thread so we can wait for Ctrl+C
    observer_thread = threading.Thread(target=start_observer_func, args=(print,), daemon=True)
    observer_thread.start()

    # Wait until Ctrl+C sets the event
    while not main_stop_event.is_set():
        time.sleep(0.5)

    # Signal the observer function to stop
    stop_observer_func()

    # Wait for the observer thread to fully clean up and exit
    observer_thread.join(timeout=10.0) # Wait up to 10 seconds
    print("Main script exiting.")