"""SQLAlchemy 模型"""
import os
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import config

Base = declarative_base()


class Position(Base):
    __tablename__ = "positions"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    market = Column(String(8), nullable=False)
    name = Column(String(64), default="")
    cost_price = Column(Float, nullable=False)
    quantity = Column(Float, default=0)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    watch_below = Column(Float, nullable=True)
    watch_above = Column(Float, nullable=True)
    composite_score = Column(Float, nullable=True)
    score_valuation = Column(Float, nullable=True)
    score_capital = Column(Float, nullable=True)
    score_technical = Column(Float, nullable=True)
    score_fundamental = Column(Float, nullable=True)
    score_news = Column(Float, nullable=True)
    score_updated_at = Column(DateTime, nullable=True)
    recommended_buy = Column(Float, nullable=True)
    recommended_sell = Column(Float, nullable=True)
    last_trade_id = Column(Integer, nullable=True)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def futu_code(self) -> str:
        return f"{self.market}.{self.symbol}"


class Watchlist(Base):
    __tablename__ = "watchlist"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    market = Column(String(8), nullable=False)
    name = Column(String(64), default="")

    watch_below = Column(Float, nullable=True)
    watch_above = Column(Float, nullable=True)

    composite_score = Column(Float, nullable=True)
    score_valuation = Column(Float, nullable=True)
    score_capital = Column(Float, nullable=True)
    score_technical = Column(Float, nullable=True)
    score_fundamental = Column(Float, nullable=True)
    score_news = Column(Float, nullable=True)
    score_updated_at = Column(DateTime, nullable=True)
    recommended_buy = Column(Float, nullable=True)
    recommended_sell = Column(Float, nullable=True)

    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def futu_code(self) -> str:
        return f"{self.market}.{self.symbol}"


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), index=True)
    market = Column(String(8))
    price = Column(Float)
    change_pct = Column(Float)
    volume = Column(Float, default=0)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class Signal(Base):
    __tablename__ = "signals"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), index=True)
    market = Column(String(8))
    action = Column(String(16))
    price = Column(Float)
    cost_price = Column(Float)
    pnl_pct = Column(Float)
    reason = Column(Text)
    pushed = Column(Integer, default=0)
    acted_trade_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class News(Base):
    __tablename__ = "news"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), index=True, nullable=True)  # None = 全局新闻
    title = Column(String(500))
    url = Column(String(1000), unique=True)
    source = Column(String(64))
    summary = Column(Text, default="")
    sentiment = Column(String(16), default="")  # bullish/bearish/neutral
    sentiment_type = Column(String(8), default="")  # 事实 / 观点
    sentiment_confidence = Column(Float, nullable=True)
    published_at = Column(DateTime, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class NewsSentimentCache(Base):
    __tablename__ = "news_sentiment_cache"
    content_hash = Column(String(40), primary_key=True)
    sentiment = Column(String(16))
    news_type = Column("type", String(8))
    confidence = Column(Float)
    reason = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    market = Column(String(8), nullable=False)
    side = Column(String(8), nullable=False)  # BUY / SELL
    price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    fee = Column(Float, default=0.0)
    realized_pnl = Column(Float, nullable=True)
    holding_days = Column(Integer, nullable=True)
    linked_signal_id = Column(Integer, nullable=True, index=True)
    notes = Column(Text, default="")
    traded_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
engine = create_engine(f"sqlite:///{config.DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


def get_session():
    return SessionLocal()
