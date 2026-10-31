# 0.6.3

Görseldeki dokuz paletten isimli temalar eklendi.

Görseldeki sırayla:

| Sol | Orta | Sağ |
| --- | --- | --- |
| Gece Leylağı | Ahududu | Zeytin Bahçesi |
| Pastel Toprak | Mercan Nane | Tropik Gün Batımı |
| Köz Gecesi | Şeftali Kreması | Gül Kömürü |

- Ayarlar → Görünüm altında orijinal dört rengini gösteren, klavyeyle de seçilebilen 3×3 tema kartları bulunur. Bir karta tıklamak temayı hemen uygular ve kaydeder. Adlar Türkçe/İngilizce arayüzle çevrilir; tema kimliği aynı kalır.
- Renkler arka plan, yan menü, kartlar, formlar, tablolar, seçili/odak durumları, düğmeler, indirme çubuğu ve ana ekran manzarasına uygulanır. Eksik görsel yer tutucuları da uygulama paletini kullanır; yapımcı görselleri değiştirilmez.
- Palet önizlemeleri referans görselden alınan HEX renklerini korur. Uygulamada okunabilir metinler ve yüzeyler için bunlardan açık/koyu tonlar türetilir; dokuz temanın metinleri ve düğme gradyanları en az 4.5:1 kontrastla denetlenir.
- Eski özel vurgu rengi yeni paleti gizlemez. Saklanan özel renk silinmez; Vurgu rengini seç ile ayrıca uygulanabilir, Paletin varsayılan vurgusu ile palete dönülebilir.
- Gün doğumu, Sunset, Sistem ve Yüksek kontrast seçenekleri korunur. Güncelleme aktif temanı değiştirmez; yeni paleti kendin seçebilirsin. Profiller, modlar ve dünyalar ortak arşivde kalır.

256 uygulama testi (yerelde yetki gerektiren bir symlink senaryosu atlandı) ve 9 yayın testi. Palet metin/gradyan kontrastları, kart seçimi ve kalıcılığı, eski vurgu rengi, İngilizce ad/klavye seçimi ve her palet için ayrı manzara çizimi doğrulanır. Windows EXE, imza ve gerçek yerinde yeniden açılış kontrolleri ücretsiz otomatik yayında çalışır.
