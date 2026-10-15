from app.models.base import Base
from datetime import date, datetime
from sqlalchemy import String, Date, DateTime, Integer, CheckConstraint, func
from sqlalchemy.orm import Mapped, mapped_column


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Идентификатор клиента",
    )
    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Фамилия клиента",
    )
    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Имя клиента",
    )
    middle_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Отчество клиента; null, если не задано",
    )
    birth_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="Дата рождения (без времени и часового пояса)",
    )
    comment: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="Комментарий команды; может быть многострочным",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Момент создания карточки (UTC в БД)",
    )

    __table_args__ = (
        CheckConstraint("id >= 1", name="ck_clients_id_positive"),
    )

    def __repr__(self) -> str:
        return f"<Client(id={self.id}, {self.last_name} {self.first_name})>"