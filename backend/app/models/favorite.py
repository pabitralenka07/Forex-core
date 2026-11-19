"""Favorite currencies model."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class FavoriteCurrency(Base):
    """User/Session favorite currency pairing or watch item."""

    __tablename__ = "favorite_currencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    currency_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (UniqueConstraint("session_id", "currency_code", name="uq_session_currency"),)

    def __repr__(self) -> str:
        return f"<FavoriteCurrency({self.session_id}: {self.currency_code})>"
