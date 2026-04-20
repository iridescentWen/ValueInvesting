import datetime as dt

from sqlalchemy import DateTime, ForeignKeyConstraint, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Watchlist(Base):
    __tablename__ = "watchlists"
    __table_args__ = (
        ForeignKeyConstraint(
            ["symbol", "market"],
            ["stocks.symbol", "stocks.market"],
            ondelete="CASCADE",
            name="fk_watchlists_stock",
        ),
    )

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    market: Mapped[str] = mapped_column(String(2), primary_key=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
