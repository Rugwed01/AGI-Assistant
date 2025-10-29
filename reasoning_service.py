# reasoning_service.py (Refactored - Confirmed Logic)
import os
import json
import sys
import re
from llama_cpp import Llama

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
            # Use directory of current file if possible, else current working directory
            try:
                base_path = os.path.dirname(os.path.abspath(__file__))
            except NameError: # __file__ not defined (e.g., interactive)
                 base_path = os.path.abspath(".")
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
# Use resource_path for model bundled with exe
MODEL_PATH = resource_path("models/Phi-3-mini-4k-instruct-q4.gguf")
# Log/Workflow paths relative to execution directory
PROCESSED_LOG_FILE = "data/processed_log.jsonl" # Input (coordinates, text, keys)
WORKFLOW_DIR = "workflows"                   # Output
EVENT_HISTORY_COUNT = 15 # How many past events to feed to the LLM

# --- 1. Setup ---
def setup_directories(output_callback=print):
    """Ensures the workflows directory exists."""
    try:
        # Ensure path is relative to script/exe location if not absolute
        workflow_dir_abs = os.path.abspath(WORKFLOW_DIR)
        os.makedirs(workflow_dir_abs, exist_ok=True)
    except Exception as e:
        output_callback(f"Error creating workflow directory '{workflow_dir_abs}': {e}")
        raise # Re-raise error to stop execution if dir creation fails

# --- 2. Load the LLM ---
def load_llm(output_callback=print):
    """Loads the GGUF model into memory using CPU."""
    if not os.path.exists(MODEL_PATH):
        output_callback(f"Error: Model file not found at {MODEL_PATH}")
        return None # Return None on failure
    try:
        llm = Llama(
            model_path=MODEL_PATH,
            n_ctx=4096,
            n_gpu_layers=0, # CPU only
            verbose=False
        )
        return llm
    except Exception as e:
        output_callback(f"Error loading LLM model from {MODEL_PATH}: {e}")
        return None # Return None on failure

# --- 3. Load Recent Events ---
def get_recent_events(output_callback=print, n=EVENT_HISTORY_COUNT):
    """Reads the *last N* events from the processed log file."""
    log_file_abs = os.path.abspath(PROCESSED_LOG_FILE)
    if not os.path.exists(log_file_abs):
        output_callback(f"Warning: Processed log file not found: {log_file_abs}")
        return []
    events = []
    try:
        with open(log_file_abs, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        last_n_lines = lines[-n:]
        for i, line in enumerate(last_n_lines):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as json_err:
                 output_callback(f"Warning: Skipping malformed JSON line {len(lines)-n+i+1}: {json_err}")
        return events
    except Exception as e:
        output_callback(f"Error reading log file {log_file_abs}: {e}")
        return []

# --- Helper function to clean strings ---
def clean_json_string(text):
    """Removes invalid control characters from a string."""
    if not isinstance(text, str): return text
    return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)

# --- 4. Generate the Automation Plan ---
def generate_workflow_plan(llm, workflow_name, event_history, output_callback=print):
    """
    Builds the prompt (coordinate-focused), queries the LLM, gets JSON plan.
    """
    # 1. Filter and format event history
    event_strings = []
    for event in event_history:
        event_type = event.get('event')
        timestamp = event.get('timestamp')
        ocr_text = clean_json_string(event.get('ocr_text', 'N/A'))
        ocr_escaped = ocr_text.replace('\\', '\\\\').replace("'", "\\'") # Escape for prompt string

        if event_type == 'click':
            if 'x' in event and 'y' in event:
                event_strings.append(f"- {{ts:{timestamp}, event:'click', x:{event['x']}, y:{event['y']}, ocr_text:'{ocr_escaped}'}}")
            else:
                 output_callback(f"Warning: Skipping click event (ts:{timestamp}) due to missing coordinates.")
        elif event_type == 'type':
            text_raw = event.get('text', '')
            text_cleaned = clean_json_string(text_raw)
            text_escaped = text_cleaned.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t') # Escape for prompt
            event_strings.append(f"- {{ts:{timestamp}, event:'type', text:'{text_escaped}'}}")
        elif event_type == 'key_press':
             key = event.get('key', 'N/A')
             # Escape key string for prompt if needed (e.g., if it could contain quotes)
             key_escaped = key.replace("'", "\\'")
             event_strings.append(f"- {{ts:{timestamp}, event:'key_press', key:'{key_escaped}'}}")
        # Ignore audio_command etc.

    formatted_events = "\n".join(event_strings)

    if not formatted_events:
        output_callback("Error: No relevant 'click', 'type', or 'key_press' events found.")
        return None

    # 2. Build the coordinate-focused prompt (with space/modifier fix)
    #    (Using the version with explicit key list for press_key)
    prompt = f"""You are a precise desktop automation assistant. Your task is to convert a sequence of user actions into a structured JSON automation plan. The user wants to create a workflow named "{workflow_name}".

Here are the user's recent actions (including coordinates and OCR text for clicks):
{formatted_events}

Generate a JSON plan for this workflow.
**Instructions:**
- **Action Types:** Use ONLY `click`, `type_text`, or `press_key`.
- **`click` Actions:** Use the exact `x` and `y` coordinates provided in the log. Infer a `target_description` based on the `ocr_text` if available, otherwise use a generic description like 'Clicked element'.
- **`type_text` Actions:** Combine consecutive 'type' events AND any 'key_press' events where the key is just a space (' ') that occur between them into a single `text_to_type` string. **Crucially, IGNORE any 'key_press' events for modifier keys like '[shift_l]', '[shift_r]', '[ctrl_l]', '[ctrl_r]', '[alt_l]', '[alt_r]' when combining text.** The final `text_to_type` string should represent the characters exactly as typed (e.g., 'Hello', not 'hello' preceded by a shift action). For example, `{{"key_press":"[shift_l]"}}, {{"type":"H"}}, {{"type":"ello"}}, {{"key_press":" "}}, {{"type":"world"}}` should become `{{"action_type": "type_text", "text_to_type": "Hello world"}}`. Infer a `target_description` like 'Typed text'.
- **`press_key` Actions:** Create a `press_key` action ONLY for specific intentional keys logged as `key_press` events: **'[enter]', '[tab]', '[esc]', '[backspace]', '[delete]', '[up]', '[down]', '[left]', '[right]', and function keys like '[f1]' through '[f12]'**. Do **NOT** create `press_key` actions for modifier keys like '[shift_l]', '[ctrl_l]', '[alt_l]', etc., unless they are clearly part of a separate hotkey combination not related to typing text. The `key` field in the JSON should contain the string representation from the log (e.g., "[enter]"). Infer a `target_description`.
- **Filtering:** Try to ignore redundant or clearly accidental actions if possible.

**Output JSON Schema:**
{{
  "workflow_name": "{workflow_name}",
  "steps": [
    {{
      "step_id": 1,
      "action_type": "click",
      "target_description": "Description (e.g., 'File Menu based on OCR')",
      "coordinates": {{"x": 123, "y": 456}}
    }},
    {{
      "step_id": 2,
      "action_type": "type_text",
      "target_description": "Description (e.g., 'Typed filename')",
      "text_to_type": "Text that was typed"
    }},
    {{
      "step_id": 3,
      "action_type": "press_key",
      "target_description": "Description (e.g., 'Pressed Enter Key')",
      "key": "[enter]"
    }}
  ]
}}

Provide ONLY the raw JSON object as your response, starting with {{ and ending with }}. Do not include markdown formatting or any other text.
"""

    # 3. Add the Phi-3 chat template
    formatted_prompt = f"<s><|user|>\n{prompt}<|end|>\n<|assistant|>\n" # Phi-3 template

    output_callback("Sending prompt to LLM (coordinate focus)...")

    # 4. Call the LLM
    try:
        output = llm(
            formatted_prompt,
            max_tokens=4000, # Keep high
            temperature=0.0,
            stop=["<|end|>"]
        )
        raw_output_text = output["choices"][0]["text"]
        output_callback(f"\nRaw LLM Output:\n---\n{raw_output_text}\n---")
    except Exception as e:
         output_callback(f"Error during LLM inference: {e}")
         return None


    # 5. Parse and return the JSON
    json_plan_str = None
    try:
        cleaned_output_text = clean_json_string(raw_output_text)
        json_start = cleaned_output_text.find('{')
        json_end = cleaned_output_text.rfind('}')

        if json_start == -1 or json_end == -1 or json_start > json_end:
            output_callback("--- LLM Output Error ---")
            output_callback("The cleaned model output did not contain valid JSON brackets.")
            output_callback(cleaned_output_text)
            output_callback("------------------------")
            return None

        json_plan_str = cleaned_output_text[json_start:json_end+1]
        return json.loads(json_plan_str)

    except json.JSONDecodeError as e:
        output_callback("--- LLM Output Error ---")
        output_callback(f"The cleaned model output was not valid JSON (Error: {e}):")
        if json_plan_str: output_callback(json_plan_str)
        else: output_callback("Could not extract potential JSON text.")
        output_callback("------------------------")
        return None
    except Exception as e:
        output_callback(f"An unexpected error occurred during JSON parsing: {e}")
        return None


# --- 5. Save the Workflow ---
def save_workflow(workflow_name, plan_json, output_callback=print):
    """Saves the generated JSON plan to a file."""
    safe_chars = set('abcdefghijklmnopqrstuvwxyz0123456789_-')
    filename_base = "".join(c for c in workflow_name.lower().replace(" ", "_") if c in safe_chars)
    if not filename_base: filename_base = "untitled_workflow"
    filename = filename_base + ".json"
    # Ensure path is relative to script/exe location if not absolute
    workflow_dir_abs = os.path.abspath(WORKFLOW_DIR)
    filepath = os.path.join(workflow_dir_abs, filename)
    try:
        # Ensure directory exists before saving
        os.makedirs(workflow_dir_abs, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(plan_json, f, indent=2)
        output_callback(f"\nSuccess! Workflow saved to: {filepath}")
    except Exception as e:
        output_callback(f"Error saving workflow file '{filepath}': {e}")


# --- 6. NEW Main Function (Callable by GUI) ---
def run_reasoner(workflow_name, output_callback=print):
    """
    Main logic wrapped in a function. Uses callback for output.
    Returns True on success, False on failure.
    """
    llm = None # Ensure llm is defined in outer scope
    try:
        setup_directories(output_callback) # Ensure workflow dir exists

        output_callback(f"Loading model: {MODEL_PATH}...")
        llm = load_llm(output_callback)
        if llm is None: return False # Stop if model loading failed
        output_callback("Model loaded.")

        output_callback(f"Loading last {EVENT_HISTORY_COUNT} events...")
        events = get_recent_events(output_callback, EVENT_HISTORY_COUNT)
        if not events:
            output_callback("No recent events found to process. Cannot learn workflow.")
            return False # Cannot proceed without events

        output_callback(f"Generating plan for workflow: '{workflow_name}'...")
        plan = generate_workflow_plan(llm, workflow_name, events, output_callback)

        if plan:
            # Format plan nicely for output callback
            plan_str = json.dumps(plan, indent=2)
            output_callback("\n--- Generated Plan ---")
            output_callback(plan_str)
            output_callback("----------------------")
            save_workflow(workflow_name, plan, output_callback)
            return True # Signal success
        else:
            output_callback("\nFailed to generate a valid workflow plan.")
            return False # Signal failure

    except Exception as e:
        output_callback(f"\nAn unexpected error occurred in run_reasoner: {e}")
        # import traceback # Uncomment for debugging
        # output_callback(traceback.format_exc()) # Uncomment for debugging
        return False # Signal failure
    finally:
         # Optional: Explicitly free model resources if loaded
         if llm is not None:
             # Add specific cleanup if needed for llama-cpp-python v0.2.77
             pass # Usually garbage collection is sufficient


# --- Original main block (Now just calls the function if run directly) ---
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python reasoning_service.py \"<your workflow name>\"")
        sys.exit(1) # Okay to exit when run directly
    workflow_name_arg = sys.argv[1]
    # Call the main function, using default print for output
    run_reasoner(workflow_name_arg)