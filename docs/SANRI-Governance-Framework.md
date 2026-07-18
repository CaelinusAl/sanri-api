# SANRI Governance Framework

**Status:** Operational  
**Version:** 1.0  
**Scope:** SANRI OS, AURA, product, engineering, security, data, AI,
operations, and release decisions

## Constitutional Metadata

```text
Authority Level: Level 2 — Governance
Owner: SANRI Governance Framework
Source of Truth: SANRI Governance Framework
Supersedes: Previous governance notes and informal release rules
Depends On: SANRI Constitutional Architecture, SANRI Constitution
Referenced ADRs: ADR-016
Related Standards: SDS, SLS, Release Constitution, Security & Trust Standard
Lifecycle State: Operational
Last Reviewed: 2026-07-18
```

SANRI Governance Framework, **SANRI Constitutional Architecture (SCA)** içindeki
Level 2 yönetim katmanıdır. SCA bütün anayasal seviyelerin çatısıdır; Governance
Framework ise bu seviyeler arasındaki karar, yetki, kanıt ve tutarlılık
kurallarını yönetir.

Belgeler farklı sorulara cevap verir; hiçbir belge kullanıcı güveni ilkesinden
bağımsız yorumlanamaz.

## SCA içindeki konum

```text
SANRI Constitutional Architecture
│
├── Level 1 — Principles
├── Level 2 — Governance
│   └── SANRI Governance Framework  ← bu belge
├── Level 3 — Product
├── Level 4 — Engineering
└── Level 5 — Operations
```

Tam mimari `docs/SANRI-Constitutional-Architecture.md` içinde tanımlıdır.

## Constitutional Freeze Rule

SCA v1.0 `Accepted & Frozen` durumundadır. Governance Framework yeni
anayasal belge üretimini teşvik etmez.

Yeni ihtiyaçlarda önce mevcut belgenin kapsamı, sonra ADR yeterliliği
incelenir. Yeni anayasal belge ancak SDS L4 Constitutional Decision ile
oluşturulabilir. L4 kararı olmadan SCA’nın seviyesi, hiyerarşisi veya yetki
modeli genişletilemez.

## Governance katmanının belgeleri

- `SANRI Governance Framework`
- `SANRI Release Constitution`
- `SANRI Security & Trust Standard`
- `SANRI Decision Standard`
- `SANRI Lifecycle Standard`
- `ADR`

## Yönetim ilkesi

SANRI için temel yön:

> Kod, mimariye uyar. Mimari, ilkelere uyar. İlkeler ise kullanıcı güvenine
> hizmet eder.

Bu ilke; feature, deadline, yatırım, büyüme, model seçimi ve release
kararlarının üzerinde duran ortak değerlendirme standardıdır.

## Federated Source of Truth

SANRI tek bir belgeyi her alanın kaynağı yapmaz. Her alanın kendi yetkili
kaynağı vardır:

| Alan | Tek yetkili kaynak |
|---|---|
| Amaç ve anayasal ilkeler | SANRI Constitution |
| Ürün | SANRI Whitepaper / Product Bible |
| Teknik mimari | STAS |
| AURA davranışı | AURA Bible |
| Mimari karar gerekçesi | ADR |
| Yayın kuralları | SANRI Release Constitution |
| Yayın kanıtı | Release Evidence Pack |
| Güvenlik ve trust | Security & Trust Standard |
| Geliştirme pratiği | Engineering Handbook |
| Operasyon | Runbooks, Migration, Rollback, Incident Response |

Bu kaynaklar bağımsız adacıklar değildir. SCA, SDS, cross-reference,
versioning ve REP kayıtlarıyla tek bir tutarlı anayasal sistem oluştururlar.

## Principle of Least Surprise

Yeni hiçbir davranış, mevcut kullanıcının SANRI’ya güvenmesini sağlayan temel
davranışı beklenmedik biçimde değiştiremez.

AURA özelinde yeni model, provider veya prompt değişikliği:

- memory davranışını,
- consent ve izin modelini,
- identity ve ownership sözünü,
- session continuity’yi,
- AURA’nın temel karakterini

sessizce değiştiremez. Böyle bir değişiklik SDS ile sınıflandırılır, ilgili
kaynak belgeler güncellenir ve REP içinde açıkça kanıtlanır.

## Belgelerin görevleri

### SANRI Constitution

SANRI’nın varlık nedenini, temel değerlerini, kullanıcıya verdiği sözü ve
değiştirilemez ürün ilkelerini tanımlar.

### SANRI Whitepaper

SANRI OS’un ne inşa ettiğini, ürün vizyonunu, sistem sınırlarını ve uzun
vadeli yönünü tanımlar.

### STAS

SANRI’nın sistem tasarımını, teknik çalışma modelini, katmanlarını,
entegrasyonlarını ve uygulama standartlarını tanımlar.

### AURA Bible

AURA’nın karakterini, düşünme biçimini, dilini, çalışma modlarını,
memory davranışını ve kullanıcıyla ilişki sınırlarını tanımlar.

### ADR

Geriye dönük olarak anlaşılması gereken mimari kararları, nedenlerini,
alternatiflerini ve sonuçlarını kaydeder. Kod veya operasyon ADR ile
çelişiyorsa karar gözden geçirilir; sessiz sapma kabul edilmez.

### SANRI Decision Standard

Kararları L1 Local, L2 Architectural, L3 Governance ve L4 Constitutional
seviyelerine ayırır. Karar seviyesi yükseldikçe yetki, kanıt, review ve
belge güncelleme yükümlülüğü artar.

### Release Constitution

Bir sürümün hangi kanıtlarla ve hangi yetkiyle yayınlanabileceğini tanımlar.
Release Council, veto sistemi ve Release Evidence Pack bu katmanın parçasıdır.

### Engineering Handbook

Branch, commit, test, code review, dependency, observability, documentation,
incident ve günlük mühendislik çalışma standartlarını tanımlar.

### Security & Trust Standard

Identity, authentication, authorization, RLS, privacy, consent, secret,
retention, audit, incident response ve kullanıcı güveni kontrollerini
tanımlar.

## Çelişki çözüm sırası

Belgeler arasında çelişki olduğunda aşağıdaki sıra uygulanır:

1. SANRI Constitutional Architecture
2. User Trust Principle
3. SANRI Constitution
4. Security & Trust Standard
5. Governance Framework
6. Release Constitution
7. SANRI Decision Standard
8. STAS
9. ADR
10. Engineering Handbook
11. Whitepaper ve ürün kapsamı
12. Uygulama kodu ve geçici operasyon notları

Bu sıra daha alt belgenin daha üst belgeyi sessizce geçersiz kılmasını önler.
Değişiklik gerekiyorsa önce ilgili üst belge ve ADR güncellenir, ardından kod
değiştirilir.

## Constitutional Consistency Rule

Hiçbir belge, kendisinden daha üst anayasal seviyedeki bir belgeyle çelişemez.

- STAS, Whitepaper veya Constitution ile çelişemez.
- Engineering Handbook, STAS ile çelişemez.
- Release Constitution, Constitution’daki temel ilkeleri geçersiz kılamaz.
- REP yeni politika oluşturamaz; yalnızca uygulanmış kararın kanıtını içerir.
- Migration ve rollback runbook’ları Security & Trust Standard’ı gevşetemez.

Çelişen alt belge `Blocked` veya `Proposed` durumuna alınır. Önce üst seviye
karar SDS ile sınıflandırılır, ardından etkilenen belgeler birlikte
güncellenir.

## Governance Health Check

Yılda en az bir kez ve her büyük release öncesinde Governance Health Check
yapılır. Sonuç bir governance review kaydı veya REP içinde tutulur.

SCA bir ürün/artifact gibi yaşam döngüsüne sahiptir. SCA v1.0 `Accepted &
Frozen` durumundadır; constitutional ihtiyaç yoksa yeni SCA sürümü
çıkarılmaz. Yeni anayasal içerik varsayılan olarak oluşturulmaz.

Kontrol listesi:

- Üst ve alt seviye belgeler arasında çelişki var mı?
- Document drift tespit edildi mi?
- Constitutional Metadata alanları güncel mi?
- REP’ler eksiksiz oluşturuluyor mu?
- ADR’ler kod ve operasyon tarafından gerçekten uygulanıyor mu?
- Deprecated belgeler hâlâ referans gösteriliyor mu?
- SCA freeze kuralını aşan yeni belge veya yetki eklenmiş mi?
- Federated Source of Truth sahipleri ve review tarihleri güncel mi?
- Açık veto, istisna ve süresi geçmiş risk var mı?
- İlk production migration, rollback veya ciddi security incident sonrası
  süreçler SDS, ADR, REP ve Release Constitution’a gerçekten referans verdi mi?
- Büyük mimari değişiklik veya ekip büyümesi sonrası karar sahipliği ve veto
  alanları çalıştı mı?
- Release baskısı altında blocker’lar korunabildi mi?

Başarısız bir kontrol, ilgili belgeyi veya release’i otomatik olarak
`Blocked` durumuna taşıyabilir. Health Check yeni anayasal belge yazma
gerekçesi değildir; önce mevcut yapıyı koruma ve düzeltme mekanizmasıdır.

## SCA Success Criteria

Bu ölçütler yeni anayasal kural üretmez. Mevcut SCA, SDS, ADR, Release
Constitution ve REP süreçlerinin gerçek hayatta uygulanıp uygulanmadığını
ölçer.

| Ölçüt | Başarı göstergesi | Kanıt |
|---|---|---|
| ADR Adoption | Mimari değişikliklerin %100’ü ADR ile kayıtlı | ADR index ve change review |
| Release Evidence | Her release için eksiksiz REP mevcut | `releases/<version>/REP.md` |
| Governance Compliance | L3/L4 kararlarında süreç atlanmamış | SDS karar kayıtları ve Council record |
| Blocker Integrity | Release blocker’ları baskı altında kaldırılmamış | Veto ve incident kayıtları |
| Constitutional Stability | L4 değişiklik ihtiyacı çok düşük ve gerekçeli | Governance Review geçmişi |
| Trust Incidents | Kullanıcı güvenini zedeleyen yönetişim ihlali yok | Security/incident review |
| RLS and Ownership | Cross-user testleri geçerli kanıtla başarılı | Live RLS report |
| Migration Safety | Dry run, rollback ve verification tamamlanmış | Migration/rollback REP artefact’ları |
| AI Behavior Quality | AURA Quality Gate ve Golden Corpus hedefleri korunmuş | AI quality report |

Önerilen minimum hedef:

- ADR Adoption: `%100`
- Release Evidence: `%100`
- Governance Compliance: `%100`
- Blocker Integrity: `0` bypass
- Trust Incidents: `0` governance-caused incident
- RLS and Ownership: `0` cross-user violation

Bu metrikler yılda en az bir kez, her major release öncesinde ve ilk gerçek
production migration/rollback/security incident sonrasında değerlendirilir.

## Document drift yönetimi

Governance Framework sahibi düzenli olarak Constitutional Metadata,
referanslar, lifecycle state’leri, supersedes/depends-on ilişkileri, ADR/REP
bağlantıları ve üst-alt belge tutarlılığını kontrol eder. Drift bulunan bir
belge `Active` kabul edilmez.

## Yeni belge kabul standardı

SANRI’ya eklenen her kalıcı belge:

- bu Framework içindeki yerini belirtir,
- Constitutional Metadata başlığını içerir,
- hangi üst belgeye bağlı olduğunu yazar,
- çelişki halinde hangi belgeye öncelik verdiğini belirtir,
- sahibi ve gözden geçirme tarihini içerir,
- kullanıcı güvenine etkisini değerlendirir,
- gerekiyorsa ADR veya Release Evidence Pack bağlantısı taşır.

Belge yazmak tek başına yönetişim değildir. Belgenin uygulama, kanıt, review
ve güncelleme sahibi de tanımlanmalıdır.

## Release Evidence Pack bağlantısı

Her release, kararın sohbetlerde veya kişisel hafızalarda kalmaması için
versioned bir **Release Evidence Pack (REP)** üretir. REP; test, güvenlik,
AI Quality, Golden Corpus, performans, migration, rollback, risk, ADR etkisi
ve Release Council kararını aynı release kaydında toplar.

REP olmadan release `READY` olamaz. Release Council veto kayıtları REP
içinde kapanmadan release `RELEASED` olamaz.

## Yönetişim sahipliği

SANRI Governance Framework sahibi, belgeler arası tutarlılığı korur.
Security & Trust Standard sahibi güvenlik veto alanlarını korur.
Release Council ise release kararlarının ve REP kayıtlarının bütünlüğünden
sorumludur.

Bu Framework, SANRI’nın yalnızca bir AI ürünü değil; ilkeleri, mimarisi,
güvenlik modeli ve yayın disiplini birlikte tasarlanmış bir teknoloji
platformu olarak yönetilmesini sağlar.
