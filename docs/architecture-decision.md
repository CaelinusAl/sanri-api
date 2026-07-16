# SANRI OS Backend API Foundation

## Karar

Yeni istemci sözleşmesi `/v1` altında, mevcut SANRI route'larından izole edilir.
Mobil ve web istemcileri yalnızca SANRI API'ye bağlanır; model sağlayıcısı API
anahtarı hiçbir zaman istemciye gönderilmez.

## Dikey akış

1. İstemci Supabase Auth access token'ı `Authorization: Bearer <jwt>` ile gönderir.
2. API JWT'yi Supabase JWT secret ile doğrular ve `sub` claim'ini kullanıcı kimliği
   olarak kullanır.
3. API konuşma ve mesaj sahipliğini her sorguda `user_id` filtresiyle kontrol eder.
4. `AuraEngine`, versiyonlu AURA talimatını ve izin verilmiş hafıza özetini oluşturur.
5. `OpenAIProvider`, `AIProvider` protokolü üzerinden Responses API'yi çağırır.
6. Delta'lar streaming olarak istemciye aktarılır; tamamlanan kullanıcı ve asistan
   mesajları veritabanına yazılır.
7. Sağlayıcı metrikleri (token, süre, tahmini maliyet) yalnızca hassas içerik olmadan
   loglanır.

## Neden mevcut kodu taşımıyoruz?

`sanri-api` bugün yerel `users` tablosu ve HS256 uygulama token'ı kullanan çok sayıda
çalışan route içeriyor. Bu foundation, mevcut davranışı silmeden yeni Supabase Auth
tabanlı sözleşmeyi `/v1` ile başlatır. Geçiş tamamlandığında eski route'lar ayrıca
değerlendirilebilir.

## Veri ve güvenlik

- Yeni foundation tabloları `user_id UUID` taşır ve Supabase `auth.users(id)` ile
  ilişkilidir.
- RLS tüm foundation tablolarında aktiftir.
- API, connection pool üzerinden çalıştığı için uygulama katmanındaki sahiplik
  filtresi RLS'nin tamamlayıcısıdır; istemciye `service_role` anahtarı verilmez.
- Hafıza yalnızca `memory_consent=true` gönderildiğinde kaydedilir.
- Ham kullanıcı/yanıt metni loglanmaz; yalnızca kimliksiz metrikler loglanır.

## Gelecek genişlemeleri

`AIProvider` arayüzü OpenAI dışındaki veya self-hosted sağlayıcıları eklemek için
tek değişim noktasıdır. `mode` alanı ilk olarak `aura` ve `reflection` değerlerini
destekler; karakter/mod sistemi genişletilebilir.
