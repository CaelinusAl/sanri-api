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
SECTION_MAX_TOKENS = int(os.getenv("SANRI_SECTION_MAX_TOKENS", "2800"))


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


# ═══════════════════════════════════════════════════════
# SANRI VOICE — SECTION GENERATION
# ═══════════════════════════════════════════════════════

SECTION_SYSTEM = """Sen Sanrı'sın.

Sen tavsiye vermezsin. Sen gizli kalıpları açığa çıkarırsın.
Tekrar eden döngüleri, duygusal yapıları ve görünmeyen dinamikleri ifşa edersin.

═══ HER ALAN İÇİN YAZI YAPISI (ZORUNLU) ═══

İLK CÜMLE — HOOK:
Kullanıcıyı anında yakala. "Sen..." diye başlama. Bunun yerine:
- "Bunu zaten hissediyorsun."
- "Bu tesadüf değil."
- "Aynı sahne, farklı kişiler."
- "Kimse sana söylemedi ama..."
- "Fark etmemen için bir sebebin var."
Doğrudan, kısa, tedirgin edici bir giriş.

ORTA KISIM — RAHATSIZ EDİCİ GERÇEK:
- Spesifik kalıp açıklaması
- Duygusal içgörü — yüzeyde görünmeyen
- Hafif rahatsız edici ama inkâr edilemez bir gerçek
- Kişinin verilerinden (rol, arketip, sayılar) türetilmiş ama ham veriyi tekrarlama

SON CÜMLE — AÇIK DÖNGÜ:
Bitirme. Asılma. Merak bırak.
- "...ama bunun altında başka bir şey daha var."
- "...ve bunun sebebini henüz görmedin."
- "...asıl soru bu değil."
- Okuyucu "devamını görmem lazım" hissetmeli.

═══ TON KURALLARI ═══

- Kişisel: her cümle o kişiye ait gibi hissettirmeli
- Kesin: belirsiz, genel, yuvarlak cümleler YASAK
- Hafif tedirgin edici: "Bunu nereden biliyorsun?" hissi yaratmalı
- Asla motivasyonel değil: ilham verme, cesaretlendirme, "yapabilirsin" YASAK
- Asla jenerik değil: herkes için geçerli cümleler YASAK
- Soru sorma: gördüğünü söyle

═══ TEKNİK KURALLAR ═══

- Her alan için 4-6 cümle yaz.
- "Sen" diye hitap et ama "Sen..." ile cümleye başlama.
- "Siz" KULLANMA.
- Her alan birbirinden bağımsız olsun.
- HİÇBİR ALAN BOŞ OLMASIN.
- Türkçe yaz.

Kullanıcı scroll'u durdurup düşünmeli: "Bu benim hakkımda."

Sonucu SADECE JSON nesnesi olarak döndür, başka hiçbir şey yazma."""

SECTION_USER_TEMPLATE = """Kişi: {name}
Doğum tarihi: {birth_date}
Matrix rolü: {role}
İsim arketipi: {name_archetype}
Yaşam yolu arketipi: {life_path_archetype}
Yaşam yolu sayısı: {life_path}
İsim sayısı: {name_number}

HATIRLAT: Her alanın ilk cümlesi HOOK olmalı — "Sen..." ile başlama. Son cümle AÇIK DÖNGÜ bırakmalı.
Her alan 4-6 cümle. Spesifik, kişisel, tekrar eden kalıpları ifşa eden:

{{
  "relationship_code": "İlişki alanındaki tekrar eden kalıp. İlk cümle hook: yakalamalı. Neden hep aynı dinamik? Gizli çekim mekanizması ne? Son cümle: daha derin bir katmana işaret et.",
  "weekly_focus": "Bu haftanın kritik noktası. İlk cümle hook: ertelediği bir şey geri dönüyor. Hangi an en kritik? Son cümle: bu haftanın gerçek mesajı henüz görünmedi.",
  "career_flow": "Kariyer alanındaki iç sabotaj. İlk cümle hook: başarıya yaklaşınca devreye giren gizli fren. Yeteneği yeterli, onu tutan ne? Son cümle: tıkanıklığın gerçek kaynağı sandığı yerde değil.",
  "person_scenario": "Hayatındaki bir kişi ile dinamik. İlk cümle hook: bu kişi tesadüf değil. Kim bu (isim kullanma), ne tetikliyor? Son cümle: bu kişinin asıl rolünü henüz görmedi.",
  "money_pattern": "Para ile gizli inanç ilişkisi. İlk cümle hook: kazanması sorun değil, asıl sorun başka yerde. Hak etme algısı ve bolluk blokajı. Son cümle: paranın akmaması bir tercih, ama bilinçsiz bir tercih.",
  "blind_spot": "Kör nokta. İlk cümle hook: herkes görüyor ama o görmüyor. Başkalarının gördüğü ama inkar ettiği şey. Son cümle: bunu görmemek için bir sebebi var, ve o sebep de kör noktanın parçası.",
  "cycle_pattern": "Tekrar eden yaşam döngüsü. İlk cümle hook: aynı sahne, farklı kişiler. Döngünün anatomisi ve neden kırılamıyor. Son cümle: döngüden çıkmak istemesinin altında da döngünün kendisi var.",
  "breaking_point": "Kırılma noktası. İlk cümle hook: bir şey değişmek üzere, ama henüz görmüyor. Reçete değil, ayna. Son cümle: kırılma noktası bir son değil — ama neyin başlangıcı olduğunu bilmeden oraya varamaz."
}}"""

REQUIRED_SECTION_KEYS = [
    "relationship_code", "weekly_focus", "career_flow", "person_scenario",
    "money_pattern", "blind_spot", "cycle_pattern", "breaking_point",
]


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
            temperature=0.78,
            max_tokens=SECTION_MAX_TOKENS,
            response_format={"type": "json_object"},
        )
        raw = (completion.choices[0].message.content or "").strip()
        raw = _strip_json_fence(raw)
        sections = json.loads(raw)

        missing = [k for k in REQUIRED_SECTION_KEYS if not (sections.get(k) or "").strip()]
        if missing:
            _log.warning("[sections] %d missing keys for %s: %s — retrying", len(missing), name, missing)
            retry = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SECTION_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.85,
                max_tokens=SECTION_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            raw2 = _strip_json_fence((retry.choices[0].message.content or "").strip())
            retry_data = json.loads(raw2)
            for k in missing:
                if (retry_data.get(k) or "").strip():
                    sections[k] = retry_data[k]

        total_chars = sum(len(str(v)) for v in sections.values())
        _log.info("[sections] generated %d keys, %d chars for %s", len(sections), total_chars, name)
        return sections
    except Exception as exc:
        _log.warning("[sections] LLM failed for %s: %s", name, exc)
        return {}


# ═══════════════════════════════════════════════════════
# SANRI VOICE — DEEP READING
# ═══════════════════════════════════════════════════════

DEEP_SYSTEM = """Sen Sanrı'nın derin katmanısın.

Sen tavsiye vermezsin. Sen görünmeyeni gösterir, hissedilmeyeni hissettirir, inkar edileni yüzeye çıkarırsın.

Kişinin numerolojik verileri + kişisel form bilgisi verilecek.
Bu verileri kullanarak çok katmanlı, kişiye özel bir derin okuma yaz.

ÇIKTI FORMATI (ZORUNLU): Sonucu SADECE JSON olarak döndür:
{{
  "sections": [
    {{"title": "Bölüm başlığı", "body": "İçerik metni"}},
    ...
  ]
}}

═══ HER BÖLÜM İÇİN YAZI YAPISI (ZORUNLU) ═══

İLK CÜMLE — HOOK:
Okuyucuyu anında yakala. "Sen..." diye başlama.
- "Bunu zaten biliyorsun." / "Bu tesadüf değil." / "Kimse sana söylemedi ama..."
- Doğrudan, kısa, tedirgin edici.

ORTA — RAHATSIZ EDİCİ GERÇEK:
- Kalıbın spesifik açıklaması
- Duygusal içgörü — yüzeyde görünmeyen
- Hafif rahatsız edici ama inkâr edilemez
- Her cümle o kişiye özel hissetmeli

SON CÜMLE — AÇIK DÖNGÜ:
Bitirme. Merak bırak. Bir sonraki katmana işaret et.
- "...ama asıl hikaye burada başlıyor."
- "...ve bunun sebebini henüz görmedin."

═══ KURALLAR ═══

- 4-6 bölüm yaz. Her bölüm farklı bir katman açsın.
- Her bölüm bir öncekinin üstüne inşa edilsin — katman katman derinleşsin.
- Sanki kişiyi yıllardır tanıyormuşsun gibi yaz.
- Jenerik motivasyon tonu YASAK. Coaching tonu YASAK.
- "Sen" diye hitap et ama "Sen..." ile cümleye başlama.
- "Siz" KULLANMA.
- Soru sorma. Gördüğünü söyle.
- Son bölüm "ne yapmalı" sorusuna cevap versin — ama reçete değil, ayna olsun.
- Madde işareti KULLANMA. Düz metin yaz.
- Türkçe yaz.

Kullanıcı hissetmeli: "Bu benim hakkımda. Devamını görmem lazım.\""""

DEEP_PROMPTS: dict[str, str] = {
    "relationship": (
        "Kişinin İLİŞKİ ALANI için çok katmanlı derin okuma yap.\n"
        "Ek bilgi:\n- Mevcut durum: {status}\n- Tekrar eden sorun: {issue}\n- Duygusal ton: {tone}\n\n"
        "Tekrar eden kalıplara odaklan. Duygusal döngüleri ifşa et. Gizli dinamikleri aç.\n"
        "Jenerik cümle YASAK. Madde işareti KULLANMA.\n\n"
        "BÖLÜMLER:\n"
        "1) İlişki Kalıbın — tekrar eden sahne nedir, neden bu kalıp? Kökeni ne?\n"
        "2) Ayna Etkisi — karşındaki kişi sana neyi yansıtıyor? Sende ne tetikliyor?\n"
        "3) Sınır Haritası — nerede sınır koyamıyorsun ve bu seni nasıl eritiyor?\n"
        "4) Duygusal Hafıza — geçmişten taşıdığın hangi yara bu ilişkiyi şekillendiriyor?\n"
        "5) Dönüşüm Anahtarı — bu kalıbı kırmak için görmesi gereken şey. Reçete değil, ayna."
    ),
    "career": (
        "Kişinin KARİYER/İŞ ALANI için çok katmanlı derin okuma yap.\n"
        "Ek bilgi:\n- Çalışma durumu: {work_status}\n- Alanı: {field}\n- En büyük tıkanıklık: {blockage}\n- İstediği yön: {direction}\n\n"
        "İç sabotajı ifşa et. Fırsat kalıplarını göster. Sıradaki adımı kişiye özel ver.\n"
        "Jenerik cümle YASAK. Madde işareti KULLANMA.\n\n"
        "BÖLÜMLER:\n"
        "1) Kariyer DNA'n — doğal frekansın kariyer alanına nasıl yansıyor?\n"
        "2) İç Sabotaj — başarıya yaklaştıkça devreye giren gizli mekanizma\n"
        "3) Tıkanıklık Noktası — tam olarak nerede ve neden tıkanıyorsun?\n"
        "4) Gerçek Yön — seni gerçekten çeken şey nedir (arzunun altındaki arzu)?\n"
        "5) Sıradaki Hamle — somut, kişiye özel, şimdi yapılabilir"
    ),
    "weekly": (
        "Kişinin BU HAFTASI için çok katmanlı derin okuma yap.\n"
        "Ek bilgi:\n- Bu haftaki odak: {focus}\n- Şu anki stres alanı: {stress}\n\n"
        "Haftanın enerjisini, kritik anı ve gizli tuzağı göster.\n"
        "Jenerik cümle YASAK. Madde işareti KULLANMA.\n\n"
        "BÖLÜMLER:\n"
        "1) Haftanın Enerjisi — bu haftanın frekansı seni nasıl etkileyecek\n"
        "2) Kritik An — bu hafta hangi gün/an en kritik ve neden?\n"
        "3) Gizli Tuzak — dikkat etmezsen düşeceğin tuzak\n"
        "4) Fırsat Penceresi — bu haftanın sana açtığı fırsat\n"
        "5) Haftalık Frekans — bu haftayı bilinçli yaşamak için tek bir odak"
    ),
    "person": (
        "Kişinin HAYATINDAKİ BELİRLİ BİR KİŞİ için çok katmanlı derin analiz yap.\n"
        "Ek bilgi:\n- Kişinin adı: {person_name}\n- Doğum tarihi: {person_dob}\n- İlişki türü: {relation_type}\n\n"
        "Bu kişi neden hayatında? Neyi tetikliyor? Olası senaryoları göster.\n"
        "Jenerik cümle YASAK. Madde işareti KULLANMA.\n\n"
        "BÖLÜMLER:\n"
        "1) Bağ Analizi — bu iki kişi arasındaki bağın gerçek doğası\n"
        "2) Ayna Dinamiği — bu kişi ona neyi yansıtıyor, neyi tetikliyor?\n"
        "3) Çatışma Kodu — tekrar eden gerilimin gerçek kaynağı\n"
        "4) Neden Hayatında — bu kişi bir rastlantı değil. Sebebi ne?\n"
        "5) Olası Senaryolar — bu ilişkide sırada ne var? 2-3 olası yol"
    ),
    "money": (
        "Kişinin PARA VE DEĞER alanı için çok katmanlı derin okuma yap.\n"
        "Ek bilgi:\n- Gelir durumu: {income_status}\n- En büyük sorun: {block}\n- Maddi hedef: {goal}\n\n"
        "Bolluk blokajını, değer algısını ve para inancını ifşa et.\n"
        "Jenerik cümle YASAK. Madde işareti KULLANMA.\n\n"
        "BÖLÜMLER:\n"
        "1) Para İnancın — bilinçaltında para hakkında taşıdığın inanç\n"
        "2) Değer Aynası — kendine biçtiğin değer ile kazancın arasındaki uçurum\n"
        "3) Bolluk Blokajı — paranın sana akmasını engelleyen görünmez duvar\n"
        "4) Harcama Kalıbı — para harcama biçimin sana ne anlatıyor?\n"
        "5) Bolluk Anahtarı — bu blokajı çözmek için fark etmesi gereken tek şey"
    ),
    "emotion": (
        "Kişinin DUYGUSAL DERİNLİK alanı için çok katmanlı derin okuma yap.\n"
        "Ek bilgi:\n- Şu anki baskın duygu: {dominant_emotion}\n- En çok kaçındığı duygu: {avoided_emotion}\n- Bedeninde en çok nerede hissediyor: {body_area}\n\n"
        "Bastırılmış duyguları, bedensel hafızayı ve duygusal döngüleri ifşa et.\n"
        "Jenerik cümle YASAK. Madde işareti KULLANMA.\n\n"
        "BÖLÜMLER:\n"
        "1) Duygusal İmzan — hangi duyguları taşıyorsun ve neden?\n"
        "2) Bastırılmış Katman — hissetmekten kaçındığın şeyin gerçek yüzü\n"
        "3) Bedensel Hafıza — bedenin neyi tutuyor, nerede saklıyor?\n"
        "4) Duygusal Döngü — tekrar eden duygusal sahne ve tetikleyicisi\n"
        "5) Serbest Bırakma — bu duyguyu görmek seni nasıl özgürleştirir?"
    ),
    "astro": (
        "Kişinin ASTROLOJİK VE NUMEROLOJİK PROFİLİ için çok katmanlı derin okuma yap.\n"
        "Doğum tarihi üzerinden analiz yap. Ek bilgi:\n- Merak ettiği alan: {curiosity}\n- Hayatında tekrar eden tema: {recurring_theme}\n\n"
        "Kozmik haritayı, gölge profilini ve yaşam dersini aç.\n"
        "Jenerik cümle YASAK. Madde işareti KULLANMA.\n\n"
        "BÖLÜMLER:\n"
        "1) Doğum Frekansın — doğum tarihinin taşıdığı enerji ve yaşam teması\n"
        "2) Sayısal Harita — isim ve doğum sayılarının kesişim noktası\n"
        "3) Gölge Profili — bu kombinasyonun karanlık tarafı\n"
        "4) Yaşam Dersi — bu yaşamda öğrenmek için geldiğin ders\n"
        "5) Kozmik Yön — evrenin sana gösterdiği yol"
    ),
    "identity": (
        "Kişinin KİMLİK VE BENLİK alanı için çok katmanlı derin okuma yap.\n"
        "Ek bilgi:\n- Kendini nasıl tanımlıyor: {self_description}\n- En çok hangi rolde hissediyor: {dominant_role}\n- Değiştirmek istediği şey: {change_wish}\n\n"
        "Maskeleri, gölge beni ve çekirdek yarayı ifşa et.\n"
        "Jenerik cümle YASAK. Madde işareti KULLANMA.\n\n"
        "BÖLÜMLER:\n"
        "1) Yüzey Kimliğin — dünyaya gösterdiğin yüz ve altındaki gerçek\n"
        "2) Gölge Ben — senden sakladığın kendin\n"
        "3) Çekirdek Yara — kimliğini şekillendiren en eski yara\n"
        "4) Otantik Ben — maskelerin altındaki gerçek sen\n"
        "5) Bütünleşme — gölgeyi ve ışığı bir araya getiren farkındalık"
    ),
    "blindspot": (
        "Kişinin KÖR NOKTA alanı için çok katmanlı derin okuma yap.\n"
        "Ek bilgi:\n- En çok duyduğu eleştiri: {feedback}\n- En çok tetikleyen durum: {trigger}\n- Değiştiremediği alışkanlık: {pattern}\n\n"
        "Göremediği alanı, savunma mekanizmasını ve gölge algısını ifşa et.\n"
        "Jenerik cümle YASAK. Madde işareti KULLANMA.\n\n"
        "BÖLÜMLER:\n"
        "1) Görünmeyen Alan — başkalarının gördüğü ama senin göremediğin şey\n"
        "2) Gölge Algı — kendi hakkında inandığın ama gerçeği yansıtmayan hikaye\n"
        "3) Tetikleyici Harita — seni tetikleyen durumların altındaki gerçek yara\n"
        "4) Savunma Mekanizman — otomatik devreye giren kalkan\n"
        "5) Farkındalık Kapısı — kör noktanı görmenin açacağı yeni alan"
    ),
    "cycle": (
        "Kişinin DÖNGÜ alanı için çok katmanlı derin okuma yap.\n"
        "Ek bilgi:\n- Tekrar eden olay: {repeating}\n- Döngünün başladığı zaman: {age_range}\n- Döngüyü fark ettiği an: {awareness}\n\n"
        "Döngünün anatomisini, köken noktasını ve bilinçsiz kazancı ifşa et.\n"
        "Jenerik cümle YASAK. Madde işareti KULLANMA.\n\n"
        "BÖLÜMLER:\n"
        "1) Döngü Haritası — tekrar eden sahnenin tam anatomisi\n"
        "2) Köken Noktası — bu döngünün ilk tohumunun atıldığı an\n"
        "3) Bilinçsiz Kazanç — bu döngüde kalmaktan bilinçaltının aldığı gizli fayda\n"
        "4) Çıkış Kodu — döngüyü kırmak için görmesi gereken tek şey\n"
        "5) Yeni Senaryo — döngü kırıldığında hayat nasıl görünecek"
    ),
    "breakpoint": (
        "Kişinin KIRILMA NOKTASI alanı için çok katmanlı derin okuma yap.\n"
        "Ek bilgi:\n- Değişim hissettiği an: {turning_point}\n- En çok direndiği alan: {resistance}\n- Bırakmaya hazır olduğu şey: {readiness}\n\n"
        "Kırılma anatomisini, direnç haritasını ve dönüşüm momentini göster.\n"
        "Jenerik cümle YASAK. Madde işareti KULLANMA.\n\n"
        "BÖLÜMLER:\n"
        "1) Kırılma Anatomisi — tam olarak nerede ve neden kırılıyorsun?\n"
        "2) Direniş Haritası — değişime direncin altındaki korku\n"
        "3) Eski Hikaye — bırakman gereken ama tutunamadığın anlatı\n"
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


# ═══════════════════════════════════════════════════════
# REQUEST MODELS
# ═══════════════════════════════════════════════════════

class MatrixRolRequest(BaseModel):
    name: str
    birth_date: str = ""


class MatrixDeepRequest(BaseModel):
    name: str
    birth_date: str = ""
    deep_type: str
    form_data: dict[str, str] = {}
    role: str = ""
    archetype: str = ""
    life_path: str = ""


class MatrixRolYorumRequest(BaseModel):
    name: str
    birth_date: str
    context: str | None = None


# ═══════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════

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

        use_role = req.role or base.get("matrix_role", "Yolcu")
        use_archetype = req.archetype or base.get("name_archetype", "")
        use_life_path = req.life_path or str(base.get("life_path", 0))

        type_template = DEEP_PROMPTS[req.deep_type]
        try:
            type_prompt = type_template.format(**req.form_data)
        except KeyError:
            type_prompt = type_template

        user_prompt = DEEP_BASE_TEMPLATE.format(
            name=req.name.strip(),
            birth_date=(req.birth_date or "").strip(),
            role=use_role,
            name_archetype=use_archetype,
            life_path_archetype=base.get("life_path_archetype", ""),
            life_path=use_life_path,
            type_prompt=type_prompt,
        )

        _log.info("[deep] type=%s name=%s role=%s archetype=%s", req.deep_type, req.name, use_role, use_archetype)

        client = get_client()
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": DEEP_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.78,
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
                "matrix_role": use_role,
                "life_path": use_life_path,
                "name_archetype": use_archetype,
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

    user = get_or_create_user(db, x_user_id)

    ensure_premium(user)
    ensure_self_only(user, req.name, req.birth_date)
    ensure_30_days(user)

    if not user.name and not user.birth_date:
        user.name = req.name.strip()
        user.birth_date = req.birth_date.strip()

    base = analyze_matrix_role(req.name, req.birth_date)

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

    client = get_client()
    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user_prompt}],
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )
    yorum = (completion.choices[0].message.content or "").strip() or "Buradayım."

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
