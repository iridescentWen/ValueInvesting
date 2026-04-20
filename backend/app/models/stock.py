from sqlalchemy import CheckConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import MARKETS

_market_values = ", ".join(f"'{m}'" for m in MARKETS)


class Stock(Base):
    __tablename__ = "stocks"
    __table_args__ = (
        CheckConstraint(f"market IN ({_market_values})", name="ck_stocks_market"),
        Index("ix_stocks_market", "market"),
    )

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    market: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    exchange: Mapped[str | None] = mapped_column(String(20), nullable=True)
