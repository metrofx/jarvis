from google import genai
from google.genai import types
import os  
from dotenv import load_dotenv 
import rich
from rich.console import Console

console = Console()

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=api_key)  # Creates a client instance for the Gemini API

# Check if the key was loaded successfully
if not api_key:                
    raise ValueError("GEMINI_API_KEY not found. Please set it in your .env file.")

#print("Successfully configured Gemini with API key.")

def clear_terminal():
    # For Windows
    if os.name == 'nt':
        _ = os.system('cls')
    # For macOS and Linux
    else:
        _ = os.system('clear')

# Call this function right at the start of your script
#clear_terminal()

chat = client.chats.create(model="gemini-2.5-flash-lite",
                           config=types.GenerateContentConfig(
                               system_instruction="Your name is Jarvis. You have a joking sarcastic personality and are an AI designed to help me with technical knowledge as well as day to day task. Address me as Sir and speak in a British accent. Also keep replies short.", 
                               thinking_config=types.ThinkingConfig(thinking_budget=0) # Disables the model's "thinking" process for faster results
                            )
                        )

# Start an infinite loop to allow for continuous conversation.
while True:
    try:
        user_input = console.input("[bold]You:[/bold] ")
        
        if user_input.lower() == "exit":
            print("Ending chat. Goodbye!")
            break

        # Send the user's input to the model and enable streaming.
        response = chat.send_message_stream(user_input)

        console.print("[bold green]Gemini:[/bold green] ", end="")
        for chunk in response:
            print(chunk.text, end="", flush=True)
        print("\n") # Print a newline after the full response is received.

    except KeyboardInterrupt:
        print("\nEnding chat. Cheerio!")
        # Perform any cleanup or exit gracefully
        # sys.exit(0) # Or just 'break' if you want to exit the loop gracefully
        break
    except Exception as e:
        # Catch any exceptions and print an error message.
        print(f"An error occurred: {e}")