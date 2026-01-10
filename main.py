# --- Core Imports ---
import asyncio
import base64
import os
import sys
import traceback
import json
import websockets
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

# --- PySide6 GUI Imports ---
from PySide6.QtWidgets import QApplication, QMainWindow, QTextEdit, QVBoxLayout, QWidget, QLineEdit
from PySide6.QtCore import QObject, Signal, Slot

# --- AI Imports ---
from google import genai
from google.genai import types
from dotenv import load_dotenv

# --- Load Environment Variables ---
load_dotenv()
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    sys.exit("Error: GEMINI_API_KEY not found. Please set it in your .env file.")
if not ELEVENLABS_API_KEY:
    sys.exit("Error: ELEVENLABS_API_KEY not found. Please check your .env file.")

# --- Configuration ---
RECEIVE_SAMPLE_RATE = 24000
MODEL = "gemini-2.5-flash-lite"
VOICE_ID = 'SnAS1AhU43gJHbuUJIdM'

# ==============================================================================
# AI BACKEND LOGIC
# ==============================================================================
class AI_Core(QObject):
    """
    Handles all backend operations. Inherits from QObject to emit signals
    for thread-safe communication with the GUI.
    """
    text_received = Signal(str)
    end_of_turn = Signal()

    def __init__(self):
        super().__init__()
        self.is_running = True
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.system_instruction = ( 
            "Your name is Jarvis. You have a joking sarcastic personality and are an AI designed to help me with technical knowledge as well as day to day task. Address me as Sir and speak in a British accent. Also keep replies short.\n"
            "Tool use:\n"
            "- If the user asks for today's date (or current date), call get_today_date."
        )
        
        self.response_queue_tts = asyncio.Queue()
        self.audio_in_queue_player = asyncio.Queue()
        self.text_input_queue = asyncio.Queue()
        self.conversation_history = [] # list[types.Content]
        self.tasks = []
        self.loop = asyncio.new_event_loop()
        self.tools = self._build_tools()

    def get_today_date(self, timezone: str = "Asia/Jakarta") -> dict:
        # Hardcode the timezone here so it's impossible to override
        timezone = "Asia/Jakarta"
        dt = datetime.now(ZoneInfo(timezone))
        nice = f"Today is {dt:%A}, {dt.day} {dt:%B} {dt:%Y}"
        return {
            "text": nice,
            "iso": dt.isoformat(),
            "timezone": timezone,
        }

    def _build_tools(self):
        return [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name="get_today_date",
                        description="Get today's date in Asia/Jakarta timezone.",
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={}, # Remove the timezone property
                            required=[],
                        ),
                    )
                ]
            )
        ]

    def _dispatch_tool(self, name: str, args: dict) -> dict:
        if name == "get_today_date":
            return self.get_today_date(**(args or {}))
        raise ValueError(f"Unknown tool: {name}")

    async def process_text_input_queue(self):
        """Processes text input sent from the GUI and sends it to the AI."""
        while self.is_running:
            text = await self.text_input_queue.get()
            if text is None:
                self.text_input_queue.task_done()
                break
            
            print(f">>> [INFO] Sending text to AI: '{text}'")
            
            # Clear TTS and audio queues to prevent overlapping audio
            for q in [self.response_queue_tts, self.audio_in_queue_player]:
                while not q.empty():
                    q.get_nowait()
            
            # Add user message to conversation history (TYPED)
            self.conversation_history.append(
                types.Content(role="user", parts=[types.Part(text=text)])
            )

            try:
                final_text = None

                # Tool loop: model -> (maybe tool call) -> tool response -> model ...
                for _ in range(3):  # prevent infinite loops
                    response = await asyncio.to_thread(
                        self.client.models.generate_content,
                        model=MODEL,
                        contents=self.conversation_history,
                        config={
                            "system_instruction": self.system_instruction,
                            "temperature": 0.7,
                            "tools": self.tools,
                        },
                    )

                    model_content = response.candidates[0].content
                    self.conversation_history.append(model_content)

                    # Check for function calls
                    function_calls = []
                    for p in (model_content.parts or []):
                        fc = getattr(p, "function_call", None)
                        if fc:
                            function_calls.append(fc)

                    # No tool call -> this is the final answer
                    if not function_calls:
                        texts = [p.text for p in (model_content.parts or []) if getattr(p, "text", None)]
                        final_text = "".join(texts).strip()
                        break

                    # Execute tool calls and append tool responses
                    for fc in function_calls:
                        print(f">>> [TOOL] Calling {fc.name} with args: {fc.args}")
                        tool_result = self._dispatch_tool(fc.name, fc.args)
                        print(f">>> [TOOL] Result: {tool_result}")

                        self.conversation_history.append(
                            types.Content(
                                role="user",
                                parts=[
                                    types.Part.from_function_response(
                                        name=fc.name,
                                        response=tool_result
                                    )
                                ],
                            )
                        )

                if not final_text:
                    final_text = "Sorry Sir, I'm having trouble fetching that right now."

                # Emit the text to GUI
                self.text_received.emit(final_text)

                # Send to TTS
                await self.response_queue_tts.put(final_text)
                await self.response_queue_tts.put(None)

                self.end_of_turn.emit()

            except Exception as e:
                error_msg = f"Error generating response: {str(e)}"
                print(f">>> [ERROR] {error_msg}")
                self.text_received.emit(error_msg)
                self.end_of_turn.emit()
            
            self.text_input_queue.task_done()

    async def tts(self):
        """Converts text responses to speech using ElevenLabs."""
        uri = f"wss://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream-input?model_id=eleven_turbo_v2&output_format=pcm_24000"
        while self.is_running:
            text_chunk = await self.response_queue_tts.get()
            if text_chunk is None or not self.is_running:
                self.response_queue_tts.task_done()
                continue
            try:
                async with websockets.connect(uri) as websocket:
                    await websocket.send(json.dumps({
                        "text": " ",
                        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
                        "xi_api_key": ELEVENLABS_API_KEY,
                    }))

                    async def listen():
                        while self.is_running:
                            try:
                                message = await websocket.recv()
                                data = json.loads(message)
                                if data.get("audio"):
                                    await self.audio_in_queue_player.put(base64.b64decode(data["audio"]))
                                elif data.get("isFinal"):
                                    break
                            except websockets.exceptions.ConnectionClosed:
                                break

                    listen_task = asyncio.create_task(listen())
                    
                    # Send the entire text at once (not streaming from Gemini anymore)
                    await websocket.send(json.dumps({"text": text_chunk + " "}))
                    
                    # Signal end of text
                    await websocket.send(json.dumps({"text": ""}))
                    self.response_queue_tts.task_done()

                    await listen_task
            except Exception as e:
                print(f">>> [ERROR] TTS Error: {e}")
                self.response_queue_tts.task_done()

    async def play_audio(self):
        """Plays audio from TTS using PyAudio."""
        import pyaudio
        pya = pyaudio.PyAudio()
        stream = await asyncio.to_thread(
            pya.open,
            format=pyaudio.paInt16,
            channels=1,
            rate=RECEIVE_SAMPLE_RATE,
            output=True
        )
        print(">>> [INFO] Audio output stream is open.")
        while self.is_running:
            bytestream = await self.audio_in_queue_player.get()
            if bytestream and self.is_running:
                await asyncio.to_thread(stream.write, bytestream)
            self.audio_in_queue_player.task_done()
        stream.stop_stream()
        stream.close()
        pya.terminate()

    async def main_task_runner(self):
        """Creates and gathers all main async tasks."""
        print(">>> [INFO] Starting all backend tasks...")
        self.tasks.append(asyncio.create_task(self.tts()))
        self.tasks.append(asyncio.create_task(self.play_audio()))
        self.tasks.append(asyncio.create_task(self.process_text_input_queue()))
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def run(self):
        try:
            await self.main_task_runner()
        except asyncio.CancelledError:
            print(f"\n>>> [INFO] AI Core run loop gracefully cancelled.")
        except Exception as e:
            print(f"\n>>> [ERROR] AI Core run loop encountered an error: {type(e).__name__}: {e}")
            traceback.print_exc()
        finally:
            if self.is_running:
                self.stop()

    def start_event_loop(self):
        """Starts the asyncio event loop."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.run())

    @Slot(str)
    def handle_user_text(self, text):
        """This slot receives the text from GUI signal and puts it in the async queue."""
        if self.is_running and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.text_input_queue.put(text), self.loop)

    async def shutdown_async_tasks(self):
        """Coroutine to cancel all running tasks."""
        print(">>> [DEBUG] Shutting down async tasks...")
        if self.text_input_queue:
            await self.text_input_queue.put(None)
        for task in self.tasks:
            task.cancel()
        await asyncio.sleep(0.1)
        print(">>> [DEBUG] Async tasks shutdown complete.")

    def stop(self):
        """Thread-safe method to stop the asyncio loop and tasks."""
        if self.is_running and self.loop.is_running():
            self.is_running = False
            future = asyncio.run_coroutine_threadsafe(self.shutdown_async_tasks(), self.loop)
            try:
                future.result(timeout=5)
            except Exception as e:
                print(f">>> [ERROR] Timeout or error during async shutdown: {e}")

# ==============================================================================
# GUI APPLICATION
# ==============================================================================
class MainWindow(QMainWindow):
    user_text_submitted = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis AI Assistant")
        self.setGeometry(100, 100, 800, 600)
        self.setStyleSheet("background-color: #2b2b2b; color: #f0f0f0;")

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)

        # Chat Display #3c3f41
        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        self.text_display.setStyleSheet("""
            QTextEdit { background-color: #000000; color: #a9b7c6;
                        font-size: 16px; border: 1px solid #555; border-radius: 5px; }""")
        self.main_layout.addWidget(self.text_display)

        # Input Box
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Type your message to Jarvis here and press Enter...")
        self.input_box.setStyleSheet("""
            QLineEdit { background-color: #3c3f41; color: #a9b7c6; font-size: 14px;
                        border: 1px solid #555; border-radius: 5px; padding: 5px; }""")
        self.input_box.returnPressed.connect(self.send_user_text)
        self.main_layout.addWidget(self.input_box)
        self.input_box.setFocus()

        self.setup_backend_thread()

    def setup_backend_thread(self):
        self.ai_core = AI_Core()
        self.user_text_submitted.connect(self.ai_core.handle_user_text)
        self.ai_core.text_received.connect(self.update_text)
        self.ai_core.end_of_turn.connect(self.add_newline)

        self.backend_thread = threading.Thread(target=self.ai_core.start_event_loop)
        self.backend_thread.daemon = True
        self.backend_thread.start()

    def send_user_text(self):
        """This function is called when the user presses Enter in the input box."""
        text = self.input_box.text().strip()
        if text:
            self.text_display.append(f"<b style='color:#6DAEED;'>You:</b> {text}")
            self.user_text_submitted.emit(text)
            self.input_box.clear()
            self.input_box.setFocus() # Ensure focus stays here after sending

    @Slot(str)
    def update_text(self, text):
        """Displays the complete response from Jarvis."""
        self.text_display.append(f"<b style='color:#A9B7C6;'>Jarvis:</b> {text}")
        self.text_display.verticalScrollBar().setValue(self.text_display.verticalScrollBar().maximum())

    @Slot()
    def add_newline(self):
        """Called at the end of Jarvis's turn."""
        pass  # Not needed anymore since we display complete responses

    def closeEvent(self, event):
        print(">>> [INFO] Closing application...")
        self.ai_core.stop()
        event.accept()

# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        window = MainWindow()
        window.show()
        sys.exit(app.exec())
    except KeyboardInterrupt:
        print(">>> [INFO] Application interrupted by user.")
    finally:
        print(">>> [INFO] Application terminated.")