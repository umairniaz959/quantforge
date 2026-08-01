import os
import json
import google.generativeai as genai

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
    if api_key is None:
        api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return fallback_full(description)
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

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

Return ONLY a valid JSON object, no extra text.
"""
    full_prompt = system_prompt + "\nUser description: " + description
    response = model.generate_content(full_prompt)
    content = response.text.strip()
    try:
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        data = json.loads(content)
        data.setdefault("code", fallback_code())
        data.setdefault("summary", "Strategy generated.")
        data.setdefault("params", {})
        data["params"].setdefault("stop_loss_pips", 20)
        data["params"].setdefault("take_profit_pips", 40)
        data["params"].setdefault("risk_per_trade", 2.0)
        data["params"].setdefault("indicators", [])
        return data
    except Exception as e:
        print(f"JSON parsing error: {e}\nResponse: {content}")
        return fallback_full(description)

def fallback_full(description):
    return {
        "code": fallback_code(),
        "summary": "This strategy uses a 5‑period SMA crossing above/below a 20‑period SMA to trigger buy/sell signals.",
        "params": {
            "stop_loss_pips": 20,
            "take_profit_pips": 40,
            "risk_per_trade": 2.0,
            "indicators": [
                {"name": "sma", "period": 5, "source": "close"},
                {"name": "sma", "period": 20, "source": "close"}
            ]
        }
    }

def fallback_code():
    return """
class UserStrategy(Strategy):
    def init(self):
        self.data['sma5'] = self.data['close'].rolling(5).mean()
        self.data['sma20'] = self.data['close'].rolling(20).mean()
    def next(self, i):
        if i < 20:
            return
        if self.position == 0:
            if self.data['sma5'].iloc[i] > self.data['sma20'].iloc[i] and self.data['sma5'].iloc[i-1] <= self.data['sma20'].iloc[i-1]:
                self.buy(self.data['close'].iloc[i], sl=self.data['close'].iloc[i]-self.stop_loss_pips*0.0001, tp=self.data['close'].iloc[i]+self.take_profit_pips*0.0001)
            elif self.data['sma5'].iloc[i] < self.data['sma20'].iloc[i] and self.data['sma5'].iloc[i-1] >= self.data['sma20'].iloc[i-1]:
                self.sell(self.data['close'].iloc[i], sl=self.data['close'].iloc[i]+self.stop_loss_pips*0.0001, tp=self.data['close'].iloc[i]-self.take_profit_pips*0.0001)
        else:
            pass
"""
