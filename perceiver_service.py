import os
import json
import sys # Added
import pytesseract
import subprocess
from PIL import Image, ImageEnhance, ImageFilter

# --- Helper to get correct path when running as bundled .exe ---
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        # For one-folder mode, base is sys.executable's dir
        # For one-file mode, base is _MEIPASS
        if hasattr(sys, '_MEIPASS'):
            # Check if running as a bundled app (_MEIPASS exists)
            base_path = sys._MEIPASS
            # Construct path relative to _MEIPASS
            internal_path = os.path.join(base_path, relative_path)
            if os.path.exists(internal_path):
                 # print(f"Resource Path (_MEIPASS): Found in _internal: {internal_path}") # Debug
                 return internal_path

            # Fallback for one-folder mode where files might be next to exe OR in _internal
            base_path_exe = os.path.dirname(sys.executable)
            exe_relative_path = os.path.join(base_path_exe, relative_path)
            if os.path.exists(exe_relative_path):
                 # print(f"Resource Path (_MEIPASS Fallback): Found next to exe: {exe_relative_path}") # Debug
                 return exe_relative_path

            # If still not found, default to _MEIPASS path even if non-existent
            # print(f"Resource Path (_MEIPASS Default): Returning internal path: {internal_path}") # Debug
            return internal_path

        else:
            # Not bundled, running as normal script
            base_path = os.path.dirname(os.path.abspath(__file__))
            if not base_path: base_path = os.path.abspath(".")
            final_path = os.path.join(base_path, relative_path)
            # print(f"Resource Path (Dev): Path: {final_path}") # Debug
            return final_path

    except Exception as e:
        print(f"Error in resource_path: {e}")
        # Fallback in case of any error
        base_path = os.path.abspath(".")
        final_path = os.path.join(base_path, relative_path)
        # print(f"Resource Path (Error Fallback): Path: {final_path}") # Debug
        return final_path

# --- Configuration ---
# Use resource_path for files bundled with the exe
WHISPER_EXE_PATH = resource_path("whisper-cli.exe")
WHISPER_MODEL_PATH = resource_path("models/ggml-base.en.bin")
TESSDATA_PREFIX = resource_path("tessdata") # Path to bundled tessdata folder

# Log file paths (relative to where the exe runs)
OBSERVER_LOG_FILE = "data/observer_log.jsonl"
PROCESSED_LOG_FILE = "data/processed_log.jsonl"

# Tesseract command path (still might need external install)
TESSERACT_CMD_PATH = r'C:\Program Files\Tesseract-OCR\tesseract.exe' # Keep for development/fallback
# Set TESSDATA_PREFIX environment variable for Tesseract
try:
    os.environ['TESSDATA_PREFIX'] = TESSDATA_PREFIX
    print(f"Set TESSDATA_PREFIX to: {TESSDATA_PREFIX}") # Debug print
except Exception as e:
    print(f"Error setting TESSDATA_PREFIX: {e}")

# Set tesseract command path if found externally
if os.name == 'nt' and os.path.exists(TESSERACT_CMD_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD_PATH
else:
    # If external tesseract isn't found, hope it's in PATH or bundled
    print(f"External Tesseract command not found at {TESSERACT_CMD_PATH}. Relying on PATH or bundled data.")

# --- OCR Processing Function ---
def process_ocr(image_path, output_callback=print):
    """Runs Tesseract OCR, logs errors via callback."""
    if not image_path or not os.path.exists(image_path):
        return None
    try:
        img = Image.open(image_path)
        img = img.convert('L')
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2)
        img = img.filter(ImageFilter.SHARPEN)
        custom_config = r'--oem 3 --psm 6'
        text = pytesseract.image_to_string(img, config=custom_config)
        return text.strip().replace('\n', ' ')
    except pytesseract.TesseractNotFoundError:
        output_callback("--- TESSERACT ERROR ---")
        output_callback("Tesseract executable not found or not configured correctly.")
        output_callback(f"Ensure '{TESSERACT_CMD_PATH}' is correct or Tesseract is in PATH.")
        # Don't exit, just return None and let the main function handle it
        return None
    except Exception as e:
        output_callback(f"Error processing OCR for {os.path.basename(image_path)}: {e}")
        return None

# --- STT Processing Function ---
def process_stt(audio_path, output_callback=print):
    """Runs Whisper STT via CLI, logs errors via callback."""
    if not audio_path or not os.path.exists(audio_path):
        return None

    command = [
        WHISPER_EXE_PATH,
        "-m", WHISPER_MODEL_PATH,
        "-f", audio_path,
        "-otxt", # Output to text file
        "-np"    # No progress prints
    ]
    output_txt_path = audio_path + ".txt"

    try:
        # Use Popen to potentially capture output better if needed, but run waits
        result = subprocess.run(command,
                                check=True, # Raise error on non-zero exit
                                capture_output=True,
                                text=True,
                                encoding='utf-8')

        if not os.path.exists(output_txt_path):
            output_callback(f"Error: STT ran but output file not found: {output_txt_path}")
            if result.stderr: output_callback(f"Stderr: {result.stderr}")
            return None

        with open(output_txt_path, 'r', encoding='utf-8') as f:
            transcription = f.read().strip()
        return transcription

    except subprocess.CalledProcessError as e:
        output_callback(f"Error running Whisper executable for {os.path.basename(audio_path)} (Exit Code: {e.returncode}):")
        if e.stderr: output_callback(f"Stderr: {e.stderr}")
        if e.stdout: output_callback(f"Stdout: {e.stdout}") # Show stdout too on error
        return None
    except FileNotFoundError:
        output_callback(f"Error: Whisper executable not found at {WHISPER_EXE_PATH}")
        output_callback("Ensure whisper-cli.exe and its DLLs are bundled correctly.")
        return None # Return None instead of exiting
    except Exception as e:
        output_callback(f"An unexpected error occurred during STT for {os.path.basename(audio_path)}: {e}")
        return None
    finally:
        if os.path.exists(output_txt_path):
            try: os.remove(output_txt_path)
            except Exception as e: output_callback(f"Warning: Could not delete temp file {output_txt_path}: {e}")

# --- Main Perceiver Function ---
def run_perceiver(output_callback=print):
    """
    Reads the observer log, processes events, writes to processed log.
    Uses output_callback for messages. Returns True on success, False on critical error.
    """
    output_callback("Starting Perceiver Service...")

    # --- Dependency Checks ---
    critical_error = False
    # Check Tesseract (pytesseract checks command on first use, rely on that)
    # Check Whisper exe
    if not os.path.exists(WHISPER_EXE_PATH):
        output_callback(f"Error: Whisper executable not found: {WHISPER_EXE_PATH}")
        critical_error = True
    # Check Whisper model
    if not os.path.exists(WHISPER_MODEL_PATH):
        output_callback(f"Error: Whisper model not found: {WHISPER_MODEL_PATH}")
        critical_error = True
     # Check Tessdata (crucial for bundled app)
    if not os.path.exists(TESSDATA_PREFIX) or not os.listdir(TESSDATA_PREFIX):
         output_callback(f"Error: Tesseract data ('tessdata') not found or empty at: {TESSDATA_PREFIX}")
         output_callback(f"Ensure TESSDATA_PREFIX is set correctly and the folder was bundled.")
         critical_error = True # OCR will likely fail without this
    # Check input log file
    if not os.path.exists(OBSERVER_LOG_FILE):
        output_callback(f"Error: Input file not found: {OBSERVER_LOG_FILE}")
        output_callback("Please run the Observer first.")
        # Don't treat as critical, maybe just no data yet
        # critical_error = True
        output_callback("Perceiver finished (No input file).")
        return True # Return success, just nothing to do

    if critical_error:
        output_callback("Perceiver cannot continue due to missing dependencies.")
        return False # Signal failure

    output_callback("Dependencies found. Starting log processing...")

    # --- Processing Loop ---
    processed_count = 0
    errors_encountered = 0
    output_lines = [] # Collect output lines to write at the end

    try:
        with open(OBSERVER_LOG_FILE, 'r', encoding='utf-8') as f_in:
            lines = f_in.readlines()

        for i, line in enumerate(lines):
            try:
                event_data = json.loads(line)

                # --- Enrichment Logic ---
                if event_data.get('event') == 'click':
                    image_path = event_data.get('region_img')
                    if image_path and os.path.exists(resource_path(image_path)): # Check relative path existence
                        ocr_text = process_ocr(resource_path(image_path), output_callback)
                        event_data['ocr_text'] = ocr_text # Add even if None
                    elif image_path:
                         output_callback(f"Warning: region_img path not found: {image_path} for event {i+1}")

                elif event_data.get('event') == 'audio_command':
                    audio_path = event_data.get('audio_file')
                    if audio_path and os.path.exists(resource_path(audio_path)): # Check relative path existence
                        transcription = process_stt(resource_path(audio_path), output_callback)
                        event_data['transcription'] = transcription # Add even if None
                    elif audio_path:
                         output_callback(f"Warning: audio_file path not found: {audio_path} for event {i+1}")

                # --- End Enrichment ---

                # Append processed line to output list
                output_lines.append(json.dumps(event_data) + '\n')
                processed_count += 1

                if processed_count % 10 == 0:
                    output_callback(f"Processed {processed_count} events...")

            except json.JSONDecodeError:
                output_callback(f"Skipping malformed JSON line {i+1}: {line.strip()}")
                errors_encountered += 1
            except Exception as e:
                output_callback(f"Error processing line {i+1}: {e}")
                errors_encountered += 1
                # Try to add original line if processing fails? Might break downstream.
                # output_lines.append(line) # Or skip the line

    except Exception as e:
        output_callback(f"Fatal error reading input log file {OBSERVER_LOG_FILE}: {e}")
        return False # Signal failure

    # --- Write Output File ---
    try:
        os.makedirs(os.path.dirname(PROCESSED_LOG_FILE), exist_ok=True) # Ensure data dir exists
        with open(PROCESSED_LOG_FILE, 'w', encoding='utf-8') as f_out:
            f_out.writelines(output_lines)
    except Exception as e:
        output_callback(f"Fatal error writing processed log file {PROCESSED_LOG_FILE}: {e}")
        return False # Signal failure

    output_callback("---")
    output_callback(f"Perceiver processing complete.")
    output_callback(f"Total events processed: {processed_count}")
    if errors_encountered > 0:
        output_callback(f"Errors encountered during processing: {errors_encountered}")
    output_callback(f"Enriched log saved to: {PROCESSED_LOG_FILE}")
    return True # Signal success

# --- Direct Execution Block ---
if __name__ == "__main__":
    run_perceiver() # Call the main function with default print callback