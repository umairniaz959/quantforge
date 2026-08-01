import os
import json
from google import genai  # New SDK – no more warnings

# This is the base class that the generated strategy will inherit from.
# It stays unchanged.
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

def parse_strategy_full(description, api_key=None):
    """
    Main function: takes a plain‑English strategy description,
    sends it to Gemini, and returns a dict with 'code', 'summary', and 'params'.
    """
    if api_key is None:
        api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("No Gemini API key found. Please set GEMINI_API_KEY in your environment or secrets.")

    try:
        # 1. Create the new Gemini client
        client = genai.Client(api_key=api_key)

        # 2. Build the prompt – this tells Gemini exactly what to produce
        system_prompt = f"""
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

Important: The `data` DataFrame passed to your strategy has columns named **'open'**, **'high'**, **'low'**, **'close'** – all lowercase. Use these exact names in your code. Use `self.data['close']` for close prices.

Return ONLY a valid JSON object, no extra text.
"""
        full_prompt = system_prompt + "\nUser description: " + description

        # 3. Call Gemini – using the new `generate_content` method
        response = client.models.generate_content(
            model="gemini-2.0-flash",   # stable and fast model
            contents=full_prompt,
        )

        # 4. Extract the response text
        content = response.text.strip()

        # 5. Remove any markdown code fences that Gemini might add
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        # 6. Parse JSON and fill defaults
        data = json.loads(content)
        data.setdefault("code", "")
        data.setdefault("summary", "Strategy generated.")
        data.setdefault("params", {})
        data["params"].setdefault("stop_loss_pips", 20)
        data["params"].setdefault("take_profit_pips", 40)
        data["params"].setdefault("risk_per_trade", 2.0)
        data["params"].setdefault("indicators", [])
        return data

    except Exception as e:
        raise RuntimeError(f"Failed to generate strategy code with Gemini: {e}")

# Backward compatibility – so you can still use `parse_strategy` if needed
parse_strategy = parse_strategy_full
