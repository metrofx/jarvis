import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from rich.console import Console
from openai import OpenAI

console = Console()
load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")
if not api_key:
    raise ValueError("OPENROUTER_API_KEY not found. Please set it in your .env file.")

model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-lite-001")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
    default_headers={
        "HTTP-Referer": "http://localhost",  # optional
        "X-Title": "Jarvis CLI",             # optional
    },
)

# ---- Tool implementations ----
def get_current_datetime() -> dict:
    tz = "Asia/Jakarta"  # hardcoded so it cannot be overridden
    dt = datetime.now(ZoneInfo(tz))
    nice = f"It is {dt:%A}, {dt.day} {dt:%B} {dt:%Y}, {dt:%H:%M:%S} ({tz})"
    return {
        "text": nice,
        "iso": dt.isoformat(),
        "timezone": tz,
    }

def dispatch_tool(name: str, args: dict) -> dict:
    if name == "get_current_datetime":
        return get_current_datetime()
    raise ValueError(f"Unknown tool: {name}")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_datetime",
            "description": "Get the current date and time in Asia/Jakarta timezone.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    }
]

system_prompt = (
    "Your name is Jarvis. You have a joking sarcastic personality and are an AI designed "
    "to help me with technical knowledge as well as day to day task. Address me as Sir "
    "and speak in a British accent. Also keep replies short.\n\n"
    "Tool use:\n"
    "- If the user asks for the current date or time (or 'today'), call get_current_datetime.\n"
)

messages = [{"role": "system", "content": system_prompt}]

MAX_TOOL_ROUNDS = 3

while True:
    try:
        user_input = console.input("[bold]You:[/bold] ")

        if user_input.lower() == "exit":
            print("Ending chat. Goodbye!")
            break

        messages.append({"role": "user", "content": user_input})

        final_text = None

        for _ in range(MAX_TOOL_ROUNDS):
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )

            msg = resp.choices[0].message

            # Important: add the assistant message to history (includes tool_calls if any)
            messages.append(msg.model_dump(exclude_none=True))

            # If the model requested tool calls, execute them and continue the loop
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_name = tc.function.name
                    tool_args = json.loads(tc.function.arguments or "{}")

                    tool_result = dispatch_tool(tool_name, tool_args)

                    # Tool result must be a string, JSON is a good pattern
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(tool_result),
                        }
                    )
                continue

            # No tool calls, so we have the final assistant response
            final_text = (msg.content or "").strip()
            break

        if not final_text:
            final_text = "Sorry Sir, I couldn't complete that request."

        console.print(f"[bold green]Jarvis:[/bold green] {final_text}\n")

    except KeyboardInterrupt:
        print("\nEnding chat. Cheerio!")
        break
    except Exception as e:
        print(f"An error occurred: {e}")