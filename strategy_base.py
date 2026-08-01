# strategy_base.py

class Strategy:
    """
    Base class for user-generated strategies.
    The `init` method is called once at the start.
    The `next` method is called on every bar (index from 0 to len(data)-1).
    """
    def __init__(self, data):
        self.data = data          # expects a DataFrame or dictionary with OHLC
        self.position = 0         # 0 = flat, 1 = long, -1 = short
        self.entry_price = 0.0
        self.sl_price = 0.0
        self.tp_price = 0.0
        self.trades = []

    def init(self):
        """Override this method to set up indicators, etc."""
        pass

    def next(self, i):
        """
        Called on each bar index `i`.
        Use self.data to get current price and indicators.
        Call self.buy() or self.sell() to enter a trade.
        Call self.close() to exit.
        """
        pass

    def buy(self, price, sl=None, tp=None):
        """Place a buy order at given price (optional SL/TP)."""
        self.position = 1
        self.entry_price = price
        self.sl_price = sl
        self.tp_price = tp

    def sell(self, price, sl=None, tp=None):
        """Place a sell order."""
        self.position = -1
        self.entry_price = price
        self.sl_price = sl
        self.tp_price = tp

    def close(self, price):
        """Close the current position."""
        if self.position != 0:
            self.trades.append({
                'entry': self.entry_price,
                'exit': price,
                'type': 'BUY' if self.position == 1 else 'SELL',
                'pnl': (price - self.entry_price) if self.position == 1 else (self.entry_price - price)
            })
            self.position = 0
