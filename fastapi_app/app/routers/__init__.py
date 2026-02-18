from fastapi import APIRouter, Depends
from app.core.security import verify_internal_key

router = APIRouter(
    prefix="/internal",
    tags=["internal"],
    dependencies=[Depends(verify_internal_key)],
)