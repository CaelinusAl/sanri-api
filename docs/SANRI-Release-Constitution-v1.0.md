# SANRI Release Constitution v1.0

**Status:** Operational  
**Applies to:** SANRI OS, AURA, mobile, web, backend, database, migrations,
AI behavior, infrastructure, and operational configuration  
**Authority:** This constitution overrides release pressure, informal approval,
and undocumented exceptions.

## Constitutional Metadata

```text
Authority Level: Level 2 — Governance
Owner: SANRI Release Council
Source of Truth: SANRI Release Constitution
Supersedes: Informal release approvals and undocumented launch exceptions
Depends On: SANRI Constitutional Architecture, Governance Framework
Referenced ADRs: ADR-016
Related Standards: SDS, SLS, Security & Trust Standard, REP
Lifecycle State: Operational
Last Reviewed: 2026-07-18
```

## Article 0 — The User Trust Principle

Hiçbir sürüm, kullanıcı güvenini azaltacak bilinen veya kanıtlanmamış bir riski
kabul ederek yayımlanamaz.

Yeni özellikler ertelenebilir. Pazarlama tarihi değişebilir. Yatırımcı
beklentileri ertelenebilir. Kullanıcı güveni ertelenemez.

Bu madde Release Constitution’ın diğer bütün maddelerini yönetir. Bir karar
kullanıcı güveni ile çelişiyorsa daha düşük maliyetli, daha yavaş veya daha
dar kapsamlı seçenek uygulanır; risk kullanıcıya devredilmez.

## Bir sürümün yayımlanmasına kim izin verir?

Yalnızca **SANRI Release Council**, bu belgede tanımlanan kanıtlar eksiksiz
olduğunda yayıma izin verir.

Release Council şu sorumluluklardan oluşur:

- **Release Owner:** kapsamı, kanıt paketini ve rollback hazırlığını koordine
  eder.
- **Security Authority:** güvenlik açıkları, secret yönetimi, RLS ve veri
  izolasyonu üzerinde veto yetkisine sahiptir.
- **Identity Authority:** kimlik doğrulama, ownership, session isolation ve
  authorization üzerinde veto yetkisine sahiptir.
- **AI Quality Authority:** model davranışı, memory consent, prompt injection,
  Golden Corpus ve AI Quality Gate üzerinde veto yetkisine sahiptir.
- **Product Authority:** kullanıcı deneyimi, kullanıcıya verilen sözler ve
  güven kaybı riski üzerinde veto yetkisine sahiptir.
- **Architecture Authority:** ADR, domain sınırları, migration ve
  compatibility kararları üzerinde veto yetkisine sahiptir.
- **Operations Authority:** rollback, observability, incident hazırlığı,
  deployment ve kill-switch üzerinde veto yetkisine sahiptir.

**Release Owner** koordinasyon rolüdür; release veto yetkisi yoktur.

Bir kişi birden fazla sorumluluk taşıyabilir; ancak Security, Identity,
Architecture ve Operations veto alanlarının tamamı aynı kişi tarafından
kullanılamaz.

## Council veto kuralı

Her Council üyesi kendi sorumluluk alanında bağımsız veto hakkına sahiptir.
Veto bir kişisel tercih değil, REP içinde kanıtlanmış bir risk kaydıdır.

- Veto gerekçesi açıkça yazılır.
- Gerekçenin ilgili kanıtı REP’e eklenir.
- Gerekçe kapanmadan release `RELEASED` durumuna geçemez.
- Veto yalnızca aynı yetki alanındaki kanıtla kaldırılabilir.
- Veto sahibinin fikrini değiştirmesi tek başına kapanış kanıtı değildir.
- Release Council, veto kapatılmadan kapsamı daraltabilir veya sürümü
  erteleyebilir; veto kuralını bypass edemez.

## 1. Anayasal ilkeler

1. **Kanıt olmadan yayımlama yoktur.** Sözlü onay, niyet, demo veya zaman
   baskısı kanıt yerine geçmez.
2. **Güvenlik veto edebilir.** Security Authority bir P0 veya kanıtlanmamış
   kimlik/RLS riski gördüğünde yayımlamayı durdurur.
3. **Rollback yayımdan önce gelir.** Geri dönüş yolu doğrulanmamış bir sürüm
   release adayı değildir.
4. **ADR mimari hafızadır.** ADR ile çelişen değişiklik yeni ADR olmadan
   yayımlanamaz.
5. **Üretim trafiği ayrı bir karardır.** Bir build’in hazır olması, V1 veya
   başka bir özelliğin production trafiğine açıldığı anlamına gelmez.
6. **Kişi değil rol karar verir.** Kurucu, geliştirici, müşteri veya model tek
   başına bu anayasayı geçersiz kılamaz.
7. **İstisna kayıt altına alınır.** Her istisna sahibi, süresi, riski,
   telafisi ve kapanış tarihiyle release kaydında bulunur.
8. **Principle of Least Surprise.** Yeni model, provider veya özellik,
   kullanıcıların güven duyduğu memory, consent, identity, ownership, session
   veya AURA davranışını açıklanmadan değiştiremez.

## 2. Release Train

Release Train, sprint tamamlanma duygusu yerine kanıtlanabilir ürün
olgunluğunu takip eder. Her release bir sonrakinin önkoşullarını taşır.

### Release Alpha — Foundation

Kapsam:

- Identity
- Supabase Auth
- Memory consent
- Prompt architecture
- AURA persona
- Session state
- Conversation continuity
- Domain/Application/Infrastructure sınırları
- Legacy containment

Alpha çıkış kapıları:

- Canonical Supabase UUID doğrulanmış olmalı.
- Legacy kimlik yolları fail-closed veya onaylı adapter arkasında olmalı.
- Memory consent ihlali bulunmamalı.
- Ownership matrix tamamlanmış olmalı.
- Migration yalnızca dry-run seviyesinde olmalı.
- V1 production traffic yüzde sıfırda kalmalı.

### Release Beta — Migration Readiness

Kapsam:

- Verified migration design
- Teams
- Knowledge
- Projects
- Context Engine
- Legacy/V1 parity
- Read-only migration assessment
- RLS integration tests

Beta çıkış kapıları:

- Gerçek izole Supabase kullanıcılarıyla cross-user testleri geçmiş olmalı.
- Linkable candidate, conflict, duplicate ve orphan raporları üretilmiş
  olmalı.
- Hiçbir otomatik identity link oluşturulmamalı.
- Service-role işlemleri ayrıştırılmış ve audit edilmiş olmalı.
- Rollout yüzdesi hâlâ sıfır olmalı.

### Release RC — Quality and Operations

Kapsam:

- AI Quality Gate
- Golden Corpus
- Load Tests
- Security Audit
- Performance
- Observability
- Rollback rehearsal
- Incident and kill-switch verification

RC çıkış kapıları:

- Golden Corpus beklenen davranış ve yasaklı davranış sonuçlarıyla
  raporlanmış olmalı.
- Streaming, provider failure, token cost ve latency eşikleri ölçülmüş
  olmalı.
- Rollback gerçek bir rehearsal ile doğrulanmış olmalı.
- P0/P1 güvenlik bulguları kapatılmış veya yayımlamayı bloke etmiş olmalı.

### Release 1.0 — First Real Users

Release 1.0 yalnızca Alpha, Beta ve RC kapılarının tamamı geçtikten sonra
ve Release Council oybirliğiyle onay verdikten sonra açılabilir.

İlk kullanıcı cohort’u:

- açıkça tanımlı,
- geri alınabilir,
- gözlemlenebilir,
- destek ve incident prosedürü hazır,
- veri kaybı ve kimlik karışması açısından sınanmış

olmalıdır.

## 3. Mutlak release blocker’ları

Aşağıdaki maddelerden biri mevcutsa release durumu **BLOCKED** olur:

- P0 güvenlik açığı.
- Kimlik doğrulama belirsizliği.
- Canonical UUID dışında ownership kararı.
- `X-User-Id`, device ID, email equality, display name, IP, default session
  veya latest-user fallback’i.
- Memory consent ihlali veya proposed memory’nin prompt’a sızması.
- Cross-user read, write, update, delete veya association testi başarısızlığı.
- RLS’in nested relation veya foreign-key üzerinden aşılabilmesi.
- AI Quality Gate başarısızlığı.
- Golden Corpus’ta kritik regresyon.
- Doğrulanmamış rollback.
- Şema değişikliğinde geri dönüş planı olmaması.
- ADR’lerle çelişen ve onaylanmamış mimari değişiklik.
- Loglarda secret, token, parola veya kullanıcı içeriğinin uygunsuz bulunması.
- Güncel olmayan migration, ownership matrix veya runbook.
- V1 rollout yüzdesinin release kararına aykırı artırılması.
- Principle of Least Surprise ihlali.

Hiçbir product deadline, müşteri beklentisi, demo, yatırım görüşmesi veya
kurucu talimatı bu blocker’ları geçersiz kılamaz.

## 4. Release kanıt paketi

Release Owner aşağıdaki tekil kanıt paketini oluşturur:

- sürüm kapsamı ve değişen dosyalar,
- commit ve build bilgisi,
- backend test sonuçları,
- mobile type-check/lint/test sonuçları,
- web build/lint/test sonuçları,
- auth ve token lifecycle kanıtı,
- live RLS test raporu,
- ownership matrix diff’i,
- memory consent test raporu,
- AI Quality Gate sonucu,
- Golden Corpus scorecard,
- load/performance raporu,
- security audit sonucu,
- migration/dry-run raporu,
- rollback rehearsal kaydı,
- observability ve kill-switch doğrulaması,
- bilinen riskler ve kabul sahipleri.

Kanıt paketi `releases/<version>/` altında arşivlenir ve en az `release-notes`,
`REP`, security, AI quality, performance, rollback, migration ve
`council-approval` artefact’larını içerir.

Kanıt paketi eksikse release `READY` durumuna geçemez.

## 5. Karar durumları

- **DRAFT:** kapsam hazırlanıyor.
- **IN REVIEW:** kanıt paketi inceleniyor.
- **BLOCKED:** en az bir mutlak blocker mevcut.
- **READY:** zorunlu kanıtlar tamam, blocker yok.
- **APPROVED:** Release Council gerekli onayları verdi.
- **RELEASED:** sürüm kontrollü biçimde yayımlandı.
- **ROLLED BACK:** rollback uygulandı; incident incelemesi zorunlu.

`READY` ve `APPROVED` aynı durum değildir. Release Council kararı olmadan
otomatik CI/CD süreci production yayımlaması yapamaz.

## 6. Rollback ve sonrası

Yayımdan sonra:

- telemetry ve error budget izlenir,
- cohort genişletme ayrı bir karar olarak kaydedilir,
- kritik alarm otomatik stop condition oluşturur,
- rollback kararı için yeni bir onay beklenmez,
- veri kaybı veya identity incident’ı varsa trafik derhal durdurulur,
- post-release review ve ADR güncellemesi yapılır.

Rollback sonrası yeniden yayımlama yeni bir release adayıdır; eski onay
otomatik olarak geçerli sayılmaz.

## 7. Yürürlük

Bu anayasa yürürlüğe girdiği andan itibaren SANRI Release Train’in temel
kontrol belgesidir. Yeni release türü, yeni production cohort’u veya
release gate değişikliği bu belgeye eklenmeden uygulanamaz.
