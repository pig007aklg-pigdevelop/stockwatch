"""SQLAlchemy 模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import config

Base = declarative_base()


class Position(Base):
    """持仓表 - 看板可编辑"""
    __tablename__ = "positions"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)  # NVDA / 00700
    market = Column(String(8), nullable=False)               # US / HK
    name = Column(String(64), default="")
    cost_price = Column(Float, nullable=False)
    quantity = Column(Float, default=0)
    stop_loss = Column(Float, nullable=True)                 # 止损价
    take_profit = Column(Float, nullable=True)               # 止盈价
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def futu_code(self) -> str:
        """转富途代码格式: US.NVDA / HK.00700"""
        return f"{self.market}.{self.symbol}"


class PriceSnapshot(Base):
    """价格快照 - 每次扫描写一条"""
    __tablename__ = "price_snapshots"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), index=True)
    market = Column(String(8))
    price = Column(Float)
    change_pct = Column(Float)         # 当日涨跌幅
    volume = Column(Float, default=0)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class Signal(Base):
    """信号记录 - 止盈止损触发"""
    __tablename__ = "signals"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), index=True)
    market = Column(String(8))
    action = Column(String(16))        # STOP_LOSS / TAKE_PROFIT / HOLD / ALERT
    price = Column(Float)
    cost_price = Column(Float)
    pnl_pct = Column(Float)            # 盈亏百分比
    reason = Column(Text)
    pushed = Column(Integer, default=0)  # 是否已推送
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


# 引擎+会话
import os
os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
engine = create_engine(f"sqlite:///{config.DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


def get_session():
    return SessionLocal()
