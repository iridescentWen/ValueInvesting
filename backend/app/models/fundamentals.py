import datetime as dt
from decimal import Decimal

from sqlalchemy import (
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


class Fundamentals(Base):
    __tablename__ = "fundamentals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["symbol", "market"],
            ["stocks.symbol", "stocks.market"],
            name="fk_fundamentals_stock",
        ),
        Index("ix_fundamentals_as_of", "as_of"),
    )

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    market: Mapped[str] = mapped_column(String(2), primary_key=True)
    as_of: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    pe: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    pb: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    roe: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    dividend_yield: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(22, 2), nullable=True)
    fetched_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
