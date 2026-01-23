from pydantic import BaseModel, EmailStr
from datetime import datetime, date
from typing import Optional, List
from enum import Enum


class ReportStatusEnum(str, Enum):
    IN_PROGRESS = "IN-PROGRESS"
    PUBLISHED = "PUBLISHED"


class SystemMetadataBase(BaseModel):
    entity_name: str
    category_type: str
    parent_id: Optional[int] = None
    is_active: Optional[bool] = True



class SystemMetadataOut(SystemMetadataBase):
    metadata_id: int
    entity_name: str
    category_type: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True



class LanguageBase(BaseModel):
    language_name: Optional[str]
    is_active: Optional[bool] = True


class LanguageOut(LanguageBase):
    language_id: int

    class Config:
        from_attributes = True


class ReportBase(BaseModel):
    report_name: Optional[str]
    report_type: Optional[str]
    language_id: Optional[int]
    is_translated: Optional[bool]
    translated_from: Optional[int]
    cpt_id: Optional[int]
    layout: Optional[int]
    est_publication_date: Optional[date]
    pr_publication_date: Optional[date]


class ReportCreate(ReportBase):
    pass


class ReportOut(ReportBase):
    report_id: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True



class ReportStatusBase(BaseModel):
    report_id: int
    workflow_id: int
    workflow_step_id: int
    report_status: ReportStatusEnum


class ReportStatusOut(ReportStatusBase):
    class Config:
        from_attributes = True


class PersonaPermissionBase(BaseModel):
    persona_id: int
    permission_id: int


class PersonaPermissionOut(PersonaPermissionBase):
    class Config:
        from_attributes = True


class ReportUserPersonaBase(BaseModel):
    report_id: int
    user_id: int
    persona_id: int


class ReportUserPersonaOut(ReportUserPersonaBase):
    mapping_key: int

    class Config:
        from_attributes = True
