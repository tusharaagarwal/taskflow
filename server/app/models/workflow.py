from sqlalchemy import Column, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.db.database import Base

# TODO this file will be changed or removed whrn the workflow related code will be migrated
# from the workspace application to workflow orchestrator
class Workflow(Base):
    __tablename__ = "workflow"
    __table_args__ = {"schema": "public"}

    workflow_id = Column(Integer, primary_key=True, index=True)
    workflow_json = Column(Text, nullable=False)
