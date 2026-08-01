import json
import os
import google.generativeai as genai

def parse_strategy(text, api_key=None):
    if api_key is None:
        api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        try:
            return generate_strategy_code(text, api_key)
        except Exception as e:
            print(f"Gemini code generation failed: {e}")
            return fallback_code()
    else:
        return fallback_code()

def generate_strategy_code(description, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    system_prompt = f"""
You are an expert trading strategy coder. Given a user description, generate a complete Python class that inherits from the Strategy base class.

The base class is:

```python
class Strategy:
    def __init__(self, data):
        self.data = data
        self.position = 0
        self.entry_price = 0.0
        self.sl_price = 0.0
        self.tp_price = 0.0
        self.trades = []
    def init(self):
        pass
    def next(self, i):
        pass
    def buy(self, price, sl=None, tp=None):
        self.position = 1
        self.entry_price = price
        self.sl_price = sl
        self.tp_price = tp
    def sell(self, price, sl=None, tp=None):
        self.position = -1
        self.entry_price = price
        self.sl_price = sl
        self.tp_price = tp
    def close(self, price):
        if self.position != 0:
            self.trades.append({{'entry': self.entry_price, 'exit': price, 'type': 'BUY' if self.position == 1 else 'SELL', 'pnl': (price - self.entry_price) if self.position == 1 else (self.entry_price - price)}})
            self.position = 0
