# SANRI Product Maturation Program (PMP)

**Program status:** Active — Execution Planning  
**Program type:** Operational product maturation  
**Governance source:** SANRI Constitutional Architecture v1.0  
**Decision source:** SANRI Decision Standard  
**Release source:** SANRI Release Constitution  

PMP, SANRI’nın anayasal ve governance tasarımından ürün olgunlaştırma
uygulamasına geçiş programıdır. Yeni anayasal belge üretmez ve SCA’yı
genişletmez.

## SANRI Foundation Baseline (SFB) v1.0

**Baseline status:** Established  
**Baseline type:** Operational reference milestone  
**Baseline date:** 2026-07-18  

SFB v1.0, SANRI’nın kurumsal temelinin tamamlandığı referans noktasıdır:

- Architecture Program tamamlandı.
- Unification Program tamamlandı.
- Governance Program tamamlandı.
- Product Maturation Program başlatıldı.
- SCA v1.0 `Accepted & Frozen`.

Bu baseline yeni bir anayasal belge değildir, SCA’yı değiştirmez ve yeni bir
governance katmanı oluşturmaz. Bundan sonraki ürün geliştirme ve release
kararları bu baseline üzerine inşa edilir.

## PMP focus rule

SANRI Product Era’nın varsayılan sorusu şudur:

> Bu, PMP’deki hangi hedefi ilerletiyor?

Her ürün, engineering veya operasyon işi en az bir PMP workstream’i ve
ölçülebilir bir beklenen sonuçla ilişkilendirilir. Bir iş PMP hedefini,
güvenlik/reliability zorunluluğunu veya mevcut bir release blocker’ını
ilerletmiyorsa öncelikli çalışma olarak başlatılmaz.

## Product Era review role

Product Era’da kurucu ve ürün gözden geçirme rolünün önceliği yeni anayasal
yapılar önermek değil, mevcut sistemin gerçek kullanıcılar ve release’ler
üzerinde doğru uygulanıp uygulanmadığını denetlemektir.

İnceleme odağı:

- PMP hedefleri ve Problem–Evidence–Exit kayıtları,
- migration planları ve rollback kanıtı,
- AI davranış kalitesi ve Golden Corpus sonuçları,
- Alpha/Beta cohort sonuçları,
- REP bütünlüğü,
- risk analizi ve blocker’lar,
- kullanıcıya gerçekten değer katılıp katılmadığı.

Temel review sorusu:

> Bu çalışma gerçek kullanıcıya ölçülebilir bir değer katıyor mu?

Bu rol, SCA’nın yerine yeni karar kuralları koymaz; SDS, Release Constitution,
PMP ve mevcut evidence artefaktlarını gerçek kararlar için kullanır.

## PMP work initiation gate

Her PMP çalışması başlamadan önce şu üç soru cevaplanır:

1. **Problem** — Hangi gerçek kullanıcı problemini çözüyoruz?
2. **Evidence** — Problemin çözüldüğünü hangi metrik gösterecek?
3. **Exit** — PMP hedefinin tamamlandığını hangi objektif kriterle ilan
   edeceğiz?

Bu üç cevap workstream kaydında, implementation planında veya mevcut REP/ADR
artefaktında tutulabilir. Ayrı bir belge yalnızca Documentation Debt Rule
gerektiriyorsa oluşturulur. Cevaplardan biri yoksa çalışma `PLANNED` veya
`INCOMPLETE` kalır; `ACTIVE` ya da `DONE` olarak sınıflandırılamaz.

## Governance program closure

| Program / capability | Status | Meaning |
|---|---|---|
| SCA v1.0 | Completed | Accepted & Frozen constitutional reference |
| Governance Framework | Operational | Active decision and consistency input |
| Release Constitution | Operational | Active release gate and veto input |
| SDS | Operational | Active decision classification input |
| SLS | Operational | Active lifecycle and drift-control input |
| ADR Framework | Operational | Active architectural decision record |
| REP | Operational | Active release evidence requirement |
| Governance Health Check | Operational | Active governance compliance review |

`Operational`, bu unsurların artık geliştirme programı olmadığını ve gerçek
kararlarda kullanılmaları gerektiğini ifade eder. Operational sınıflandırma,
uygulamanın otomatik olarak başarılı olduğu anlamına gelmez; başarı Governance
Health Check ve REP kanıtlarıyla ölçülür.

## Documentation Debt Rule

Yeni ürün dokümantasyonu yalnızca mevcut bir operasyonel ihtiyacı
karşılıyorsa oluşturulur.

Yeni bir belge açmadan önce:

1. PMP, REP, ADR veya mevcut operasyonel dokümanlardan biri yeterli mi?
2. Belgenin sahibi, lifecycle state’i ve güncelleme tetikleyicisi belli mi?
3. Gerçek bir execution, evidence veya operations ihtiyacını karşılıyor mu?
4. Belge açılmadığında güvenlik, release, incident veya kullanıcı güveni riski
   doğuyor mu?

`"Belki ileride lazım olur"` gerekçesi tek başına yeterli değildir. Mevcut bir
belge genişletilebiliyorsa yeni belge açılmaz. Dokümantasyon da kod gibi bakım,
drift ve doğrulama maliyeti oluşturur.

## PMP çalışma akışı

### PMP-01 — Secure Migration

PMP-01, `docs/pmp-01-secure-migration-execution-plan.md` içindeki execution
planı ile yönetilir. Program governance katmanı `PMP-01.0`’dır; aşağıdaki
alt başlıklar bağımsız iş paketleridir.

#### PMP-01.0 — Program Governance

PMP-01.0 kod yazmaz. İş paketlerini koordine eder, dependency map’i ve
Problem–Evidence–Exit kayıtlarını korur, REP girdilerini toplar ve her paket
için risk, rollback ve MUV etkisini gözden geçirir.

#### PMP-01A–F — Work packages

- **PMP-01A:** Identity Linking Execution
- **PMP-01B:** Migration Engine
- **PMP-01C:** Resource Migration
- **PMP-01D:** Verification Engine
- **PMP-01E:** Rollback Engine
- **PMP-01F:** Migration Dashboard

Current execution status: **PMP-01A BLOCKED** —
`PMP-01A-BLK-001 / VERIFIED_LEGACY_IDENTITY_SOURCE_MISSING`. Bu blocker
çözülmeden PMP-01B’ye, PMP-01C’ye veya sonraki ürün engine’lerine geçilmez.

Sıradaki çalışma blocker’ı zorla aşmak değildir. Öncelik:

1. **PMP-01A.1** — Reachable Legacy Ask Surface Containment — completed.
2. **PMP-01A.2** — Web Event Contract Audit — closed as `NOT_VERIFIABLE`
   (inspectable source absent; no trust assumed).
3. **PMP-01A.3** — Manual Recovery Execution — contract + edge-case review
   complete (`IMPLEMENTATION_READY`); implementation may begin with Reviewer
   API → assertion store → workflow → evidence. Still
   `POLICY_DEFINED / NOT_OPERATIONAL` until exit evidence is produced.
4. A.3 tamamlanması PMP-01A’yı otomatik `DONE` yapmaz. Evidence pack sonrası
   ayrı **Resolution Review** `PMP-01A-BLK-001` için `BLOCKED` veya
   `UNBLOCKED` kararını verir.

Bu riskler kapanmadan hiçbir release gate açılmaz. `BLOCKED` ise blocker
çözülür; `READY` ise uygulanır; `DONE` demeden kanıt istenir; `RELEASE`
demeden REP ve release gate kontrol edilir.

Amaç:

- canonical Supabase identity,
- live RLS doğrulaması,
- cross-user ownership,
- migration dry-run,
- verified linking,
- rollback hazırlığı.

Çıkış kanıtı:

- gerçek izole test kullanıcılarıyla RLS raporu,
- ownership matrix doğrulaması,
- dry-run assessment,
- migration ve rollback REP artefact’ları.

Production user-data migration, bu kanıtlar ve Release Council onayı olmadan
başlamaz.

PMP-01 yalnızca migration’ın teknik olarak çalışmasıyla tamamlanmış sayılmaz.
Çıkış için migration’ın güvenli, geri alınabilir ve bağımsız kanıtlarla
doğrulanabilir olması gerekir. Ambiguous ownership, unverified identity,
consent ihlali veya rollback rehearsal eksikliği blocker’dır.

Migration Engine’in başarılı sonucu tek başına migration tamamlandı anlamına
gelmez. Verification Engine bağımsız olarak `PASS` üretmeden migration
tamamlanamaz; `FAIL` sonucu rollback değerlendirmesini zorunlu kılar.

### PMP-02 — Alpha Cohort

Amaç:

- ilk kontrollü gerçek kullanıcı grubu,
- gözlemlenebilir V1 akışı,
- açık rollback ve stop condition,
- destek ve incident prosedürü,
- gerçek REP üretimi,
- Release Council incelemesi,
- Governance Health Check uygulaması.

Önkoşullar:

- PMP-01 tamamlanmış olmalı,
- rollout cohort’u deterministik olmalı,
- V1 production yüzdesi Release Council kararı olmadan artırılmamalı,
- REP release öncesinde tamamlanmalı,
- Release Council kararı kayda alınmalı,
- Governance Health Check sonuçları ve açık aksiyonlar görünür olmalı.

Alpha, SCA’nın ilk gerçek operasyon sınavıdır. Governance belgelerinin
varlığı tek başına yeterli değildir; REP, Council ve Health Check gerçek
karar akışında kullanılmalıdır.

### PMP-03 — Context Engine & Project Engine

Amaç:

- conversation context,
- approved memory,
- project context,
- session state,
- project state,
- sprint,
- checkpoint,
- decision,
- risk,
- next smallest action,
- relevance ve isolation.

Başarı:

- ilgisiz memory prompt’a girmemeli,
- proposed memory kullanılmamalı,
- cross-user context mümkün olmamalı,
- context davranışı Golden Corpus ile ölçülmeli.
- her project canonical UUID ile sahiplenilmeli,
- task ve session ilişkileri owner doğrulamalı,
- kullanıcı sonraki adımı anlayabilmeli,
- project continuity gerçek oturumlarla ölçülmeli.

Context Engine ve Project Engine, eksik yan özellikler değil, SANRI’nın
“kullanıcıyı ve devam eden işi bağlam içinde taşıma” ürün vaadinin temelidir.

### PMP-04 — AI Quality Gate

Amaç:

- intent ve mode doğruluğu,
- output-first davranışı,
- AURA character consistency,
- memory consent,
- prompt injection,
- provider failure,
- multilingual behavior,
- living Golden Corpus maintenance.

Başarı:

- Golden Corpus hedefleri sağlanmalı,
- kritik forbidden-behavior ihlali bulunmamalı,
- model/provider değişiklikleri Principle of Least Surprise kontrolünden
  geçmeli,
- sonuç REP’e eklenmeli,
- Golden Corpus yeni gerçeklerden ve regresyonlardan kontrollü biçimde
  güncellenmeli; ham üretim kullanıcı içeriği corpus’a alınmamalı.

Golden Corpus, tek seferlik bir test dosyası değil, beklenen ve yasaklanan
davranışların release’ler arasında izlenmesini sağlayan yaşayan kalite
sistemidir. Corpus değişiklikleri gerekçeli, anonimleştirilmiş ve sürüm
kanıtına bağlı olmalıdır.

### PMP-05 — Beta Release

Beta, Alpha cohort kanıtları ve migration/RLS güvenliği sonrasında daha geniş
ama hâlâ kontrollü kullanıcı grubudur.

Gereklilikler:

- REP,
- AI Quality report,
- security report,
- performance baseline,
- rollback rehearsal,
- açık P0/P1 blocker olmaması.

### PMP-06 — Performance & Scale

Ölçülecek alanlar:

- TTFT,
- toplam response latency,
- streaming interruption,
- provider error rate,
- token cost,
- database query latency,
- concurrent sessions,
- rate-limit behavior,
- queue ve worker saturation.

Load test sonuçları production traffic açma kararından önce REP’e eklenir.

### PMP-07 — Release Candidate

RC, yeni feature geliştirme aşaması değil; release kanıtlarının son
birleştirme ve doğrulama aşamasıdır.

RC kapıları:

- AI Quality Gate,
- Golden Corpus,
- Security Audit,
- Performance,
- rollback,
- observability,
- kill-switch,
- documentation,
- Release Council veto review.

### PMP-08 — SANRI OS 1.0

İlk gerçek kullanıcı release’i yalnızca Alpha, Beta ve RC kapıları geçildikten
sonra yapılır. `SANRI OS 1.0` için:

- cohort açıkça tanımlanır,
- release directory oluşturulur,
- REP tamamlanır,
- council-approval kaydı tutulur,
- post-release Governance Health Check tarihi atanır.

## PMP deliverable sınıfları

PMP kapsamında üretilen belgeler üç sınıfa ayrılır:

### Execution

- migration planları,
- rollout planları,
- implementation plans,
- cohort plans,
- test plans.

### Evidence

- REP,
- test reports,
- RLS reports,
- AI Quality reports,
- Golden Corpus scorecards,
- performance reports,
- security verification.

### Operations

- runbooks,
- rollback,
- incident response,
- observability,
- support procedures,
- stop conditions.

Bu belgeler SCA’yı değiştirmez; SCA’nın tanımladığı süreçleri uygular ve
kanıtlar.

## PMP başarı ölçütü

PMP’nin amacı daha fazla doküman üretmek değil, gerçek kullanıcılar ve gerçek
operasyon altında:

- güvenli migration,
- güvenilir identity,
- ölçülebilir AURA kalitesi,
- kullanılabilir Context ve Project Engine,
- kontrollü release,
- kanıtlanabilir rollback

sağlamaktır.

Her PMP fazı için karar SDS ile sınıflandırılır, mimari değişiklikler ADR ile
kaydedilir ve release etkisi REP ile kanıtlanır.

## Product Maturation Health Metrics

Bu metrikler Governance Health Check’ten ayrıdır. Governance Health Check
süreçlerin uygulanıp uygulanmadığını; aşağıdaki metrikler ürünün gerçek
kullanıcılar ve gerçek operasyon altında olgunlaşıp olgunlaşmadığını ölçer.

### North KPI — Measured User Value (MUV)

PMP’nin tek üst seviye ürün KPI’ı **Measured User Value (MUV)**’dir:

> Üretilen önemli bir değişiklik, gerçek kullanıcı davranışında veya
> deneyiminde ölçülebilir bir iyileşme oluşturuyor mu?

Migration, Context Engine, Project Engine, AI Quality Gate ve Alpha Cohort
çalışmalarının tamamı MUV’ye hizmet eder. Bir çalışma teknik olarak başarılı
olsa bile kullanıcı için ölçülebilir değer üretmiyorsa ürün açısından
tamamlanmış sayılmaz.

Her önemli değişiklik için MUV kanıtı:

- başlangıç davranışı veya deneyim baseline’ı,
- beklenen kullanıcı değeri,
- ölçüm yöntemi ve örneklem,
- gözlenen sonuç,
- güven aralığı veya belirsizlik,
- karar ve takip aksiyonu

olarak kaydedilir. Kullanıcı değeri ölçülemiyorsa sonuç `VALUE_UNPROVEN`
olarak işaretlenir; `DONE` veya release approval varsayılmaz.

Alt metrikler MUV’yi açıklar, onun yerine geçmez:

| Alan | Ölçüt | Kanıt / sahip |
|---|---|---|
| Migration | Başarılı migration oranı; rollback gerektiren olay sayısı | Migration report / Migration Owner |
| Reliability | Uptime; hata oranı; kritik incident sayısı | Observability report / Operations |
| AI Quality | Golden Corpus başarı oranı; Quality Gate geçiş oranı | AI Quality report / AI Quality Authority |
| Performance | TTFT; toplam yanıt gecikmesi; başarısız istek oranı | Performance report / Operations |
| User Trust | Consent ihlalleri; cross-user ihlalleri; güvenlik olayları | Security report / Security & Identity Authorities |
| Product | Alpha/Beta cohort geri bildirimi; kritik UX sorunu sayısı | Cohort report / Product Authority |

Her metrik için dönem, örneklem, hedef, gerçek değer, trend, owner ve eşik
ihlali kaydedilir. Ham kullanıcı içeriği ölçüm artefaktlarına yazılmaz.

Bu tablo alt metrikler içindir. Hiçbir alt metrik tek başına MUV başarısı
olarak yorumlanamaz.

## PMP Definition of Done

Bir PMP işi veya release etkisi olan değişiklik aşağıdaki koşullar sağlanmadan
`Done` sayılamaz:

- Kod veya yapılandırma değişikliği tamamlandı.
- İlgili testler geçti ve sonuçları kaydedildi.
- Gerekliyse ADR güncellendi veya yeni ADR ihtiyacı SDS ile karara bağlandı.
- Teknik ve operasyonel dokümantasyon güncellendi.
- Release etkisi varsa REP girdileri hazırlandı.
- Gerekli observability, telemetry ve failure logging eklendi.
- Rollback etkisi değerlendirildi ve gerekiyorsa rehearsal yapıldı.
- Identity, ownership, memory consent ve kullanıcı güveni etkileri kontrol
  edildi.
- Değişiklik ilgili PMP exit gate’ini ve Release Constitution blocker
  kontrollerini geçti.

`Done`, yalnızca kodun derlenmesi veya testlerin geçmesi anlamına gelmez.
Eksik kanıt `Done` değil, `INCOMPLETE` durumudur. MUV kanıtı yoksa iş
`VALUE_UNPROVEN` olarak kalır.
