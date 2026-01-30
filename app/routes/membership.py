import json
import os
import secrets
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(prefix="/auth", tags=["auth"])


DATA_FILE = Path("data/memberships.json")


def _load_db() -> Dict[str, Any]:
    if not DATA_FILE.exists():
        raise HTTPException(status_code=500, detail="memberships.json not found")
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def _save_db(db: Dict[str, Any]) -> None:
    DATA_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


def _require_admin(admin_key: Optional[str]) -> None:
    expected = (os.getenv("ADMIN_KEY") or "").strip()
    if not expected:
        raise HTTPException(status_code=500, detail="ADMIN_KEY is not set on server")
    if not admin_key or admin_key.strip() != expected:
        raise HTTPException(status_code=401, detail="Invalid admin key")


def _resolve_token(db: Dict[str, Any], token: str) -> Dict[str, Any]:
    tokens = db.get("tokens", {})
    entry = tokens.get(token)
    if not entry:
        raise HTTPException(status_code=401, detail="Invalid token")
    if not entry.get("active", False):
        raise HTTPException(status_code=403, detail="Token is inactive")
    plan_name = entry.get("plan")
    plans = db.get("plans", {})
    plan = plans.get(plan_name)
    if not plan:
        raise HTTPException(status_code=500, detail="Token plan not found")
    return {
        "token": token,
        "plan": plan_name,
        "label": plan.get("label"),
        "level": plan.get("level"),
        "v1_max_gate": plan.get("v1_max_gate"),
        "v2_max_gate": plan.get("v2_max_gate"),
        "features": plan.get("features", []),
    }


class VerifyRequest(BaseModel):
    token: str = Field(min_length=3, max_length=128)


class VerifyResponse(BaseModel):
    token: str
    plan: str
    label: str
    level: int
    v1_max_gate: int
    v2_max_gate: int
    features: list[str]


@router.post("/verify", response_model=VerifyResponse)
def verify(req: VerifyRequest) -> VerifyResponse:
    db = _load_db()
    info = _resolve_token(db, req.token.strip())
    return VerifyResponse(**info)


@router.get("/me", response_model=VerifyResponse)
def me(x_sanri_token: Optional[str] = Header(default=None)) -> VerifyResponse:
    if not x_sanri_token:
        raise HTTPException(status_code=401, detail="Missing X-Sanri-Token header")
    db = _load_db()
    info = _resolve_token(db, x_sanri_token.strip())
    return VerifyResponse(**info)


class IssueRequest(BaseModel):
    plan: str = Field(min_length=2, max_length=16)
    note: Optional[str] = Field(default=None, max_length=200)


class IssueResponse(BaseModel):
    token: str
    plan: str
    active: bool
    note: Optional[str]


@router.post("/issue", response_model=IssueResponse)
def issue(
    req: IssueRequest,
    x_admin_key: Optional[str] = Header(default=None),
) -> IssueResponse:
    _require_admin(x_admin_key)
    db = _load_db()

    plan_name = req.plan.strip().upper()
    plans = db.get("plans", {})
    if plan_name not in plans:
        raise HTTPException(status_code=400, detail="Unknown plan")

    # Token format: SANRI-<32hex>
    token = "SANRI-" + secrets.token_hex(16).upper()

    db.setdefault("tokens", {})
    db["tokens"][token] = {
        "plan": plan_name,
        "active": True,
        "note": req.note or "",
    }
    _save_db(db)

    return IssueResponse(token=token, plan=plan_name, active=True, note=req.note or "")


class RevokeRequest(BaseModel):
    token: str = Field(min_length=3, max_length=128)


@router.post("/revoke")
def revoke(req: RevokeRequest, x_admin_key: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    _require_admin(x_admin_key)
    db = _load_db()

    tokens = db.get("tokens", {})
    entry = tokens.get(req.token)
    if not entry:
        raise HTTPException(status_code=404, detail="Token not found")

    entry["active"] = False
    _save_db(db)

    return {"ok": True, "token": req.token, "active": False}