# gui_app.py (Refactored for In-Process Execution)
import tkinter as tk
from tkinter import simpledialog, messagebox, scrolledtext, ttk
# import subprocess # No longer needed for core logic
import sys
import os
import threading
import queue # For thread communication
import time

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

# --- Import refactored service functions ---
try:
    from observer_service import start_observer_func, stop_observer_func
    from perceiver_service import run_perceiver
    from reasoning_service import run_reasoner
    from automation_service import run_automator
    from command_interpreter import run_interpreter
    from storage_service import run_storage_cleanup
    SERVICES_AVAILABLE = True
except ImportError as import_err:
    SERVICES_AVAILABLE = False
    # Display error during GUI startup if imports fail
    def show_import_error():
        messagebox.showerror("Import Error", f"Failed to import service modules:\n{import_err}\n\nPlease ensure all service .py files are present and correct.")
        sys.exit(1) # Exit if core components are missing

# --- Define paths (Relative to script/exe location) ---
# These might still be needed if service functions expect them relative to CWD
WORKFLOW_DIR = "workflows"
DATA_DIR = "data" # Main data directory

# --- Global Variables ---
_observer_thread = None # Thread object for the observer
output_queue = queue.Queue() # Queue for thread output

# --- Function to run service logic in thread ---
def run_service_in_thread(target_func, args=(), service_name="Service", callback_on_finish=None):
    """
    Runs a target service function (like run_perceiver) in a dedicated thread.
    Uses output_queue for logging. Calls callback_on_finish when done.
    """
    def wrapper():
        global output_queue
        output_queue.put(f"--- Starting {service_name} ---\n")
        success = False
        try:
            # Pass the queue's put method as the output callback
            # Ensure target_func accepts output_callback argument
            success = target_func(*args, output_callback=output_queue.put)
            output_queue.put(f"--- {service_name} finished (Success: {success}) ---\n")
        except TypeError as te:
             # Catch if the target function doesn't accept output_callback
             if 'output_callback' in str(te):
                 output_queue.put(f"--- ERROR: {service_name} function might not be refactored correctly for output_callback ---\n")
                 try: # Try running without callback as fallback
                     success = target_func(*args)
                     output_queue.put(f"--- {service_name} finished (Ran without callback. Success: {success}) ---\n")
                 except Exception as fallback_e:
                      output_queue.put(f"--- ERROR in {service_name} (Fallback): {fallback_e} ---\n")
             else:
                 output_queue.put(f"--- ERROR in {service_name} (Args): {te} ---\n")
        except Exception as e:
            output_queue.put(f"--- ERROR in {service_name}: {e} ---\n")
            # import traceback # Uncomment for debugging
            # output_queue.put(traceback.format_exc()) # Uncomment for debugging
            success = False # Ensure failure is marked
        finally:
            # Call the completion callback in the main thread using 'after'
            if callback_on_finish:
                root.after(0, callback_on_finish, success) # Pass success status

    thread = threading.Thread(target=wrapper, daemon=True)
    thread.start()
    return thread

# --- UI Functions ---
def start_observer_gui():
    global _observer_thread, observer_button, stop_observer_button
    if _observer_thread and _observer_thread.is_alive():
        messagebox.showwarning("Observer", "Observer is already running.")
        return

    log_output("Starting Observer...")
    try:
        # Run start_observer_func in a thread
        _observer_thread = threading.Thread(target=start_observer_func, args=(output_queue.put,), daemon=True)
        _observer_thread.start()
        # Update button states immediately (observer starts quickly)
        observer_button.config(state=tk.DISABLED)
        stop_observer_button.config(state=tk.NORMAL)
        log_output("Observer thread started.\n") # Confirmation
    except Exception as e:
        log_output(f"ERROR starting observer thread: {e}\n")
        messagebox.showerror("Error", f"Failed to start observer thread:\n{e}")

def stop_observer_gui():
    global _observer_thread, observer_button, stop_observer_button
    if _observer_thread and _observer_thread.is_alive():
        log_output("Sending stop signal to Observer...")
        try:
            # Signal the observer thread to stop via its dedicated function
            stop_observer_func()
            # Disable stop button, enable start button
            # We don't wait (join) here to keep GUI responsive.
            # The observer thread handles its own cleanup messages.
            stop_observer_button.config(state=tk.DISABLED)
            observer_button.config(state=tk.NORMAL)
            log_output("Stop signal sent. Observer will shut down.\n")
            _observer_thread = None # Clear the thread variable
        except Exception as e:
            log_output(f"Error sending stop signal: {e}\n")
            messagebox.showerror("Error", f"Failed to send stop signal:\n{e}")
            # Consider trying a more forceful stop if needed, but risky
    else:
        log_output("Observer not running or already stopped.\n")
        # Ensure buttons are in correct state if something went wrong
        stop_observer_button.config(state=tk.DISABLED)
        observer_button.config(state=tk.NORMAL)
        _observer_thread = None


def run_perceiver_gui():
    # Disable button during run? Optional.
    # perceiver_button.config(state=tk.DISABLED)
    # def on_finish(success): perceiver_button.config(state=tk.NORMAL)
    run_service_in_thread(run_perceiver, service_name="Perceiver") #, callback_on_finish=on_finish)

def learn_workflow_gui():
    workflow_name = simpledialog.askstring("Learn Workflow", "Enter the name for the new workflow:")
    if workflow_name:
        log_output("Running Perceiver before learning...\n")
        learn_button.config(state=tk.DISABLED) # Disable learn button

        # Define what happens *after* perceiver finishes
        def on_perceiver_finish(perceiver_success):
            if perceiver_success:
                log_output("Perceiver finished. Running Reasoner...\n")
                # Define what happens *after* reasoner finishes
                def on_reasoner_finish(reasoner_success):
                    learn_button.config(state=tk.NORMAL) # Re-enable learn button
                # Run reasoner
                run_service_in_thread(run_reasoner, args=(workflow_name,), service_name="Reasoner", callback_on_finish=on_reasoner_finish)
            else:
                log_output("Perceiver failed. Cannot proceed with learning.\n")
                messagebox.showerror("Learn Error", "Perceiver failed. Check logs. Cannot learn workflow.")
                learn_button.config(state=tk.NORMAL) # Re-enable on failure too

        # Start perceiver with the callback chain
        run_service_in_thread(run_perceiver, service_name="Perceiver", callback_on_finish=on_perceiver_finish)
    else:
        messagebox.showwarning("Learn Workflow", "Workflow name cannot be empty.")


def run_workflow_gui():
    # Populate dropdown with current workflows
    workflow_dir_abs = os.path.abspath(WORKFLOW_DIR)
    try:
        os.makedirs(workflow_dir_abs, exist_ok=True) # Ensure dir exists
        workflows = [f.replace('.json', '') for f in os.listdir(workflow_dir_abs) if f.endswith('.json')]
        # Convert filenames (like 'my_workflow') back to user-friendly names for display
        display_workflows = [wf.replace('_', ' ').title() for wf in workflows]
        # Store mapping from display name back to original (potentially slugified) name
        workflow_map = {disp: orig for disp, orig in zip(display_workflows, workflows)}

    except Exception as e:
        workflows = []
        display_workflows = []
        workflow_map = {}
        log_output(f"Error listing workflows: {e}\n")
        messagebox.showerror("Run Workflow", f"Error listing workflows:\n{e}")

    if not display_workflows:
        messagebox.showinfo("Run Workflow", f"No saved workflows found in '{workflow_dir_abs}'.")
        return

    # Dialog with dropdown
    dialog = tk.Toplevel(root)
    dialog.title("Select Workflow")
    dialog.geometry("350x150") # Slightly larger
    dialog.resizable(False, False)

    label = ttk.Label(dialog, text="Choose a workflow to run:")
    label.pack(pady=5)

    workflow_var = tk.StringVar()
    # Use display names in Combobox
    combo = ttk.Combobox(dialog, textvariable=workflow_var, values=display_workflows, state="readonly", width=40)
    combo.current(0)
    combo.pack(pady=5, padx=10)

    def on_ok():
        selected_display_name = workflow_var.get()
        # Map display name back to original name for the function call
        selected_workflow_name = workflow_map.get(selected_display_name)
        dialog.destroy()
        if selected_workflow_name:
             run_button.config(state=tk.DISABLED) # Disable run button during execution
             def on_run_finish(success): run_button.config(state=tk.NORMAL) # Re-enable
             run_service_in_thread(run_automator, args=(selected_workflow_name,), service_name="Automator", callback_on_finish=on_run_finish)
        else:
             messagebox.showerror("Run Error", "Could not map selected workflow name.")


    ok_button = ttk.Button(dialog, text="Run", command=on_ok)
    ok_button.pack(pady=10)
    dialog.transient(root)
    dialog.grab_set()
    root.wait_window(dialog)


def run_command_interpreter_gui():
     log_output("Running Perceiver before checking commands...\n")
     interpret_button.config(state=tk.DISABLED) # Disable button

     def on_perceiver_finish(perceiver_success):
          if perceiver_success:
               log_output("Perceiver finished. Running Command Interpreter...\n")
               def on_interpreter_finish(interpreter_success): interpret_button.config(state=tk.NORMAL) # Re-enable
               run_service_in_thread(run_interpreter, service_name="Interpreter", callback_on_finish=on_interpreter_finish)
          else:
               log_output("Perceiver failed. Cannot run interpreter.\n")
               messagebox.showerror("Interpreter Error", "Perceiver failed. Check logs.")
               interpret_button.config(state=tk.NORMAL) # Re-enable

     run_service_in_thread(run_perceiver, service_name="Perceiver", callback_on_finish=on_perceiver_finish)


def cleanup_data_gui():
    cleanup_button.config(state=tk.DISABLED)
    def on_finish(success): cleanup_button.config(state=tk.NORMAL)
    run_service_in_thread(run_storage_cleanup, service_name="Storage Cleanup", callback_on_finish=on_finish)

def log_output(message):
    """Adds message to the text area in a thread-safe way via queue."""
    # Ensure message ends with newline for clarity in text widget
    if isinstance(message, str) and not message.endswith('\n'):
        message += '\n'
    # Put message into queue, let process_output_queue handle UI update
    output_queue.put(message)

def process_output_queue():
    """Checks the output queue and updates the log area (runs in main thread)."""
    try:
        while True: # Process all messages currently in queue
            line = output_queue.get_nowait()
            if line: # Avoid inserting empty lines if queue somehow gets them
                log_text_area.insert(tk.END, line)
                log_text_area.see(tk.END) # Scroll to the end
            output_queue.task_done() # Mark task as done
    except queue.Empty:
        pass # No messages currently
    # Schedule the next check
    root.after(100, process_output_queue) # Check every 100ms

def on_closing():
    """Handle window close event."""
    global _observer_thread
    if _observer_thread and _observer_thread.is_alive():
        if messagebox.askokcancel("Quit", "Observer is running. Stop observer and quit?"):
            stop_observer_gui() # Use the UI function to stop it
            # Give a moment for stop signal to potentially process
            root.after(500, root.destroy) # Destroy after a short delay
        else:
            return # Don't close if user cancels
    else:
        root.destroy() # Close normally if observer isn't running

# --- Create Main Window ---
root = tk.Tk()
root.title("AGI Assistant Control Panel")
root.geometry("700x500") # Made slightly wider/taller

# --- Check Service Imports ---
if not SERVICES_AVAILABLE:
    root.withdraw() # Hide main window before showing error
    show_import_error()
    # sys.exit(1) # Already exits in show_import_error

# --- Ensure Data Directories Exist ---
try:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(WORKFLOW_DIR, exist_ok=True)
except Exception as e:
     messagebox.showerror("Startup Error", f"Could not create data directories:\n{e}")
     sys.exit(1)


# --- Control Buttons Frame ---
button_frame = ttk.Frame(root, padding="10")
button_frame.pack(side=tk.TOP, fill=tk.X)

observer_button = ttk.Button(button_frame, text="Start Observer", command=start_observer_gui)
observer_button.pack(side=tk.LEFT, padx=5)

stop_observer_button = ttk.Button(button_frame, text="Stop Observer", command=stop_observer_gui, state=tk.DISABLED)
stop_observer_button.pack(side=tk.LEFT, padx=5)

perceiver_button = ttk.Button(button_frame, text="Process Logs", command=run_perceiver_gui)
perceiver_button.pack(side=tk.LEFT, padx=5)

learn_button = ttk.Button(button_frame, text="Learn Workflow", command=learn_workflow_gui)
learn_button.pack(side=tk.LEFT, padx=5)

run_button = ttk.Button(button_frame, text="Run Workflow", command=run_workflow_gui)
run_button.pack(side=tk.LEFT, padx=5)

# --- Second row of buttons ---
button_frame2 = ttk.Frame(root, padding="5 10 5 10") # Added vertical padding
button_frame2.pack(side=tk.TOP, fill=tk.X)

interpret_button = ttk.Button(button_frame2, text="Check Voice Commands", command=run_command_interpreter_gui)
interpret_button.pack(side=tk.LEFT, padx=10)

cleanup_button = ttk.Button(button_frame2, text="Cleanup Old Data", command=cleanup_data_gui)
cleanup_button.pack(side=tk.LEFT, padx=10)


# --- Log Output Area ---
log_label = ttk.Label(root, text="Log Output:", padding="10 0 0 10")
log_label.pack(side=tk.TOP, anchor=tk.W)

log_text_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, height=15, width=80) # Increased width
log_text_area.pack(expand=True, fill=tk.BOTH, padx=10, pady=5)

# --- Start Queue Processor ---
root.after(100, process_output_queue)

# --- Handle Closing ---
root.protocol("WM_DELETE_WINDOW", on_closing)


# --- Run ---
root.mainloop()