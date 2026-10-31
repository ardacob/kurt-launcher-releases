# 0.6.4

Arkadaşlarına göndermek için tek dosyalı Windows Setup eklendi.

- `KurtLauncher-v0.6.4-Setup.exe` dosyasına çift tıklamak uygulamayı kullanıcı klasörüne kurar, masaüstü kısayolu oluşturur ve açar. Yönetici yetkisi, Python veya ZIP açma programı gerekmez.
- Oyunlar, modlar, profiller, dünyalar ve tema tercihleri ortak veri klasöründe korunur. Kurulum dosyasını sonradan silebilirsin. Daha yeni kurulu sürüm eski Setup ile düşürülmez.
- Launcher açıkken Setup ikinci bir kopya kurmaz. Yeni sürümler aynı ücretsiz GitHub otomatik güncelleme kanalından alınır; oyun ve sunucu kapandığında uygulanır.
- GitHub Actions her yeni sürüm için ücretsiz NSIS derleyicisini SHA256 ile doğrular, Setup üretir ve gerçek kurulum/başlangıç, tekrar çalıştırma, Türkçe dosya yolları, mod/dünya koruma ve geçici dosya temizliğini test eder. ZIP ve imzalı güncelleme paketleri de yayımlanmaya devam eder.

Setup Windows Authenticode sertifikası içermez; uygulama içi güncelleme paketleri mevcut Ed25519 yayıncı anahtarıyla imzalanır. Dokuz renk paleti ve önceki özellikler korunur.
