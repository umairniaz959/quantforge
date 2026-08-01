import os
import json
from google import genai
from groq import Groq
from huggingface_hub import InferenceClient
import time

# ---------- Base class code ----------
BASE_CLASS_CODE = """
class Strategy:
    def __init__(self, data):
        self.data = data
        self.position = 0
        self.entry_price = 0.0
        self.sl_price = 0.0
        self.tp_price = 0.0
        self.trades = []
        self.stop_loss_pips = 20
        self.take_profit_pips = 40
        self.risk_per_trade = 2.0
    def init(self):
        pass
    def next(self, i):
        pass
    def buy(self, price, sl=None, tp=None):
        self.position = 1
        self.entry_price = price
        self.sl_price = sl if sl is not None else price - self.stop_loss_pips * 0.0001
        self.tp_price = tp if tp is not None else price + self.take_profit_pips * 0.0001
    def sell(self, price, sl=None, tp=None):
        self.position = -1
        self.entry_price = price
        self.sl_price = sl if sl is not None else price + self.stop_loss_pips * 0.0001
        self.tp_price = tp if tp is not None else price - self.take_profit_pips * 0.0001
    def close(self, price):
        if self.position != 0:
            self.trades.append({'entry': self.entry_price, 'exit': price, 'type': 'BUY' if self.position == 1 else 'SELL', 'pnl': (price - self.entry_price) if self.position == 1 else (self.entry_price - price)})
            self.position = 0
"""

# ---------- Shared system prompt ----------
SYSTEM_PROMPT = f"""
You are an expert trading strategy coder. Given a user description, generate three things in a single JSON object:

1. "code": a complete Python class `UserStrategy` that inherits from the provided `Strategy` base class.
   - Use `self.stop_loss_pips` and `self.take_profit_pips` (which will be set before the strategy runs) for stop loss and take profit values.
   - Use `self.risk_per_trade` (percentage) for position sizing.
2. "summary": a plain‑English summary of what the strategy does (max 3 sentences).
3. "params": an object with keys:
   - "stop_loss_pips": number (if mentioned, else 20)
   - "take_profit_pips": number (if mentioned, else 40)
   - "risk_per_trade": number (percentage, e.g., 2.0)
   - "indicators": list of objects each with {{"name": "sma", "period": 14, "source": "close"}}

The base class is:

{BASE_CLASS_CODE}

Important: The `data` DataFrame passed to your strategy has columns named **'open'**, **'high'**, **'low'**, **'close'** – all lowercase. Use these exact names in your code.

Return ONLY a valid JSON object, no extra text.
"""

def parse_response(content):
    """Extract JSON from possible markdown and parse."""
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    data = json.loads(content)
    data.setdefault("code", "")
    data.setdefault("summary", "Strategy generated.")
    data.setdefault("params", {})
    data["params"].setdefault("stop_loss_pips", 20)
    data["params"].setdefault("take_profit_pips", 40)
    data["params"].setdefault("risk_per_trade", 2.0)
    data["params"].setdefault("indicators", [])
    return data

# ---------- Provider 1: Gemini ----------
def call_gemini(description, api_key):
    client = genai.Client(api_key=api_key)
    full_prompt = SYSTEM_PROMPT + "\nUser description: " + description
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=full_prompt,
    )
    return parse_response(response.text)

# ---------- Provider 2: Groq (using Llama 3) ----------
def call_groq(description, api_key):
    client = Groq(api_key=api_key)
    full_prompt = SYSTEM_PROMPT + "\nUser description: " + description
    response = client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[{"role": "user", "content": full_prompt}],
        temperature=0.2,
        response_format={"type": "json_object"}  # Groq supports JSON mode
    )
    content = response.choices[0].message.content
    return parse_response(content)

# ---------- Provider 3: Hugging Face (free inference) ----------
def call_huggingface(description, api_token):
    client = InferenceClient(token=api_token)
    full_prompt = SYSTEM_PROMPT + "\nUser description: " + description
    response = client.post(
        model="meta-llama/Llama-3.2-3B-Instruct",  # free model
        inputs=full_prompt,
        parameters={"temperature": 0.2, "max_new_tokens": 2048}
    )
    # Response is a list of dicts – extract generated text
    if isinstance(response, list) and len(response) > 0:
        content = response[0].get("generated_text", "")
    else:
        content = str(response)
    return parse_response(content)

# ---------- Main function: try providers in order ----------
def parse_strategy_full(description, api_key=None):
    # 1. Gemini
    gemini_key = api_key or os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            return call_gemini(description, gemini_key)
        except Exception as e:
            print(f"Gemini failed: {e}")
    else:
        print("Gemini API key not set, skipping.")

    # 2. Groq
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            return call_groq(description, groq_key)
        except Exception as e:
            print(f"Groq failed: {e}")
    else:
        print("Groq API key not set, skipping.")

    # 3. Hugging Face
    hf_token = os.getenv("HF_API_TOKEN")
    if hf_token:
        try:
            return call_huggingface(description, hf_token)
        except Exception as e:
            print(f"Hugging Face failed: {e}")
    else:
        print("Hugging Face token not set, skipping.")

    # If all fail
    raise RuntimeError(
        "All AI providers failed. Please check your API keys or try again later.\n"
        "Providers tried: Gemini, Groq, Hugging Face.\n"
        "Set at least one of: GEMINI_API_KEY, GROQ_API_KEY, HF_API_TOKEN."
    )

# Alias for backward compatibility
parse_strategy = parse_strategy_full
