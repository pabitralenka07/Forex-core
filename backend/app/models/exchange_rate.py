"""Exchange rate database model."""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.currency import Currency


class ExchangeRate(Base):
    """Historical and daily exchange rates with explicit Decimal precision."""

    __tablename__ = "exchange_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    base_currency: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code", ondelete="CASCADE"), nullable=False, index=True
    )
    target_currency: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code", ondelete="CASCADE"), nullable=False, index=True
    )
    rate: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=10), nullable=False)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    base_curr: Mapped[Currency] = relationship("Currency", foreign_keys=[base_currency])
    target_curr: Mapped[Currency] = relationship("Currency", foreign_keys=[target_currency])

    __table_args__ = (
        UniqueConstraint(
            "base_currency",
            "target_currency",
            "rate_date",
            "provider",
            name="uq_pair_date_provider",
        ),
        Index("ix_pair_date", "base_currency", "target_currency", "rate_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<ExchangeRate({self.base_currency}/{self.target_currency}="
            f"{self.rate} on {self.rate_date} via {self.provider})>"
        )
