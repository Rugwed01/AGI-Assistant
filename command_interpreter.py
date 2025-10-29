# command_interpreter.py (Refactored)
import json
import os
import time
import sys
import re

# --- Import functions from other service modules ---
# Assuming these files are in the same directory and have been refactored
try:
    from perceiver_service import run_perceiver
    from reasoning_service import run_reasoner
    from automation_service import run_automator
    SERVICES_AVAILABLE = True
except ImportError as e:
    print(f"Error importing service modules: {e}", file=sys.stderr)
    print("Ensure perceiver_service.py, reasoning_service.py, and automation_service.py are present and refactored.", file=sys.stderr)
    SERVICES_AVAILABLE = False

# --- Configuration ---
PROCESSED_LOG_FILE = "data/processed_log.jsonl"
LAST_COMMAND_TIMESTAMP_FILE = "data/last_command_ts.txt"

# --- Internal Helper Functions ---
def _load_last_timestamp(output_callback=print):
    """Loads the timestamp of the last processed command."""
    if os.path.exists(LAST_COMMAND_TIMESTAMP_FILE):
        try:
            with open(LAST_COMMAND_TIMESTAMP_FILE, 'r') as f:
                return int(f.read().strip())
        except ValueError:
            output_callback("Warning: Invalid timestamp file content.")
            return 0
        except Exception as e:
             output_callback(f"Error loading last timestamp: {e}")
             return 0
    return 0 # File doesn't exist

def _save_last_timestamp(timestamp, output_callback=print):
    """Saves the timestamp of the last processed command."""
    try:
        os.makedirs(os.path.dirname(LAST_COMMAND_TIMESTAMP_FILE), exist_ok=True)
        with open(LAST_COMMAND_TIMESTAMP_FILE, 'w') as f:
            f.write(str(timestamp))
    except Exception as e:
        output_callback(f"Error saving last timestamp: {e}")

# --- Main Interpreter Function (Callable by GUI) ---
def run_interpreter(output_callback=print):
    """
    Finds the latest audio command, parses it, and calls the appropriate service function.
    Uses output_callback for messages. Returns True if a command was processed (or none needed), False on error.
    """
    if not SERVICES_AVAILABLE:
        output_callback("Cannot run interpreter: Required service modules are missing or failed to import.")
        return False

    output_callback("Starting Command Interpreter...")
    last_processed_ts = _load_last_timestamp(output_callback)
    latest_audio_command = None
    latest_ts = 0

    if not os.path.exists(PROCESSED_LOG_FILE):
        output_callback(f"Log file not found: {PROCESSED_LOG_FILE}. Cannot process commands.")
        # Return True because it's not an error state, just nothing to do
        output_callback("Command Interpreter finished (no log file).")
        return True

    # 1. Find the most recent audio command
    try:
        with open(PROCESSED_LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        for line in reversed(lines):
            try:
                event = json.loads(line)
                # Check for audio command with a non-empty transcription
                if (event.get("event") == "audio_command" and
                        "transcription" in event and
                        event["transcription"] is not None and
                        event["transcription"].strip() != ""):
                    latest_audio_command = event
                    latest_ts = event.get("timestamp", 0)
                    break # Found the latest valid one
            except json.JSONDecodeError:
                continue # Skip malformed lines

    except Exception as e:
        output_callback(f"Error reading log file {PROCESSED_LOG_FILE}: {e}")
        return False # Signal error reading log

    if not latest_audio_command:
        output_callback("No valid audio commands with transcriptions found in the log.")
        output_callback("Command Interpreter finished.")
        return True # Not an error

    # 2. Check if it's already processed
    if latest_ts <= last_processed_ts:
        output_callback(f"Latest command (ts: {latest_ts}) already processed (last ts: {last_processed_ts}). No action taken.")
        output_callback("Command Interpreter finished.")
        return True # Not an error

    # 3. Process the command
    transcription = latest_audio_command.get("transcription", "").strip().lower()
    output_callback(f"Processing new command (ts: {latest_ts}): '{transcription}'")

    # Regex Matching
    # Added flexibility: allow optional punctuation at the end
    run_match = re.match(r"^(?:run|execute|start|perform)\s+(.+?)[.!?]?$", transcription)
    learn_match = re.match(r"^(?:learn|teach|save|record)\s+(.+?)[.!?]?$", transcription)

    workflow_name = None
    action_to_take = None
    success = False # Track if action was successfully executed

    if run_match:
        workflow_name = run_match.group(1).strip()
        action_to_take = "run"
        output_callback(f"Intent: Run workflow '{workflow_name}'")
    elif learn_match:
        workflow_name = learn_match.group(1).strip()
        action_to_take = "learn"
        output_callback(f"Intent: Learn workflow '{workflow_name}'")
    else:
        output_callback("Command not recognized as 'run' or 'learn'.")
        _save_last_timestamp(latest_ts, output_callback) # Save ts to avoid re-processing noise
        output_callback("Command Interpreter finished.")
        return True # Command processed (ignored), not an error

    # Execute the action by calling imported functions
    if workflow_name:
        if action_to_take == "run":
            # Directly call the run_automator function
            success = run_automator(workflow_name, output_callback)
        elif action_to_take == "learn":
            # Run perceiver first to ensure logs are processed up to this point
            output_callback("Running perceiver to ensure logs are up-to-date before learning...")
            perceiver_success = run_perceiver(output_callback)
            if perceiver_success:
                # Directly call the run_reasoner function
                success = run_reasoner(workflow_name, output_callback)
            else:
                output_callback("Perceiver failed. Cannot proceed with learning.")
                success = False # Mark as failure
        # Save the timestamp only if the action was attempted (success or fail)
        _save_last_timestamp(latest_ts, output_callback)
    else:
        output_callback("Could not extract a valid workflow name from the command.")
        _save_last_timestamp(latest_ts, output_callback) # Save ts anyway
        success = True # Consider it processed (ignored)

    output_callback(f"Command Interpreter finished (Action success: {success}).")
    return success


# --- Direct Execution Block ---
if __name__ == "__main__":
    # Check if services can be imported when run directly
    if not SERVICES_AVAILABLE:
        sys.exit(1) # Exit if imports failed

    # Call the main function using default print for output
    run_interpreter()