from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db import get_db
from sqlalchemy import text

router = APIRouter(prefix="/content", tags=["content"])

@router.get("/system-feed")
def get_system_feed(lang: str = Query("tr"), db: Session = Depends(get_db)):

    row = db.execute(text("""
        SELECT title, subtitle, body_tr, body_en
        FROM system_feed_items
        ORDER BY created_at DESC
        LIMIT 1
    """)).fetchone()

    if not row:
        return {
            "signal": "Sistem sessiz.",
            "symbol": "Henüz veri yok.",
            "message": "Yeni bir akış oluşturulacak.",
            "action": "Bekle",
            "share": ""
        }

    return {
        "signal": row.title,
        "symbol": row.subtitle,
        "message": row.body_tr if lang == "tr" else row.body_en,
        "action": "Observe",
        "share": ""
    }


@router.get("/system-feed/generate")
def generate_system_feed(lang: str = Query("tr"), db: Session = Depends(get_db)):

    db.execute(text("""
        INSERT INTO system_feed_items
        (kind,title,subtitle,body_tr,body_en,tags)
        VALUES
        ('system',
        'Yeni bilinç akışı başladı',
        'Sistem',
        'Bugün sistem yeni bir bilinç katmanı açtı.',
        'A new consciousness layer opened today.',
        'system')
    """))

    db.commit()

    return {"status": "generated"}