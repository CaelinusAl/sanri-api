# PMP-01 Secure Migration Execution Plan

**Status:** Planned — pre-implementation  
**Program:** SANRI Product Maturation Program  
**Owner:** PMP-01.0 Program Governance  
**Governance:** SCA v1.0, SDS, SLS, Release Constitution  
**Product KPI:** Measured User Value (MUV)  
**Technical confidence view:** Migration Confidence Score (MCS)  

## Current execution status

**PMP-01A status:** `BLOCKED`  
**Blocker:** `VERIFIED_LEGACY_IDENTITY_SOURCE_MISSING`  
**Security impact:** Cross-user association and account takeover risk

### Blocker metadata

| Field | Value |
|---|---|
| Blocker ID | `PMP-01A-BLK-001` |
| Title | Verified Legacy Identity Source Missing |
| Severity | Critical |
| Category | Identity / Security |
| Introduced | PMP-01A |
| Blocks | PMP-01B, PMP-01C, Context Engine, Project Engine, Production Migration |
| Owner | PMP-01 Program |

### Resolution criteria

`PMP-01A-BLK-001` yalnızca aşağıdaki koşulların tamamı sağlandığında
`RESOLVED` olarak işaretlenebilir:

- server-side verified legacy identity source exists,
- client-controlled identity hiçbir akışta authoritative değil,
- manual recovery policy execution akışına entegre,
- ilgili security tests geçer,
- approval, revoke ve audit implementasyonu doğrulanır,
- Release Council blocker resolution’ı kabul eder.

Blocker çözüm kararı ilgili REP ve Governance Health Check kayıtlarına
eklenmeden PMP-01B veya PMP-01C başlatılamaz.

Güvenilir server-side legacy identity proof olmadan `legacy_user_id` client
payload’ından alınamaz ve linking authority olarak kullanılamaz. Bu blocker,
eksik bir endpoint implementasyonu değil, identity proof eksikliğidir.

### Allowed work while blocked

- verified legacy identity source seçeneklerinin teknik incelemesi,
- schema hardening,
- transaction ve state model tasarımı,
- manual recovery assertion contract’ı,
- audit contract’ı,
- negatif güvenlik testlerinin hazırlanması,
- concurrency ve rollback test harness’i.

### Forbidden work while blocked

- public linking endpoint aktivasyonu,
- migration execution,
- otomatik identity linking,
- client-controlled identity ile authorization,
- Context Engine veya Project Engine’e geçiş,
- production rollout veya user-data write.

## 1. Program objective

PMP-01’in amacı migration yapmak değildir. Amaç; SANRI’nın kullanıcı verisini
kaybetmeden, yanlış kullanıcıya bağlamadan, consent kurallarını bozmadan ve
rollback yapılabilir biçimde migration yapabildiğini kanıtlamaktır.

Bu plan production user-data migration başlatmaz, otomatik identity link
oluşturmaz ve rollout yüzdesini değiştirmez. İlk uygulama izole ortam,
anonim/sentetik fixture ve dry-run/rehearsal ile sınırlıdır.

## 2. Program governance — PMP-01.0

PMP-01.0 aşağıdaki karar ve kanıt akışını yönetir:

| Alan | Zorunlu cevap |
|---|---|
| Problem | Bu paket hangi gerçek kullanıcı problemini veya güvenlik riskini çözüyor? |
| Evidence | Başarıyı hangi teknik ve ürün metrikleri gösterecek? |
| Exit | Paket hangi objektif kriterlerle tamamlanmış sayılacak? |
| Dependencies | Hangi paketler veya altyapılar önce tamamlanmalı? |
| Risks | Başarısızlık hangi veri, güvenlik veya operasyon etkisini doğurur? |
| Rollback | Paket geri alınabilir mi; geri dönüş kanıtı nedir? |
| MUV impact | Kullanıcıya ölçülebilir değer nasıl sağlanıyor veya korunuyor? |
| REP | Hangi kanıt release evidence paketine girecek? |

PMP-01.0 hiçbir paketi yalnızca niyet veya kod tamamlanmasına dayanarak
`DONE` ilan edemez.

PMP-01A, verified legacy identity source server tarafından doğrulanana ve
negatif güvenlik testleri geçene kadar `BLOCKED` kalır. Bu durum aşağıdaki
paketlere devredilerek veya endpoint açılarak atlanamaz.

## 3. Dependency map

Ana bağımlılık akışı:

```text
PMP-01A Identity Linking
          │
          ▼
PMP-01B Migration Engine ─────┐
          │                    │
          ▼                    ▼
PMP-01C Resource Migration → PMP-01D Verification
                                      │
                                      ▼
                              PMP-01E Rollback
                                      │
                                      ▼
                              PMP-01F Dashboard
```

Bağımlılık kuralları:

- 01D, 01B ve 01C ile birlikte tasarlanır; sonradan eklenen bir kontrol
  katmanı olamaz.
- 01E, migration executor ile aynı snapshot, lineage ve state modelini
  paylaşır.
- 01F’nin dashboard ekranı en son görünür olabilir; ancak telemetry,
  counters, audit events ve stop-condition sinyalleri ilk günden üretilir.
- 01B, 01C ve 01D için deterministic fixture ve test contract’ları 01.0
  tarafından önceden onaylanır.

## 4. Work packages

### PMP-01A — Identity Linking Execution

**Problem:** Legacy ve Supabase kimlikleri yalnızca tasarım seviyesinde
tanımlı; doğrulanmış, kullanıcı onaylı ve denetlenebilir link execution akışı
eksik.

**Scope:**

- verified legacy session ve Supabase session doğrulaması,
- server-side conflict ve duplicate checks,
- user-visible approval ve conflict decision contract’ları,
- idempotent link transaction,
- revoke ve audit kayıtları.

**Exit:**

- email, display name veya device ID ile otomatik link yok,
- duplicate ve conflict testleri geçer,
- approval olmadan link oluşmaz,
- revoke davranışı doğrulanır,
- audit evidence üretilir.

PMP-01A’nın implementation’a geçiş önkoşulları:

- server-side verified legacy identity source seçildi ve doğrulandı,
- reviewer assertion serbest metin veya doğrudan DB müdahalesi değil, policy
  version, evidence reference, reviewer identity ve expiry içeren imzalı/
  denetlenebilir bir karar modeline bağlandı,
- approval, conflict detection, link creation, revoke state ve audit tek
  atomic transaction sınırında tanımlandı,
- audit yazılamadığında link creation’ın rollback olduğu kanıtlandı.

### PMP-01B — Migration Engine

**Problem:** Resolver’dan executor’a kadar idempotent, tekrar çalıştırılabilir
ve durdurulabilir bir migration pipeline yok.

**Pipeline:**

`Resolver → Validator → Planner → Dry Run → Executor → Verifier → Rollback`

**Exit:**

- aynı input tekrar çalıştırıldığında duplicate üretmez,
- plan ve executor deterministiktir,
- her record source identifier ve lineage taşır,
- failure state ve resume noktası kaydedilir,
- production yazımı kapalı testte pipeline rehearsal geçer.

### PMP-01C — Resource Migration

**Problem:** Kullanıcı migration’ı resource ownership ve consent ayrıntılarını
tek başına garanti etmez.

**Strategies:**

- profile,
- memory,
- conversations ve messages,
- projects,
- tasks,
- subscriptions/payments,
- insights.

Her resource stratejisi owner alanını, ilişki doğrulamasını, duplicate
politikasını, consent politikasını, source lineage’ı ve rollback davranışını
ayrı belirtir. Legacy automatic memory kayıtları approved/live olarak
aktarılmaz; reviewable candidate veya `proposed` olarak kalır.

**Exit:**

- her resource için strategy contract mevcut,
- cross-user association reddedilir,
- ownership ve consent parity doğrulanır,
- orphan ve conflict kayıtları migration’ı sessizce geçemez.

### PMP-01D — Verification Engine

**Problem:** Executor’ın “başarılı” sonucu bağımsız doğrulama olmadan güvenilir
kanıt değildir.

**Checks:**

- conversation count,
- message count,
- memory count ve approval state,
- project/task count,
- deterministic hashes,
- ownership parity,
- consent parity,
- orphan/conflict count,
- lineage completeness,
- idempotency consistency.

**Exit:**

- 100% verification pass,
- 0 data loss,
- 0 cross-user association,
- 0 consent violation,
- tüm farklar açıklanmış veya migration `FAIL` olmuştur.

`PASS` migration complete için zorunludur. `FAIL`, rollback değerlendirmesini
otomatik olarak başlatır.

### PMP-01E — Rollback Engine

**Problem:** Rollback şu anda yalnızca runbook seviyesinde; migration state’i,
snapshot’ı ve restore doğrulaması kodla güvence altında değil.

**Flow:**

`Migration → Snapshot → Restore → Verify → Close`

**Exit:**

- snapshot ve migration state aynı lineage ile ilişkilidir,
- partial failure sonrasında restore deterministiktir,
- restore sonrası verification geçer,
- rollback V1-created data’yı sessizce silmez,
- rehearsal kanıtı REP’e eklenir.

### PMP-01F — Migration Dashboard

**Problem:** Kontrollü migration operasyonu için merkezi ve gözlemlenebilir
durum görünümü eksik.

**Minimum view:**

- users,
- migrated,
- pending,
- failed,
- conflict,
- rollback,
- verification,
- ETA.

Dashboard son kullanıcı ürünü olarak değil, migration operator surface olarak
başlar. İlk günden itibaren dashboard’ın besleyeceği telemetry ve audit
events üretilir.

**Exit:**

- counters source-of-truth state ile tutarlı,
- failed/conflict/rollback durumları görünür,
- sensitive user content dashboard veya loglara yazılmaz,
- stop condition sinyalleri gözlemlenebilir.

## 5. Standard work-package Definition of Done

Her PMP-01 iş paketi için:

- Problem kaydı tamamlandı.
- Evidence üretildi ve owner’ı belli.
- Exit kriterleri objektif olarak sağlandı.
- İlgili unit/integration/security testleri geçti.
- Observability ve audit events eklendi.
- Rollback etkisi değerlendirildi ve uygunsa rehearsal yapıldı.
- MUV etkisi değerlendirildi.
- REP’e girecek evidence artefact’ı hazırlandı.
- Açık riskler, blocker’lar ve residual riskler kaydedildi.

## 6. Migration Confidence Score (MCS)

MCS, tek başına release approval veren bir skor değildir; PMP-01 güven
durumunu görünür kılan bir evidence panelidir.

MCS bileşenleri:

- verification pass rate,
- hash parity,
- ownership parity,
- consent parity,
- rollback success,
- idempotency success,
- dry-run consistency.

Her bileşen ayrı raporlanır. Bir bileşenin kritik başarısızlığı toplam skor
yüksek görünse bile PMP-01 exit’ini bloke eder. MCS raporu sample, period,
fixture version, method, result ve uncertainty alanlarını içerir.

## 7. Program-level Problem–Evidence–Exit

### Problem

Legacy kullanıcı verisini güvenli, doğru sahiplikle ve geri alınabilir biçimde
taşıyabildiğimiz henüz kanıtlanmış değildir.

PMP-01A özelinde daha temel problem, legacy identity’nin server tarafından
bağımsız biçimde kanıtlanamamasıdır.

### Evidence

- migration rehearsal’da %100 verification pass,
- 0 cross-user association,
- 0 consent violation,
- 0 data loss,
- hash, ownership ve consent parity,
- rollback `PASS`,
- idempotency `PASS`,
- dry-run ve execution consistency,
- tamamlanmış work-package REP girdileri.

PMP-01A için ek negatif test kanıtı:

- sahte `legacy_user_id`,
- başka kullanıcıya ait evidence,
- tekrar kullanılan approval,
- revoked link,
- conflict,
- yarış koşulu,
- eksik audit,
- transaction rollback.

### Exit

PMP-01 yalnızca aşağıdaki koşulların tamamı sağlandığında `DONE` olur:

- 01A–01F exit kriterleri tamamlandı,
- tüm kritik P0/P1 riskler kapatıldı veya release blocker olarak kaldı,
- Release Council kanıtları inceledi,
- gerekli Governance Health Check uygulandı,
- production migration için ayrı ve açık bir release kararı alındı.

PMP-01 `DONE`, production migration’ın otomatik olarak başlatıldığı anlamına
gelmez; yalnızca güvenli migration capability’sinin kanıtlandığı anlamına
gelir.

PMP-01A ayrıca şu koşulları birlikte kanıtlamadan `DONE` olamaz:

- client-controlled identity hiçbir akışta authority değil,
- her link verified server-side evidence’a dayanıyor,
- bir legacy identity yalnızca izin verilen canonical identity ile eşleşiyor,
- conflict durumları otomatik çözülmüyor,
- revoke sonrası link tekrar kullanılamıyor,
- tüm state değişiklikleri eksiksiz audit ediliyor,
- belirsiz ve yetkisiz durumlar fail-closed sonuçlanıyor.
