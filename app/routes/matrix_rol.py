import json
import logging
import os
import re
from datetime import datetime
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from openai import OpenAI

from app.db import get_db
from app.services.matrix_role import analyze_matrix_role
from app.services.user_repo import get_or_create_user
from app.services.premium_guard_db import ensure_premium, ensure_self_only, ensure_30_days
from app.models.user_profile import UserProfile

_log = logging.getLogger("matrix_rol")

router = APIRouter(prefix="/matrix-rol", tags=["matrix-rol"])

MODEL_NAME = (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()
TEMPERATURE = float(os.getenv("SANRI_TEMPERATURE", "0.45"))
MAX_TOKENS = int(os.getenv("SANRI_MAX_TOKENS", "900"))
SECTION_MAX_TOKENS = int(os.getenv("SANRI_SECTION_MAX_TOKENS", "2400"))


def get_client() -> OpenAI:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY missing or empty")
    return OpenAI(api_key=api_key)


def _strip_json_fence(raw: str) -> str:
    t = (raw or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


# ── Section-level AI generation ──

SECTION_SYSTEM = """Sen SANRI'nın derin okuma katmanısın.
Sana bir kişinin numerolojik verileri verilecek.
Her alan için 2-4 cümle yaz. KURALLAR:
- Kişiye özel, spesifik, duygusal olarak isabetli yaz.
- Jenerik ya da motivasyon kitabı tonu KULLANMA.
- Soru sorma. Cevap ver.
- "Sen" diye hitap et, "siz" kullanma.
- Türkçe yaz. Ton: sakin, keskin, samimi, gizemli.
- Her alan birbirinden bağımsız olsun.
- Her alanı doldurmak ZORUNLU, hiçbir alan boş olmasın.
Sonucu SADECE JSON nesnesi olarak döndür, başka hiçbir şey yazma."""

SECTION_USER_TEMPLATE = """Kişi: {name}
Doğum tarihi: {birth_date}
Matrix rolü: {role}
İsim arketipi: {name_archetype}
Yaşam yolu arketipi: {life_path_archetype}
Yaşam yolu sayısı: {life_path}
İsim sayısı: {name_number}

Şu alanları JSON olarak doldur:
{{
  "relationship_code": "İlişki alanındaki temel kalıp ve gerilim",
  "weekly_focus": "Bu haftanın kritik noktası ve dikkat edilmesi gereken alan",
  "career_flow": "Kariyer/iş alanındaki temel dinamik ve tıkanıklık",
  "person_scenario": "Hayatındaki önemli bir kişi senaryosu (isim kullanma, ilişki dinamiği anlat)",
  "money_pattern": "Para ve değer ilişkisindeki temel kalıp",
  "blind_spot": "Göremediği kör nokta",
  "cycle_pattern": "Tekrar eden yaşam döngüsü",
  "breaking_point": "Kırılma noktası — döngüyü kıracak farkındalık"
}}"""


def _generate_sections(client: OpenAI, base: dict, name: str, birth_date: str) -> dict:
    user_prompt = SECTION_USER_TEMPLATE.format(
        name=name,
        birth_date=birth_date,
        role=base.get("matrix_role", "Yolcu"),
        name_archetype=base.get("name_archetype", ""),
        life_path_archetype=base.get("life_path_archetype", ""),
        life_path=base.get("life_path", 0),
        name_number=base.get("name_number", 0),
    )

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SECTION_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.72,
            max_tokens=SECTION_MAX_TOKENS,
            response_format={"type": "json_object"},
        )
        raw = (completion.choices[0].message.content or "").strip()
        raw = _strip_json_fence(raw)
        sections = json.loads(raw)
        _log.info("[sections] generated %d keys for %s", len(sections), name)
        return sections
    except Exception as exc:
        _log.warning("[sections] LLM failed for %s: %s", name, exc)
        return {}


# ── Deep reading AI generation ──

DEEP_SYSTEM = """Sen SANRI'nın derin analiz katmanısın.
Kullanıcının numerolojik verileri + kişisel form bilgisi verilecek.

ÇIKTI FORMATI (ZORUNLU): Sonucu SADECE JSON olarak döndür:
{{
  "sections": [
    {{"title": "Bölüm başlığı", "body": "İçerik metni"}},
    ...
  ]
}}

HER BÖLÜM İÇİN KURALLAR:
- 3-6 bölüm yaz. Her bölüm farklı bir katman açsın.
- Çok spesifik, kişiye özel, duygusal olarak isabetli yaz.
- Jenerik motivasyon tonu KULLANMA. Coaching tonu KULLANMA.
- "Sen" diye hitap et. Sanki kişiyi yıllardır tanıyormuşsun gibi yaz.
- Her bölüm bir öncekinin üstüne inşa edilsin — katman katman derinleşsin.
- Son bölüm "şimdi ne yapmalı" sorusuna cevap versin — ama reçete değil, ayna olsun.
- Türkçe yaz. Ton: sakin, keskin, samimi, gizemli, derin, bağımlılık yaratan."""

DEEP_PROMPTS: dict[str, str] = {
    "relationship": (
        "Kişinin İLİŞKİ ALANI için çok katmanlı derin okuma yap.\n"
        "Ek bilgi:\n- Mevcut durum: {status}\n- Tekrar eden sorun: {issue}\n- Duygusal ton: {tone}\n\n"
        "BÖLÜMLER:\n"
        "1) İlişki Kalıbın — tekrar eden sahne nedir, neden bu kalıp?\n"
        "2) Ayna Etkisi — karşındaki sana neyi yansıtıyor?\n"
        "3) Sınır Haritası — nerede sınır koyamıyorsun ve bu seni nasıl etkiliyor?\n"
        "4) Duygusal Hafıza — geçmişten taşıdığın ne bu ilişkiyi şekillendiriyor?\n"
        "5) Dönüşüm Anahtarı — bu kalıbı kırmak için görmesi gereken şey ne?"
    ),
    "career": (
        "Kişinin KARİYER/İŞ ALANI için çok katmanlı derin okuma yap.\n"
        "Ek bilgi:\n- Çalışma durumu: {work_status}\n- Alanı: {field}\n- En büyük tıkanıklık: {blockage}\n- İstediği yön: {direction}\n\n"
        "BÖLÜMLER:\n"
        "1) Kariyer DNA'n — doğal yeteneklerin ve frekansının kariyer alanına nasıl yansıyor?\n"
        "2) İç Sabotaj — başarıya yaklaştıkça devreye giren gizli mekanizma\n"
        "3) Tıkanıklık Noktası — tam olarak nerede ve neden tıkanıyorsun?\n"
        "4) Gerçek Yön — seni gerçekten çeken şey nedir (arzularının altındaki arzu)?\n"
        "5) Hareket Planı — sıradaki adımın ne olmalı (somut, kişiye özel)"
    ),
    "weekly": (
        "Kişinin BU HAFTASI için çok katmanlı derin okuma yap.\n"
        "Ek bilgi:\n- Bu haftaki odak: {focus}\n- Şu anki stres alanı: {stress}\n\n"
        "BÖLÜMLER:\n"
        "1) Haftanın Enerjisi — bu haftanın genel frekansı ve seni nasıl etkileyecek\n"
        "2) Kritik Gün — bu hafta hangi gün/an en kritik ve neden?\n"
        "3) Dikkat Noktası — kaçınman/dikkat etmen gereken gizli tuzak\n"
        "4) Fırsat Penceresi — bu haftanın sana açtığı fırsat nedir?\n"
        "5) Haftalık Ritüel — bu hafta her gün yapabileceğin tek bir bilinçli eylem"
    ),
    "person": (
        "Kişinin HAYATINDAKİ BELİRLİ BİR KİŞİ için çok katmanlı derin analiz yap.\n"
        "Ek bilgi:\n- Kişinin adı: {person_name}\n- Doğum tarihi: {person_dob}\n- İlişki türü: {relation_type}\n\n"
        "BÖLÜMLER:\n"
        "1) Bağ Analizi — bu iki kişi arasındaki enerjetik bağın doğası\n"
        "2) Ayna Dinamiği — bu kişi ona neyi yansıtıyor, neyi tetikliyor?\n"
        "3) Çatışma Kodu — arada tekrar eden gerilimin gerçek kaynağı\n"
        "4) Ruhsal Kontrat — bu iki kişi neden birbirinin hayatında?\n"
        "5) Yol Haritası — bu ilişkide sırada ne var?"
    ),
    "money": (
        "Kişinin PARA VE DEĞER alanı için çok katmanlı derin okuma yap.\n"
        "Ek bilgi:\n- Gelir durumu: {income_status}\n- En büyük sorun: {block}\n- Maddi hedef: {goal}\n\n"
        "BÖLÜMLER:\n"
        "1) Para İnancın — bilinçaltında para hakkında taşıdığın inanç sistemi\n"
        "2) Değer Aynası — kendine biçtiğin değer ile kazancın arasındaki bağ\n"
        "3) Bolluk Blokajı — paranın sana akmasını engelleyen görünmez duvar\n"
        "4) Harcama Kalıbı — para harcama biçimin sana ne anlatıyor?\n"
        "5) Bolluk Anahtarı — bu blokajı çözmek için fark etmesi gereken şey"
    ),
    "emotion": (
        "Kişinin DUYGUSAL DERİNLİK alanı için çok katmanlı derin okuma yap.\n"
        "Ek bilgi:\n- Şu anki baskın duygu: {dominant_emotion}\n- En çok kaçındığı duygu: {avoided_emotion}\n- Bedeninde en çok nerede hissediyor: {body_area}\n\n"
        "BÖLÜMLER:\n"
        "1) Duygusal İmzan — hangi duyguları taşıyorsun ve neden?\n"
        "2) Bastırılmış Katman — hissetmekten kaçındığın şeyin gerçek yüzü\n"
        "3) Bedensel Hafıza — bedenin neyi tutuyor, nerede saklıyor?\n"
        "4) Duygusal Döngü — tekrar eden duygusal sahne ve tetikleyicisi\n"
        "5) Serbest Bırakma — bu duyguyu dönüştürmek için farkındalık noktası"
    ),
    "astro": (
        "Kişinin ASTROLOJİK VE NUMEROLOJİK PROFİLİ için çok katmanlı derin okuma yap.\n"
        "Doğum tarihi üzerinden analiz yap. Ek bilgi:\n- Merak ettiği alan: {curiosity}\n- Hayatında tekrar eden tema: {recurring_theme}\n\n"
        "BÖLÜMLER:\n"
        "1) Doğum Frekansın — doğum tarihinin taşıdığı enerji ve yaşam teması\n"
        "2) Sayısal Harita — isim ve doğum sayılarının kesişim noktası\n"
        "3) Gölge Profili — bu kombinasyonun karanlık/gölge tarafı\n"
        "4) Yaşam Dersi — bu yaşamda öğrenmek için geldiğin ana ders\n"
        "5) Kozmik Yön — evrenin sana gösterdiği yol"
    ),
    "identity": (
        "Kişinin KİMLİK VE BENLİK alanı için çok katmanlı derin okuma yap.\n"
        "Ek bilgi:\n- Kendini nasıl tanımlıyor: {self_description}\n- En çok hangi rolde hissediyor: {dominant_role}\n- Değiştirmek istediği şey: {change_wish}\n\n"
        "BÖLÜMLER:\n"
        "1) Yüzey Kimliğin — dünyaya gösterdiğin yüz ve onun altındaki gerçek\n"
        "2) Gölge Ben — senden sakladığın kendin, görmek istemediğin parça\n"
        "3) Çekirdek Yara — kimliğini şekillendiren en eski yara\n"
        "4) Otantik Ben — maskelerin altındaki gerçek sen\n"
        "5) Bütünleşme — gölgeyi ve ışığı bir araya getiren farkındalık"
    ),
    "blindspot": (
        "Kişinin KÖR NOKTA alanı için çok katmanlı derin okuma yap.\n"
        "Ek bilgi:\n- En çok duyduğu eleştiri: {feedback}\n- En çok tetikleyen durum: {trigger}\n- Değiştiremediği alışkanlık: {pattern}\n\n"
        "BÖLÜMLER:\n"
        "1) Görünmeyen Alan — başkalarının gördüğü ama senin göremediğin şey\n"
        "2) Gölge Algı — kendi hakkında inandığın ama gerçeği yansıtmayan hikaye\n"
        "3) Tetikleyici Harita — seni tetikleyen durumların altındaki gerçek yara\n"
        "4) Savunma Mekanizman — kendini korumak için otomatik devreye giren kalkan\n"
        "5) Farkındalık Kapısı — kör noktanı görmenin sana açacağı yeni alan"
    ),
    "cycle": (
        "Kişinin DÖNGÜ alanı için çok katmanlı derin okuma yap.\n"
        "Ek bilgi:\n- Tekrar eden olay: {repeating}\n- Döngünün başladığı zaman: {age_range}\n- Döngüyü fark ettiği an: {awareness}\n\n"
        "BÖLÜMLER:\n"
        "1) Döngü Haritası — hayatında tekrar eden sahnenin tam anatomisi\n"
        "2) Köken Noktası — bu döngünün ilk tohumunun atıldığı an\n"
        "3) Bilinçsiz Kazanç — bu döngüde kalmaktan bilinçaltının aldığı gizli fayda\n"
        "4) Çıkış Kodu — döngüyü kırmak için görmesi gereken tek şey\n"
        "5) Yeni Senaryo — döngü kırıldığında hayatın nasıl görünecek"
    ),
    "breakpoint": (
        "Kişinin KIRILMA NOKTASI alanı için çok katmanlı derin okuma yap.\n"
        "Ek bilgi:\n- Değişim hissettiği an: {turning_point}\n- En çok direndiği alan: {resistance}\n- Bırakmaya hazır olduğu şey: {readiness}\n\n"
        "BÖLÜMLER:\n"
        "1) Kırılma Anatomisi — tam olarak nerede ve neden kırılıyorsun?\n"
        "2) Direniş Haritası — değişime direncin altındaki korku\n"
        "3) Eski Hikaye — bırakman gereken ama tutunamadığın eski anlatı\n"
        "4) Dönüşüm Momenti — kırılmanın aslında bir doğum olduğunu gör\n"
        "5) Yeni Ben — kırılmadan sonra ortaya çıkacak versiyonun portresi"
    ),
}

DEEP_BASE_TEMPLATE = """Kişi: {name}
Doğum tarihi: {birth_date}
Matrix rolü: {role}
İsim arketipi: {name_archetype}
Yaşam yolu arketipi: {life_path_archetype}
Yaşam yolu sayısı: {life_path}

{type_prompt}"""


class MatrixRolRequest(BaseModel):
    name: str
    birth_date: str = ""


class MatrixDeepRequest(BaseModel):
    name: str
    birth_date: str = ""
    deep_type: str
    form_data: dict[str, str] = {}


class MatrixRolYorumRequest(BaseModel):
    name: str
    birth_date: str
    context: str | None = None


@router.post("")
def matrix_rol(req: MatrixRolRequest):
    if not (req.name or "").strip():
        raise HTTPException(status_code=400, detail="name is required")

    try:
        base = analyze_matrix_role(req.name, req.birth_date)

        def _to_int(v, default=0):
            try:
                if v is None:
                    return default
                if isinstance(v, (int, float)):
                    return int(v)
                s = str(v).strip()
                return int(s) if s else default
            except Exception:
                return default

        name_number = _to_int(base.get("name_number"), 0)
        life_path = _to_int(base.get("life_path"), 0)

        NAME_MAP = {
            1: ("Öncü", "başlatırsın", "aceleyle kırarsın"),
            2: ("Bağ Kurucu", "uzlaştırırsın", "fazla yük alırsın"),
            3: ("Yaratıcı / İfade", "ilham yayırsın", "dağılabilirsin"),
            4: ("Kurucu", "sistem kurarsın", "katılaşabilirsin"),
            5: ("Değişim", "kapı açarsın", "istikrarsızlaşabilirsin"),
            6: ("Şifacı", "iyileştirirsin", "herkesi kurtarmaya çalışırsın"),
            7: ("Bilge", "derin görürsün", "fazla içe kapanırsın"),
            8: ("Güç / Yönetim", "inşa edersin", "kontrol edebilirsin"),
            9: ("Tamamlayıcı", "kapanış açarsın", "fazla fedakâr olabilirsin"),
            11: ("Uyanış / İlham", "ışık getirirsin", "aşırı hassaslaşabilirsin"),
            22: ("Usta Kurucu", "büyük yapı kurarsın", "yükün altında ezilebilirsin"),
            33: ("Usta Şifa / Rehber", "rehberlik edersin", "sınır koymayı unutabilirsin"),
        }

        LP_MAP = {
            1: ("Başlatma", "tek bir karar al", "ertelemeyi kes"),
            2: ("Uyum", "bir ilişkiyi yumuşat", "kırılganlığı yönet"),
            3: ("İfade", "tek bir cümle yaz", "dağınıklığı toparla"),
            4: ("Düzen", "bir sistemi tamamla", "katılığı gevşet"),
            5: ("Özgürlük", "bir değişim yap", "savrukluğu kes"),
            6: ("Hizmet", "birine şifa ver", "kendini ihmal etme"),
            7: ("İçgörü", "10 dk sessizlik", "yalnızlığa kaçma"),
            8: ("Güç", "bir hedef koy", "kontrol takıntısını bırak"),
            9: ("Tamamlama", "yarım kalan bir şeyi bitir", "fazla yüklenme"),
            11: ("Uyanış", "bir işaret seç", "duyusal aşırılığa dikkat"),
            22: ("Ustalık", "bir yapı planla", "mükemmeliyetçiliği bırak"),
            33: ("Rehberlik", "bir kişiyi yükselt", "kurtarıcı moduna girme"),
        }

        n_title, n_light, n_shadow = NAME_MAP.get(name_number, ("Öz", "yol açarsın", "yorulabilirsin"))
        lp_title, lp_step, lp_warn = LP_MAP.get(life_path, ("Yol", "tek bir adım at", "dağılma"))

        teaser = (
            f"Çekirdek Rol: {base.get('matrix_role')}\n\n"
            f"Işık Frekansı: {n_title} — bu yaşamda {n_light}.\n"
            f"Gölge İpucu: {n_shadow}. ({lp_warn})\n\n"
            f"Bugün 1 Adım: {lp_step}."
        )

        # AI-generated section content
        client = get_client()
        sections = _generate_sections(client, base, req.name.strip(), req.birth_date.strip())

        return {**base, "teaser": teaser, **sections}

    except HTTPException:
        raise
    except Exception as e:
        _log.exception("MATRIX_BASE_ERROR")
        raise HTTPException(status_code=500, detail=f"MATRIX_BASE_ERROR: {type(e).__name__}: {str(e)}")


@router.post("/deep")
def matrix_rol_deep(req: MatrixDeepRequest):
    if not (req.name or "").strip():
        raise HTTPException(status_code=400, detail="name is required")
    if req.deep_type not in DEEP_PROMPTS:
        raise HTTPException(status_code=400, detail=f"invalid deep_type: {req.deep_type}")

    try:
        base = analyze_matrix_role(req.name, req.birth_date or "01.01.2000")

        type_template = DEEP_PROMPTS[req.deep_type]
        try:
            type_prompt = type_template.format(**req.form_data)
        except KeyError:
            type_prompt = type_template

        user_prompt = DEEP_BASE_TEMPLATE.format(
            name=req.name.strip(),
            birth_date=(req.birth_date or "").strip(),
            role=base.get("matrix_role", "Yolcu"),
            name_archetype=base.get("name_archetype", ""),
            life_path_archetype=base.get("life_path_archetype", ""),
            life_path=base.get("life_path", 0),
            type_prompt=type_prompt,
        )

        client = get_client()
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": DEEP_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.72,
            max_tokens=3000,
            response_format={"type": "json_object"},
        )
        raw = (completion.choices[0].message.content or "").strip()
        raw = _strip_json_fence(raw)
        result = json.loads(raw)

        sections = result.get("sections", [])
        reading = result.get("reading", "").strip()

        if not sections and reading:
            sections = [{"title": "Derin Okuma", "body": reading}]
        if not sections:
            raise ValueError("LLM returned empty deep reading")

        total_chars = sum(len(s.get("body", "")) for s in sections)
        _log.info("[deep] type=%s for %s — %d sections, %d chars", req.deep_type, req.name, len(sections), total_chars)

        return {
            "deep_type": req.deep_type,
            "name": req.name.strip(),
            "sections": sections,
            "base": {
                "matrix_role": base.get("matrix_role"),
                "life_path": base.get("life_path"),
                "name_archetype": base.get("name_archetype"),
                "life_path_archetype": base.get("life_path_archetype"),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        _log.exception("MATRIX_DEEP_ERROR")
        raise HTTPException(status_code=500, detail=f"MATRIX_DEEP_ERROR: {type(e).__name__}: {str(e)}")


@router.post("/yorum")
def matrix_rol_yorum(
    req: MatrixRolYorumRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-Id")

    if not (req.name or "").strip():
        raise HTTPException(status_code=400, detail="name is required")
    if not (req.birth_date or "").strip():
        raise HTTPException(status_code=400, detail="birth_date is required")

    # 1) user
    user = get_or_create_user(db, x_user_id)

    # 2) premium + self-only + 30 gün
    ensure_premium(user)
    ensure_self_only(user, req.name, req.birth_date)
    ensure_30_days(user)

    # 3) ilk kullanımda profili kilitle
    if not user.name and not user.birth_date:
        user.name = req.name.strip()
        user.birth_date = req.birth_date.strip()

    # 4) deterministik base
    base = analyze_matrix_role(req.name, req.birth_date)

    # 5) LLM yorum promptu
    system = (
        "Sen SANRI'nin Matrix Rol yorum katmanısın.\n"
        "Kurallar:\n"
        "1) Deterministik değerleri ASLA değiştirme.\n"
        "2) Soru sorma. Kullanıcıyı yormadan rehberlik ver.\n"
        "3) 3 katman yaz: Kişisel Rol, Kolektif Rol, Ruh Görevi.\n"
        "4) Sonunda 'Bugün 1 Adım' ekle.\n"
        "5) Dil: Türkçe. Ton: sakin, net, güçlü.\n"
    )

    user_prompt = (
        f"İsim: {base.get('name_normalized')}\n"
        f"İsim Sayısı: {base.get('name_number')} ({base.get('name_archetype')})\n"
        f"Yaşam Yolu: {base.get('life_path')} ({base.get('life_path_archetype')})\n"
        f"Matrix Rol: {base.get('matrix_role')}\n"
        f"Bağlam: {req.context or '(yok)'}\n\n"
        "FORMAT:\n"
        "KİŞİSEL ROL:\n- (3-6 madde)\n"
        "KOLEKTİF ROL:\n- (3-6 madde)\n"
        "RUH GÖREVİ:\n- (3-6 madde)\n"
        "BUGÜN 1 ADIM:\n- (tek cümle)\n"
    )

    # 6) LLM call
    client = get_client()
    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user_prompt}],
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )
    yorum = (completion.choices[0].message.content or "").strip() or "Buradayım."

    # 7) başarılıysa sayaç bas + profil hafıza güncelle
    user.last_matrix_deep_analysis = datetime.utcnow()
    db.add(user)

    profile_data = {
        "name_normalized": base.get("name_normalized"),
        "name_number": base.get("name_number"),
        "life_path": base.get("life_path"),
        "matrix_role": base.get("matrix_role"),
        "last_context": (req.context or "").strip(),
        "last_deep_at": user.last_matrix_deep_analysis.isoformat(),
    }

    prof = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if not prof:
        prof = UserProfile(user_id=user.id, data=profile_data)
    else:
        prof.data = {**(prof.data or {}), **profile_data}
    db.add(prof)

    db.commit()

    return {"base": base, "yorum": yorum}