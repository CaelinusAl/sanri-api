from fastapi import APIRouter, HTTPException, Header
from app.services.memberships import resolve_token

router = APIRouter(prefix="/auth", tags=["auth"])

@router.get("/verify")
def verify_token(x_sanri_token: str | None = Header(default=None)):
    if not x_sanri_token:
        return {"plan": "GUEST", "label": "Guest", "v2_max_gate": 0}

    info = resolve_token(x_sanri_token)
    if not info or not info.get("active"):
        raise HTTPException(status_code=401, detail="Geçersiz token")

    return {
        "plan": info["plan"],
        "label": info["label"],
        "v2_max_gate": info["v2_max_gate"]
    }