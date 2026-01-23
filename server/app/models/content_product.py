from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from typing import Dict, Any, Optional
from app.db.base_class import Base

# TODO this file will be removed as this is getting picked up from the content designer application
class ContentProduct(Base):
    __tablename__ = "content_product"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False)
    workflow_id = Column(Integer, nullable=False, index=True)
    created_ts = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_ts = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    async def get_workflow_json(self, db: AsyncSession) -> Optional[Dict[str, Any]]:
        """
        Get the workflow JSON for this content product.
        
        Args:
            db: Database session
            
        Returns:
            Dict containing the workflow JSON or None if not found
        """
        from app.services.workflow_service import WorkflowService
        return await WorkflowService.get_workflow_json_from_workflow(db, self.workflow_id)
    
    def __repr__(self):
        return f"<ContentProduct(id={self.id}, name={self.name}, workflow_id={self.workflow_id})>"