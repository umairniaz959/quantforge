import sqlalchemy as db
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import hashlib
import os

# Database file (SQLite)
DB_FILE = "quantforge.db"
Base = declarative_base()

# --- User Model ---
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# --- Backtest Result Model ---
class BacktestResult(Base):
    __tablename__ = 'backtest_results'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    risk_cents = Column(Integer)
    start_date = Column(String(20))
    end_date = Column(String(20))
    total_trades = Column(Integer)
    win_rate = Column(Float)
    profit_factor = Column(Float)
    total_withdrawn_usd = Column(Float)
    avg_monthly_usd = Column(Float)
    max_dd_cents = Column(Integer)
    max_dd_percent = Column(Float)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    # We'll store the trade log as JSON or CSV? For simplicity, store as text (JSON)
    trade_log_json = Column(Text)  # optional

# --- Database Connection ---
def get_engine():
    return create_engine(f'sqlite:///{DB_FILE}')

def init_db():
    engine = get_engine()
    Base.metadata.create_all(engine)
    return engine

def get_session():
    engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()

# --- Password Hashing ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hash_val):
    return hash_password(password) == hash_val

# --- User Functions ---
def register_user(username, email, password):
    session = get_session()
    try:
        # Check if user exists
        existing = session.query(User).filter((User.username == username) | (User.email == email)).first()
        if existing:
            return False, "Username or email already exists."
        new_user = User(
            username=username,
            email=email,
            password_hash=hash_password(password)
        )
        session.add(new_user)
        session.commit()
        return True, "User created successfully."
    except Exception as e:
        session.rollback()
        return False, str(e)
    finally:
        session.close()

def login_user(username, password):
    session = get_session()
    try:
        user = session.query(User).filter(User.username == username).first()
        if user and verify_password(password, user.password_hash):
            return True, user.id
        return False, None
    finally:
        session.close()

def save_backtest_result(user_id, results, trades_df, monthly_df, start_date, end_date):
    session = get_session()
    try:
        # Convert trades_df to JSON (optional)
        trade_json = trades_df.to_json(orient='records') if trades_df is not None else None
        new_result = BacktestResult(
            user_id=user_id,
            risk_cents=results['risk_cents'],
            start_date=start_date,
            end_date=end_date,
            total_trades=results['total_trades'],
            win_rate=results['win_rate'],
            profit_factor=results['profit_factor'],
            total_withdrawn_usd=results['total_withdrawn_usd'],
            avg_monthly_usd=results['avg_monthly_usd'],
            max_dd_cents=results['max_dd_cents'],
            max_dd_percent=results['max_dd_percent'],
            trade_log_json=trade_json
        )
        session.add(new_result)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        print(f"Error saving: {e}")
        return False
    finally:
        session.close()

def get_user_results(user_id):
    session = get_session()
    try:
        results = session.query(BacktestResult).filter(BacktestResult.user_id == user_id).order_by(BacktestResult.created_at.desc()).all()
        return results
    finally:
        session.close()
