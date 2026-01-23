
from fastapi import APIRouter, status

router = APIRouter()

@router.get("/")
async def ping():
    return "Pong"