# Kurt Launcher

Minecraft Java Edition için Türkçe, bağımsız Windows launcher'ı. Geliştirme sürümüdür.

## İndir

[En yeni Windows sürümü](https://github.com/ardacob/kurt-launcher-releases/releases/latest)

ZIP dosyasını kendine ait yazılabilir bir klasöre çıkar ve `KurtLauncher.exe` dosyasını aç. Python kurulması gerekmez. Güncellerken mevcut `data` klasörünü koru; dünyalar, kurulumlar ve profiller burada saklanır. 0.4.0'dan 0.4.1'e ilk geçiş ZIP ile yapılır.

## Sürümler

Her sürüm sayfasında Windows ZIP'i ve SHA-256 doğrulama dosyası bulunur. Eski sürümler güncelleme kanalının en yeni sürümünü değiştirmez.

| Sürüm | Durum |
|---|---|
| [0.4.1](https://github.com/ardacob/kurt-launcher-releases/releases/tag/v0.4.1) | Güncel |
| [0.4.0](https://github.com/ardacob/kurt-launcher-releases/releases/tag/v0.4.0) | Arşiv |
| [0.3.1](https://github.com/ardacob/kurt-launcher-releases/releases/tag/v0.3.1) | Arşiv |
| [0.3.0](https://github.com/ardacob/kurt-launcher-releases/releases/tag/v0.3.0) | Arşiv |
| [0.2.0](https://github.com/ardacob/kurt-launcher-releases/releases/tag/v0.2.0) | Arşiv |
| [0.1.0](https://github.com/ardacob/kurt-launcher-releases/releases/tag/v0.1.0) | Arşiv |

## Çevrimiçi güncelleme

0.4.1 ve sonrası, açılışta GitHub Releases kanalını arka planda kontrol eder. Yeni sürüm varsa bildirim gösterilir; indirme ve yeniden başlatma kullanıcı onayıyla yapılır. Güncellemeler sayfasından otomatik kontrol kapatılabilir.

[İmzalı sürüm duyurusu](https://github.com/ardacob/kurt-launcher-releases/releases/latest/download/latest.json)

Duyuru Ed25519 yayıncı imzasıyla, indirilen paket SHA-512 ile ve paketin dosya listesi ayrıca yayıncı imzasıyla doğrulanır. Her sürümün paket adresi sabittir. Güncelleme kullanıcı verilerini içermez. Açılmayan yeni sürümde önceki uygulama dosyalarına geri dönüş desteği bulunur.

Windows EXE'si Authenticode yayıncı sertifikasıyla imzalanmamıştır. Güncelleme imzası bu sertifikadan farklıdır.

## Kapsam

- Ayrı oyun profilleri, görselli mod kataloğu ve uyumlu sürüm seçimi.
- Yerel yedekleme, mod paketi paylaşımı ve mod güncelleme araçları.
- Türkçe hata yardımcısı, koleksiyonlar ve donanıma göre ayar önerileri.
- Yerel sunucu yönetimi; davet bağlantıları için üçüncü taraf hizmetin hesabı ve koşulları geçerlidir.

Tüm Minecraft sürümleri, mod kombinasyonları ve farklı ağ bağlantıları tek tek doğrulanmamıştır. Ayrıntılı kullanım ve test kapsamı ZIP içindeki README.md ve DOGRULAMA.txt dosyalarındadır. Uygulama kaynakları ve üçüncü taraf lisansları dağıtım paketinde bulunur.

Minecraft lisansı bu uygulamayla verilmez. Hesap doğrulaması isteyen sunucular için lisanslı Microsoft hesabı gerekir; Microsoft girişinin geliştirici uygulama kaydı ve API izinleri ayrıca yapılandırılmalıdır.

**Resmî bir Minecraft ürünü değildir. Mojang veya Microsoft tarafından onaylanmamıştır ve bu şirketlerle bağlantısı yoktur.** Minecraft oyun dosyaları ve üçüncü taraf modlar dağıtım paketine dahil edilmez; ilgili kaynaklardan indirilir.
