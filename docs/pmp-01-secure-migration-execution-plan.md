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

### Official status snapshot

| Item | Status |
|---|---|
| PMP-01A | `BLOCKED` |
| Blocker | `VERIFIED_LEGACY_IDENTITY_SOURCE_MISSING` |
| Release gate | `CLOSED` |
| Automatic linking | `DISABLED` |
| Manual recovery | `POLICY_DEFINED / NOT_OPERATIONAL` |
| Web event contract | `NOT_VERIFIABLE` |
| Legacy reachable UX | `UNSAFE_FOR_RELEASE` |
| PMP-01B | `NOT_STARTED` |

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

## Legacy Identity Trust Model assessment

Mevcut legacy sistemde üç ayrı identity davranışı görülmektedir:

1. Canonical V1 Supabase JWT `sub` UUID’si server-side doğrulanabilir.
2. Legacy HS256 token üretimi tarihsel olarak mevcut olsa da decoder
   fail-closed durumdadır; aktif legacy session verifier yoktur.
3. Bazı legacy yollar hâlâ client-controlled `user_id`, `X-User-Id`,
   `device_fp` veya default session sinyallerini kabul etmektedir.

İncelenen kritik örnekler:

- `app/routes/events.py`: payload/header user identity ve
  `mobile-default` session kabul ediyor.
- `app/routes/activity.py`: auth guard olmadan integer `user_id` ile memory
  okuma/yazma yapıyor.
- `app/routes/device.py`: client-provided integer `user_id` ile user kaydı
  güncelliyor.
- `app/services/auth.py`: legacy token decoder bilinçli olarak `None`
  döndürüyor.
- `app/application/identity_linking.py`: yalnızca dry-run contract’ı;
  public route veya production write yok.
- `docs/sprint-3.2b-manual-recovery-governance.md`: manual recovery politikası
  mevcut, fakat execution workflow ve reviewer assertion store kodda yok.

### Trust model decision

Mevcut kanıta göre:

- **Server-side legacy verification:** bugün mevcut değil.
- **Manual-recovery-only:** mevcut governance ile uyumlu ve savunulabilir.
- **Automatic linking:** verified legacy proof ve uncontained client identity
  yolları nedeniyle iptal edilmiş olarak kalmalı.

Email, display name, device, IP, fingerprint, default session, client
`legacy_user_id` veya unsigned/custom token hiçbir şekilde identity proof
sayılmaz. `PMP-01A-BLK-001` bu nedenle implementasyon eksikliği değil, trust
model blocker’ıdır.

Bu bulgu aynı zamanda `events.py`, `activity.py`, `device.py` ve benzeri
legacy yolların identity/ownership kararlarında fail-closed yapılması veya
canonical doğrulama arkasına alınması gerektiğini gösterir. Bu containment
tamamlanmadan otomatik linking veya PMP-01B başlatılamaz.

## PMP-01A containment evidence / REP input

**Evidence status:** Prepared — containment review  
**Scope:** Untrusted legacy identity signal containment  
**Production migration:** Not enabled  
**Identity linking:** Not enabled  
**Rollout:** 0%

### Verification results

| Check | Result | Evidence |
|---|---|---|
| Backend full test suite | PASS — 83 passed, 6 skipped | `python -m pytest -q` |
| Targeted identity tests | PASS — included in full suite | `tests/test_legacy_identity_containment.py`, `tests/test_sprint32a_identity.py` |
| Mobile TypeScript | PASS | `npx tsc --noEmit` |
| Changed mobile files lint | PASS | `npx eslint lib/analytics.ts lib/LogEvent.ts lib/eventSession.ts` |
| Full mobile lint | BLOCKED by baseline | 16 errors, 34 warnings in unrelated existing files |
| Web event source audit | NOT VERIFIABLE | Source tree is not present in the inspected web checkout |

### Known warning

The backend suite emits one `PendingDeprecationWarning` from Starlette
`formparsers.py` because the installed compatibility import uses `multipart`
and recommends `python_multipart`. It is dependency-level, does not originate
in the containment files, and does not fail the suite. It remains a deferred
dependency maintenance item.

### Client contract verification

Mobile event consumers no longer send `user_id` or `X-User-Id`. They use the
Supabase access token and a persisted UUID event session from
`lib/eventSession.ts`. Legacy `mobile-default` event sessions are not sent.
Unauthenticated event ingestion fails closed and is handled as an offline
analytics failure.

The web source checkout could not be independently verified because it
contains built/runtime artifacts but no inspectable application source tree.
This is a remaining verification gap, not evidence that web usage is safe.

### Open risks retained for production

These are integration and UX risks. They do not block committing the
containment change, but they must remain open in REP and be resolved before
any release gate opens:

1. **Mobile lint baseline** — Full mobile lint still reports pre-existing
   errors/warnings unrelated to the containment files. Tracked separately;
   must not grow with new changes.
2. **Web event consumer unverified** — See assessment below. Release gate
   remains closed until the web source is available and audited.
3. **Legacy shared-session UX breakage** — See impact matrix below. Release
   gate remains closed until affected surfaces are migrated, disabled, or
   given a verified user-facing fallback.

### Risk assessment — legacy shared-session UX

Shared session IDs are not an event-ingestion-only problem. Multiple mobile
surfaces still call fail-closed legacy chat (`/bilinc-alani/ask`) with
shared or static `session_id` values.

| Surface | Session signal | Endpoint | User impact | Status |
|---|---|---|---|---|
| `sanri_flow.tsx` | `mobile-default` | `/bilinc-alani/ask` | Chat fails with canonical-identity required | REACHABLE via gates/city/my_area |
| `observer.tsx` | `mobile-default` | `/bilinc-alani/ask` | Same failure | Hidden from tab bar (`href: null`) |
| `pattern.tsx` | `mobile-default` | `/bilinc-alani/ask` | Same failure | Hidden from tab bar |
| `symbol.tsx` | `mobile-default` | `/bilinc-alani/ask` | Same failure | Hidden from tab bar |
| `lib/api.ts` `askSanri` | default `"mobile"` | `/bilinc-alani/ask` | Same failure for callers | Shared helper |
| `daily_stream.tsx` | `daily-stream-mobile` | `/bilinc-alani/ask` | Same failure | Active surface |
| `kod_ders.tsx` | `mobile-kod-okuma` | `/bilinc-alani/ask` | Same failure | Active surface |
| `rituals/live.tsx` | `"mobile"` | `/bilinc-alani/ask` | Same failure | Active surface |
| `my_area`, `world_events`, `okuma_detail`, `matrix_mini`, `global-signal` | various | `/bilinc-alani/ask` | Same failure | Active surfaces |
| Event analytics (`LogEvent` / `analytics`) | UUID + Supabase JWT | `/events/log` | Contained | CLOSED for this risk |

Verdict: changing only the string `"mobile-default"` does not restore these
screens. The trust boundary is correct — legacy chat is fail-closed — but
product surfaces still route users into that dead end. Before any release
gate opens, every reachable legacy ask surface must either:

- migrate to authenticated V1 chat, or
- be removed/hidden from navigation, or
- show an explicit, non-spoofable “canonical auth required” product state.

### Risk assessment — web event consumer

Inspected checkout `asksanri-frontend` currently contains:

- `dist/`, `dev-dist/`, `.vite/`, `node_modules/`, `public/`, `.env`
- no `package.json`
- no application `src/` tree

Search for `events/log`, `X-User-Id`, and `mobile-default` in non-build
paths returned no matches. This is **not** evidence that web is safe; it is
evidence that web source of truth is not present for audit.

Verdict: web event consumer status = `NOT VERIFIABLE`. Release gate remains
closed until an inspectable web source tree is restored and proven to:

- omit client-controlled `user_id` / `X-User-Id`,
- send Supabase JWT for authenticated event ingestion,
- never use shared/default session identifiers as identity.

### Manual-recovery-only executability assessment

Governance document:

- `docs/sprint-3.2b-manual-recovery-governance.md`

What exists:

- policy for acceptable/prohibited evidence,
- four-eyes approval rule,
- idempotency and revocation intent,
- dry-run identity link contracts (`app/application/identity_linking.py`),
- empty identity-link / migration-audit schema models.

What does **not** exist in executable code:

- reviewer case create/approve/reject APIs,
- signed reviewer assertion store with policy version, evidence reference,
  reviewer identity, and expiry,
- four-eyes enforcement in a transaction,
- user-visible recovery confirmation UI,
- server channel that can independently verify a legacy session,
- operational audit trail for recovery decisions.

Verdict: **manual-recovery-only is the correct strategy, but it is not yet
operationally executable.** Choosing this strategy is a security decision,
not a completed capability. Until the execution gap above is closed,
recovery must remain a documented exception path that cannot mint
`verified`/`linked` identity states through automation.

This assessment does **not** resolve `PMP-01A-BLK-001`. It confirms that
forcing automatic linking would recreate unsafe trust, and that the safer
path is manual-recovery-only once it becomes executable.

### Release gate rule for these risks

No Alpha, Beta, RC, or production release gate may open while any of the
following remain true:

- reachable mobile surfaces still call fail-closed legacy ask without a
  verified product fallback,
- web event consumer is `NOT VERIFIABLE`,
- manual recovery is policy-only and cannot produce audited recovery
  decisions without ad-hoc database edits.

### REP decision

This evidence is suitable as a draft REP input for the containment change.
It does not resolve `PMP-01A-BLK-001`, authorize identity linking, authorize
migration, or authorize rollout. The blocker remains `BLOCKED` until all
resolution criteria are met. Commit is allowed for containment evidence;
release and rollout remain forbidden.

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
