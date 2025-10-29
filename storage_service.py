import os
import time
import sys

# --- Configuration ---
# Ensure RAW_DATA_DIR is relative to the execution path
RAW_DATA_DIR = "data/raw"
MAX_AGE_SECONDS = 24 * 60 * 60  # 24 hours

# --- Main Cleanup Function (Callable by GUI) ---
def run_storage_cleanup(output_callback=print):
    """
    Scans RAW_DATA_DIR and deletes files older than MAX_AGE_SECONDS.
    Uses output_callback for messages. Returns True on success, False on error.
    """
    deleted_count = 0
    error_count = 0
    current_time = time.time()
    # Use absolute path for clarity, especially when run from different contexts
    raw_data_dir_abs = os.path.abspath(RAW_DATA_DIR)

    output_callback(f"Scanning '{raw_data_dir_abs}' for files older than 24 hours...")

    if not os.path.isdir(raw_data_dir_abs):
        output_callback(f"Error: Directory not found: {raw_data_dir_abs}")
        # Return True as it's not a critical failure of the cleanup *process* itself
        output_callback("Cleanup finished (Directory not found).")
        return True

    try:
        # Use os.scandir for potentially better performance
        with os.scandir(raw_data_dir_abs) as it:
            for entry in it:
                if entry.is_file():
                    try:
                        file_path = entry.path
                        # Get the last modification time
                        mod_time = entry.stat().st_mtime # Use stat result from scandir
                        file_age = current_time - mod_time

                        if file_age > MAX_AGE_SECONDS:
                            output_callback(f"  Deleting old file: {entry.name} (Age: {file_age/3600:.1f} hours)")
                            os.remove(file_path)
                            deleted_count += 1
                    except FileNotFoundError:
                        # File might have been deleted between scandir and remove
                        output_callback(f"  Warning: File disappeared during scan: {entry.name}")
                        continue # Continue with the next file
                    except Exception as e:
                        output_callback(f"  Error deleting file {entry.name}: {e}")
                        error_count += 1
    except Exception as e:
        output_callback(f"Error scanning directory {raw_data_dir_abs}: {e}")
        # Consider returning False here if scanning failure is critical
        output_callback("Cleanup finished with scanning error.")
        return False # Indicate scanning failed

    output_callback("\nCleanup complete.")
    output_callback(f"Files deleted: {deleted_count}")
    if error_count > 0:
        output_callback(f"Errors encountered during deletion: {error_count}")

    return True # Signal successful completion


# --- Direct Execution Block ---
if __name__ == "__main__":
    # Call the main function using default print callback
    run_storage_cleanup()