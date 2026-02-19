def postprocess(self, raw: str, req: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    ci = ctx.get("city_info")
    plate = ctx.get("plate") or ""
    if not ci:
        return {
            "module": "awakened_cities",
            "title": "Uyanmış Şehirler",
            "answer": "Plaka bulunamadı. Örnek: 34, 06, 35…",
            "sections": [
                {"label": "Nasıl Kullanılır", "text": "Sadece 2 haneli plaka yaz: 34 / 06 / 35 …"}
            ],
            "tags": ["awakened_cities"]
        }

    # ✅ Şehir haritasından “yolculuk” üret
    city = ci["city"]
    archetype = ci.get("archetype", "")
    shadow = ", ".join(ci.get("shadow", []))
    light = ", ".join(ci.get("light", []))

    journey = [
        {"label": "Kapı", "text": f"{city} ({plate}) — {archetype}"},
        {"label": "Mesaj", "text": f"{city} seni merkeze çağırır: odağını topla, dağılmış parçaları tek bir niyette birleştir."},
        {"label": "Gölge", "text": f"Bu şehirde gölge: {shadow}. Gürültü/dağılma varsa bu bir işarettir: enerjin parçalanıyordur."},
        {"label": "Işık", "text": f"Işık: {light}. Bağ kur, yön belirle, ritmini kur."},
        {"label": "Rota", "text": "1) Bugün tek bir niyet seç. 2) 24 saat boyunca onu koru. 3) Dağıtan şeyi kes."},
        {"label": "Ritüel", "text": "• 3 nefes (burun) \n• 1 cümle niyet \n• 9 dakika sessizlik \n• ardından tek bir eylem"},
        {"label": "Sembol", "text": "Şehrin sembolü sende bugün: 'kapı' — bir eşikten geçiyorsun."}
    ]

    answer = journey[1]["text"]

    return {
        "module": "awakened_cities",
        "title": f"{city} / {plate}",
        "answer": answer,
        "sections": journey,
        "tags": ["awakened_cities", plate, city],
    }
