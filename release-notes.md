# 0.6.1

Modern açık/koyu tema ve sekiz yeni oyun aracı.

- **Yeni görünüm:** Açık Gün doğumu (varsayılan), koyu Sunset, sistem ve yüksek kontrast temaları. Sade kartlar, okunaklı tablolar ve klavye odak göstergeleri. Tema, Türkçe/İngilizce arayüz ve %90–140 ölçek Görünüm bölümünden anında uygulanır. Profil adları ve üçüncü taraf açıklamaları korunur.
- **Dünyana devam et:** Ana ekranda aktif profilin en son oynanan dünyası; Dünyalarım ekranında seçili dünya. Quick Play destekleyen Minecraft Java sürümleri gerekir (1.20+). Dünya ve profil sürümü farklıysa doğrudan açma durdurulur; launcher dünya verisini dönüştürmez.
- **Favori sunucular:** Ad/adres ve kullanılacak profil kaydedilir. Gerçek Java durum sorgusu, sürüm, oyuncu sayısı ve ping; kayıtlı profille katılım. Özel port adresin sonuna yazılır; DNS SRV otomatik port keşfi yapılmaz.
- **Başka launcher’dan aktar:** Resmî .minecraft ve Prism/MultiMC taraması; oyun/yükleyici önizlemesi, elle düzeltme ve dünyaları dahil etme seçeneği. Modlar, config, paketler ve oyun ayarları doğrulanarak ayrı profile kopyalanır. Kaynak korunur; hesaplar, token'lar ve özel JVM komutları alınmaz. İlk Oyna gerekli Minecraft/Java dosyalarını ortak arşive hazırlar.
- **Tıklanabilir davet:** Sunucunun kodundan kurt://join/ bağlantısı kopyalanır. Kurulu Windows uygulaması bağlantıyı açar; zaten açıksa mevcut pencereye aktarır. Adres/sürüm önizlemesinden sonra mevcut mod karşılaştırma ve onaylı katılım akışı kullanılır. Çok uzun davetler kod veya mod listesi dosyasıyla paylaşılır.
- **Donanıma göre shader:** Yerel ekran kartı adı ve RAM ile temkinli başlangıç sınıfı önerilir. Modrinth'in gerçek düşük/potato, orta ve yüksek performans etkisi etiketleriyle uyumlu shader aranır. Bu, FPS/VRAM ölçümü veya performans garantisi değildir; etiketler yapımcılardan gelir.
- **Dünya geçmişi:** Tarihli geri dönüş noktaları. Aynı SHA-512 içeriğine sahip değişmeyen dosyalar bir kez saklanır. Her noktada toplam boyut ve yeni saklanan alan görünür. Hızlı devam öncesi otomatik nokta varsayılan açıktır ve kapatılabilir. Geri yükleme mevcut dünyayı önce ZIP olarak korur ve doğrulanmış güvenli değişimi kullanır. Geçmiş yereldir, otomatik silinmez; Depolama ekranında Yedekler altında sayılır.
- **Oyun istatistikleri:** Bu sürümden itibaren profil başına toplam oturum süresi ve son 100 oturum. Menü süresi dahildir. Launcher kapalıyken geçen süre ölçülmez; ani kapanan oturum kesintili gösterilir. Veriler yalnız bilgisayarda tutulur.
- **Erişilebilirlik:** Ölçekli yazı ve kontroller, yüksek kontrast, erişilebilir kontrol adları, Tab ile dolaşma. Ctrl+1 ana ekran, Ctrl+2 modlar, Ctrl+3 dünyalar, Ctrl+, ayarlar, F6 profil, Ctrl+Enter Oyna.

Araçlar: Ana ekran → hızlı devam/favoriler/aktarım; Kütüphane → Yönetim → Favori sunucular, Dışarıdan aktar, Oyun istatistikleri; Dünyalarım → Dünya geçmişi; Kütüphane → Görünüm → tema/dil/ölçek.

Ortak oyun arşivi, profiller, Minecraft sürümleri, modlar ve dünyalar korunur. Ücretli hizmet gerekmez. GitHub Actions test, Windows derleme, yayıncı imzası ve otomatik yayını aynı ücretsiz kanalda sürdürür.

Doğrulama: 250 uygulama testi ve 9 yayın testi; gerçek yerel Java durum/ping sunucusu, farklı süreçler arasında davet aktarımı, kaynak hash'lerini koruyan kopya, değişen dosyalı geri dönüş ve bozuk yedek koruması. Windows açık/koyu arayüzü kontrol edildi. Paket CI üzerinde gerçek EXE başlangıcı ve yerinde otomatik yeniden açılışla ayrıca kontrol edilir.

