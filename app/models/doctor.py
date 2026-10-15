from app.models.base import Base
from sqlalchemy import String, Boolean, Integer, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column


class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Фамилия, имя и отчество врача",
    )
    specialty: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Специальность врача",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Признак активности. false — деактивирован администратором",
    )

    __table_args__ = (
        CheckConstraint("id >= 1", name="ck_doctors_id_positive"),
    )

    def __repr__(self) -> str:
        return f"<Doctor(id={self.id}, full_name={self.full_name!r})>"