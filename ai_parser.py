import os
import google.generativeai as genai

# --------------------------------------------------------------
# Base class code used in the prompt (no triple quotes inside)
# --------------------------------------------------------------
BASE_CLASS_CODE = """
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
            self.trades.append({'entry': self.entry_price, 'exit': price, 'type': 'BUY' if self.position == 1 else 'SELL', 'pnl': (price - self.entry_price) if self.position == 1 else (self.entry_price - price)})
            self.position = 0
"""

# --------------------------------------------------------------
# Main parser
# --------------------------------------------------------------
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

# --------------------------------------------------------------
# Gemini code generator
# --------------------------------------------------------------
def generate_strategy_code(description, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    # This prompt string has no internal triple quotes – the base class is inserted via placeholder.
    system_prompt = """
You are an expert trading strategy coder. Given a user description, generate a complete Python class that inherits from the Strategy base class.

The base class is:

{base_class}

Now, write a new class named `UserStrategy` that overrides `init` and `next`.  
Inside `init`, you can pre‑compute indicators using pandas on `self.data` (which is a DataFrame with columns: 'open','high','low','close').  
Inside `next`, use `self.data.iloc[i]` to access current bar; use `self.buy()`, `self.sell()`, `self.close()` to trade.  
Only use standard libraries: pandas, numpy.

The user description is: {description}

Return ONLY the Python code for the `UserStrategy` class, no explanations, no markdown.
"""
    full_prompt = system_prompt.format(base_class=BASE_CLASS_CODE, description=description)
    response = model.generate_content(full_prompt)
    code = response.text.strip()
    # Remove markdown code fences if present
    if code.startswith("```python"):
        code = code[9:]
    if code.startswith("```"):
        code = code[3:]
    if code.endswith("```"):
        code = code[:-3]
    return code.strip()

# --------------------------------------------------------------
# Fallback code (simple MA crossover)
# --------------------------------------------------------------
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
                self.buy(self.data['close'].iloc[i], sl=self.data['close'].iloc[i]-20*0.0001, tp=self.data['close'].iloc[i]+40*0.0001)
            elif self.data['sma5'].iloc[i] < self.data['sma20'].iloc[i] and self.data['sma5'].iloc[i-1] >= self.data['sma20'].iloc[i-1]:
                self.sell(self.data['close'].iloc[i], sl=self.data['close'].iloc[i]+20*0.0001, tp=self.data['close'].iloc[i]-40*0.0001)
        else:
            pass
"""
