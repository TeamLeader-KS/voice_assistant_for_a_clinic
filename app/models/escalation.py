from datetime import datetime

from sqlalchemy import (
    Integer, Text, DateTime, ForeignKey, CheckConstraint, Index,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.client import Client


class Escalation(Base):
    __tablename__ = "escalations"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Идентификатор заявки",
    )
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="FK на карточку клиента",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Описание проблемы; может быть многострочным",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Момент создания заявки (UTC в БД)",
    )

    client: Mapped["Client"] = relationship(
        "Client",
        lazy="joined",              # всегда тянем клиента одним JOIN
        backref="escalations",
    )

    __table_args__ = (
        CheckConstraint("id >= 1", name="ck_escalations_id_positive"),
        # защита от пустого описания
        CheckConstraint(
            "length(btrim(description)) > 0",
            name="ck_escalations_description_not_blank",
        ),
        Index("ix_escalations_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Escalation(id={self.id}, client_id={self.client_id}, "
            f"dt={self.created_at:%Y-%m-%d %H:%M:%S})>"
        )