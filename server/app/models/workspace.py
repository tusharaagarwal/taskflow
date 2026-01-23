from sqlalchemy import (
    Column, Integer, String, Boolean, TIMESTAMP, Date, Enum, ForeignKey
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from enum import Enum as PyEnum
from db.database import Base

class ReportStatusEnum(PyEnum):
    IN_PROGRESS = "IN-PROGRESS"
    PUBLISHED = "PUBLISHED"


class SystemMetadata(Base):
    __tablename__ = "system_metadata"
    __table_args__ = {"schema": "workspace"}

    metadata_id = Column(Integer, primary_key=True, index=True)
    entity_name = Column(String, nullable=False)
    category_type = Column(String, nullable=False)
    parent_id = Column(Integer, ForeignKey("workspace.system_metadata.metadata_id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    parent = relationship("SystemMetadata", remote_side=[metadata_id], backref="children")


class Language(Base):
    __tablename__ = "language"
    __table_args__ = {"schema": "workspace"}

    language_id = Column(Integer, primary_key=True, index=True)
    language_name = Column(String)
    is_active = Column(Boolean)


class Report(Base):
    __tablename__ = "report"
    __table_args__ = {"schema": "workspace"}

    report_id = Column(Integer, primary_key=True, index=True)
    external_report_id = Column(String)
    report_name = Column(String)
    report_type = Column(String)
    language_id = Column(Integer, ForeignKey("workspace.language.language_id"))
    is_translated = Column(Boolean)
    translated_from = Column(Integer)
    cpt_id = Column(Integer)
    layout = Column(Integer)
    est_publication_date = Column(Date)
    pr_publication_date = Column(Date)
    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)
    created_by = Column(Integer)
    updated_by = Column(Integer)

    language = relationship("Language")
    report_statuses = relationship("ReportStatus", back_populates="report")

class ReportStatus(Base):
    __tablename__ = "report_status"
    __table_args__ = {"schema": "workspace"}

    report_id = Column(Integer, ForeignKey("workspace.report.report_id"), primary_key=True)
    workflow_id = Column(Integer)
    workflow_step_id = Column(Integer)
    report_status = Column(Enum(ReportStatusEnum, name="report_status_enum", create_type=True, schema="workspace"), nullable=False)

    report = relationship("Report", back_populates="report_statuses")


class PersonaPermission(Base):
    __tablename__ = "persona_permission"
    __table_args__ = {"schema": "workspace"}

    persona_id = Column(Integer, ForeignKey("workspace.system_metadata.metadata_id"), primary_key=True)
    permission_id = Column(Integer, ForeignKey("workspace.system_metadata.metadata_id"), primary_key=True)

    persona = relationship("SystemMetadata", foreign_keys=[persona_id])
    permission = relationship("SystemMetadata", foreign_keys=[permission_id])


class ReportUserPersona(Base):
    __tablename__ = "report_user_persona"
    __table_args__ = {"schema": "workspace"}

    mapping_key = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("workspace.report.report_id"))
    user_id = Column(String)  # Changed from ForeignKey to String to support alphanumeric IDs
    persona_id = Column(Integer, ForeignKey("workspace.system_metadata.metadata_id"))

    report = relationship("Report")
    persona = relationship("SystemMetadata")

