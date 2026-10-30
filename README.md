# Kurt Launcher 0.4.9

[En yeni Windows sürümünü indir](https://github.com/ardacob/kurt-launcher-releases/releases/latest) · [Tüm sürümler](https://github.com/ardacob/kurt-launcher-releases/releases) · [Otomatik derleme](https://github.com/ardacob/kurt-launcher-releases/actions/workflows/release.yml)

## 0.4.8: Shaderpack atölyesi

Sol menüde **Shaderpack’ler** bölümünden Modrinth'in Iris/OptiFine paketlerini görselleriyle keşfedebilirsiniz. Arama, en çok indirilen, en yeni ve son güncellenen sıralaması, sayfalama ve shader desteği filtresi bulunur. Her satırda açıklama, indirme sayısı, gerçek paket sürümü, Minecraft uyumluluğu, yapımcı ve yayın tarihi gösterilir. Destek bilgileri yapımcının yayımladığı sürümlerden doğrulanır; donanımda çalışma garantisi değildir.

**İndir** düğmesi ZIP'i yüzde göstergesiyle indirir, SHA-512 ve shader arşivi yapısını doğrular ve seçili profilin `shaderpacks` klasörüne kurar. Dosya mods klasörüne taşınmaz veya açılmaz. **İndirilen shaderpack’ler** sekmesinden yerel ZIP ekleyebilir, paketleri görebilir, kaldırabilir ve klasörü açabilirsiniz. Profillerin paketleri birbirinden ayrıdır; ortak oyun arşivinde ve profil yedeklerinde korunur.

Shaderpack kullanmak için uygun Iris veya OptiFine kurulumu gerekir. Uyumlu Fabric/NeoForge profilinde **Iris’i kur** düğmesi Iris'i ve gerekli mod bağımlılıklarını kurar; desteklenmeyen Minecraft/yükleyici sürümünde işlem durur. OptiFine kullanıyorsanız kurulumunu ayrıca yapabilirsiniz. İndirdikten sonra paketi Minecraft'ın **Video ayarları → Shader Packs** menüsünden seçin. İndirildi etiketi, oyunda etkin olduğu anlamına gelmez. Oyun çalışırken paket değişikliği engellenir; değişiklik öncesi mevcut otomatik yedekleme tercihi kullanılır.

Kaynaklar: [Modrinth arama API'si](https://docs.modrinth.com/api/operations/searchprojects/), [Iris indirme ve yükleyici bilgisi](https://irisshaders.dev/download/).

## 0.4.5: ortak oyun klasörü ve tam otomatik güncelleme

Oyunlar, Java, modlar, dünyalar, profiller, ayarlar ve sunucular `%LOCALAPPDATA%\KurtLauncher\data` içinde tutulur. Eski arşiv önce bu klasöre kopyalanır ve bütün dosyaların SHA-512 değerleri doğrulanır; ancak sonra ortak konum kullanılmaya başlanır. Aktarım sırasında yüzde görünür. Eski launcher klasörü silinse de ortak arşiv kalır; oyunları yeniden indirmek gerekmez.

Launcher `%LOCALAPPDATA%\KurtLauncher\app` içine bir kez kurulur ve masaüstüne **Kurt Launcher** kısayolu eklenir. Yeni sürümler açılışta ve uygulama açıkken beş dakikada bir aranır; varsayılan olarak otomatik indirilir, imzası doğrulanır, kurulur ve yeniden açılır. Oyun, sunucu veya başka bir işlem çalışıyorsa bitmesi beklenir. Yeni sürüm açıldıktan sonra eski uygulama kopyası, geri dönüş dosyaları ve geçici kurulum temizlenir. Yeni sürüm açılmazsa eski uygulama geri yüklenir; aynı bozuk sürüm durmadan denenmez. Güncellemeler sayfasından otomatik kurulum kapatılabilir.

İlk geçişte kayıtlı veya yakındaki eski oyun arşivi bulunur; birden fazla arşiv varsa seçim istenir. **Ayarlar → Eski oyun klasörünü seç…** ile eski launcher veya data klasörü seçilerek doğrulanmış aktarım yapılabilir. Oyun/sunucu dünyası kullanımdaysa aktarım başlamaz. Ortak klasörde farklı bir arşiv varsa dosyalar karıştırılmaz veya üzerlerine yazılmaz. Konum ve aktarım kaydı yalnız bu bilgisayarda tutulur; kullanıcı verileri GitHub'a yüklenmez. Profilin Minecraft sürümü ve mod yükleyicisi korunur.

## Ücretsiz otomatik yayın

`main` dalına gönderilen değişiklikler GitHub Actions üzerinde test edilip Windows EXE'sine derlenir. `src/core.py` içindeki `APP_VERSION` artırılmışsa başarılı derleme aynı yayıncı anahtarıyla imzalanır ve GitHub Releases'e otomatik yayımlanır. Sürüm notları `release-notes.md` dosyasında tutulur. Mevcut sürümler yeniden yazılmaz; hesaplar ve oyun verileri pakete alınmaz. Kurulum ve yeniden deneme adımları [yayın belgesindedir](GUNCELLEME-YAYINLAMA.md).

Geçmiş sürümler: [0.4.1](https://github.com/ardacob/kurt-launcher-releases/releases/tag/v0.4.1), [0.4.0](https://github.com/ardacob/kurt-launcher-releases/releases/tag/v0.4.0), [0.3.1](https://github.com/ardacob/kurt-launcher-releases/releases/tag/v0.3.1), [0.3.0](https://github.com/ardacob/kurt-launcher-releases/releases/tag/v0.3.0), [0.2.0](https://github.com/ardacob/kurt-launcher-releases/releases/tag/v0.2.0), [0.1.0](https://github.com/ardacob/kurt-launcher-releases/releases/tag/v0.1.0).

Windows x64 için Türkçe Minecraft **Java Edition** launcher'ı. Siyah ve sunset teması, kullanıcı adıyla giriş, görselli mod kataloğu, yerel sunucu yönetimi ve ücretsiz internet davetleri içerir. Arşivde yayımlanan sürümleri Mojang'dan alır; sabit bir sürüm listesine bağlı kalmaz. Geliştirme sürümüdür.

## 0.4.1: düzenli menü ve çevrimiçi güncelleme

Sol menüde **Oyun alanı** altında Oyun merkezi, Mod atölyesi, Kütüphane ve Sunucular yer alır. **Uygulama** bölümü alttadır: Güncellemeler, Günlük ve Ayarlar. Oyuncu hesabı ayrı karttadır. Sayfaların işlevleri korunur; güncelleme sayfasının kendi menü seçimi vardır.

Ücretsiz GitHub Releases kanalı `https://github.com/ardacob/kurt-launcher-releases/releases/latest/download/latest.json` adresine bağlanır. Kontrol arka planda yapılır; 0.4.5'ten itibaren doğrulanmış yeni sürüm uygun olduğunda otomatik kurulur ve yeniden açılır. Otomatik kontrol ve kurulum Güncellemeler sayfasından kapatılabilir. İmzalı sürüm bilgisi, paket hash'i ve paket içi yayıncı imzası ayrı ayrı doğrulanır. Her sürümün indirme adresi sabittir; latest.json yalnız en yeni sürümü duyurur.

İlk GitHub yayını yapılmadan kanal "ilk yayını bekliyor" bildirir; bu durum "launcher güncel" diye gösterilmez. Özel anahtar, hesaplar, oyunlar, modlar ve dünyalar yayına alınmaz. 0.4.0'ın yayın adresi boş olduğundan bu sürüme ilk geçiş ZIP ile yapılır; sonraki sürümler aynı kanal üzerinden bulunabilir. Çevrimiçi yayın adımları `GUNCELLEME-YAYINLAMA.md` dosyasındadır.

## 0.4.0 ile gelen araçlar

Sol menüdeki **Kütüphane** bölümünde yedi sekme bulunur:

- **Yedekler:** Profil/sunucu seçin, şimdi yedekleyin veya seçili yedeği geri yükleyin. Geri yüklemeden önce mevcut durum ayrıca yedeklenir. Otomatik yedek varsayılan açıktır; mod ekleme/kaldırma/etkinlik değişikliği, mod güncelleme, oyun onarımı, görüntü ayarı ve sunucu ayarları öncesinde çalışır. Sunucu açılmadan önce ve normal kapandıktan sonra da yedeklenir. Varsayılan son 5 otomatik yedek saklanır; elle alınan yedekler otomatik silinmez. Oyun veya ilgili sunucu çalışırken dosya yedeği/geri yükleme yapılmaz. Yedekler yereldir; donanım arızasına karşı haricî kopya ayrıca gerekir.
- **Paket paylaş:** `.mrpack` dosyası seçerek Minecraft/yükleyici, indirme boyutu ve dosya sayısını görün; onaydan sonra yeni ve ayrı profile kurun. İsteğe bağlı istemci dosyaları seçilebilir. Paketin belirttiği yükleyici sürümü sabitlenir. Oyun/Java, Oyna veya Kur / onar ile hazırlanır. Dışa aktarım JAR'ları kopyalamaz; doğrulanmış mod indirme adresleri ve hash'leri paylaşılır. Kapalı modlar dışa aktarılmaz. Kaynağı bulunamayan/değiştirilmiş yerel mod varsa açıklamalı olarak durur. Config paylaşımı ayrıca işaretlenir; önce içeriğini kontrol edin. İçe aktarılan modlar/betikler oyun içinde kod çalıştırabilir; güvenilir paketleri seçin.
- **Mod güncellemeleri:** Uyumlu sürümleri kontrol edin, değişiklik açıklamasını okuyun ve işaretlediklerinizi güncelleyin. İşlem geçici profilde hazırlanır; bağımlılık çatışması/indirme hatasında eski modlar kalır. Kurulu modlar ekranından sürümü sabitleyebilir veya sabitlemeyi kaldırabilirsiniz. Yerel, Modrinth kaydı olmayan modlar otomatik güncellenmez.
- **Koleksiyonlar:** Mod keşfetteki **☆ Kaydet** ile Favoriler'e veya kendi adlandırdığınız koleksiyonlara ekleyin. Kaydedilen modu aktif profil filtreleriyle tekrar arayın. Veriler yalnız bu bilgisayarda tutulur.
- **Performans:** Toplam/kullanılabilir bellek ve boş diski görün. Önerilen RAM'i kaydedin veya aktif profile düşük/dengeli/yüksek görüntü ayarı uygulayın. Diğer options.txt ayarları korunur. Bu bir FPS garantisi değildir; eski sürümler bazı ayarları tanımayabilir.
- **Görünüm:** Sunset vurgu rengini, kompakt/geniş mod listesini ve profil kapağını seçin. Kapaklar ana ekrandaki son kullanılan profil listesinde gösterilir; çift tıklama profili seçer. Mod ayrıntılarında, varsa yapımcının yayımladığı ilk altı ekran görüntüsü gösterilir. Görseli çift tıklayarak açabilirsiniz.
- **Launcher güncellemesi:** Soldaki Güncellemeler kısayolundan çevrimiçi kanalı kontrol edin veya yayıncı anahtarıyla Ed25519 imzalanmış `.kurtupdate` paketi seçin. Veri klasörü güncelleme listesine alınamaz. Windows yardımcısı uygulama kapanınca yeni dosyaları kurar; yeni EXE başlangıç kontrolünü geçemezse eski uygulama dosyalarına döner. Yayınlama bilgileri `GUNCELLEME-YAYINLAMA.md` dosyasındadır. Güncelleme imzası, Windows Authenticode sertifikası değildir; launcher EXE'si Windows yayıncı sertifikasıyla imzalanmamıştır.

**Günlük → Oyun/Sunucu hatasını incele**; Java, bellek, eksik bağımlılık, kopya mod, grafik, port, hesap doğrulama ve bağlantı hata kalıpları için Türkçe öneriler sunar. Bu yerel bir kural motorudur; çevrimiçi yapay zekâ servisi gerekmez. Rapor otomatik gönderilmez. Token, kullanıcı klasörü ve IP gibi bilinen kalıplar filtrelenir; paylaşmadan önce raporu inceleyin. Her kişisel bilgi veya hata yakalanamayabilir.

Alt çubuktaki **İndirmeler** düğmesi geçerli işlem, yüzde, dosya boyutu/hızı, tahmini süre ve mod/paketlerin bekleyen dosyalarını gösterir. Minecraft/Java indirmeleri de akış halinde ölçülür. Bilinmeyen toplam için sahte süre/yüzde üretilmez. Hata sonrası **Tekrar dene**, işlemi yeniden başlatır; Minecraft'ın doğrulanmış mevcut dosyaları yeniden kullanılabilir. İndirmelerde byte düzeyinde kaldığı yerden devam etme garantisi yoktur.

Ana ekrandaki **Profil sürümünü değiştir**, zorunlu güvenlik yedeği aldıktan sonra sürümü değiştirir. Eski modlar removed-mods altında korunur; yeni sürüme uygun modları ayrıca kurmalısınız. Eski Minecraft sürümüyle yeni bir dünyayı açmak veri kaybına yol açabilir; geri dönüş için yedeği kullanın.

## Arkadaşlarla aynı modları kullanma

Sunucu sahibi **Kütüphane → Paket paylaş → Sunucu mod listesi oluştur** ile `.kurtmods.json` dosyası paylaşabilir. Arkadaş, uygun profili seçip **Mod listesiyle karşılaştır** düğmesini kullanır. Modlar dosya adıyla değil SHA-512 içeriğiyle karşılaştırılır. Eksik/farklı modlar, yerel dosyalar ve fazladan istemci modları gösterilir. Otomatik kaynak varsa kullanıcı onayından sonra kurulur; eski Modrinth sürümü tanınabiliyorsa yerine yenisi geçirilir. Kaynağı bilinmeyen yerel JAR için sunucu sahibinden izinli kaynağı istemelisiniz. Mod listesi tam çalışma zamanı uyumluluğu garantisi değildir.

0.4.0 davetleri mod listesini **KURT2-** koduna ekleyebilir. Arkadaş önce uyumluluk ekranını görür, onaylı kurulumdan sonra kodu yeniden girmeden oyuna katılabilir. KURT1 kodları desteklenmeye devam eder; KURT2 için her iki tarafta 0.4.0 gerekir. Çok büyük mod listeleri kod yerine dosyayla paylaşılır. Kodda parola/erişim anahtarı yoktur; kodu bilenlerin kimliği bu kodla doğrulanmaz.

**Sunucular** sayfasının altındaki panelden zorluk, oyun modu, görüş mesafesi, RAM, oyuncu sınırı ve izin listesi yönetilir. Ayar değişiklikleri sunucu kapalıyken uygulanır. Çalışırken oyuncu listesi ve list komutunun yanıtı gösterilir. Microsoft doğrulamalı sunucuda oyuncu ekleme işlemi çalışır sunucunun kendi whitelist komutuyla yapılır. Kullanıcı adıyla katılımda whitelist kimlik doğrulama sağlamaz.

## Başlatma

`KurtLauncher.exe` dosyasını bir kez açın. Python veya yönetici kurulumu gerekmez. Ortak arşiv doğrulandıktan sonra launcher kullanıcıya ait uygulama klasörüne kurulur; sonraki açılışlarda masaüstündeki **Kurt Launcher** kısayolunu kullanabilirsiniz. **Ayarlar → Veri klasörü** ortak oyun konumunu açar.

1. Oyun merkezinden sürüm kanalı, Minecraft sürümü ve mod yükleyicisi seçin.
2. **Profil oluştur** ile profilinize bir ad verin.
3. **Kur / onar** ile Minecraft, gerekli Java ve seçilen yükleyiciyi indirin. İnternet ve yeterli disk alanı gerekir.
4. **Mod atölyesi → Mod keşfet** bölümünde modları inceleyip kurun. **Kurulu modlar** sekmesindeki **.jar dosyası ekle** ile kendi modlarınızı da seçebilirsiniz.
5. Sol altta **Kullanıcı adıyla** seçeneğini kullanın, adınızı yazıp **Giriş yap** düğmesine basın; ardından **Oyna** düğmesini kullanın. Kullanıcı adı modundaki giriş düğmesi Microsoft ekranı açmaz, uygulama kimliği istemez ve adınızı yerel olarak kaydeder. İsterseniz giriş yöntemini **Microsoft hesabı** olarak değiştirebilirsiniz; Microsoft giriş düğmesi o modda görünür.

Kullanıcı adı 3–16 karakter olmalı; İngilizce harf, rakam ve `_` kullanılabilir. Aynı ad aynı çevrimdışı oyuncu kimliğini üretir; adı değiştirince oyuncu kimliği de değişir. Kullanıcı adıyla giriş, tek oyunculu oyunlar ve hesap doğrulaması istemeyen sunucular içindir. Microsoft doğrulaması isteyen sunucular için gerçek hesap girişi gerekir. İlk oyun/Java/mod indirmesinde internet gerekir; kurulu profil kullanıcı adıyla açılırken Microsoft servisine veya kurulum API'lerine bağlanılmaz. Eksik/bozuk dosyalar için **Kur / onar** kullanılmalıdır.

Eski sürümden güncellerken paketi aynı klasöre çıkarabilirsiniz. Mevcut `data` klasörünü koruyun; dağıtım paketi oyun dünyalarını içermez.

## İlerleme yüzdesi ve mod sıralaması

Alt durum çubuğunda geçerli indirme/kurulum aşamasının yüzdesi görünür. Boyutu veya işlem sayısı bilinen aşamalar `%0`–`%100` olarak ilerler. Toplamı henüz bilinmeyen ağ/kurulum işlemleri **İşleniyor…** olarak gösterilir. Her yeni aşamada yüzde yeniden başlayabilir; bu, önceki indirmenin silindiği anlamına gelmez. İşlem tamamlanınca `%100`, hata veya iptalde ilgili durum ve varsa son yüzde gösterilir.

Mod atölyesindeki sıralama menüsünde **En çok indirilen**, **En yeni**, **Son güncellenen** ve **Aramaya göre** seçenekleri bulunur. Sıralama, arama metni ve Minecraft/yükleyici filtresiyle birlikte tüm sonuçlara uygulanır; yalnızca görünen sayfa yeniden dizilmez. Sıralama değişince ilk sayfaya dönülür. Her modun toplam indirme sayısı satırında görünmeye devam eder.

## Güncellemede kurduklarım korunur mu?

Evet. **Sürümleri yenile** yalnızca resmî sürüm listesi önbelleğini günceller. Minecraft dosyaları, modlar, profiller, dünyalar ve sunucular silinmez. Launcher paketini güncellerken yeni dosyaları mevcut launcher klasörüne çıkarın ve **`data` klasörünü silmeyin veya değiştirmeyin**. Paketin içinde `data` yoktur.

0.4.5'in ortak klasöre aktarımı tamamlandıktan sonra eski launcher klasörlerini silmek oyunları etkilemez. İlk geçişte eski klasör bulunamazsa **Ayarlar → Eski oyun klasörünü seç…** üzerinden seçip aktarımın tamamlanmasını bekleyin. Farklı bir Minecraft sürümü için oluşturulan yeni profilin mod klasörü ayrıdır; uyumlu modlar o profile ayrıca eklenir.

## Ücretsiz, port açmadan davetle oynama

Minecraft Java için **Playit'in ücretsiz Global tüneli** kullanılır. Ücretli bölge, özel alan adı, abonelik veya satın alma çağrısı yoktur. Hizmetin ücretsiz kotası ve erişilebilirliği geçerlidir; sınırsız veya kalıcı ücretsiz hizmet garantisi verilemez. Sunucu kendi bilgisayarınızda çalışır.

**Sunucuyu açan kişi:**

1. **Sunucular → Ücretsiz bağlantıyı kur** düğmesine basın. Tarayıcıda Playit'in ücretsiz hesap/cihaz bağlantısını kendiniz onaylayın. Minecraft/Microsoft hesabı bu bağlantı için gerekli değildir. Kart veya Premium satın alma gerekmez.
2. Sunucuyu oluşturup EULA'yı onaylayın ve başlatın. Konsolda **Done** mesajı çıkınca **Davet oluştur** düğmesine basın.
3. Tünel servisi ve yerel yardımcı hazır olduğu doğrulanınca `KURT1-` ile başlayan kod görünür. **Kodu kopyala** ile arkadaşınıza gönderin. Yönetim anahtarı bu koda eklenmez.
4. **Paylaşımı kapat** tünel yardımcısını durdurur. Yerel Minecraft sunucusu açık kalabilir. Sunucu veya launcher kapanınca internet paylaşımı da kapanır. Kod o sırada çalışır bir tünel gerektirir.

**Katılacak arkadaş:**

1. Kurt Launcher 0.3.0 veya yenisini açıp kullanıcı adını yazın ya da Microsoft girişi kullanın.
2. **Sunucular** ekranındaki arkadaş daveti alanına kodu yapıştırıp **Davetle katıl** düğmesine basın.
3. Launcher resmî listede sürümü doğrular, uygun Minecraft/Fabric profilini seçer veya oluşturur ve oyunu sunucu adresiyle açar. Yeni Minecraft sürümlerinde Quick Play, eski sürümlerde doğrudan sunucu argümanları kullanılır.

Arkadaşların Playit kurmasına veya Playit hesabı açmasına gerek yoktur. İlk oyun/Java/Fabric kurulumu için internet gerekir. Kod mod dosyalarını dağıtmaz; KURT2 kodundaki listeyle eksik modlar kullanıcı onayından sonra kaynağından indirilebilir. Giriş yöntemi sunucunun hesap doğrulama ayarıyla uyumlu olmalıdır.

**Ücretsiz kurulumda sorun olursa:** **Ücretsiz panel** düğmesiyle Playit panelini açın. Sunucunuzu çalıştıran launcher ajanı için **Minecraft Java** tüneli, **Global** bölge ve `127.0.0.1` ile sunucunuzun yerel portunu seçin. Sonra **Davet oluştur** düğmesini tekrar kullanın. Servis kota veya izin nedeniyle reddederse launcher ücretli pakete geçmez; kullanılmayan ücretsiz tüneli panelden kaldırmanız veya ücretsiz hesabın e-posta doğrulamasını tamamlamanız gerekebilir.

Davet kodu bağlantı adresi ile oyun/yükleyici bilgisini taşır; tek kullanımlık parola veya erişim kontrolü değildir. Kodun yanlış kopyalanması kontrol toplamıyla algılanır. Özel erişim gerekiyorsa sunucunun whitelist özelliğini kullanın. İnternet trafiği Playit üzerinden geçer; modem port yönlendirme veya arkadaş tarafında VPN gerekmez. Windows hizmeti/otomatik başlangıç kurulmaz. İmzalı Playit 1.2.0 yardımcısı yalnız host düğmesiyle çalışır; SHA-256 doğrulanır. Ajan anahtarı Windows kasasında, kısa süreli yardımcı dosyası kullanıcıya özel erişim izinleriyle tutulur ve silinir.

[Ücretsiz Minecraft Java desteği](https://playit.gg/) · [Yardımcı kaynak kodu ve sürümü](https://github.com/playit-cloud/playit-agent/releases/tag/v1.2.0)

## Özellikler

- Resmî Mojang manifestindeki release, snapshot/ön sürüm, old_beta ve old_alpha kanalları; aranabilir sürüm seçimi.
- Vanilla, Fabric, Forge, NeoForge ve Quilt. Profil oluşturulurken yükleyicinin sürüm desteği kontrol edilir. Yükleyicinin ilk kurulan sürümü profile sabitlenir.
- Profiller için ayrı dünyalar, modlar, oyun ayarları ve günlükler; ortak oyun kütüphanesi ve Java önbelleği.
- Modrinth arama ve sayfalama; Minecraft/yükleyiciye göre filtreleme; zorunlu bağımlılıkları çözme; bildirilen uyumsuzlukları denetleme.
- Mod satırlarında gerçek logo, sürüm numarası, kısa açıklama, içerik kategorileri, desteklenen Minecraft sürümleri/yükleyiciler, zorunlu bağımlılık sayısı ve yayın tarihi. **Ayrıntılar** yapımcının tam açıklamasını açar. Kurulumda ekranda gösterilen mod sürümü kullanılır.
- Mod logoları Modrinth CDN'den alınarak yerelde önbelleğe kaydedilir. Görseli olmayan veya indirilemeyen modlarda sunset tonlarında baş harf simgesi gösterilir. Kurulu modların eski kayıtları **Bilgileri güncelle** ile tamamlanabilir. Yerel JAR uyumluluğu otomatik biliniyormuş gibi gösterilmez.
- Siyah zemin, turuncu/mercan/pembe/mor vurgular, gün batımı manzarası ve yeni uygulama simgesi.
- SHA-512 doğrulamalı indirme. Bütün dosyalar hazırlanmadan modlar etkin klasöre taşınmaz; hata veya iptalde yeni dosyalar geri alınır.
- Mod açma/kapatma. Bağımlı bir mod etkinken gerekli modun kapatılması/kaldırılması engellenir. Kaldırılan JAR dosyaları profilin `removed-mods` klasöründe saklanır.
- Yerel JAR içe aktarma, RAM ve özel Java seçimi, kurulum ilerlemesi, iptal, işlem/oyun günlüğü, çevrimdışı sürüm listesi önbelleği.
- Microsoft tarayıcı girişi: PKCE + state kontrolü; yenileme anahtarı Windows Kimlik Bilgisi Yöneticisi'nde tutulur. Hesap parolası launcher'a girilmez.

## Arkadaşlarla sunucuda oynama

1. **Sunucular** bölümünde ad, kararlı Minecraft sürümü, **Vanilla** veya **Fabric**, port, RAM ve oyuncu sayısı seçip **Oluştur** düğmesine basın. Sunucu dünyaları istemci profillerinden ayrı tutulur.
2. Sadece kullanıcı adıyla girilecekse **Kullanıcı adıyla katılıma izin ver** açık olmalıdır. Bu seçenek sunucunun Microsoft hesap doğrulamasını kapatır. Microsoft hesabı doğrulansın istiyorsanız bu seçeneği kapatın.
3. Minecraft EULA bağlantısını okuyup uygulamadaki onay kutusunu kendiniz işaretleyin. Uygulama bu sözleşmeyi sizin yerinize otomatik kabul etmez.
4. **Başlat** sunucu dosyasını ve uygun Java'yı hazırlar. İlk Fabric açılışında ek kütüphaneler indirilebilir. Konsolda **Done** göründüğünde sunucu hazırdır.
5. Bu bilgisayardan `localhost:25565` adresine; aynı ağdaki arkadaşlarınız ekranda gösterilen LAN adresine bağlanır. Farklı port seçtiyseniz o portu kullanın. Minecraft'ta **Çok oyunculu → Doğrudan bağlantı** bölümüne adres yazılır.
6. Farklı ağlardaki arkadaşlar için üstte açıklanan **ücretsiz davet** özelliğini kullanın. Modem port yönlendirme gerekmez. Sunucu, launcher ve tünel yardımcısı açık kalmalıdır. Doğrudan bağlantı isteyenler için LAN adresi de sunulur.
7. Sunucuyu **Durdur** ile kapatın; konsola `stop` gönderilir ve oyun dünyayı kaydeder. Launcher kapanırken çalışan sunucuya da düzgün kapanma komutu gönderilir. Canlı konsoldan `list`, `op OyuncuAdi`, `whitelist on`, `whitelist add OyuncuAdi` gibi Minecraft komutları gönderilebilir.

Fabric sunucularına **Mod .jar** düğmesiyle sunucuya uygun mod eklenebilir. Önce sunucuyu durdurun. Yalnız istemci için işaretlenmiş Fabric modları sunucuya eklenmez; diğer modların oyun sürümü ve bağımlılıklarını kontrol edin. Oyuncularda gerekli istemci modları da kurulu olmalıdır. Forge/NeoForge/Quilt sunucuları, sunucu mod kataloğu ve uzaktan yönetim bu sürümde bulunmaz. Aynı anda bir yerel sunucu yönetilir; bilgisayar ve launcher açık kalmalıdır.

Resmî sunucu ve ağ gereksinimleri: https://www.minecraft.net/en-us/download/server

## Microsoft girişinin geliştirici kurulumu

Bu bölüm isteğe bağlı **Microsoft hesabı** girişine aittir; kullanıcı adıyla oynama ve yerel sunucu yönetimi için gerekmez. Pakete başka bir uygulamaya ait Client ID eklenmemiştir. Microsoft girişi sunacağınız launcher için size ait uygulama kaydı ve Minecraft API erişim onayı gereklidir.

1. Microsoft Entra uygulama kaydı oluşturun; kişisel Microsoft hesaplarının girişine izin verin.
2. Uygulama için **Mobile and desktop applications / public client** platformunu kullanın. Loopback dönüş adresini `http://localhost/callback` olarak kaydedin. Launcher rastgele bir localhost portu kullanır. Microsoft'un masaüstü loopback adres kurallarına uygun kayıt yapın.
3. Client secret üretip launcher içine koymayın. Bu uygulama public client + PKCE akışını kullanır.
4. Minecraft API erişimi için resmî başvuru/onay sürecini tamamlayın. Onay olmadan uygulama kimliği doğru olsa bile Minecraft doğrulaması reddedilebilir.
5. **Ayarlar → Microsoft hesabı** alanına Application (client) ID değerini yazıp kaydedin. **Microsoft ile giriş** düğmesine basın ve tarayıcıda hesabınızla giriş yapın.

Giriş rehberi: https://minecraft-launcher-lib.readthedocs.io/en/stable/tutorial/microsoft_login.html

Microsoft loopback rehberi: https://learn.microsoft.com/en-us/entra/identity-platform/reply-url

Bu dış uygulama kaydı/onayı sağlanmadan Microsoft hesabıyla giriş uçtan uca doğrulanamaz.

## Kapsam ve sınırlar

“Bütün sürümler”, Mojang'ın Java Edition manifestinde sunduğu sürümler anlamına gelir. Bedrock Edition bu uygulamanın kapsamında değildir. Her arşiv sürümünün güncel Windows, Java ve sürücülerle çalışacağı garanti edilemez; bütün sürümler tek tek denenmemiştir.

Her mod her sürümde ve her yükleyicide çalışmaz. Modrinth indirmeleri API'deki uyumluluk bilgilerini kullanır; modların çalışma zamanındaki tüm çakışmaları önceden tespit edilemez. Yerel JAR dosyalarının yükleyici tanımı kontrol edilir; oyun sürümü ve harici bağımlılıklarının uygunluğunu kullanıcının kontrol etmesi gerekir. Modrinth dışındaki otomatik kataloglar, CurseForge API'si ve skin düzenleyici bu sürümde yoktur. mrpack indirmelerinde izinli HTTPS kaynakları ve güvenli profil yolları kullanılır; tanınmayan bağımlılık/yol/kaynak açıklamalı olarak reddedilir. Her üçüncü taraf paketinin kurulabileceği garanti edilmez.

İptal mevcut ağ isteğinin veya yükleyici alt işleminin bitmesini bekleyebilir. Yarım kalan Minecraft dosyaları sonraki **Kur / onar** işleminde doğrulanır. Oyun çalışırken kurulum ve mod değişiklikleri engellenir. Arayüzde manuel profil silme bulunmaz; dünyalar yanlışlıkla silinmez.

## Kaynak koduyla çalıştırma

Python 3.12+ ile:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe src/main.py
```

`Baslat.cmd`, EXE varsa onu açar; yoksa Python ortamını hazırlayıp kaynak sürümü çalıştırır. `build.ps1` kaynak kodundan değiştirilebilir DLL'lerle bir klasör derlemesi üretir. `requirements.txt` sürümleri sabitler.

Testler:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`KURT_DATA_DIR` ortam değişkeniyle farklı veri klasörü seçilebilir. Aynı veri klasörünü kullanan iki launcher'ın eşzamanlı açılması engellenir. Yenileme anahtarının kasa kaydı veri klasörüne ve Client ID'ye bağlıdır; klasör taşındığında yeniden giriş gerekebilir.

## Doğrulama

0.4.0 geliştirmesinde 113 otomatik test geçti. Gerçek Modrinth modlarıyla kurulum → mrpack dışa aktarım → ayrı profile içe aktarım → SHA-512 karşılaştırma → güncelleme taraması → yedek geri yükleme doğrulandı. Mojang'dan akışlı indirme SHA-1 ile doğrulandı. Gerçek Windows güncelleme yardımcısı ayrı deneme uygulamalarında hem başarılı yükseltme hem açılmayan EXE'den geri dönüş için test edildi; deneme dünyası korundu. Windows arayüzü ve paketlenmiş EXE ayrıca kontrol edilir; ayrıntılar `DOGRULAMA.txt` dosyasındadır.

Microsoft uygulama kaydı/API izni sağlanmadığından gerçek Microsoft oturumu; kullanıcı adına Playit hesabı bağlanmadığından gerçek herkese açık tünel ve iki farklı ağdan oyun bağlantısı bu sürümde doğrulanmadı. Minecraft EULA onayı kullanıcıya bırakıldı. Tünel/kota API senaryoları taklit servisle test edildi. Bütün eski Minecraft sürümleri veya tüm mod kombinasyonları tek tek denenmedi.

Bağımsız projedir; Mojang/Microsoft ile bağlantısı veya resmî onayı yoktur. Minecraft varlıkları ve modlar dağıtım paketine dahil edilmez; ilgili kaynaklardan indirilir. Kullanılan açık kaynak bileşenlerinin lisansları `third-party` klasöründedir. Qt/PySide DLL'leri dinamik olarak yüklenir; kaynak kodu ve yeniden derleme betiği pakete dahildir.
