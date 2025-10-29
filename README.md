# Local-First AGI Assistant 🤖

## 📜 Description

This project is a desktop assistant built for the "AGI Assistant" hackathon. Its goal is to learn user workflows by observing screen interactions (clicks, typing) and voice commands, and then automate those tasks. Crucially, **all processing (observation, transcription, reasoning, automation) happens 100% locally** on the user's machine, ensuring privacy and offline functionality.

---

## ✨ Core Features

* **Screen Observation:** Captures mouse clicks, keyboard inputs, and associated screenshots locally using `pynput` and `mss`.
* **Audio Capture:** Records voice commands using a push-to-talk key (`sounddevice`).
* **Local Transcription:** Uses a pre-built `whisper-cli.exe` binary to transcribe captured audio offline.
* **Local OCR:** Employs `pytesseract` (interfacing with a local Tesseract OCR installation) to extract text from screenshots.
* **Local Reasoning:** Utilizes a local quantized language model (Phi-3 GGUF via `llama-cpp-python` on CPU) to analyze observed actions and generate automation plans (JSON format).
* **Desktop Automation:** Executes the learned workflows using `pyautogui` to simulate clicks and typing based on coordinates and text from the plan.
* **GUI Control Panel:** A simple `tkinter` interface to manage the assistant's functions.
* **Offline First:** Designed to run entirely without external API calls or internet connectivity (after initial setup).

---

## 💻 Technology Stack

* **Language:** Python 3.10
* **Core Libraries:**
    * `pynput`: Global input monitoring (mouse, keyboard).
    * `mss`: Fast screen capture.
    * `sounddevice`, `scipy`, `numpy`: Audio recording and processing.
    * `pytesseract`, `Pillow`: Optical Character Recognition (OCR).
    * `llama-cpp-python`: CPU-based inference for the local LLM (Phi-3 GGUF).
    * `pyautogui`: Desktop automation (clicks, typing).
    * `tkinter`, `ttk`: Graphical User Interface.
* **Packaging:** `PyInstaller`
* **External Dependencies (Required):**
    * **Tesseract OCR Engine:** Must be installed separately. [Installation Guide](https://tesseract-ocr.github.io/tessdoc/Installation.html)
    * **Whisper CLI Binary:** Pre-built `whisper-cli.exe` (and its required DLLs like `ggml.dll`, `whisper.dll`) from the [ggml/whisper.cpp releases](https://github.com/ggerganov/whisper.cpp/releases).
    * **LLM Model:** Phi-3 Mini Instruct GGUF (e.g., `Phi-3-mini-4k-instruct-q4_0.gguf`) from [Hugging Face](https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf).
    * **Whisper Model:** Base English model (e.g., `ggml-base.en.bin`) from [ggml/whisper.cpp datasets](https://huggingface.co/datasets/ggerganov/whisper.cpp).
    * **Microsoft Visual C++ Redistributable:** Required for `llama-cpp-python` and potentially Whisper CLI. [Download Link](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)

---

## 📁 Project Structure
```
/agi-assistant/
|-- gui_app.py                # Main Tkinter GUI application
|-- observer_service.py       # Captures user inputs and screenshots/audio
|-- perceiver_service.py      # Runs OCR and STT on captured data
|-- reasoning_service.py      # Uses LLM to generate automation plans (JSON)
|-- automation_service.py     # Executes automation plans using pyautogui
|-- command_interpreter.py    # Parses transcribed audio commands
|-- storage_service.py        # Cleans up old raw data
|
|-- requirements.txt          # Python dependencies
|-- AGI_Assistant.spec        # PyInstaller configuration file
|
|-- /models/                  # LLM (.gguf) and Whisper (.bin) models go here
|   |-- Phi-3-mini-4k-instruct-q4.gguf
|   |-- ggml-base.en.bin
|
|-- /data/                    # Runtime data (logs, processed data)
|   |-- /raw/                 # Raw screenshots (.png) and audio (.wav)
|   |-- observer_log.jsonl    # Raw event log from observer
|   |-- processed_log.jsonl   # Enriched log after perceiver runs
|   |-- last_command_ts.txt   # Timestamp for command interpreter
|
|-- /workflows/               # Saved automation plans (.json)
|   |-- example_workflow.json
|
|-- whisper-cli.exe           # Whisper executable (place in root)
|-- whisper.dll               # Whisper DLL (place in root)
|-- ggml.dll                  # Whisper DLL (place in root)
|-- ggml-base.dll             # Whisper DLL (place in root)
|-- ggml-cpu.dll              # Whisper DLL (place in root)
|-- SDL2.dll                  # Whisper DLL (place in root)
# Add any other required DLLs for whisper-cli.exe here
```
## ⚙️ Setup Instructions

1.  **Prerequisites:**
    * Install **Python 3.10**. Ensure `python` and `pip` are in your system PATH.
    * Install **Tesseract OCR**. Make note of the installation path, especially the `tessdata` folder. [Tesseract Installation](https://tesseract-ocr.github.io/tessdoc/Installation.html)
    * Install the **Microsoft Visual C++ Redistributable (x64)**. [Download Link](https://aka.ms/vs/17/release/vc_redist.x64.exe)
2.  **Clone Repository:** (If applicable)
    ```bash
    git clone <your-repo-url>
    cd agi-assistant
    ```
3.  **Create Virtual Environment:**
    ```bash
    python -m venv .venv
    .\.venv\Scripts\activate
    ```
4.  **Install Python Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *(Make sure `requirements.txt` includes: `pynput`, `mss`, `sounddevice`, `numpy`, `scipy`, `pytesseract`, `Pillow`, `llama-cpp-python`)*
5.  **Download & Place External Files:**
    * Download the **Phi-3 GGUF model** and place it in the `/models/` folder.
    * Download the **Whisper `ggml-base.en.bin` model** and place it in the `/models/` folder.
    * Download the **Whisper CLI Windows binary zip** from [ggml/whisper.cpp releases](https://github.com/ggerganov/whisper.cpp/releases). Extract `whisper-cli.exe` and **all** accompanying `.dll` files directly into the project's root folder (`/agi-assistant/`).
6.  **(Optional but Recommended) Configure Paths:**
    * In `perceiver_service.py`, verify that `TESSERACT_CMD_PATH` points to your `tesseract.exe` if it's not in your system PATH.
    * In `AGI_Assistant.spec`, verify the **source path** for `tessdata` is correct before building the `.exe`.

---

## ▶️ How to Run

1.  **Activate Virtual Environment:**
    ```bash
    .\.venv\Scripts\activate
    ```
2.  **Run the GUI:**
    ```bash
    python gui_app.py
    ```
3.  **Using the GUI:**
    * **Start Observer:** Begins recording user actions. Status messages appear in the log.
    * **Stop Observer:** Stops recording.
    * **Process Logs:** Runs OCR on screenshots and Whisper STT on audio files captured since the last run. Updates `processed_log.jsonl`.
    * **Learn Workflow:** Prompts for a workflow name. Runs "Process Logs" again, then uses the LLM to analyze the latest events in `processed_log.jsonl` and saves a plan to the `workflows` folder.
    * **Run Workflow:** Shows a dropdown of saved `.json` files in the `workflows` folder. Select one to execute the automation.
    * **Check Voice Commands:** Runs "Process Logs", then checks the latest audio command transcription for "run" or "learn" intents and triggers the corresponding action.
    * **Cleanup Old Data:** Deletes raw screenshots/audio older than 24 hours from `data/raw/`.

---

## 🧠 How It Works (Simplified Loop)

1.  **Observe:** `observer_service.py` logs clicks (coords), typing (text), key presses (codes), and audio commands (`.wav`).
2.  **Perceive:** `perceiver_service.py` enriches the log: runs OCR on click screenshots (`ocr_text`) and transcribes audio commands (`transcription`).
3.  **Interpret (Voice):** `command_interpreter.py` checks the latest transcription for keywords ("run", "learn") and triggers the next step.
4.  **Reason:** `reasoning_service.py` takes the last N processed events, feeds them (and instructions) to the local LLM, asking for a JSON automation plan based on the observed sequence.
5.  **Act:** `automation_service.py` reads a saved JSON plan and uses `pyautogui` to execute the sequence of clicks, types, and key presses.

---

## 📦 Building the `.exe`

1.  **Ensure `AGI_Assistant.spec` is configured correctly:**
    * Verify all **source paths** in the `datas` section are correct (especially `tessdata`, Whisper files, model files, `llama.dll`).
    * Ensure all necessary **`hiddenimports`** are listed.
2.  **Activate Virtual Environment:** `.\.venv\Scripts\activate`
3.  **Run PyInstaller:**
    ```bash
    pyinstaller AGI_Assistant.spec
    ```
4.  **Find Output:** The distributable application folder will be created in `dist/AGI_Assistant_App`.
5.  **Distribute:** Share the **entire `AGI_Assistant_App` folder**. Run `AGI_Assistant.exe` from inside this folder.

---

## ⚠️ Limitations

* **Automation Fragility:** Relies on screen coordinates (`pyautogui`), which can break if windows are moved, resized, or UI elements change position.
* **LLM Interpretation:** The LLM might not always perfectly interpret the action sequence or follow prompt instructions, leading to incorrect or incomplete JSON plans (e.g., issues with modifier keys, complex sequences). Requires careful prompt engineering and clean input logs.
* **Basic UI:** The Tkinter interface is functional but minimal.
* **No Robust Window Tracking:** The automation assumes the correct window is active; it doesn't explicitly track or switch between application windows based on the learned workflow context.
* **Error Handling:** Basic error handling; complex failures during automation might require manual intervention.

---

## 🚀 Future Improvements

* **OpenCV Integration:** Replace coordinate clicks with image template matching (`pyautogui.locateCenterOnScreen`) for more visual robustness.
* **Accessibility APIs (`pywinauto`):** Integrate `pywinauto` to interact with UI elements via their properties (name, control type) instead of coordinates or images for maximum robustness (major refactor).
* **Improved UI/UX:** Enhance the GUI with better status feedback, workflow management (edit/delete), and configuration options.
* **Advanced Command Parsing:** Use more sophisticated NLP for interpreting voice commands.
* **Contextual Awareness:** Track active application windows during observation and use that info during reasoning and automation.
* **Error Recovery:** Implement strategies for the automator to recover from errors (e.g., element not found).
