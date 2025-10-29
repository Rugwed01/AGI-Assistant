# automation_service.py (Restored Logic + Refactored)
import pyautogui
import json
import sys
import os
import time

# --- Helper to get correct path when running as bundled .exe ---
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        if hasattr(sys, '_MEIPASS'):
             base_path = os.path.dirname(sys.executable)
        else:
             base_path = os.path.dirname(os.path.abspath(__file__))
             if not base_path: base_path = os.path.abspath(".")
    except Exception:
        base_path = os.path.abspath(".")
    final_path = os.path.join(base_path, relative_path)
    return final_path

# --- Configuration ---
WORKFLOW_DIR = "workflows" # Relative to execution dir
DEFAULT_PAUSE_DURATION = 0.5  # Seconds between actions
IMAGE_CONFIDENCE = 0.8 # Keep for potential click_image fallback

# --- Key Mapping (JSON key name -> PyAutoGUI key name) ---
KEY_MAP_PYAUTOGUI = {
    "[enter]": "enter",
    "[ctrl_l]": "ctrlleft",
    "[ctrl_r]": "ctrlright",
    # Note: Shift keys are generally NOT needed for .press()
    # pyautogui.write() handles capitalization automatically.
    # We map them here primarily so the filtering logic in 'type_text'
    # recognizes them and doesn't type them literally.
    "[shift_l]": "shiftleft",
    "[shift_r]": "shiftright",
    "[alt_l]": "altleft",
    "[alt_r]": "altright",
    "[tab]": "tab",
    "[esc]": "esc",
    "[f1]": "f1",
    "[space]": "space", # Explicit map for [space]
    "[backspace]": "backspace",
    "[delete]": "delete",
    "[up]": "up",
    "[down]": "down",
    "[left]": "left",
    "[right]": "right",
}

# --- Main Automation Function (Callable by GUI) ---
def run_automator(workflow_name, output_callback=print):
    """
    Loads and executes steps using pyautogui (coordinates, typing, keys).
    Uses output_callback for messages. Returns True on success, False on failure.
    (Restored logic for key filtering and handling)
    """
    output_callback(f"Attempting to run workflow: '{workflow_name}'")

    # 1. Construct filename and check if it exists
    safe_chars = set('abcdefghijklmnopqrstuvwxyz0123456789_-')
    filename_base = "".join(c for c in workflow_name.lower().replace(" ", "_") if c in safe_chars)
    filename = filename_base + ".json" if filename_base else "untitled_workflow.json"
    workflow_dir_abs = os.path.abspath(WORKFLOW_DIR)
    filepath = os.path.join(workflow_dir_abs, filename)

    if not os.path.exists(filepath):
        output_callback(f"Error: Workflow file not found: {filepath}")
        # ... (list available workflows logic) ...
        return False

    # 2. Load the plan
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            plan = json.load(f)
        output_callback(f"Executing workflow: {plan.get('workflow_name', 'Unnamed Workflow')}")
    except Exception as e:
        output_callback(f"Error loading/parsing workflow file '{filepath}': {e}")
        return False

    # 3. Initial Delay
    original_pause = pyautogui.PAUSE
    pyautogui.PAUSE = DEFAULT_PAUSE_DURATION
    output_callback(f"Starting execution in 3 seconds... (Switch to the target window!)")
    time.sleep(3)

    # 4. Execute steps
    success = True
    if "steps" not in plan or not isinstance(plan["steps"], list):
        output_callback("Error: JSON plan is missing a valid 'steps' list.")
        pyautogui.PAUSE = original_pause
        return False

    for i, step in enumerate(plan["steps"]):
        action = step.get("action_type")
        step_id = step.get("step_id", i + 1)
        desc = step.get("target_description", "No description")
        output_callback(f"  Step {step_id}: {action} - {desc}")

        try:
            # --- ACTION: click (Coordinate-based) ---
            if action == "click":
                coords = step.get("coordinates")
                if coords and isinstance(coords, dict) and "x" in coords and "y" in coords:
                    pyautogui.click(x=int(coords["x"]), y=int(coords["y"]))
                else:
                    output_callback(f"    Warning: Skipping click step {step_id} - missing/invalid coordinates.")

            # --- ACTION: type_text (RESTORED/VERIFIED Logic) ---
            elif action == "type_text":
                output_callback("    Waiting briefly before typing...")
                time.sleep(0.5) # Delay for focus
                text_to_type = step.get("text_to_type")

                # *** Check if text_to_type exists ***
                if text_to_type is None:
                    output_callback(f"    Warning: Skipping type_text step {step_id} - missing 'text_to_type' field.")
                    continue # Skip to next step

                # *** Logic from your working version to filter keys ***
                filtered_text = ""
                current_key = ""
                in_key = False
                for char in text_to_type:
                    if char == '[':
                        in_key = True
                        current_key += char
                    elif char == ']' and in_key:
                        current_key += char
                        # Check if it's a known key *we should press instead of type*
                        # (Mainly Enter, Tab, Backspace, Delete, Esc, F-keys, maybe Arrows)
                        # We specifically DON'T want to press Shift/Ctrl/Alt here as .write handles them.
                        pyautogui_key_name = KEY_MAP_PYAUTOGUI.get(current_key)
                        if pyautogui_key_name and current_key not in ["[shift_l]", "[shift_r]", "[ctrl_l]", "[ctrl_r]", "[alt_l]", "[alt_r]"]:
                            output_callback(f"    Note: Pressing '{current_key}' ({pyautogui_key_name}) instead of typing.")
                            pyautogui.press(pyautogui_key_name)
                        elif current_key == "[space]": # Handle space explicitly
                            output_callback(f"    Note: Pressing space instead of typing '[space]'.")
                            pyautogui.press("space")
                        else:
                            # If it's Shift/Ctrl/Alt or unknown, type it literally if needed
                            # This part is debatable - usually we want .write() to handle mods.
                            # If the LLM correctly ignored mods, this won't be hit often.
                            if current_key not in ["[shift_l]", "[shift_r]", "[ctrl_l]", "[ctrl_r]", "[alt_l]", "[alt_r]"]:
                                 output_callback(f"    Warning: Unknown key '{current_key}' in type_text. Typing literally.")
                                 filtered_text += current_key
                            # else: We intentionally ignore typing modifier keys literally
                    elif in_key:
                        current_key += char
                    else:
                        filtered_text += char # Append normal characters

                # Type the accumulated non-key text
                if filtered_text:
                    output_callback(f"    Typing text: '{filtered_text}'")
                    pyautogui.write(filtered_text, interval=0.01)
                elif not any('[' in c for c in text_to_type): # Check original text wasn't empty
                     if text_to_type == "": output_callback(f"    Note: type_text step {step_id} had empty string.")
                     # else: output_callback(f"    Note: type_text step {step_id} contained only key sequences.")


            # --- ACTION: press_key (RESTORED/VERIFIED Logic) ---
            elif action == "press_key":
                key_name_json = step.get("key") or step.get("key_pressed")
                if key_name_json:
                     if key_name_json == " ": # Simple space
                          pyautogui_key = "space"
                     else: # Bracketed key like "[enter]" or "[shift_l]"
                          pyautogui_key = KEY_MAP_PYAUTOGUI.get(key_name_json)

                     if pyautogui_key:
                         # *** Critical: Don't .press() standalone modifiers ***
                         if pyautogui_key in ["shiftleft", "shiftright", "ctrlleft", "ctrlright", "altleft", "altright"]:
                              output_callback(f"    Warning: Skipping press_key step {step_id} for modifier key '{key_name_json}'. Use pyautogui.hotkey() for combinations or rely on pyautogui.write() for shifted characters.")
                         else:
                              output_callback(f"    Pressing key: {pyautogui_key}")
                              pyautogui.press(pyautogui_key)
                     else: # Handle single characters not in map
                         if len(key_name_json) == 1:
                              output_callback(f"    Pressing literal key: {key_name_json}")
                              pyautogui.press(key_name_json)
                         else:
                              output_callback(f"    Warning: Skipping press_key step {step_id}. Unknown key: '{key_name_json}'.")
                else:
                     output_callback(f"    Warning: Skipping press_key step {step_id} - missing key field.")

            # --- ACTION: click_image (Keep fallback) ---
            elif action == "click_image":
                # ... (Include OpenCV logic here if needed as fallback) ...
                output_callback(f"    Warning: 'click_image' action present but OpenCV logic might be needed.")

            # --- ACTION: click_control / type_text_control (Ignore) ---
            elif action in ["click_control", "type_text_control"]:
                 output_callback(f"    Warning: Skipping step {step_id} - action '{action}' requires pywinauto.")

            # --- Unknown Action ---
            else:
                output_callback(f"    Warning: Skipping step {step_id} - unknown action_type: '{action}'.")

            # Optional pause after typing
            if action == "type_text": time.sleep(0.1)

        # --- General Error Handling ---
        except pyautogui.FailSafeException:
             output_callback(f"    Error: PyAutoGUI Fail-Safe triggered.", file=sys.stderr)
             success = False; break
        except Exception as e:
            output_callback(f"    Error executing step {step_id} ({action}): {e}", file=sys.stderr)
            success = False; break

    # Restore original pause setting
    pyautogui.PAUSE = original_pause

    if success:
        output_callback("\nWorkflow complete.")
    else:
        output_callback("\nWorkflow stopped due to error.")

    return success


# --- Direct Execution Block ---
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python automation_service.py \"<workflow name>\"")
        # ... (List available workflows logic) ...
        sys.exit(1)

    workflow_name_arg = sys.argv[1]
    # Call the main function using default print callback
    run_automator(workflow_name_arg)