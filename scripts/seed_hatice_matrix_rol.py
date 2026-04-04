"""
Hatice Kübra Bağdatlı — Matrix Rol Okuma teslimatını user_deliverables tablosuna yazar.
Çalıştır: sanri-api kökünden  python scripts/seed_hatice_matrix_rol.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from sqlalchemy import text

from app.db import engine
from app.routes import deliverables as deliverables_mod

deliverables_mod._ensure_deliverables_table()


def _is_pg() -> bool:
    return engine.dialect.name == "postgresql"


EMAIL = "haticebelmas@gmail.com"
CUSTOMER_NAME = "Hatice Kübra Bağdatlı"
CONTENT_ID = "role_unlock"

SECTIONS = [
    {
        "heading": "Giriş",
        "body": (
            "Hatice Kübra, bu metin sana dışarıdan bir etiket yapıştırmak için değil; zaten içinde taşıdığın "
            "farkındalığı, kelimelere dökülmeyi bekleyen kısımlarıyla buluşturmak için var. İsminde bir "
            "hatırlayış ve bir derinlik titreşimi var; Kübra ise büyüklüğü sadece görünür alanda değil, "
            "sessizlikte de taşıyan bir genişlik çağrısı. 22 Eylül çizgisinde doğmuş olman, dengeye yakın "
            "ama dengeyi çoğu zaman başkaları için kurmaya çalışan bir iç mimariyi işaret edebilir. "
            "Sayıların sana kader yazmaz; ama 1978 yolunun getirdiği kuşaksal ve kişisel katmanlar, "
            "seni “güçlü durmalıyım” öğrenimine erken tanıştırmış olabilir. Bu okuma, seni sabit bir kutuya "
            "koymaz; yalnızca senin Matrix içindeki rolünün sıklıkla nerede devreye girdiğini gösterir."
        ),
    },
    {
        "heading": "Matrix Rolün: Ana Rol Analizi",
        "body": (
            "Senin matrix rolün, çoğu zaman “ortamı ayakta tutan, çatıyı taşıyan, kırılganlığı görünmez "
            "kılan kişi” frekansında çalışır. Bu rol bazen resmi bir liderlik değildir; daha çok sistem "
            "içindeki görünmez omurgadır: bir şeyler yarım kaldığında tamamlayan, birileri dağıldığında "
            "toparlayan, birileri yorulduğunda devreye giren. Bu rol seni değerli kılar çünkü içinde "
            "ciddi bir sorumluluk etiği ve bağlılık kapasitesi vardır. Aynı zamanda bu rol, seni “insanların "
            "duygusal ve pratik yükünü taşıyan varsayılan adres” haline getirebilir. Matrix burada şunu "
            "sorar: Bu taşıyıcılık bilinçli bir seçim mi, yoksa kimliğe dönüşmüş bir refleks mi?"
        ),
    },
    {
        "heading": "Tekrar Eden Döngü",
        "body": (
            "Tekrar eden döngün genellikle şu ritimde döner: önce fazla verirsin — zaman, dikkat, "
            "naziklik, çözüm üretme, ardından içeride bir “yine ben mi?” sessizliği belirir. İkinci aşama, "
            "anlaşılmama hissiyle birlikte kendini daha da netleştirmeye çalışmaktır; bazen bu netlik "
            "dışarıda kontrol gibi okunur oysa içeride güven arayışıdır. Üçüncü aşama ise güçlü görünme "
            "ihtiyacıdır; çünkü kırılganlığını göstermek, senin hikâyende riskli bir alan olabilir. "
            "Döngü kapanırken sen yine toparlayan olursun — çünkü bunu yapabildiğini kanıtlamışsındır. "
            "Burada suçlama yok; sadece bir iç kod: “Ben dayanıklıyım” cümlesi, bazen “Benim de ihtiyacım "
            "olabilir” cümlesinin önüne geçer."
        ),
    },
    {
        "heading": "İlişkiler Alanı",
        "body": (
            "İlişkilerde sık üstlendiğin rol, çevirmenlik ve köprü kurmak olabilir: herkesin dilinden "
            "anlayan, arayı düzelten, gerilimi yumuşatan. Bu güzel bir yetenektir; fakat görülmeyen emek "
            "birikince içeride bir yorgunluk katmanı oluşur. Bazen fazla vermen, karşı tarafın seni "
            "“zaten iyidir” diye okumasına yol açar; bu okuma kötü niyetli olmak zorunda değildir — çoğu "
            "zaman alışkanlıktır. İlişkide üstlenilen rolün, seni merkezden uzaklaştırdığı anlar olabilir: "
            "kendi ihtiyacını en sona koyduğun, sonra da bunu “fedakârlık” diye yücelttiğin. Asıl mesele "
            "fedakârlık değil; sınırın ne zaman sevgi, ne zaman kendini silme olduğunu ayırt etmektir."
        ),
    },
    {
        "heading": "Korku ve Savunma Mekanizması",
        "body": (
            "Korkunun yüzeyi çoğu zaman kontrol ve düzen ihtiyacında görünür: planlar, doğrular, "
            "“her şey yolunda” hissi. Derinde ise güven meselesi yatar — kendine, hayata, ilişkilere "
            "dair. Savunman bazen sakin ve kontrollü görünmektir; bu görünüm dışarıyı rahatlatır ama "
            "içeride yoğun bir baskı biriktirebilir. Başka bir savunma da erken müdahale: bir şey kırılmadan "
            "onu tamir etmeye koşmak. Bu, sevgiyle karıştığında “ben varım” der; tükenmişlikle karıştığında "
            "ise “ben yokum”a döner. Burada yargı yok; sadece fark etme: güçlü görünmek bazen hayatta "
            "kalmak için öğrenilmiş bir zırh, bazen de artık seni sıkan bir kalıp olabilir."
        ),
    },
    {
        "heading": "Güçlü Yön",
        "body": (
            "Senin güçlü yönün, derin bir vefa ve içsel ahlaki dikendir. İnsanları yüz üstü bırakmama "
            "isteğin, çoğu zaman gerçek bir özdeğer kaynağıdır. Anlayışın yüksektir; başkalarının "
            "kırılganlığını erken sezersin. Bu, seni ilişkilerde güvenilir kılar. Ayrıca sessiz direnç "
            "taşırsın: gürültü çıkarmadan, dayanıklılığı sürdürebilirsin. Kadınlık, emek ve görülme "
            "temalarında, senin gücün “gösterişli olmayan ama gerçek” taraftadır: evi, sofrayı, duyguyu, "
            "geçmişi, geleceği içten içe ören bir el işi gibi. Bu güç, merkezine döndüğünde daha da "
            "parlar; çünkü artık sadece taşımak değil, seçmek de senin elindedir."
        ),
    },
    {
        "heading": "Gölge Yön",
        "body": (
            "Gölge yönün, görülmemişliğe karşı içten içe öfke biriktirmek ve bunu dışarı vurmadan "
            "bedende, uykuda, iç sıkışmasında yaşamak olabilir. Bazen “her şeyi ben düzelttim” haklılığı, "
            "yakınlığı uzaklaştırır; çünkü haklılık ile yalnızlık yan yana gelebilir. Aşırı sorumluluk "
            "aldığında, başkalarının özgürlüğünü de elinden almış olabilirsin — iyi niyetle. Gölge, "
            "burada şunu fısıldar: “Ben vazgeçersem düşerler” inancı. Bu inanç seni yüceltmez; seni "
            "donuk tutar. Gölgeyi düşman gibi okuma; o, sınırlarını hatırlatan bir iç rehberdir."
        ),
    },
    {
        "heading": "Hayat Dersi",
        "body": (
            "Hayat dersin, taşıyıcılığı onurlandırmak ama onu tek kimlik haline getirmemektir. "
            "Merkezine dönmek, bencillik değildir; bütünlüktür. Senin yolun, “ben güçlüyüm” cümlesini "
            "“ben insanım ve ihtiyaçlarım da kutsal” cümlesiyle genişletmekten geçebilir. Matrix’te "
            "rolünü bırakmak, hayattan çıkmak değildir; rolü seçerek oynamaktır. Bir gün şunu "
            "deneyimleyebilirsin: toparlamadan önce durduğunda dünya çökmez; sadece sorumluluklar "
            "sahiplerine geri döner. Bu dönüş, seni küçültmez; seni özgürleştirir."
        ),
    },
    {
        "heading": "Kendine Sor",
        "body": (
            "• Bugün hangi “ben hallederim” anı gerçekten benim işimdi, hangisi başkasının büyüme alanıydı?\n"
            "• Kontrol ettiğim şey güven mi arıyor, yoksa korku mu yönetiliyor?\n"
            "• İlişkide üstlendiğim rol, beni büyütüyor mu yoksa görünmez mi kılıyor?\n"
            "• Güçlü görünmek yerine dürüst görünmek bana ne kazandırır, ne kaybettirir — ve bu kayıp gerçek mi?\n"
            "• Görülmek istediğim yerde, neyi söylemekten çekiniyorum?\n"
            "• Kendi merkezimde kaldığımda, sevgim nasıl değişiyor?"
        ),
    },
    {
        "heading": "Kapanış",
        "body": (
            "Hatice Kübra, bu okuma sana bir hüküm vermez; seni tanır gibi yapan bir ayna tutar. "
            "Senin içinde hem derin bir şefkat hem de “artık yeter” diyen sağlıklı bir ses var; ikisi "
            "birbirine düşman değil, birbirini tamamlar. Matrix rolün seni küçültmez; ama rolü fark "
            "etmezsen seni yorar. Bugünden sonra küçük bir davranış yeter: ihtiyacını ertelemeden bir "
            "cümleyle, bir nefesle, bir sınırla kendine yer aç. Sen zaten hatırlıyorsun; bu metin yalnızca "
            "hatırlattı. Yolun açık olsun."
        ),
    },
]

SUMMARY_LINES = [
    "Matrix rolün çoğu zaman görünmez taşıyıcı ve toparlayıcı frekansında çalışır; güçlü görünme ile içsel kırılganlık arasında bir gerilim taşırsın.",
    "İlişkilerde çevirmenlik ve fazla verme döngüsü, anlaşılmama hissini besleyebilir; kontrol ise çoğu zaman güven arayışının dili olur.",
    "Hayat dersin, taşıyıcılığı onurlandırıp onu tek kimlik yapmadan kendi merkezine dönmek ve ihtiyaçlarını kutsal saymak üzerinedir.",
]

CARD_TITLE = "Matrix Rolün: Merkezine dönen taşıyıcı"
PREVIEW_TEXT = (
    "Görünürde sakin ve güçlü duran iç katmanında yoğun bir baskı taşıyabilirsin; "
    "bu okuma rolünü, döngülerini ve merkeze dönüş çağrını hatırlatır."
)
TITLE = "Hatice Kübra Bağdatlı — Matrix Rol Okuman"
PRICE_NOTE = "369 TL"
BIRTH_DATE = "22.09.1978"


def main() -> None:
    email = EMAIL.strip().lower()
    payload = {
        "content_id": CONTENT_ID,
        "title": TITLE,
        "customer_name": CUSTOMER_NAME,
        "customer_email": email,
        "product_name": "Matrix Rol Okuma",
        "birth_date": BIRTH_DATE,
        "sections": SECTIONS,
        "summary_lines": SUMMARY_LINES,
    }
    payload_json = json.dumps(payload, ensure_ascii=False)
    now = datetime.utcnow()

    with engine.connect() as conn:
        uid_row = conn.execute(
            text("SELECT id FROM users WHERE lower(trim(email)) = :em LIMIT 1"),
            {"em": email},
        ).mappings().first()
        uid = int(uid_row["id"]) if uid_row else None

    params = {
        "uid": uid,
        "email": email,
        "cid": CONTENT_ID,
        "pn": "Matrix Rol Okuma",
        "title": TITLE,
        "ct": CARD_TITLE,
        "pv": PREVIEW_TEXT,
        "price": PRICE_NOTE,
        "pj": payload_json,
        "now": now,
        "now2": now,
    }

    if _is_pg():
        sql = """
            INSERT INTO user_deliverables (
                user_id, email, content_id, product_name, title, card_title, preview_text,
                price_note, payload_json, created_at, updated_at
            ) VALUES (
                :uid, :email, :cid, :pn, :title, :ct, :pv, :price, :pj, :now, :now2
            )
            ON CONFLICT (email, content_id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                product_name = EXCLUDED.product_name,
                title = EXCLUDED.title,
                card_title = EXCLUDED.card_title,
                preview_text = EXCLUDED.preview_text,
                price_note = EXCLUDED.price_note,
                payload_json = EXCLUDED.payload_json,
                updated_at = EXCLUDED.updated_at
        """
    else:
        sql = """
            INSERT INTO user_deliverables (
                user_id, email, content_id, product_name, title, card_title, preview_text,
                price_note, payload_json, created_at, updated_at
            ) VALUES (
                :uid, :email, :cid, :pn, :title, :ct, :pv, :price, :pj, :now, :now2
            )
            ON CONFLICT(email, content_id) DO UPDATE SET
                user_id = excluded.user_id,
                product_name = excluded.product_name,
                title = excluded.title,
                card_title = excluded.card_title,
                preview_text = excluded.preview_text,
                price_note = excluded.price_note,
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
        """

    with engine.begin() as conn:
        conn.execute(text(sql), params)

    print("OK — user_deliverables upsert:", email, CONTENT_ID, "user_id=", uid)


if __name__ == "__main__":
    main()
