from sqlalchemy import Column, DateTime, Integer, JSON, text
from sqlalchemy.sql import func

from app.db.database import Base


RUNTIME_CONFIG_ROW_ID = 1


class ApplicationRuntimeConfig(Base):
    """Singleton table: exactly one row (id=1) with JSON map of runtime key-value pairs."""

    __tablename__ = "application_runtime_config"

    id = Column(Integer, primary_key=True, nullable=False)
    data = Column(JSON, nullable=False, server_default=text("'{}'"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<ApplicationRuntimeConfig(id={self.id})>"
