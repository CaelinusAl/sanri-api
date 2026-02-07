# app/routes/auth.py
from fastapi import APIRouter

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.get("/me")
def me():
    # Frontend checkAuth bunu çağırıyor.
    # Şimdilik "logged out" dönelim, UI çökmeyecek.
    return {"user_id": None, "has_profile": False}

@router.post("/logout")
def logout():
    return {"success": True}

@router.post("/email/login")
def email_login():
    # Şimdilik stub
    return {"success": False, "detail": "Email login not enabled yet."}

@router.post("/email/register")
def email_register():
    return {"success": False, "detail": "Email register not enabled yet."}

@router.post("/google/session")
def google_session():
    return {"success": False, "detail": "Google session not enabled yet."}

@router.post("/onboarding")
def onboarding():
    return {"success": False, "detail": "Onboarding not enabled yet."}