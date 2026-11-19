"""Conversion history model."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ConversionHistory(Base):
    """Log of currency conversions performed by users or sessions."""

    __tablename__ = "conversion_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    from_currency: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code", ondelete="CASCADE"), nullable=False
    )
    to_currency: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=4), nullable=False)
    converted_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=4), nullable=False
    )
    rate: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    __table_args__ = (Index("ix_session_created", "session_id", "created_at"),)

    def __repr__(self) -> str:
        return (
            f"<ConversionHistory({self.amount} {self.from_currency} -> "
            f"{self.converted_amount} {self.to_currency})>"
        )
