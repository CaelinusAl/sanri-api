import re
from dataclasses import dataclass
from typing import Dict, Any

# Türkçe harfleri normalize et
TR_MAP = str.maketrans({
    "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
    "Ç": "C", "Ğ": "G", "İ": "I", "Ö": "O", "Ş": "S", "Ü": "U",
})

def normalize_name(s: str) -> str:
    s = (s or "").strip()
    s = s.translate(TR_MAP)
    s = re.sub(r"[^a-zA-Z\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.upper()

def digitsum(n: int) -> int:
    return sum(int(ch) for ch in str(abs(int(n))) if ch.isdigit())

def reduce_num(n: int, keep_master: bool = True) -> int:
    # 11/22/33 gibi master sayıları koru (istersen kapatırız)
    while n > 9:
        if keep_master and n in (11, 22, 33):
            break
        n = digitsum(n)
    return n

def letter_value(ch: str) -> int:
    # Pythagorean numerology mapping (A=1..I=9 then repeats)
    # A J S = 1, B K T = 2, C L U = 3, D M V = 4, E N W = 5,
    # F O X = 6, G P Y = 7, H Q Z = 8, I R = 9
    mapping = {
        1: "AJS",
        2: "BKT",
        3: "CLU",
        4: "DMV",
        5: "ENW",
        6: "FOX",
        7: "GPY",
        8: "HQZ",
        9: "IR",
    }
    for k, letters in mapping.items():
        if ch in letters:
            return k
    return 0

def name_number(name: str) -> int:
    name = normalize_name(name)
    total = 0
    for ch in name.replace(" ", ""):
        total += letter_value(ch)
    return reduce_num(total)

def birth_path(birth_date: str) -> int:
    # supports "21.06.1989" or "1989-06-21" or "21/06/1989"
    s = (birth_date or "").strip()
    s = s.replace("/", ".").replace("-", ".")
    parts = [p for p in s.split(".") if p]
    if len(parts) == 3:
        # detect YYYY.MM.DD vs DD.MM.YYYY
        if len(parts[0]) == 4:
            y, m, d = parts[0], parts[1], parts[2]
        else:
            d, m, y = parts[0], parts[1], parts[2]
        raw = f"{d}{m}{y}"
    else:
        raw = re.sub(r"\D", "", s)

    if len(raw) < 8:
        # fallback: digit sum of whatever provided
        return reduce_num(digitsum(int(raw or "0")))

    total = sum(int(ch) for ch in raw if ch.isdigit())
    return reduce_num(total)

def archetype_for(n: int) -> str:
    # basit, genişletilebilir
    table = {
        1: "Başlatan / Lider",
        2: "Yansıtıcı / Aracı",
        3: "Yaratıcı / İfade",
        4: "Yapı Kurucu / Düzen",
        5: "Gezgin / İletişim",
        6: "Şifacı / Sorumluluk",
        7: "Bilge / Araştırmacı",
        8: "Güç / Yönetim",
        9: "Tamamlayıcı / Hizmet",
        11: "Uyanış / İlham",
        22: "Usta İnşa / Büyük Sistem",
        33: "Usta Şifa / Rehber",
    }
    return table.get(n, "Arketip")

def role_sentence(name_n: int, path_n: int) -> str:
    # rol cümlesi: deterministik ve kısa
    if name_n == 2 or path_n == 2:
        return "Sistemde köprü rolü: ikilikleri birleştirip anlamı yansıtmak."
    if name_n == 4 or path_n == 4:
        return "Sistemde yapı kurucu rolü: düzen kurmak ve sağlamlaştırmak."
    if name_n == 6 or path_n == 6:
        return "Sistemde şifa/hizmet rolü: dengelemek, onarmak, sorumluluk almak."
    if name_n == 9 or path_n == 9:
        return "Sistemde tamamlayıcı rolü: kapanış açmak, kolektife hizmet etmek."
    if path_n in (11, 22, 33) or name_n in (11, 22, 33):
        return "Sistemde master rol: büyük ölçekli uyanış/kurulum/rehberlik frekansı."
    return "Sistemde ayna rolü: farkındalık açmak ve yön göstermek."

def analyze_matrix_role(name: str, birth_date: str) -> Dict[str, Any]:
    norm = normalize_name(name)
    n_num = name_number(norm)
    p_num = birth_path(birth_date)

    return {
        "name_normalized": norm,
        "name_number": n_num,
        "life_path": p_num,
        "name_archetype": archetype_for(n_num),
        "life_path_archetype": archetype_for(p_num),
        "matrix_role": role_sentence(n_num, p_num),
        "note": "Bu modül deterministiktir (LLM kullanmaz). İstersen bir sonraki aşamada 'yorum katmanı' ekleriz."
    }