# Another Jarvis AI Assistant

This repository contains the source code for Jarvis, a conversational AI assistant with a personality. Jarvis can be run in two modes: as a command-line interface (CLI) for quick interactions, or as a graphical user interface (GUI) for a more user-friendly experience with voice output.

## Features

*   **Conversational AI:** Powered by Google's Gemini model, Jarvis can engage in natural-sounding conversations.
*   **Sarcastic Personality:** Jarvis is configured to have a joking, sarcastic personality, addressing the user as "Sir" with a British accent.
*   **Two Modes of Operation:**
    *   **CLI Mode (`cli.py`):** A simple, text-based chat interface for direct interaction with the AI.
    *   **GUI Mode (`main.py`):** A PySide6-based graphical interface that includes:
        *   Text-to-speech (TTS) output using ElevenLabs for a voice-based experience.
        *   A chat window to display the conversation history.
        *   An input box for sending messages to Jarvis.
*   **Tool Usage:** Jarvis can use tools to perform specific tasks, such as getting the current date.

## Requirements

*   Python 3.x
*   The required Python packages are listed in `pyproject.toml`.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/jarvis.git
    cd jarvis
    ```
2.  **Install the dependencies:**
    ```bash
    uv sync
    ```
    *(Note: You may need to install [uv](https://docs.astral.sh/uv/#installation) as python package manager.)*

3.  **Set up your API keys:**
    Create a `.env` file in the root of the project and add your API keys for Google Gemini and ElevenLabs:
    ```
    GEMINI_API_KEY="your_gemini_api_key"
    ELEVENLABS_API_KEY="your_elevenlabs_api_key"
    ```

## Usage

### CLI Mode

To run the command-line interface, execute the following command:

```bash
uv run cli.py
```

You can then type your messages in the console and press Enter to chat with Jarvis. To exit, type `exit`.

### GUI Mode

To launch the graphical user interface, run:

```bash
uv run main.py
```

This will open a window where you can interact with Jarvis. The GUI provides a more immersive experience with voice responses.

## How it Works

### `cli.py`

The CLI application uses the `google-generativeai` library to create a simple chat client. It sends user input to the Gemini model and prints the response to the console. The conversation history is maintained to provide context for the AI.

### `main.py`

The GUI application is built using PySide6 for the user interface and asyncio for handling asynchronous tasks. It consists of two main components:

*   **`AI_Core`:** This class handles all the backend logic, including communication with the Gemini API, text-to-speech conversion using ElevenLabs, and audio playback. It runs in a separate thread to keep the GUI responsive.
*   **`MainWindow`:** This class defines the main window of the application, including the chat display and input box. It communicates with the `AI_Core` using signals and slots to ensure thread-safe operations.

The application uses websockets to stream the TTS audio from ElevenLabs, providing a real-time voice response.


