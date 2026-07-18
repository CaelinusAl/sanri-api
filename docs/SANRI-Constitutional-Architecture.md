# SANRI Constitutional Architecture (SCA)

**Status:** Completed — Accepted & Frozen  
**Version:** 1.0  
**Owner:** SANRI Governance Framework

## Constitutional Metadata

```text
Authority Level: Constitutional Architecture
Owner: SANRI Governance Framework
Source of Truth: SANRI Constitutional Architecture
Supersedes: None
Depends On: SANRI Constitution, SANRI Manifesto
Referenced ADRs: ADR-016
Related Standards: SDS, SLS, Governance Framework
Lifecycle State: Accepted & Frozen
Last Reviewed: 2026-07-18
```

SANRI Constitutional Architecture, SANRI’nın ilkelerini, kararlarını,
ürününü, mühendisliğini ve operasyonunu birbirine bağlayan anayasal
katmanlar sistemidir.

Kod bu sistemin merkezi değildir. Kod, üst katmanlarda alınan kararların
uygulanma biçimidir.

## Constitutional Freeze

SCA v1.0 anayasal olarak dondurulmuştur. Yeni anayasal belge eklemek
varsayılan olarak yasaktır.

Yeni bir yönetişim ihtiyacı ortaya çıktığında sıra şöyledir:

1. Mevcut yapı gerçekten yetersiz mi değerlendirilir.
2. İhtiyaç mevcut bir belgenin kapsamına giriyor mu kontrol edilir.
3. Yeni belge yerine mevcut belge güncellemesi yeterli mi incelenir.
4. Mimari gerekçe için ADR yeterli mi değerlendirilir.
5. Yeni anayasal belge hâlâ kaçınılmazsa SDS kapsamında L4 Constitutional
   Decision açılır.

L4 kararı olmadan SCA’ya yeni anayasal seviye, belge veya yetki alanı
eklenemez. L4 kararı; etkilenen Constitution, Whitepaper ve Governance
Framework belgelerinin birlikte güncellenmesini gerektirir.

## SCA Lifecycle and Governance Review

SCA v1.0, kritik bir platform artifact’ı gibi işletilir:

- Her yıl en az bir Governance Review yapılır.
- Her major release öncesi SCA review edilir.
- Production migration, rollback, ciddi security incident, büyük mimari
  değişiklik, ekip büyümesi veya release baskısı ilkeleri ayrıca sınar.
- Anayasal değişiklik ihtiyacı yoksa yeni SCA sürümü çıkarılmaz.
- Gerçek anayasal ihtiyaç oluşursa yalnızca SDS L4 süreciyle yeni SCA sürümü
  önerilebilir.

SCA’nın başarısı belge sayısıyla değil, gerçek karar anlarında SDS, Release
Constitution, REP, ADR ve Governance Framework’ün referans alınmasıyla
ölçülür.

Resmî durum:

> SCA v1.0 Accepted & Frozen. Yeni anayasal içerik varsayılan olarak
> oluşturulmaz. Bundan sonraki gelişim, SCA’nın tanımladığı yönetişim
> süreçleri içinde yürütülür.

## Katmanlar

```text
SANRI Constitutional Architecture
│
├── Level 1 — Principles
│   ├── SANRI Constitution
│   └── SANRI Manifesto
│      Why do we exist?
│
├── Level 2 — Governance
│   ├── SANRI Governance Framework
│   ├── SANRI Release Constitution
│   ├── SANRI Security & Trust Standard
│   ├── SANRI Decision Standard
│   ├── SANRI Lifecycle Standard
│   └── ADR
│      How do we make decisions?
│
├── Level 3 — Product
│   ├── SANRI Whitepaper
│   ├── Product Bible
│   └── AURA Bible
│      What are we building?
│
├── Level 4 — Engineering
│   ├── STAS
│   ├── Engineering Handbook
│   └── Design System
│      How do we build it?
│
└── Level 5 — Operations
    ├── Release Evidence Pack
    ├── Runbooks
    ├── Migration
    ├── Rollback
    └── Incident Response
       How do we operate it?
```

## Katman ilişkisi

- **Principles** neyin korunacağını belirler.
- **Governance** kararların kim tarafından ve hangi kanıtla alınacağını
  belirler.
- **Product** neyin inşa edileceğini belirler.
- **Engineering** ürünün nasıl inşa edileceğini belirler.
- **Operations** sistemin nasıl güvenli biçimde çalıştırılacağını belirler.

Alt katman üst katmanı sessizce değiştiremez. Üst katmanda değişiklik
gerekiyorsa `SANRI Decision Standard` seviyesine göre karar alınır ve ilgili
belgeler birlikte güncellenir.

## Federated Source of Truth

SANRI tek bir dev belgeye dayanmaz. Her alanın kendi tek ve yetkili kaynağı
vardır:

| Alan | Yetkili kaynak |
|---|---|
| Amaç ve değişmez ilkeler | SANRI Constitution |
| Ürün vizyonu ve kapsamı | SANRI Whitepaper / Product Bible |
| Teknik mimari | STAS |
| AURA davranışı | AURA Bible |
| Mimari karar gerekçeleri | ADR |
| Yayın kuralları | SANRI Release Constitution |
| Yayın kanıtları | Release Evidence Pack |
| Güvenlik ve kullanıcı güveni | Security & Trust Standard |
| Günlük geliştirme standardı | Engineering Handbook |
| Operasyonel uygulama | Runbooks, Migration, Rollback, Incident Response |

Federated Source of Truth, belgelerin bağımsızlaşması değildir. Belgeler
arasında tutarlılık, sahiplik, versioning, ADR etkisi ve REP kayıtlarıyla
korunur.

## Değişiklik sınırı

Bir değişiklik kendi katmanının dışına taşıyorsa yalnızca kod review yeterli
değildir. SDS seviyesi belirlenir, etkilenen belgeler listelenir ve release
kanıt paketine eklenir.

Özellikle kullanıcı güveni, identity, memory consent, AURA’nın temel
davranışı veya release yetkisi değiştirilemez bir davranış olarak
değerlendirilir.
