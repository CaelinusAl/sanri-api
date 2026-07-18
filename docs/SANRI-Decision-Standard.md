# SANRI Decision Standard (SDS)

**Status:** Operational  
**Version:** 1.0  
**Constitutional layer:** Level 2 — Governance  
**Owner:** SANRI Governance Framework

## Constitutional Metadata

```text
Authority Level: Level 2 — Governance
Owner: SANRI Governance Framework
Source of Truth: SANRI Decision Standard
Supersedes: Informal decision-level conventions
Depends On: SANRI Constitutional Architecture, Governance Framework
Referenced ADRs: ADR-016
Related Standards: SLS, Release Constitution, Security & Trust Standard
Lifecycle State: Operational
Last Reviewed: 2026-07-18
```

## Bir karar nasıl alınır?

Her karar önce etkisi, geri alınabilirliği, kullanıcı güveni ve etkilenen
anayasal katmanları açısından sınıflandırılır. Karar seviyesi yükseldikçe
yetki, kanıt ve belge yükümlülüğü artar.

## Karar seviyeleri

### L1 — Local Decision

Bir geliştirici veya küçük çalışma grubu alabilir.

Örnekler:

- refactoring,
- test düzenlemesi,
- logging iyileştirmesi,
- davranışı değiştirmeyen dependency güncellemesi,
- mevcut sözleşmeye uyan iç kod düzenlemesi.

Gereklilikler:

- mevcut ADR, Governance Framework ve Security Standard ile çelişmemeli,
- test sonucu bulunmalı,
- kullanıcıya görünen güven davranışı değişmemeli,
- code review tamamlanmalı.

### L2 — Architectural Decision

ADR gerekir. Architecture Authority veya yetkilendirilmiş mimari review
tarafından incelenir.

Örnekler:

- API sözleşmesi,
- veri modeli,
- provider boundary,
- memory retrieval,
- RLS policy,
- session/conversation modeli,
- yeni altyapı veya dependency ailesi,
- birden fazla bounded context’i etkileyen refactoring.

Gereklilikler:

- karar bağlamı,
- alternatifler,
- riskler,
- migration ve rollback etkisi,
- etkilenen Federated Source of Truth belgeleri,
- test ve observability planı.

### L3 — Governance Decision

Release Council gerekir.

Örnekler:

- rollout yüzdesi değişikliği,
- release gate değişikliği,
- legacy endpoint’in açılması veya kapatılması,
- migration başlangıcı,
- service-role yetkisinin genişletilmesi,
- kullanıcı güvenini veya izin modelini etkileyen ürün davranışı,
- Release Constitution veya Security & Trust Standard uygulaması.

Gereklilikler:

- REP veya karar öncesi kanıt kaydı,
- ilgili veto sahiplerinin incelemesi,
- rollback ve stop condition,
- kullanıcı güveni etkisi,
- açık risk sahibi ve son tarih.

### L4 — Constitutional Decision

SCA v1.0 `Accepted & Frozen` olduğu için bu seviye istisnai kullanılır.
Anayasal belge değişikliği gerekir. Bu seviye SANRI’nın değişmez ilkelerini,
amaç tanımını, yönetim modelini veya kullanıcıya verdiği temel sözü etkiler.

Örnekler:

- SANRI Constitution değişikliği,
- User Trust Principle değişikliği,
- Governance Framework hiyerarşisi değişikliği,
- Release Council yetkilerinin değiştirilmesi,
- canonical identity veya memory consent ilkesinin değiştirilmesi.

L4 gereklilikleri:

1. SANRI Constitution güncellenir.
2. Etkilenen Whitepaper veya Product Bible güncellenir.
3. Governance Framework güncellenir.
4. İlgili ADR eklenir veya güncellenir.
5. En az bir release cycle boyunca review süresi tanınır.
6. Security, Architecture, Product ve Release Council kayıtları tutulur.
7. Değişiklikten etkilenen REP ve runbook’lar güncellenir.

L4 kararı kod değişikliğiyle örtülemez. Belgeler güncellenmeden uygulama
değişikliği yapılmaz.

Yeni anayasal belge talebi L4’e yükselmeden önce mevcut belge kapsamı,
mevcut belge güncellemesi ve ADR yeterliliği yazılı olarak reddedilmiş
olmalıdır.

## Karar yükseltme kuralları

Aşağıdaki durumlardan biri varsa karar otomatik olarak bir üst seviyeye
çıkarılır:

- geri dönüş zor veya imkânsız hale geliyorsa,
- kullanıcı güveni etkileniyorsa,
- identity, authorization veya consent etkileniyorsa,
- birden fazla anayasal katman etkileniyorsa,
- production traffic veya migration etkileniyorsa,
- mevcut kullanıcı davranışı değişiyorsa,
- kararın kapsamı ilk tahminden büyüyorsa.

Bir kararın düşük seviyede başlatılmış olması, etkisi büyüdüğünde üst seviye
review yükümlülüğünü ortadan kaldırmaz.

## Principle of Least Surprise

Hiçbir yeni özellik, mevcut kullanıcıların SANRI’ya güvenmesini sağlayan
temel davranışı beklenmedik şekilde değiştiremez.

Özellikle AURA için:

- yeni model geldi diye memory davranışı değişemez,
- izin ve consent modeli sessizce değişemez,
- kullanıcıya verilen kimlik ve güvenlik sözü değişemez,
- AURA’nın temel karakteri model güncellemesiyle bozulamaz,
- mevcut session continuity davranışı açıklamasız biçimde kaybolamaz,
- kullanıcıya ait verinin kapsamı yeni bir provider veya prompt değişikliğiyle
  genişleyemez.

Beklenen bir davranış değişikliği varsa önce Product, AURA Bible, Security &
Trust ve gerekiyorsa Constitution/ADR etkisi değerlendirilir. Kullanıcıya
görünen değişiklik release notlarında ve REP’te açıkça belirtilir.

## Karar kaydı standardı

Her L2–L4 kararı en az şu alanları içerir:

- karar sahibi,
- karar seviyesi,
- bağlam ve problem,
- seçenekler,
- seçilen yaklaşım,
- reddedilen yaklaşımlar,
- kullanıcı güveni etkisi,
- security ve privacy etkisi,
- Federated Source of Truth etkisi,
- rollback veya reversal planı,
- kanıt bağlantıları,
- review sahipleri,
- karar tarihi ve gözden geçirme tarihi.

## Acil kararlar

Aktif bir security incident sırasında Operations veya Security Authority
geçici containment kararı alabilir. Bu karar:

- yalnızca zararı sınırlamak için,
- minimum kapsamda,
- ölçülebilir stop condition ile,
- kullanıcı verisini koruyacak biçimde,
- sonradan L2, L3 veya L4 kaydına dönüştürülmek üzere

uygulanır.

Acil durum, kalıcı anayasal değişiklik veya release approval yerine geçmez.
