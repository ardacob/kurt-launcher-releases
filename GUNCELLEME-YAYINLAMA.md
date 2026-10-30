# Ücretsiz çevrimiçi güncelleme yayını

Kurt Launcher 0.4.1, GitHub Releases üzerinde barındırılacak yayıncı imzalı güncelleme kanalına bağlanır. Alan adı, VPS, ücretli tünel veya ayrı bir sunucu satın alınmaz. GitHub hesabının kendi kullanım koşulları geçerlidir.

Depo: `ardacob/kurt-launcher-releases`

Sabit duyuru adresi:

`https://github.com/ardacob/kurt-launcher-releases/releases/latest/download/latest.json`

Kanal 0.4.1 ile yayımlandı. 0.1.0–0.4.1 arasındaki geçmiş Windows sürümleri de aynı deponun Releases bölümünde korunur.

## Otomatik yayın: GitHub Actions

Standart GitHub Actions çalıştırıcıları herkese açık bu depoda ücretsizdir. Ayrı sunucu, ücretli imzalama hizmeti veya kişisel erişim token'ı gerekmez.

1. Kod değişikliklerini hazırlayın. `src/core.py` içindeki `APP_VERSION` değerini daha önce yayımlanmamış, daha büyük bir sürüme artırın (örnek: `0.4.2`).
2. `release-notes.md` ilk satırını `# 0.4.2` yapın ve kullanıcıya görünen değişiklikleri yazın.
3. Değişiklikleri `main` dalına gönderin. **Windows build and signed release** akışı otomatik başlar.
4. Windows üzerinde testler, doğrulanmış Playit yardımcısı, EXE derlemesi ve paketlenmiş uygulamanın açılış kontrolü tamamlanır.
5. Ayrı bir Linux işi aynı yayıncı anahtarıyla `.kurtupdate` ve `latest.json` dosyalarını Ed25519 ile imzalar.
6. GitHub Release önce taslak olarak oluşturulur. Dört dosyanın yüklemesi ve GitHub SHA256 değerleri doğrulandıktan sonra yayın en güncel sürüm yapılır. Sürüm etiketi otomatik oluşturulur.

Pull request'lerde test ve derleme çalışır; imzalama/yayın çalışmaz. Aynı sürüm numarası tekrar gönderildiğinde yayımlanmış sürüm değiştirilmez. Eski bir sürüm en güncel kanalın üzerine yazılmaz. Başarısız bir akış Actions → Re-run failed jobs veya Run workflow üzerinden yeniden denenebilir; farklı dosyalar içeren bir taslağın üzerine sessizce yazılmaz.

### Bir defalık imzalama ayarı

Depo → Settings → Secrets and variables → Actions altında `KURT_SIGNING_KEY_B64` adında **Repository secret** gerekir. Değeri mevcut 32 baytlık özel Ed25519 anahtarının Base64 karşılığıdır. Mevcut kurulumların güvendiği `assets/update-public-key.bin` ile eşleşmelidir; yeni anahtar üretilmez.

Özel anahtar kaynak koduna, GitHub Release'e, Actions artifact'ına veya loglara yazılmaz. Şifreli Actions secret olarak saklanır ve yalnız imzalama adımına aktarılır. Geçici anahtar dosyası işlem sonunda silinir. Deponun yazma erişimi yayıncı yetkisidir; yalnız güvendiğiniz kişilere verin. Bağımsız güvenli anahtar yedeğinizi koruyun. Derleme işi anahtarı almaz; yayın işi GitHub'ın geçici `GITHUB_TOKEN` değerini kullanır.

Windows ZIP'leri bir gün saklanan geçici Actions artifact'larıdır; kalıcı indirmeler Releases üzerindedir. Oyun verileri, hesaplar ve `data` klasörü her iki paketin de dışındadır.

## Kullanıcının gördüğü akış

0.4.5, arşivi doğrulanmış kopyayla `%LOCALAPPDATA%\KurtLauncher\data` konumuna alır. Aktarım tamamlandığında eski launcher klasörü silinebilir; oyunlar ortak konumda kalır. Launcher `%LOCALAPPDATA%\KurtLauncher\app` içine otomatik kurulur ve masaüstü kısayolu oluşturulur. Eski güncelleme yardımcısının başlangıç kontrolü önce tamamlanır; büyük veri aktarımı ve ortak uygulama kurulumu bundan sonra yapılır. Birden fazla eski arşiv veya farklı bir dolu ortak arşiv varsa veriler birleştirilmez/üzerlerine yazılmaz.

1. Açılışta güncelleme kontrolü oyun/giriş düğmelerini kilitlemeden arka planda yapılır. Güncellemeler sayfasından kapatılabilir.
2. İmzalı latest.json doğrulanır. Yeni sürüm varsa uygulamada bir bildirim görünür.
3. Varsayılan otomatik kurulum açıkken sürüme özel HTTPS adresinden paket indirilir ve SHA-512 doğrulanır.
4. Paket içindeki dosya listesinin Ed25519 yayıncı imzası da doğrulanır.
5. Minecraft, yerel sunucu ve diğer işlemler bittiğinde uygulama otomatik kapanır ve yeniden açılır. Otomatik kurulum kapatılırsa indirme/kurulum onayı istenir.
6. Windows yardımcısı uygulama kapanınca dosyaları değiştirir. Yeni EXE başlangıç kontrolünü geçerse eski uygulama ve geçici kopyalar temizlenir. Kontrol geçmezse önceki uygulama geri yüklenir; data korunur ve aynı bozuk sürüm otomatik olarak tekrar tekrar denenmez.

0.4.0'da yayın adresi boş olduğu için 0.4.1'e ilk geçiş ZIP ile yapılır. Sonraki sürümler aynı çevrimiçi kanaldan bulunabilir. Yerel `.kurtupdate` dosyası seçimi de desteklenir.

## Yeni sürüm hazırlama

1. `src/core.py` içindeki APP_VERSION değerini artırın, testleri çalıştırın ve `build.ps1` ile Windows EXE'sini derleyin.
2. Elle yayın gerekiyorsa özel imzalama anahtarını kaynak/paket klasörü dışında tutun. Size ait güvenli bir yedeğini saklayın. Kaybolursa mevcut kurulumlar yeni bir anahtara ait paketi kendiliğinden kabul etmez. Anahtar hiçbir zaman kaynak deposuna veya uygulama paketine yüklenmez.
3. Paket ve çevrimiçi duyuruyu birlikte oluşturun. Örnek, 0.4.1 içindir; sonraki sürümde tüm sürüm numaraları değiştirilir:

```powershell
python sign_release.py --source release/KurtLauncher --key D:/private/release-signing-key.bin --output KurtLauncher-v0.4.1.kurtupdate --package-url https://github.com/ardacob/kurt-launcher-releases/releases/download/v0.4.1/KurtLauncher-v0.4.1.kurtupdate --feed-output latest.json --notes-file surum-notlari.txt
```

Örnekteki anahtar yolu kendi özel anahtar konumunuzla değiştirilir. Araç, paketin açık anahtarıyla özel anahtarın eşleştiğini denetler. `.kurtupdate` dosyasını imzalar, hash'ini hesaplar ve bu hash'i içeren latest.json dosyasını ayrıca imzalar. Oyun verileri imzalama listesinde bulunmaz.

## GitHub'da yayınlama

Normal yayınlar yukarıdaki Actions akışıyla yapılır. Aşağıdaki adımlar gerektiğinde elle yayınlama içindir; ücretli plan gerekmez.

1. Depoda yeni release'i önce **Draft** olarak hazırlayın; etiket örneğin `v0.4.1` olsun.
2. Windows ZIP'ini, `.kurtupdate` dosyasını, `latest.json` dosyasını ve ZIP'in SHA256 metnini ekleyin.
3. Dosyalar tamamen yüklendikten sonra taslağı yayınlayın. Duyurudaki paket adresi o release'in sürüme özel adresi olmalıdır.
4. Anonim bağlantıyla sabit latest.json adresinin ve paket indirmesinin açıldığını doğrulayın. Uygulamada Güncellemeleri kontrol et düğmesini deneyin.

Güncellemenin güveni yalnızca HTTPS'e dayanmaz: latest.json, paket hash'i ve paket içindeki dosya listesi doğrulanır. Çalışan bir sürüme geri dönmek gerekiyorsa sürüm numarası yeni bir düzeltme sürümü olarak artırılır; eski/aynı sürüm paketleri normal güncellemede reddedilir.

İşlem sonuçları `data/updates/*.result` altındadır. Uygulamanın geri dönüş kopyaları `.kurt-rollback-*`; oyun/profil yedekleri `data/backups` altındadır. Ed25519 güncelleme imzası Windows Authenticode yayıncı sertifikası değildir.
