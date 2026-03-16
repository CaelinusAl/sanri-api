from datetime import datetime
from fastapi import APIRouter, Request, Header, HTTPException
from fastapi.responses import JSONResponse

from app.routes.auth import _conn, _get_token_from_header_or_cookie, parse_token

router = APIRouter(prefix="/auth", tags=["account"])


@router.delete("/account")
def delete_account(request: Request, authorization: str | None = Header(default=None)):
    token = _get_token_from_header_or_cookie(request, authorization)
    user_id = parse_token(token) if token else None

    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    conn = _conn()
    cur = conn.cursor()

    try:
        # soft delete
        cur.execute(
            """
            UPDATE users
            SET
                account_deleted_at = NOW(),
                deletion_requested_at = NOW(),
                is_active = FALSE,
                email = NULL
            WHERE id = %s
            """,
            (user_id,),
        )
        conn.commit()

        resp = JSONResponse({"success": True, "message": "Account deleted"})
        resp.delete_cookie("sanri_token", path="/")
        return resp

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"delete failed: {type(e).__name__}: {str(e)}")
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()