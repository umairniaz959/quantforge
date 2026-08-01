import openai
import json
import re
import os

# --------------------------------------------------------------
# Main parser: tries OpenAI first, then fallback if no key
# --------------------------------------------------------------
def parse_strategy(text, api_key=None):
    """
    Takes a plain English strategy description and returns a structured dict.
    """
    if api_key is None:
        api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            return parse_with_openai(text, api_key)
        except Exception as e:
            print(f"OpenAI parsing failed: {e}. Using fallback.")
            return fallback_parse(text)
    else:
        return fallback_parse(text)

# --------------------------------------------------------------
# OpenAI parser (requires API key)
# --------------------------------------------------------------
def parse_with_openai(text, api_key):
    openai.api_key = api_key
    system_prompt = """
You are a trading strategy parser. Convert the following description into a structured JSON with these fields:
- entry: { type: "buy"|"sell", indicator: "sma"|"ema"|"rsi"|"macd"|"bb"|"price", period: int (if applicable), condition: "cross_above"|"cross_below"|"above"|"below"|"between", level: float (if applicable), reference_indicator: (optional) }
- exit: { type: "stop_loss"|"take_profit"|"trailing"|"indicator", indicator: ..., period: ..., condition: ..., level: ... }
- risk_per_trade: float (percentage)
- stop_loss_pips: float (optional)
- take_profit_pips: float (optional)
Return only valid JSON, no extra text.
"""
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        temperature=0.2
    )
    content = response.choices[0].message.content
    try:
        return json.loads(content)
    except:
        return fallback_parse(text)

# --------------------------------------------------------------
# Fallback parser (no API key needed) – recognises common phrases
# --------------------------------------------------------------
def fallback_parse(text):
    # Default parameters (a simple MA crossover)
    params = {
        "entry": {
            "type": "buy",
            "indicator": "sma",
            "period": 5,
            "condition": "cross_above",
            "level": None,
            "reference_indicator": "sma",
            "ref_period": 20
        },
        "exit": {
            "type": "indicator",
            "indicator": "sma",
            "period": 20,
            "condition": "cross_below",
            "level": None
        },
        "risk_per_trade": 2.0,
        "stop_loss_pips": 20,
        "take_profit_pips": 40
    }

    text_lower = text.lower()

    # --- RSI detection ---
    if "rsi" in text_lower:
        params["entry"]["indicator"] = "rsi"
        params["entry"]["period"] = 14
        if "above" in text_lower:
            params["entry"]["condition"] = "above"
            # try to extract a number after 'above'
            match = re.search(r"above\s+(\d+)", text_lower)
            if match:
                params["entry"]["level"] = float(match.group(1))
        if "below" in text_lower:
            params["entry"]["condition"] = "below"
            match = re.search(r"below\s+(\d+)", text_lower)
            if match:
                params["entry"]["level"] = float(match.group(1))
        # Also maybe exit on opposite RSI level
        if "sell when" in text_lower or "exit" in text_lower:
            # try to find another RSI level
            match = re.search(r"(?:sell|exit).*?rsi.*?(?:above|below)\s+(\d+)", text_lower)
            if match:
                params["exit"]["indicator"] = "rsi"
                params["exit"]["period"] = 14
                if "above" in text_lower:
                    params["exit"]["condition"] = "cross_above"
                else:
                    params["exit"]["condition"] = "cross_below"
                params["exit"]["level"] = float(match.group(1))

    # --- Moving Averages ---
    if "ma" in text_lower or "moving average" in text_lower:
        # find numbers like "5 period" or "20 period"
        periods = re.findall(r"(\d+)\s*[- ]?period", text_lower)
        if len(periods) >= 2:
            params["entry"]["indicator"] = "sma"
            params["entry"]["period"] = int(periods[0])
            params["exit"]["indicator"] = "sma"
            params["exit"]["period"] = int(periods[1])
            # detect cross above/below
            if "cross above" in text_lower:
                params["entry"]["condition"] = "cross_above"
                params["exit"]["condition"] = "cross_below"
            elif "cross below" in text_lower:
                params["entry"]["condition"] = "cross_below"
                params["exit"]["condition"] = "cross_above"

    # --- Stop loss and take profit ---
    sl_match = re.search(r"stop loss\s*(\d+)", text_lower)
    if sl_match:
        params["stop_loss_pips"] = float(sl_match.group(1))
    tp_match = re.search(r"take profit\s*(\d+)", text_lower)
    if tp_match:
        params["take_profit_pips"] = float(tp_match.group(1))

    # --- Risk per trade ---
    risk_match = re.search(r"risk\s*(\d+)%", text_lower)
    if risk_match:
        params["risk_per_trade"] = float(risk_match.group(1))

    return params
