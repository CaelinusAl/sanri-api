from fastapi import APIRouter, Depends

from app.core.security import get_current_user_claims
from app.schemas.v1 import MeResponse


router = APIRouter(prefix="/v1", tags=["v1-auth"])


@router.get("/me", response_model=MeResponse)
def me(claims: dict = Depends(get_current_user_claims)):
    return {"id": claims["sub"], "email": claims.get("email")}
