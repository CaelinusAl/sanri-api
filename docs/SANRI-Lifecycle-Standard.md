# SANRI Lifecycle Standard (SLS)

**Status:** Operational  
**Version:** 1.0  
**Constitutional layer:** Level 2 — Governance  
**Owner:** SANRI Governance Framework

## Constitutional Metadata

```text
Authority Level: Level 2 — Governance
Owner: SANRI Governance Framework
Source of Truth: SANRI Lifecycle Standard
Supersedes: Informal artifact and release state labels
Depends On: SANRI Constitutional Architecture, Governance Framework
Referenced ADRs: ADR-016
Related Standards: SDS, Release Constitution, Security & Trust Standard
Lifecycle State: Operational
Last Reviewed: 2026-07-18
```

SLS, SANRI içindeki artifact, API, ADR, model ve migration yaşam döngülerini
tanımlar. SLS geliştirme yöntemini değil, bir varlığın hangi evrede olduğunu,
hangi kanıtla evre değiştirebileceğini ve ne zaman sistemden çıkarılacağını
standardize eder.

## Constitutional Metadata

Her anayasal veya yönetişim belgesi aşağıdaki metadata başlığını taşımalıdır:

```text
Constitutional Metadata
Authority Level:
Owner:
Source of Truth:
Supersedes:
Depends On:
Referenced ADRs:
Related Standards:
Lifecycle State:
Last Reviewed:
```

Eksik metadata belge drift riskidir. Belge `Active` statüsüne alınmadan önce
metadata tamamlanmalıdır.

## Lifecycle state machine

Bir varlık yalnızca tanımlı kanıt ve yetkiyle bir sonraki evreye geçebilir.
Geriye dönüş gerekiyorsa yeni durum ve karar kaydı oluşturulur; geçmiş durum
silinmez.

## Artifact Lifecycle

```text
Draft → Proposed → Accepted → Active → Deprecated → Archived
```

- **Draft:** çalışma taslağı; normatif değildir.
- **Proposed:** review bekleyen öneri.
- **Accepted:** yetkili owner tarafından kabul edilmiş, fakat henüz
  yürürlükte olmayabilir.
- **Active:** geçerli ve uygulanması zorunlu kaynak.
- **Deprecated:** yeni kullanım için kapalı; geçiş planı vardır.
- **Archived:** tarihsel kayıt; yeni karar için kaynak değildir.

`Accepted → Active` geçişi owner ve ilgili governance authority onayı ister.
`Active → Deprecated` geçişi SDS seviyesiyle sınıflandırılır.

## API Lifecycle

```text
Experimental → Preview → Stable → Deprecated → Removed
```

- **Experimental:** iç test veya sınırlı deneme; compatibility garantisi yok.
- **Preview:** seçilmiş kullanıcı veya cohort için açık; değişiklikler
  release notes içinde belirtilir.
- **Stable:** sözleşme ve geriye dönük compatibility korunur.
- **Deprecated:** yeni entegrasyon yasak; sunset tarihi ve replacement bulunur.
- **Removed:** endpoint veya sözleşme artık çalışmaz; migration/rollback
  kanıtı arşivlenmiştir.

`Stable → Deprecated` geçişi Release Constitution ve deprecation runbook
gerektirir. `Deprecated → Removed` geçişi REP içinde kanıtlanmadan yapılamaz.

## ADR Lifecycle

```text
Proposed → Accepted → Superseded → Retired
```

- **Proposed:** karar önerisi.
- **Accepted:** geçerli mimari karar.
- **Superseded:** yeni ADR tarafından değiştirilmiş; tarihsel gerekçe korunur.
- **Retired:** artık uygulanmayan ve yalnızca arşiv amaçlı karar.

Bir ADR sessizce silinemez. Superseding ADR eski kararın nedenini,
etkilenen sistemleri ve geçiş durumunu belirtir.

## Model Lifecycle

```text
Experimental → Validated → Production → Sunset
```

- **Experimental:** davranış ve maliyet belirsiz.
- **Validated:** kalite, güvenlik, latency ve maliyet testleri geçmiş.
- **Production:** release gate’leri ve AI Quality Gate geçmiş.
- **Sunset:** yeni istek almıyor; replacement ve kapanış planı aktif.

Model değişimi Principle of Least Surprise kapsamındadır. Model değişimi AURA
karakterini, memory consent’i, identity davranışını veya output sözünü
değiştiriyorsa SDS sınıflandırması ve REP kanıtı zorunludur.

## Migration Lifecycle

```text
Planned → Dry Run → Staged → Executed → Verified → Closed
```

- **Planned:** kapsam, risk, owner ve rollback tanımlı.
- **Dry Run:** yalnızca okuma ve assessment; mutation yok.
- **Staged:** kontrollü ve geri alınabilir cohort.
- **Executed:** onaylı mutation uygulanmış.
- **Verified:** sonuçlar, ownership, integrity ve kullanıcı etkisi doğrulanmış.
- **Closed:** REP, audit ve rollback kayıtları tamamlanmış.

Production identity link veya user-data migration, `Dry Run` kanıtı olmadan
`Staged` durumuna geçemez. Migration kapanmadan yeni migration aynı kapsamı
örtbas edemez.

## Release Lifecycle

Release Constitution lifecycle’ı SLS ile birlikte yorumlanır:

```text
Draft → In Review → Blocked / Ready → Approved → Released → Rolled Back
```

Her release `releases/<version>/` altında REP ve bağlı kanıt artefact’larıyla
yaşar. REP yeni politika veya anayasal karar üretemez; yalnızca uygulanmış
kararın kanıtını ve Release Council sonucunu içerir.

## Constitutional Consistency Rule

Hiçbir belge, kendisinden daha üst anayasal seviyedeki belgeyle çelişemez.

Örnekler:

- STAS, Whitepaper veya Constitution ile çelişemez.
- Engineering Handbook, STAS ile çelişemez.
- Release Constitution, Constitution’daki temel ilkeleri geçersiz kılamaz.
- REP yeni politika oluşturamaz; yalnızca uygulanan kararın kanıtını içerir.
- Migration runbook, Security & Trust Standard’ın identity veya consent
  kurallarını gevşetemez.

Bir alt belge üst belgeyle çelişiyorsa alt belge `Blocked` veya `Proposed`
durumuna alınır. Önce üst seviye karar SDS ile alınır, sonra etkilenen
belgeler birlikte güncellenir.

## Document drift control

Governance Framework sahibi periyodik olarak:

- metadata alanlarını,
- broken references,
- lifecycle state tutarlılığını,
- supersedes/depends-on ilişkilerini,
- ADR ve REP bağlantılarını,
- üst-alt belge çelişkilerini

kontrol eder.

Drift bulunduğunda belge `Active` olarak kabul edilmez; düzeltme owner’ı,
etkilenen release’ler ve gerekiyorsa REP/ADR etkisi kaydedilir.
