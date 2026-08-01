import os
import json
import openai
from google import genai
from groq import Groq
from huggingface_hub import InferenceClient

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

# ---------- Provider 1: Gemini (updated models) ----------
def call_gemini(description, api_key):
    client = genai.Client(api_key=api_key)
    full_prompt = SYSTEM_PROMPT + "\nUser description: " + description
    # Try latest stable models first
    models = [
        "gemini-3.6-flash",      # Latest GA model [reference:19]
        "gemini-3.5-flash-lite", # Fastest, lowest-cost [reference:20]
        "gemini-2.5-pro",        # Most advanced [reference:21]
        "gemini-2.5-flash"       # Good balance [reference:22]
    ]
    last_error = None
    for model in models:
        try:
            response = client.models.generate_content(
                model=model,
                contents=full_prompt,
            )
            return parse_response(response.text)
        except Exception as e:
            last_error = e
            continue
    raise last_error

# ---------- Provider 2: Groq (updated models) ----------
def call_groq(description, api_key):
    client = Groq(api_key=api_key)
    full_prompt = SYSTEM_PROMPT + "\nUser description: " + description
    # Try currently supported models [reference:23][reference:24]
    models = [
        "openai/gpt-oss-120b",     # Strong reasoning, recommended replacement [reference:25]
        "llama-4-maverick",        # Meta's latest [reference:26]
        "llama-4-scout",           # Meta's latest [reference:27]
        "qwen/qwen3.6-27b"         # Recommended replacement for Qwen3-32B [reference:28]
    ]
    last_error = None
    for model in models:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": full_prompt}],
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            return parse_response(response.choices[0].message.content)
        except Exception as e:
            last_error = e
            continue
    raise last_error

# ---------- Provider 3: Hugging Face (free inference) ----------
def call_huggingface(description, api_token):
    client = InferenceClient(token=api_token)
    full_prompt = SYSTEM_PROMPT + "\nUser description: " + description
    # Use the serverless inference API with a supported model
    # For free tier, try smaller models first
    models = [
        "meta-llama/Llama-3.2-3B-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.3",
        "microsoft/Phi-3-mini-4k-instruct"
    ]
    last_error = None
    for model in models:
        try:
            response = client.chat_completion(
                model=model,
                messages=[{"role": "user", "content": full_prompt}],
                max_tokens=2048,
                temperature=0.2,
            )
            content = response.choices[0].message.content
            return parse_response(content)
        except Exception as e:
            last_error = e
            continue
    raise last_error

# ---------- Provider 4: Zhipu AI / GLM (updated endpoint) ----------
def call_glm(description, api_key):
    # Use Zhipu AI's official endpoint [reference:29]
    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://open.bigmodel.cn/api/paas/v4/"
    )
    full_prompt = SYSTEM_PROMPT + "\nUser description: " + description
    # Try latest GLM models [reference:30][reference:31]
    models = [
        "glm-5.1",      # Latest flagship [reference:32]
        "glm-5-turbo",  # Fast version
        "glm-4.7",      # Latest GLM-4 series [reference:33]
        "glm-4.6"       # Stable fallback [reference:34]
    ]
    last_error = None
    for model in models:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": full_prompt}],
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            return parse_response(response.choices[0].message.content)
        except Exception as e:
            last_error = e
            continue
    raise last_error

# ---------- Main function ----------
def parse_strategy_full(description, api_key=None):
    errors = []

    # 1. Gemini
    gemini_key = api_key or os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            return call_gemini(description, gemini_key)
        except Exception as e:
            errors.append(f"Gemini: {e}")
            print(f"Gemini failed: {e}")
    else:
        errors.append("Gemini: API key not set")

    # 2. Groq
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            return call_groq(description, groq_key)
        except Exception as e:
            errors.append(f"Groq: {e}")
            print(f"Groq failed: {e}")
    else:
        errors.append("Groq: API key not set")

    # 3. Hugging Face
    hf_token = os.getenv("HF_API_TOKEN")
    if hf_token:
        try:
            return call_huggingface(description, hf_token)
        except Exception as e:
            errors.append(f"Hugging Face: {e}")
            print(f"Hugging Face failed: {e}")
    else:
        errors.append("Hugging Face: API token not set")

    # 4. Zhipu AI / GLM
    glm_key = os.getenv("ZAI_API_KEY")
    if glm_key:
        try:
            return call_glm(description, glm_key)
        except Exception as e:
            errors.append(f"GLM: {e}")
            print(f"GLM failed: {e}")
    else:
        errors.append("GLM: API key not set")

    # If all fail
    raise RuntimeError(
        "All AI providers failed. Here are the details:\n" + "\n".join(errors)
    )

parse_strategy = parse_strategy_full
