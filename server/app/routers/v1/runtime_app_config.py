from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas.runtime_app_config import (
    RuntimeAppConfigPatchBody,
    RuntimeAppConfigResponse,
)
from app.services.runtime_app_config_service import RuntimeAppConfigService

router = APIRouter(prefix="/runtime-app-config", tags=["Runtime app config"])


@router.get("/", response_model=RuntimeAppConfigResponse)
async def get_runtime_app_config(
    db: AsyncSession = Depends(get_db),
):
    row = await RuntimeAppConfigService.get_record(db)
    return RuntimeAppConfigResponse.model_validate(row)


@router.patch("/", response_model=RuntimeAppConfigResponse)
async def patch_runtime_app_config(
    body: RuntimeAppConfigPatchBody,
    db: AsyncSession = Depends(get_db),
):
    row = await RuntimeAppConfigService.patch_merge_data(db, body.data)
    return RuntimeAppConfigResponse.model_validate(row)
