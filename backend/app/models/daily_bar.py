import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DailyBar(Base):
    __tablename__ = "daily_bars"
    __table_args__ = (
        ForeignKeyConstraint(
            ["symbol", "market"],
            ["stocks.symbol", "stocks.market"],
            name="fk_daily_bars_stock",
        ),
        Index("ix_daily_bars_date", "date"),
    )

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    market: Mapped[str] = mapped_column(String(2), primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fetched_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
