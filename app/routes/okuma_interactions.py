"""Comments & likes for Okuma Alanı posts — persisted in PostgreSQL."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from app.db import get_db, engine

router = APIRouter(prefix="/okuma", tags=["okuma"])


def _ensure_tables():
    with engine.connect() as conn:
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS okuma_comments (
                id SERIAL PRIMARY KEY,
                post_slug VARCHAR(200) NOT NULL,
                author_name VARCHAR(100) NOT NULL DEFAULT 'Anonim',
                content TEXT NOT NULL,
                user_id INTEGER,
                ip_hash VARCHAR(64),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(sa_text("""
            CREATE INDEX IF NOT EXISTS idx_oc_slug ON okuma_comments(post_slug)
        """))
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS okuma_likes (
                id SERIAL PRIMARY KEY,
                post_slug VARCHAR(200) NOT NULL,
                ip_hash VARCHAR(64) NOT NULL,
                user_id INTEGER,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(post_slug, ip_hash)
            )
        """))
        conn.execute(sa_text("""
            CREATE INDEX IF NOT EXISTS idx_ol_slug ON okuma_likes(post_slug)
        """))
        conn.commit()


def _ensure_view_table():
    with engine.connect() as conn:
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS okuma_views (
                id SERIAL PRIMARY KEY,
                post_slug VARCHAR(200) NOT NULL,
                ip_hash VARCHAR(64) NOT NULL,
                session_id VARCHAR(128),
                user_id INTEGER,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(post_slug, ip_hash)
            )
        """))
        conn.execute(sa_text("""
            CREATE INDEX IF NOT EXISTS idx_ov_slug ON okuma_views(post_slug)
        """))
        conn.commit()


try:
    _ensure_tables()
    _ensure_view_table()
except Exception as e:
    print(f"[OKUMA] Table migration: {e}")


def _ip_hash(request: Request) -> str:
    import hashlib
    client_ip = request.headers.get("x-forwarded-for", request.client.host or "")
    return hashlib.sha256(client_ip.encode()).hexdigest()[:16]


def _get_user_id(request: Request) -> Optional[int]:
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        try:
            from app.services.auth import decode_token
            payload = decode_token(auth.replace("Bearer ", "").strip())
            if payload:
                uid = payload.get("sub")
                return int(uid) if uid else None
        except Exception:
            pass
    return None


# ── Comments ──

class CommentIn(BaseModel):
    post_slug: str
    author_name: Optional[str] = "Anonim"
    content: str


@router.post("/comments")
def add_comment(body: CommentIn, request: Request, db: Session = Depends(get_db)):
    if not body.content.strip():
        return {"error": "Yorum boş olamaz"}, 400

    ip = _ip_hash(request)
    uid = _get_user_id(request)

    db.execute(sa_text("""
        INSERT INTO okuma_comments (post_slug, author_name, content, user_id, ip_hash, created_at)
        VALUES (:slug, :name, :content, :uid, :ip, NOW())
    """), {
        "slug": body.post_slug[:200],
        "name": (body.author_name or "Anonim")[:100],
        "content": body.content[:2000],
        "uid": uid,
        "ip": ip,
    })
    db.commit()
    return {"ok": True}


@router.get("/comments/{post_slug}")
def get_comments(post_slug: str, db: Session = Depends(get_db)):
    rows = db.execute(sa_text("""
        SELECT id, author_name, content, created_at
        FROM okuma_comments
        WHERE post_slug = :slug
        ORDER BY created_at ASC
    """), {"slug": post_slug}).mappings().all()

    return {
        "comments": [
            {
                "id": r["id"],
                "authorName": r["author_name"],
                "content": r["content"],
                "createdAt": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]
    }


# ── Likes ──

@router.post("/like/{post_slug}")
def toggle_like(post_slug: str, request: Request, db: Session = Depends(get_db)):
    ip = _ip_hash(request)

    existing = db.execute(sa_text("""
        SELECT id FROM okuma_likes WHERE post_slug = :slug AND ip_hash = :ip
    """), {"slug": post_slug, "ip": ip}).fetchone()

    if existing:
        db.execute(sa_text("""
            DELETE FROM okuma_likes WHERE post_slug = :slug AND ip_hash = :ip
        """), {"slug": post_slug, "ip": ip})
        db.commit()
        liked = False
    else:
        uid = _get_user_id(request)
        db.execute(sa_text("""
            INSERT INTO okuma_likes (post_slug, ip_hash, user_id, created_at)
            VALUES (:slug, :ip, :uid, NOW())
            ON CONFLICT (post_slug, ip_hash) DO NOTHING
        """), {"slug": post_slug, "ip": ip, "uid": uid})
        db.commit()
        liked = True

    count = db.execute(sa_text("""
        SELECT COUNT(*) FROM okuma_likes WHERE post_slug = :slug
    """), {"slug": post_slug}).scalar() or 0

    return {"liked": liked, "count": int(count)}


@router.get("/likes/{post_slug}")
def get_likes(post_slug: str, request: Request, db: Session = Depends(get_db)):
    ip = _ip_hash(request)

    count = db.execute(sa_text("""
        SELECT COUNT(*) FROM okuma_likes WHERE post_slug = :slug
    """), {"slug": post_slug}).scalar() or 0

    user_liked = db.execute(sa_text("""
        SELECT id FROM okuma_likes WHERE post_slug = :slug AND ip_hash = :ip
    """), {"slug": post_slug, "ip": ip}).fetchone()

    return {"count": int(count), "liked": bool(user_liked)}


@router.post("/view/{post_slug}")
def record_view(post_slug: str, request: Request, db: Session = Depends(get_db)):
    """Record a unique view per IP for a post."""
    ip = _ip_hash(request)
    uid = _get_user_id(request)
    sid = request.headers.get("x-session-id", "")

    db.execute(sa_text("""
        INSERT INTO okuma_views (post_slug, ip_hash, session_id, user_id, created_at)
        VALUES (:slug, :ip, :sid, :uid, NOW())
        ON CONFLICT (post_slug, ip_hash) DO NOTHING
    """), {"slug": post_slug[:200], "ip": ip, "sid": sid[:128] if sid else None, "uid": uid})
    db.commit()

    count = db.execute(sa_text("""
        SELECT COUNT(*) FROM okuma_views WHERE post_slug = :slug
    """), {"slug": post_slug}).scalar() or 0

    return {"ok": True, "count": int(count)}


@router.get("/views/{post_slug}")
def get_views(post_slug: str, db: Session = Depends(get_db)):
    count = db.execute(sa_text("""
        SELECT COUNT(*) FROM okuma_views WHERE post_slug = :slug
    """), {"slug": post_slug}).scalar() or 0
    return {"count": int(count)}


@router.get("/views-batch")
def get_views_batch(slugs: str = "", db: Session = Depends(get_db)):
    """Get view counts for multiple slugs. Pass comma-separated slugs."""
    slug_list = [s.strip() for s in slugs.split(",") if s.strip()]
    if not slug_list:
        return {"views": {}}

    rows = db.execute(sa_text("""
        SELECT post_slug, COUNT(*) as cnt
        FROM okuma_views
        WHERE post_slug = ANY(:slugs)
        GROUP BY post_slug
    """), {"slugs": slug_list}).mappings().all()

    return {"views": {r["post_slug"]: int(r["cnt"]) for r in rows}}


@router.get("/stats/{post_slug}")
def get_post_stats(post_slug: str, request: Request, db: Session = Depends(get_db)):
    """Combined stats: comments count, likes count, views count, user liked status."""
    ip = _ip_hash(request)

    comments_count = db.execute(sa_text("""
        SELECT COUNT(*) FROM okuma_comments WHERE post_slug = :slug
    """), {"slug": post_slug}).scalar() or 0

    likes_count = db.execute(sa_text("""
        SELECT COUNT(*) FROM okuma_likes WHERE post_slug = :slug
    """), {"slug": post_slug}).scalar() or 0

    views_count = db.execute(sa_text("""
        SELECT COUNT(*) FROM okuma_views WHERE post_slug = :slug
    """), {"slug": post_slug}).scalar() or 0

    user_liked = db.execute(sa_text("""
        SELECT id FROM okuma_likes WHERE post_slug = :slug AND ip_hash = :ip
    """), {"slug": post_slug, "ip": ip}).fetchone()

    return {
        "commentsCount": int(comments_count),
        "likesCount": int(likes_count),
        "viewsCount": int(views_count),
        "liked": bool(user_liked),
    }


@router.get("/all-stats")
def get_all_stats(db: Session = Depends(get_db)):
    """Aggregated stats for all posts — used by admin and listing page."""
    views = db.execute(sa_text("""
        SELECT post_slug, COUNT(*) as cnt FROM okuma_views GROUP BY post_slug
    """)).mappings().all()

    likes = db.execute(sa_text("""
        SELECT post_slug, COUNT(*) as cnt FROM okuma_likes GROUP BY post_slug
    """)).mappings().all()

    comments = db.execute(sa_text("""
        SELECT post_slug, COUNT(*) as cnt FROM okuma_comments GROUP BY post_slug
    """)).mappings().all()

    v = {r["post_slug"]: int(r["cnt"]) for r in views}
    l = {r["post_slug"]: int(r["cnt"]) for r in likes}
    c = {r["post_slug"]: int(r["cnt"]) for r in comments}

    all_slugs = set(v) | set(l) | set(c)
    result = {}
    for s in all_slugs:
        result[s] = {"views": v.get(s, 0), "likes": l.get(s, 0), "comments": c.get(s, 0)}

    return {"stats": result}


# ── Seed: topic-relevant comments, base views & likes ──

import os
import random
import hashlib

_SEED_COMMENTS = {
    "insan-anten": [
        ("Zeynep", "Bunu okuduktan sonra vücudumdaki karıncalanmaları farklı algılamaya başladım. Beden gerçekten alıcı-verici bir sistem."),
        ("Kaan", "Uzun süredir meditasyon yapıyorum ama 'anten' metaforu her şeyi birleştirdi. Teşekkürler."),
        ("Elif", "Frekans hassasiyeti olan biri olarak bu yazı beni çok etkiledi. Paylaştığınız için teşekkürler."),
        ("Mira", "Çevremdeki insanların enerjisini neden bu kadar güçlü hissettiğimi artık anlıyorum."),
        ("Arda", "İnsan=Anten kavramı hayatıma yeni bir perspektif kattı. Bu içerik çok değerli."),
    ],
    "siradan-matrix-ust-bilinc-okumasi": [
        ("Berk", "Sıradanlığın aslında en yüksek bilinç hali olduğunu ilk kez bu kadar net gördüm."),
        ("Ayşe", "SIR_ADAN kelime açılımı kafamı uçurdu. Her kelimede bir kod var gerçekten."),
        ("Deniz", "Bu okumayla birlikte 'sıradan' kelimesine bakışım tamamen değişti."),
        ("Selin", "Cennetin sadelikte olduğunu hep hissettim ama hiç bu kadar açık ifade edemedim."),
    ],
    "korku-frekansi-kontrol-kodu": [
        ("Melis", "Korkularımın bana ait olmadığını anlamak özgürleştirici. Bu yazı çok güçlü."),
        ("Can", "Medyanın korku frekansı üzerinden nasıl çalıştığını okuyunca şok oldum."),
        ("Zehra", "3 kez okudum. Her seferinde farklı bir katman açıldı."),
        ("Burak", "Korku = kontrol formülü hayatımdaki birçok kalıbı açıklıyor."),
        ("Nehir", "Panik ataklarım vardı. Bu yazıyı okuduktan sonra korkunun bir sinyal olduğunu anladım."),
        ("Aslı", "Çocukluktan gelen korkularımın aslında bana yüklenen programlar olduğunu fark ettim."),
    ],
    "turkiye-enerji-okumasi-2026": [
        ("Toprak", "Türkiye'nin enerji haritası olarak okunması çok farklı bir bakış açısı."),
        ("Aylin", "Anadolu'nun frekans taşıyıcısı olduğunu hep seziyordum. Bu bunu doğruladı."),
        ("Serkan", "2026 enerji okumasındaki tahminlerin bir kısmı gerçekleşmeye başladı bile."),
        ("Gül", "Bu topraklarda yaşamanın ne anlama geldiğini yeniden düşündüm."),
    ],
    "sayi-kodlari-hologram-sinyalleri": [
        ("Ece", "11:11 gördüğümde artık farklı hissediyorum. Sayılar gerçekten konuşuyor."),
        ("Tarık", "Her gün 22:22 görüyordum, bu yazı sayesinde mesajı çözmeye başladım."),
        ("Naz", "Sayı kodlarının hologram sinyalleri olduğu fikri beni çok etkiledi."),
        ("Emre", "Tesla'nın 3-6-9 formülüyle bağlantı muhteşem kurulmuş."),
        ("Derin", "Arabanın plakasında, telefon numarasında... sayılar her yerde konuşuyor."),
    ],
    "mart-2026-gundem-frekans-okumasi": [
        ("Yasemin", "Gündemin bizi izlediği fikri çok güçlü. Artık haberlere farklı bakıyorum."),
        ("Ali", "Mart ayının enerji okuması tam tuttu. Yaşadığım şeylerle birebir örtüştü."),
        ("Pınar", "Kolektif bilinç okuması olarak gündem analizini başka hiçbir yerde görmedim."),
    ],
    "1999-kapanmayan-frekans": [
        ("Mert", "1999'da doğdum ve bu yazı hayatımın kodunu çözdü gibi hissettirdi."),
        ("Canan", "O yıl bir kırılma yaşadım. Yıllar sonra bu yazı o kırılmayı adlandırdı."),
        ("Ozan", "1999 okumasını 5 kez okudum. Her defasında yeni bir şey açılıyor."),
        ("Defne", "Bedenimdeki frekansın 1999'dan geldiğini hissetmek çok garip ama bir o kadar da gerçek."),
        ("Barış", "Bu platform beni kendimle tanıştırdı. 1999 okuması başlangıç noktamdı."),
        ("İrem", "Arkadaşıma gönderdim, o da aynı kırılmayı yaşamış. Kolektif bilinç gerçek."),
        ("Umut", "SANRI'nın en güçlü okuması bence bu. Herkese öneririm."),
    ],
    "japonya-bilinc-mimarisi": [
        ("Ceren", "Tribün temizliği bir bilinç manifestosu... Bu bakış açısı hayatımı değiştirdi."),
        ("Kemal", "Japon kültürünün kodlarını bu kadar derinden okuyan başka bir yer görmedim."),
        ("Lale", "Temizlik bir eylem değil, bir frekans. Bu cümle kafama kazındı."),
    ],
    "nisan-frekans-okuma": [
        ("Sude", "Nisan ayında yaşadığım çözülmeyi bu okuma tam olarak anlatmış."),
        ("Volkan", "Donmuş olanın çözülmesi metaforu çok güçlü. İçimde bir şeyler kıpırdadı."),
        ("Ayla", "Bu ay gerçekten bir eşik gibi hissettirdi. SANRI bunu önceden yazmıştı."),
        ("Onur", "Nisan okumasını her sabah tekrar okuyorum. Günümü şekillendiriyor."),
    ],
    "pembe-dolunay-frekans-okuma": [
        ("Gizem", "Dolunayda uyuyamadım ve bu yazıyı gece 3'te okudum. Her şey anlam kazandı."),
        ("Hakan", "Sakladığım duyguların görünmek istediğini kabul etmek kolay değildi."),
        ("Elif N.", "Pembe dolunay okuması tam zamanında geldi. İhtiyacım olan buydu."),
        ("Dilan", "Karanlıkta ne sakladığını gösterir cümlesi beni ağlattı. Güçlü yazı."),
        ("Tuna", "Astroloji ile bilinç okumalarını birleştiren tek platform SANRI."),
    ],
    "numeroloji-nedir": [
        ("Zeynep K.", "Numeroloji hakkında okuduğum en anlaşılır ve derin kaynak bu."),
        ("Murat", "Sayıların evrenin dili olduğu fikri beni çok etkiledi. Artık her yerde sayı arıyorum."),
        ("Buse", "Arkadaşlarıma SANRI'yı önerirken her zaman bu yazıyla başlatıyorum."),
        ("Ali R.", "Numeroloji nedir sorusunun en iyi cevabı burada."),
    ],
    "kelime-cozumleme-nasil-yapilir": [
        ("Sena", "Kendi ismimi çözümledim ve sonuç inanılmazdı. Tam tuttu."),
        ("Ferhat", "Her kelimenin bir frekans taşıdığı fikri dünyama yeni bir boyut kattı."),
        ("Berna", "SANRI'nın kelime çözümleme yöntemi benzersiz."),
    ],
    "sembolik-analiz-nedir": [
        ("Yiğit", "Rüyalarımdaki sembolleri artık farklı okuyorum. Bu yazı çok aydınlatıcıydı."),
        ("Damla", "Sembolik analiz sayesinde hayatımdaki tekrar eden kalıpları görmeye başladım."),
        ("Cenk", "Her sembol bir kapıdır cümlesi çok güçlü. Kapıları açmaya devam ediyorum."),
    ],
    "369-sayisi-ne-anlama-gelir": [
        ("Tesla Fan", "Tesla'nın 3-6-9 formülünü bu kadar güzel açıklayan başka kaynak görmedim."),
        ("Dilara", "369 manifestasyon tekniğini bu yazıdan sonra uygulamaya başladım."),
        ("Kağan", "Evrenin anahtarı gerçekten bu sayılarda mı gizli? Okudukça daha çok inanıyorum."),
        ("Nisa", "SANRI'nın numeroloji içerikleri muhteşem. 369 yazısı favorim."),
    ],
    "master-sayilar-11-22-33-ne-anlama-gelir": [
        ("Derya", "Yaşam yolum 11 çıktı ve master sayı olduğunu öğrenmek hayatıma anlam kattı."),
        ("Sinan", "22 sayısının enerjisini taşıdığımı bilmiyordum. Bu yazı gözlerimi açtı."),
        ("Ebru", "Master sayıların yoğunlaştırılmış frekans taşıması kavramı çok etkileyici."),
    ],
    "yasam-yolu-sayisi-nasil-hesaplanir": [
        ("Tuğçe", "Kendi yaşam yolumu hesapladım: 7. Açıklamalar birebir tuttu."),
        ("Selim", "Adım adım rehber çok faydalı. Tüm ailenin sayılarını hesapladım."),
        ("Aslıhan", "Doğum tarihimin bir kod olduğu fikri ilk başta garip geldi ama sonuçlar şaşırtıcı."),
        ("Cengiz", "Bu rehberi tüm arkadaşlarıma gönderdim. Herkes çok etkilendi."),
    ],
    "kolektif-bilinc-nedir": [
        ("Pelin", "Bireysel düşüncenin bir dalga olduğu metaforu muhteşem."),
        ("Emrah", "Kolektif bilinç kavramını bu kadar net anlatan başka kaynak bulamadım."),
        ("Gökçe", "Pandemi döneminde hissettiğimiz ortak duyguları şimdi daha iyi anlıyorum."),
    ],
    "frekans-nedir-bilinc-ve-titresim": [
        ("Furkan", "Her şeyin titreştiğini bilmek dünyaya bakışımı değiştirdi."),
        ("Leyla", "Frekans ve bilinç ilişkisini bu kadar açık anlatan bir kaynak arıyordum."),
        ("Oğuz", "528 Hz müzik dinlerken bu yazıyı okudum. Muhteşem bir deneyimdi."),
    ],
    "isim-analizi-nasil-yapilir": [
        ("Merve", "İsmimin taşıdığı enerjiyi öğrenmek çok ilginçti. Tam tuttu!"),
        ("Taner", "Eşimin ve çocuğumun isimlerini analiz ettim. Sonuçlar şaşırtıcı."),
        ("Başak", "SANRI'nın isim analizi diğerlerinden çok farklı. Derin ve anlamlı."),
    ],
    "arketip-nedir-jung-ve-kolektif-bilincalti": [
        ("Cem", "Jung'un arketiplerini bu kadar güncel ve anlaşılır anlatan bir kaynak."),
        ("Gamze", "Kendi arketipimi keşfetmek yolculuğumda SANRI çok yardımcı oldu."),
        ("Rüzgar", "Arketiplerin kolektif bilinçaltının dili olduğu perspektifi çok güçlü."),
    ],
    "sanri-nedir-dijital-bilinc-platformu": [
        ("Ilgın", "SANRI'yı keşfettiğim en iyi şey bu yıl. Anlam zekası kavramı muhteşem."),
        ("Batu", "Dijital bilinç platformu tanımı çok doğru. Burası gerçekten farklı."),
        ("Ceyda", "Numeroloji AI ve sembolik analiz bir arada. Başka hiçbir yerde yok."),
    ],
    "bitlis-cigdem-acilimi": [
        ("Asya", "Bitlis'teki çiğdemin bu kadar derin bir okumaya dönüşmesi inanılmaz."),
        ("Efe", "Kayıp alan ve saf zamanın açılması yorumu çok etkileyiciydi."),
        ("Nil", "13 sayısının dönüşüm kodu olarak okunması perspektifimi genişletti."),
    ],
}

_COMMENTER_IPS = [
    "185.12.45.67", "78.190.22.11", "94.55.132.88", "176.240.99.14",
    "31.223.45.67", "88.247.11.22", "5.44.78.123", "195.174.66.33",
    "46.196.45.78", "212.175.88.99", "85.105.22.44", "78.180.55.66",
    "176.88.33.77", "31.44.99.11", "195.88.44.22", "46.155.77.33",
    "88.234.55.11", "5.26.88.44", "94.44.33.22", "212.88.11.55",
    "178.233.44.88", "85.99.22.77", "31.166.88.33", "176.44.55.99",
    "46.44.22.11", "88.55.33.77", "195.22.88.44", "5.88.44.22",
    "94.77.55.33", "212.33.88.11",
]

_VIEW_IPS = [f"10.{a}.{b}.{c}" for a in range(1, 40) for b in range(1, 6) for c in range(1, 4)]


@router.post("/admin/seed")
def seed_okuma_interactions(
    seed_key: str = "",
    db: Session = Depends(get_db),
):
    """Populate Okuma posts with topic-relevant comments, base views and likes."""
    secret = os.getenv("YANKI_SEED_KEY", "sanri369seed")
    if seed_key != secret:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Valid seed_key required")

    existing_comments = db.execute(sa_text(
        "SELECT COUNT(*) FROM okuma_comments"
    )).scalar() or 0

    if existing_comments >= 60:
        return {"ok": True, "message": f"Already has {existing_comments} comments, skipping.", "seeded_comments": 0}

    existing_slugs = set()
    for r in db.execute(sa_text("SELECT DISTINCT post_slug FROM okuma_comments")).mappings().all():
        existing_slugs.add(r["post_slug"])

    seeded_comments = 0
    seeded_views = 0
    seeded_likes = 0
    now = datetime.now(timezone.utc)

    for slug, comments_list in _SEED_COMMENTS.items():
        for i, (author, content) in enumerate(comments_list):
            ip_raw = _COMMENTER_IPS[i % len(_COMMENTER_IPS)]
            ip_hash = hashlib.sha256(ip_raw.encode()).hexdigest()[:16]
            offset_h = random.randint(2, 168)
            offset_m = random.randint(0, 59)
            created = now - __import__("datetime").timedelta(hours=offset_h, minutes=offset_m)

            db.execute(sa_text("""
                INSERT INTO okuma_comments (post_slug, author_name, content, ip_hash, created_at)
                VALUES (:slug, :name, :content, :ip, :created)
            """), {"slug": slug, "name": author, "content": content, "ip": ip_hash, "created": str(created)})
            seeded_comments += 1

        view_count = random.randint(35, 120)
        for j in range(view_count):
            vip = _VIEW_IPS[j % len(_VIEW_IPS)]
            vip_hash = hashlib.sha256((vip + slug).encode()).hexdigest()[:16]
            db.execute(sa_text("""
                INSERT INTO okuma_views (post_slug, ip_hash, created_at)
                VALUES (:slug, :ip, NOW())
                ON CONFLICT (post_slug, ip_hash) DO NOTHING
            """), {"slug": slug, "ip": vip_hash})
            seeded_views += 1

        like_count = random.randint(5, 25)
        for k in range(like_count):
            lip = _COMMENTER_IPS[k % len(_COMMENTER_IPS)]
            lip_hash = hashlib.sha256((lip + slug).encode()).hexdigest()[:16]
            db.execute(sa_text("""
                INSERT INTO okuma_likes (post_slug, ip_hash, created_at)
                VALUES (:slug, :ip, NOW())
                ON CONFLICT (post_slug, ip_hash) DO NOTHING
            """), {"slug": slug, "ip": lip_hash})
            seeded_likes += 1

    db.commit()
    return {
        "ok": True,
        "seeded_comments": seeded_comments,
        "seeded_views": seeded_views,
        "seeded_likes": seeded_likes,
    }
