"""Live Turkish/English UI catalog. User names, paths and third-party prose stay intact."""
import re
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QWidget,QLabel,QAbstractButton,QLineEdit,QComboBox,QTabWidget,
                              QTableWidget,QGroupBox,QPlainTextEdit)

CATALOG = dict(line.split('|',1) for line in '''
OYUN MERKEZİ|GAME HUB
OYUN ALANI|PLAY
UYGULAMA|APPLICATION
OYUNCU|PLAYER
AKTİF PROFİL|ACTIVE PROFILE
MOD ATÖLYESİ|MOD WORKSHOP
AYARLAR|SETTINGS
İŞLEM GÜNLÜĞÜ|ACTIVITY LOG
SUNUCULAR|SERVERS
KÜTÜPHANE VE ARAÇLAR|LIBRARY & TOOLS
SHADERPACK ATÖLYESİ|SHADER WORKSHOP
DOKU PAKETİ ATÖLYESİ|RESOURCE PACK WORKSHOP
MODPACK KATALOĞU|MODPACK CATALOG
DÜNYALARIM|MY WORLDS
Oyun merkezi|Game hub
Mod atölyesi|Mod workshop
Ayarlar|Settings
Günlük|Logs
Sunucular|Servers
Kütüphane|Library
Shaderpack’ler|Shaders
Doku paketleri|Resource packs
Modpack’ler|Modpacks
Dünyalarım|My worlds
Güncellemeler|Updates
Oynamaya hazır mısın?|Ready to play?
Sürümler yükleniyor…|Loading versions…
İlk profilini oluştur|Create your first profile
Her profilin dünyaları, ayarları ve modları ayrı tutulur.|Each profile keeps its own worlds, settings and mods.
▶  OYNA|▶  PLAY
↓  Kur / onar|↓  Install / repair
Modları yönet|Manage mods
Klasörü aç ↗|Open folder ↗
Yeni bir başlangıç|A fresh start
↻  Sürümleri yenile|↻  Refresh versions
Kararlı sürümler, snapshot'lar ve resmî arşivdeki alpha/beta sürümleri.|Releases, snapshots and alpha/beta versions from the official archive.
Kararlı sürümler|Releases
Snapshot / ön sürüm|Snapshot / preview
Eski beta|Old beta
Eski alpha|Old alpha
Bütün sürümler|All versions
+  Profil oluştur|+  Create profile
Mod uyumluluğu Minecraft ve yükleyici sürümüne bağlıdır. Eski sürümlerde ek Java ayarı gerekebilir.|Mod compatibility depends on Minecraft and loader versions. Older releases may need different Java settings.
Hesap bağlı değil|No account connected
Kullanıcı adıyla|Username
Microsoft hesabı|Microsoft account
Kullanıcı adını yaz|Enter your username
3–16 karakter: İngilizce harf, rakam ve _|3–16 characters: English letters, numbers and _
Microsoft ile giriş|Sign in with Microsoft
Hesaptan çık|Sign out
Mod keşfet|Discover mods
Kurulu modlar|Installed mods
Mod ara… ör. Sodium, Create, JEI|Search mods… e.g. Sodium, Create, JEI
En çok indirilen|Most downloaded
En yeni|Newest
Son güncellenen|Recently updated
Aramaya göre|Relevance
Ara|Search
Modları görmek için Ara'ya bas. İndirilen dosyalar SHA-512 ile doğrulanır.|Press Search to discover mods. Downloads are verified with SHA-512.
Tüm Modrinth sonuçlarını seçilen sırayla getirir.|Searches all Modrinth results in the selected order.
←  Önceki|←  Previous
Sonraki  →|Next  →
← Önceki|← Previous
Sonraki →|Next →
+  .jar dosyası ekle|+  Add .jar file
Etkinleştir / kapat|Enable / disable
Kaldır|Remove
Mod klasörü ↗|Mods folder ↗
Ayrıntılar|Details
Mod sayfası ↗|Mod page ↗
☆ Kaydet|☆ Save
★ Kaydedildi|★ Saved
★ Favoriler|★ Favorites
↓ İndir|↓ Download
✓ İndirildi|✓ Downloaded
↓ Yeniden indir|↓ Download again
Mod / Açıklama|Mod / Description
Sürüm / Uyumluluk|Version / Compatibility
İndirme|Downloads
İçerik / Uyumluluk|Content / Compatibility
Durum|Status
Dosya|File
Mod|Mod
Sürüm|Version
Uyumluluk|Compatibility
Oyun ayarları|Game settings
Her şey senin ayarında|Make it yours
Bellek, Java ve isteğe bağlı Microsoft hesabı ayarları.|Memory, Java and optional Microsoft account settings.
Bellek (RAM)|Memory (RAM)
Java yolu|Java path
Otomatik — sürüme uygun Java indirilir|Automatic — downloads Java for this version
Seç…|Browse…
Ayarları kaydet|Save settings
Veri klasörü ↗|Data folder ↗
Eski oyun klasörünü seç…|Choose old game folder…
Bilgisayarın belleğinin tamamını oyuna ayırma. Özel Java seçimi bütün profillere uygulanır.|Keep some memory available for your computer. A custom Java path applies to all profiles.
Kullanıcı adıyla oynamak için bu bölüm gerekli değildir. Microsoft hesabıyla giriş seçeneği için launcher'a ait uygulama kimliği ve Minecraft API erişim onayı gerekir.|Username mode does not need this section. Microsoft sign-in requires this launcher's application ID and Minecraft API access approval.
Geliştirici kurulum rehberi ↗|Developer setup guide ↗
Application (client) ID — ör. xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx|Application (client) ID — e.g. xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
Oyunlar, modlar ve dünyalar launcher'dan bağımsız ortak klasörde tutulur. Eski launcher klasörünü kaldırmak oyunlarını silmez.|Games, mods and worlds live in a shared folder independent of the launcher. Removing an old launcher folder does not delete your games.
Kurt Launcher bağımsız bir projedir. Mojang veya Microsoft ile bağlantılı değildir.|Kurt Launcher is an independent project, unaffiliated with Mojang or Microsoft.
İşlem günlüğü|Activity log
Günlüğü temizle|Clear log
Oyun günlüğünü aç ↗|Open game log ↗
Hazır|Ready
İptal|Cancel
Duraklat|Pause
Devam et|Resume
Tekrar dene|Retry
İndirmeler|Downloads
İndirme ve kurulum durumunu buradan takip edebilirsin.|Track download and installation progress here.
Yüzde geçerli indirme veya kurulum aşamasını gösterir. Yeni aşamada yeniden başlar.|The percentage shows the current download or installation stage and resets for the next stage.
Arkadaşlarınla aynı dünyada|In the same world with friends
Bilgisayarında Vanilla veya Fabric sunucusu oluştur. Dünyan ayrı klasörde saklanır.|Create a Vanilla or Fabric server on your computer. Its world is stored separately.
Sunucu adı|Server name
+  Oluştur|+  Create
Minecraft sürümü|Minecraft version
Sunucularım|My servers
Sunucu seçilmedi|No server selected
Sunucunu başlat; hazır olduğunda Davet oluştur düğmesini kullan.|Start your server, then create an invite when it is ready.
▶  Başlat|▶  Start
■  Durdur|■  Stop
↓  Kur|↓  Install
Klasör ↗|Folder ↗
Port açmadan, davet koduyla oyna|Play with invite codes, without port forwarding
1  Ücretsiz bağlantıyı kur|1  Set up free connection
2  Davet oluştur|2  Create invite
Paylaşımı kapat|Stop sharing
Ücretsiz panel ↗|Free dashboard ↗
Ücretsiz tünel hazır olduğunda davet kodun burada görünür|Your invite code appears here when the free tunnel is ready
Kopyala|Copy
Davetle katıl|Join with invite
Arkadaşının KURT1- veya KURT2- davet kodunu buraya yapıştır|Paste your friend's KURT1- or KURT2- invite code here
Sunucu oluşturduğunda bağlantı adresleri burada görünür.|Connection addresses appear here after you create a server.
Arkadaşlar için LAN adresi|LAN address for friends
Canlı sunucu konsolu|Live server console
Gönder|Send
Minecraft EULA'sını okudum ve kabul ediyorum|I have read and accept the Minecraft EULA
EULA'yı oku ↗|Read EULA ↗
Kullanıcı adıyla katılıma izin ver — Microsoft hesabı doğrulanmaz|Allow username-only players — Microsoft accounts are not verified
Sunucu sahibi bir kez ücretsiz Playit bağlantısını tarayıcıda onaylar. Arkadaşlarının Playit kurması veya hesap açması gerekmez. Ücretli paket satın alınmaz.|The host approves a free Playit connection in the browser once. Friends do not need Playit or an account. No paid plan is purchased.
Kod doğru Minecraft/Fabric profilini seçer ve oyunu sunucuya bağlar. Gerekli modlar iki tarafta da kurulu olmalı. Sunucu sahibi bilgisayarını, launcher'ı ve ücretsiz bağlantıyı açık tutar.|The code selects a matching Minecraft/Fabric profile and joins the server. Required mods must be installed on both sides. The host keeps their computer, launcher and free connection running.
Aynı ağdan doğrudan bağlantı için yukarıdaki LAN adresini kullanın. Farklı ağdaki arkadaşların için üstteki ücretsiz davet bağlantısını açabilirsin; modemden port yönlendirme gerekmez.|Use the LAN address on the same network. For friends on other networks, enable the free invite connection above; router port forwarding is not needed.
Kütüphane ve araçlar|Library and tools
Yedeklerin, paylaşılan paketlerin ve profil araçların tek yerde.|Backups, shared packs and profile tools in one place.
Yedekler|Backups
Paket paylaş|Share pack
Mod güncellemeleri|Mod updates
Koleksiyonlar|Collections
Performans|Performance
Görünüm|Appearance
Launcher güncellemesi|Launcher update
Yönetim|Management
Profil veya sunucu seç. Çalışan oyun/sunucu durdurulmadan yedek alınmaz veya geri yüklenmez.|Choose a profile or server. Stop the game/server before creating or restoring backups.
Şimdi yedekle|Back up now
Seçili yedeği geri yükle|Restore selected backup
Yedek klasörünü aç|Open backup folder
Değişikliklerden ve sunucu açılışından önce otomatik yedekle|Back up automatically before changes and server startup
Elle alınan ve geri yükleme öncesi alınan güvenlik yedekleri otomatik temizlenmez. Yedekler bu bilgisayarda saklanır.|Manual backups and pre-restore safety backups are not automatically removed. Backups are stored on this computer.
Tarih|Date
Boyut|Size
Neden|Reason
Tür|Type
.mrpack içe aktar|Import .mrpack
Aktif profili .mrpack olarak paylaş|Share active profile as .mrpack
Dışa aktarırken config klasörünü de ekle (paylaşmadan önce içeriğini kontrol et)|Include config folder in export (review it before sharing)
Mod listesiyle karşılaştır|Compare mod list
Sunucu mod listesi oluştur|Create server mod list
Mod paketini ayrı bir profile kur veya aktif profilindeki mod listesini arkadaşınla paylaş. Oyun dosyaları, dünyalar ve hesap bilgileri dışa aktarılmaz.|Install a modpack into a separate profile or share your current mod list. Game files, worlds and account data are not exported.
Yerel/değiştirilmiş JAR'lar izinli indirme kaynağı bulunmadan pakete eklenmez. İçe aktarılan modlar ve betikler oyun içinde kod çalıştırabilir; güvendiğin paketleri seç.|Local/modified JARs need an authorized download source before export. Imported mods and scripts can execute code in-game; choose trusted packs.
Sunucu sahibi mod listesi dosyasını paylaşabilir. Aktif profilinle karşılaştırıp eksikleri onayından sonra kurabilirsin.|The host can share a mod list. Compare it with your active profile and approve missing mods before installation.
Sunucuyla modlarım uyumlu mu?|Do my mods match the server?
Aktif profil için kararlı ve uyumlu sürümler kontrol edilir.|Checks stable, compatible versions for the active profile.
Güncellemeleri kontrol et|Check for updates
İşaretli güncellemeleri uygula|Apply checked updates
Seçili modun değişiklikleri|Selected mod changelog
Sabitlenmiş modlar otomatik seçilmez. Güncelleme geçici klasörde hazırlanır; bağımlılık sorunu olursa mevcut kurulum korunur.|Pinned mods are not selected automatically. Updates are staged separately; dependency problems leave the existing installation intact.
Seçili|Selected
Kurulu → Yeni|Installed → New
Mod keşfet ekranındaki ☆ Kaydet ile favori veya kişisel koleksiyon oluştur.|Use ☆ Save in Discover mods to build favorites or personal collections.
Seçili modu keşfette aç|Find selected mod
Koleksiyondan çıkar|Remove from collection
Bilgileri güncelle|Refresh information
Önerilen RAM'i uygula|Apply recommended RAM
Aktif profile görüntü ayarını uygula|Apply graphics preset to active profile
Düşük|Low
Dengeli|Balanced
Yüksek|High
Bu öneri toplam ve kullanılabilir belleğe dayanır. Büyük mod paketleri farklı ayar gerektirebilir; FPS artışı garantisi değildir.|This suggestion uses total and available memory. Large modpacks may need different settings; it does not guarantee higher FPS.
Görüntü ayarları options.txt dosyasına yazılır. Eski sürümler bazı ayarları tanımayabilir. Diğer kullanıcı ayarları korunur; işlemden önce otomatik yedek alınır.|Graphics presets update options.txt. Older versions may ignore some settings. Other settings are preserved, with an automatic backup before changes.
Açık, sunset, sistem veya yüksek kontrast görünümünü seç. Yazı ve kontrolleri birlikte ölçekle.|Choose light, sunset, system or high contrast. Scale text and controls together.
Açık · Gün doğumu|Light · Sunrise
Koyu · Sunset|Dark · Sunset
Sistem teması|System theme
Yüksek kontrast|High contrast
Arayüz ölçeği|Interface scale
Görünümü ve dili uygula|Apply appearance and language
Kısayollar: Ctrl+1 Oyun merkezi · Ctrl+2 Modlar · Ctrl+3 Dünyalar · Ctrl+, Ayarlar · F6 Profil seç · Ctrl+Enter Oyna. Tab ile kontroller arasında ilerle.|Shortcuts: Ctrl+1 Home · Ctrl+2 Mods · Ctrl+3 Worlds · Ctrl+, Settings · F6 Profile · Ctrl+Enter Play. Use Tab to move between controls.
Sunset vurgu rengini seç|Choose accent color
Varsayılan sunset|Default accent
Kompakt mod listesi|Compact mod list
Aktif profilin kapağını seç|Choose profile cover
Profil kapağını kaldır|Remove profile cover
Kapak ve vurgu rengi bu bilgisayarda saklanır. Mod ekran görüntüleri Ayrıntılar penceresinde açılır.|Covers and accent color are stored on this computer. View mod screenshots in Details.
Güncellemeleri bul|Find updates
Açılışta güncellemeleri arka planda kontrol et|Check for updates in the background on startup
Yeni sürümü otomatik indir, kur ve yeniden aç|Automatically download, install and restart updates
Yeni sürüm imzası doğrulanarak otomatik kurulur. Oyun, sunucu veya başka bir işlem çalışıyorsa kapanması beklenir. Başarılı açılıştan sonra eski uygulama dosyaları temizlenir. Oyunların ortak klasörde korunur.|New versions are verified and installed automatically when the game, server and other tasks are idle. Old app files are removed after successful startup. Games remain in the shared folder.
İmzalı .kurtupdate paketi seç|Choose signed .kurtupdate package
Uygulama güncelleme için kapanır. Yeni sürüm açılamazsa önceki uygulama dosyaları geri yüklenir. İşlem günlüğü data/updates altında saklanır.|The app closes to update. If the new version cannot start, previous app files are restored. The update log is kept in data/updates.
Güncellemeyi incele|Review update
Daha sonra|Later
Yedekler ve paket paylaşımı|Backups and pack sharing
Profil sürümünü değiştir|Change profile version
Görünüm / kapak|Appearance / cover
Son kullanılan profiller|Recent profiles
Oyun / yükleyici|Game / loader
Sürümü sabitle / bırak|Pin / unpin version
Oyun hatasını incele|Analyze game error
Sunucu hatasını incele|Analyze server error
Profili seçmek için çift tıkla|Double-click to select this profile
Sunucu ayarları ve oyuncular|Server settings and players
Ayarları yükle|Load settings
Ayarları kaydet (sunucu kapalıyken)|Save settings (server stopped)
Oyuncu adı|Player name
İzin listesine ekle|Add to whitelist
Listeden çıkar|Remove from whitelist
Yalnızca izin verilen oyuncular|Whitelisted players only
Kullanıcı adıyla katılımda oyuncu kimliği doğrulanmaz; izin listesi bu modda kimlik doğrulama sağlamaz.|Username-only mode does not verify player identity; a whitelist does not authenticate players in this mode.
Oyuncuları yenile|Refresh players
Bağlı oyuncu yok / sunucu kapalı|No connected players / server stopped
İzin listesi: henüz oyuncu yok|Whitelist: no players yet
İndirmeler ve işlem kuyruğu|Downloads and task queue
Hız sınırı (KiB/sn):|Speed limit (KiB/s):
Boyutu bilinen dosyalarda hız ve kalan süre gösterilir. Mod/paket kurulumlarında bekleyen dosyalar aşağıda listelenir.|Speed and remaining time are shown when file size is known. Pending mod/pack files are listed below.
Bağlantı kesilirse Tekrar dene ile, HTTP Range destekleyen sunucularda doğrulanmış kısmi dosyadan devam edilir.|After interruption, Retry resumes verified partial files when the server supports HTTP Range.
İşlem|Task
Vazgeç|Cancel
Rapor otomatik gönderilmez. Filtre her kişisel bilgiyi yakalayamayabilir; paylaşmadan önce inceleyin.|Reports are not sent automatically. Filters may miss personal information; review before sharing.
İncelediğim raporu dosyaya kaydet|Save reviewed report
Shaderpack atölyesi|Shader workshop
Bir oyuncu profili seçerek başla.|Select a player profile to begin.
Dünyana yeni bir ışık kat|See your world in a new light
Iris / OptiFine shaderpack’lerini keşfet. İndirilen ZIP’ler seçili profilin shaderpacks klasöründe tutulur. Kullanmak için Minecraft → Video ayarları → Shader Packs bölümünden paketi seç.|Discover Iris / OptiFine shaders. ZIPs are stored in this profile's shaderpacks folder. Select the pack in Minecraft → Video Settings → Shader Packs.
Iris’i kur|Install Iris
Iris için uyumlu Fabric veya NeoForge profili gerekir. OptiFine kullanacaksan kurulumunu ayrıca yapabilirsin.|Iris needs a compatible Fabric or NeoForge profile. You can install OptiFine separately.
Shaderpack keşfet|Discover shaders
İndirilen shaderpack’ler|Downloaded shaders
Minecraft sürümüne ve shader desteğine göre filtrelenir.|Filtered by Minecraft version and shader engine.
Shaderpack ara… ör. Complementary, BSL, MakeUp|Search shaders… e.g. Complementary, BSL, MakeUp
Shaderpack’leri görmek için Ara’ya bas.|Press Search to discover shaders.
İndirilmiş olması oyunda seçili olduğu anlamına gelmez. Etkin paketi Minecraft’ın Shader Packs menüsünden seçebilirsin. Yerel ZIP’lerin sürüm uyumluluğunu yapımcısından kontrol et.|Downloading does not activate a shader. Select it in Minecraft's Shader Packs menu. Check local ZIP compatibility with the author.
Shaderpack klasörü ↗|Shaders folder ↗
Ayrıntılar ve görseller ↗|Details and images ↗
Seçili Minecraft sürümü ve shader desteği için sonuç bulunamadı.|No shaders found for this Minecraft version and engine.
Shaderpack güncellemeleri|Shader updates
Yerel/değiştirilmiş ZIP’ler otomatik değiştirilmez. Güncellemeden sonra paketi oyun içinden tekrar seçebilirsin.|Local/modified ZIPs are not replaced automatically. You may need to select the updated pack again in-game.
Uyumlu yeni shaderpack sürümü bulunmadı.|No compatible shader updates found.
Güncelle|Update
Doku paketi atölyesi|Resource pack workshop
Hazır modpack kataloğu|Ready-made modpack catalog
Paket / Açıklama|Pack / Description
Paket sürümü|Pack version
Görsel|Image
Aktif Minecraft sürümüne göre filtrele|Filter by active Minecraft version
Doku paketi ara…|Search resource packs…
Hazır modpack ara…|Search modpacks…
Arama için Ara’ya basın.|Press Search to begin.
Paket sayfası ↗|Pack page ↗
Sürüm seç ve kur|Choose version and install
Seçili Minecraft sürümü için paketleri keşfet. Paket sıralamasında son satır daha yüksek önceliklidir.|Discover packs for this Minecraft version. The last selected pack has the highest priority.
Doku paketi keşfet|Discover resource packs
İndirilenler ve sıra|Downloaded packs and order
Doku paketi klasörü ↗|Resource packs folder ↗
Yerel ZIP ekle|Add local ZIP
Seçimi ve sırayı kaydet|Save selection and order
Yukarı|Move up
Aşağı|Move down
Paketler yeni ve ayrı profile kurulur. Mevcut profilin ve dünyaların korunur. Kurmadan önce oyun/yükleyici ve indirme boyutunu incele.|Packs install into a separate profile, preserving existing profiles and worlds. Review game/loader versions and download size before installing.
Modpack sürümünü seç|Select modpack version
Bu paketin kaynağına güveniyorsan kurulumu başlat. Modlar SHA-512 ile doğrulanır.|Install if you trust this pack's source. Mods are verified with SHA-512.
İsteğe bağlı istemci dosyalarını da kur|Include optional client files
İndir ve kurulumu incele|Download and review installation
Profil kopyala|Clone profile
Mod sorunu bul|Find mod problem
Depolama|Storage
Dünya sürümü, son oynanma, görsel ve boyut bilgilerini gör; dünyaya özel yedekle, kopyala, dışa aktar veya geri yükle.|View world version, last played, icon and size. Back up, copy, export or restore individual worlds.
Dünyaları yenile|Refresh worlds
Dünya|World
Son sürüm|Last version
Son oynanma|Last played
Bir dünya seçin.|Select a world.
Yedekle|Back up
ZIP dışa aktar|Export ZIP
Aktif profilin modları, shader/doku paketleri ve ayarları doğrulanarak yeni profile kopyalanır. Minecraft ve Java indirmeleri ortak kullanılmaya devam eder.|Copies this profile's verified mods, shader/resource packs and settings into a new profile. Minecraft and Java downloads stay shared.
Yeni profil adı|New profile name
Dünyaları da kopyala|Include worlds
Profili kopyala|Clone profile
Modlar ayrı ve dünyasız bir test profilinde gruplar halinde denenir. Gerekli bağımlılıklar birlikte açık tutulur. Her denemeden sonra oyunu kapatıp sonucu belirt. Mod etkileşimleri ve ortak bağımlılıklar nedeniyle sonuç olası adayları gösterir.|Test mod groups in a separate profile without worlds. Declared dependencies stay together. Close the game after each trial and report the result. Mod interactions and shared dependencies can limit diagnosis to possible candidates.
Aktif profilden yeni mod testi başlat|Create mod test from active profile
Test profilini başlat|Launch test profile
Aynı sorun oluştu|Same issue occurred
Sorun oluşmadı|Issue did not occur
Henüz mod testi yok.|No mod tests yet.
Oyun arşivindeki disk kullanımını incele. Temizleme yalnız seçtiğin yeniden indirilebilir önbellek dosyalarını kaldırır. İndirme devam verisini temizlersen o dosya yeniden baştan indirilir.|Inspect game archive storage. Cleanup only removes selected reproducible cache files. Removing partial-download data restarts those downloads.
Disk kullanımını tara|Scan disk usage
İçerik|Content
Seçili önbellek dosyası|Selected cache file
Tüm önbelleği seç / bırak|Select / deselect all cache
Seçileni temizle|Clean selected
Dünyana geri dön|Return to your world
▶  Son dünyama devam et|▶  Continue my last world
Favori sunucular|Favorite servers
Başka launcher’dan aktar|Import from another launcher
Sunucuyu kaydet, durumunu kontrol et ve seçtiğin profille katıl. Özel port kullanıyorsa adresin sonuna yaz.|Save a server, check its status and join with your chosen profile. Include the port if it uses a custom one.
Aktif profille kaydet|Save with active profile
Sunucu / adres|Server / address
Profil|Profile
Durum / sürüm|Status / version
Oyuncular|Players
Durumu kontrol et|Check status
Katıl|Join
Durum kontrolü yalnız seçtiğin sunucuya bağlantı kurar.|Status checks only connect to the server you select.
Dışarıdan aktar|Import games
Resmî .minecraft veya Prism/MultiMC oyun klasörünü seç. Dünyalar, modlar, paketler ve oyun ayarları yeni profile kopyalanır. Kaynak korunur; hesaplar ve özel başlatma komutları alınmaz.|Choose an official .minecraft or Prism/MultiMC game folder. Copy worlds, mods, packs and game settings to a new profile. The source is preserved; accounts and custom launch commands are excluded.
Kaynak klasörü seç ve tara|Choose and scan source folder
Bulunan oyun|Detected game
Minecraft / yükleyici|Minecraft / loader
Kaynak klasörü|Source folder
Dünyaları da aktar|Include worlds in import
Önizlemeyi yeni profile aktar|Import preview into new profile
Sürüm belirlenemediyse elle seç. Mod yükleyicisini kontrol et; ilk Oyna gerekli Minecraft/Java dosyalarını ortak arşive indirir.|Enter a version if detection could not determine it. Check the mod loader. The first launch downloads required Minecraft/Java files into the shared archive.
Oyun istatistikleri|Play statistics
Bu sürümden itibaren launcher açıkken ölçülen oturum süreleri. Minecraft menüleri dahildir; launcher kapalıyken geçen süre ölçülmez. Bilgiler yalnız bu bilgisayarda tutulur.|Session time measured from this release while the launcher is open. Includes Minecraft menus. Time after closing the launcher is not measured. Data stays on this computer.
İstatistikleri yenile|Refresh statistics
Toplam süre|Total time
Oturum|Sessions
Profil / sürüm|Profile / version
Başlangıç|Started
Süre|Duration
★ Favori sunuculara git|★ Open favorite servers
Davet bağlantısını kopyala|Copy invite link
Shader önerisi için ekran kartını algıla.|Detect your graphics card for shader suggestions.
Ekran kartını algıla ve shader öner|Detect graphics card and suggest shaders
Performans sınıfı|Performance class
Tüm shader’lar|All shaders
Hafif|Lightweight
Yüksek kalite|High quality
Donanımıma göre öner|Suggest for my hardware
▶ Seçili dünyayı aç|▶ Play selected world
Dünya geçmişi|World history
Değişmeyen dosyalar tekrar saklanmaz. Geri yüklemeden önce mevcut dünya ZIP olarak korunur. Geçmiş yalnız bu bilgisayardadır.|Unchanged files are stored once. Before restoring, the current world is saved as a ZIP. History is local to this computer.
Hızlı devam ile dünyayı açmadan önce otomatik geri dönüş noktası oluştur|Create a restore point automatically before opening a world with Quick Play
Dünya boyutu|World size
Yeni saklanan|New storage
Yeni geri dönüş noktası|Create restore point
Seçili tarihe geri dön|Restore selected date
Kapat|Close
Kontrol edilmedi|Not checked
Ulaşılamadı|Unreachable
Oynanıyor|Playing
Tamamlandı|Completed
Kesintili|Interrupted
Launcher kapandı|Launcher closed
Otomatik|Automatic
Elle|Manual
Yenile|Refresh
↻  Yenile|↻  Refresh
Belirtilmemiş|Not specified
Uyumlu sürüm doğrulanamadı.|Compatible version could not be verified.
Bu sürüm ve yükleyici için sonuç bulunamadı.|No results for this game version and loader.
Bir mod yükleyicili profil seçerek başla.|Select a profile with a mod loader to begin.
Seçilen sürüm ve yükleyiciye göre filtrelenir.|Filtered by the selected game version and loader.
Sürüm ve yükleyici uyumluluğu kontrol edilir.|Game version and loader compatibility are checked.
Yerel JAR sürümü ve bağımlılıkları elle kontrol edilmeli.|Check local JAR versions and dependencies manually.
Mod listesi eşleşiyor · oyuna katıl|Mod list matches · join game
Eksik modları onayla ve kur|Approve and install missing mods
Oyun/yükleyici sürümleri eşleşiyor.|Game and loader versions match.
Oyun/yükleyici sürümü farklı. Uygun bir profil seçerek yeniden karşılaştırın.|Game/loader versions differ. Choose a matching profile and compare again.
Sunucuyla mod uyumluluğu|Server mod compatibility
Modrinth'te keşfet|Discover on Modrinth
Modrinth sayfası ↗|Modrinth page ↗
Görseli açmak için çift tıkla|Double-click to open image
Etkin|Enabled
Kapalı|Disabled
Yerel|Local
Uyumlu|Compatible
Paket seçimi|Pack selection
Sabit|Pinned
Yükleyici|Loader
Hız|Speed
Kalan|Remaining
Toplam|Total
Kuyruk|Queue
'''.strip().splitlines())
CATALOG.update(dict(line.split('|',1) for line in '''
Aktif profil: Seçilmedi|Active profile: None
+  Mod .jar|+  Mod .jar
+ .zip ekle|+ Add .zip
Açıklama|Description
Barışçıl|Peaceful
Bilgisayar bilgisini yenile|Refresh hardware information
Dengeli · 10 chunk / 120 FPS sınırı|Balanced · 10 chunks / 120 FPS limit
Düşük · 6 chunk / 60 FPS sınırı|Low · 6 chunks / 60 FPS limit
Yüksek · 16 chunk / 120 FPS sınırı|High · 16 chunks / 120 FPS limit
Doku paketi|Resource pack
En fazla RAM|Maximum RAM
Favoriler|Favorites
Giriş yap|Sign in
Görüş uzaklığı|View distance
Hayatta kalma|Survival
Java çalıştırıcısı|Java executable
Katılım|Join mode
Kendi adresimi kopyala|Copy local address
Kodu kopyala|Copy code
Kolay|Easy
Komut: list, say Merhaba, op OyuncuAdi, whitelist add OyuncuAdi|Command: list, say Hello, op PlayerName, whitelist add PlayerName
Kullanıcı adıyla giriş|Username sign-in
Kur / onar|Install / repair
Kurulu → yeni|Installed → new
Listeyi yenile|Refresh list
Macera|Adventure
Oyun modu|Game mode
Oyuncu|Player
Oyuncu sınırı|Player limit
Public client / masaüstü uygulaması • kişisel Microsoft hesapları • dönüş adresi: http://localhost/callback. Şifre tarayıcıda girilir; yenileme anahtarı Windows Kimlik Bilgisi Yöneticisi'nde tutulur.|Public client / desktop app • personal Microsoft accounts • redirect: http://localhost/callback. Enter your password in the browser; refresh tokens are stored in Windows Credential Manager.
Saklanacak otomatik yedek:|Automatic backups to retain:
Seçim|Selection
Seçimi ve sırayı uygula|Apply selection and order
Shader desteği|Shader engine
Sunucu yedekleri|Server backups
Tarih / neden|Date / reason
Tüm yükleyiciler|All loaders
Yaratıcı|Creative
Yeni sunucu|New server
Zor|Hard
Zorluk|Difficulty
ÜCRETSİZ · MINECRAFT JAVA|FREE · MINECRAFT JAVA
Ücretsiz GitHub Releases kanalı. İlk çevrimiçi yayın bekleniyor; yerel imzalı paket de seçebilirsin.|Free GitHub Releases update channel. Check online or choose a locally signed update package.
Yalnızca bu yayıncının anahtarıyla imzalanmış paketler kabul edilir. Oyunlar, modlar, dünyalar ve hesap verileri güncelleme paketine dahil edilmez.|Only packages signed by this publisher are accepted. Updates do not include games, mods, worlds or account data.
İzleyici|Spectator
↑ Yukarı|↑ Move up
↓ Aşağı|↓ Move down
Başlatılıyor…|Starting…
Davet bağlantısı kopyalandı.|Invite link copied.
Sunucu daveti|Server invitation
Dünyayı geri yükle|Restore world
Seçili tarihe dönülsün mi? Şimdiki hali ayrıca yedeklenecek.|Restore this date? The current state will be backed up first.
Yeni profil hazır:|New profile ready:
Geri dönüş noktası oluşturuldu.|Restore point created.
Dünya geri yüklendi; önceki hali de yedeklerde korundu.|World restored. Its previous state was also backed up.
Aktarım tamamlandı. Oyna ile gerekli oyun dosyalarını hazırla.|Import completed. Press Play to prepare required game files.
Bu Minecraft sürümü dünyaya hızlı devam etmeyi desteklemiyor. Normal Oyna düğmesini kullanın.|This Minecraft version does not support Quick Play. Use the normal Play button.
Hızlı devam için dünya ve profil Minecraft sürümleri aynı olmalı. Dünyayı normal Oyna ile veya kopya profilde açın.|Quick Play requires matching world and profile Minecraft versions. Use normal Play or a cloned profile.
Bu profilde henüz dünya yok. Önce Oyna ile bir dünya oluştur.|This profile has no worlds yet. Press Play to create one first.
Önce Oyun merkezi bölümünden bir profil oluşturun.|Create a profile in the Game hub first.
Bir favori sunucu seçin.|Select a favorite server.
Listeden bir dünya seçin.|Select a world from the list.
Kaydedilen profil bulunamadı. Sunucuyu aktif profille yeniden kaydet.|The saved profile was not found. Save the server again with an active profile.
Davet hazır; geçerli işlem bitince Sunucuya katıl düğmesine bas.|Invite ready. Finish the current task, then press Join.
Son dünya bulunuyor…|Finding your last world…
Dünyana dönülüyor…|Returning to your world…
Sunucu durumu sorgulanıyor…|Checking server status…
Favori sunucuya katılınıyor…|Joining favorite server…
Oyun klasörü taranıyor…|Scanning game folder…
Oyun yeni profile aktarılıyor…|Importing game into a new profile…
Ekran kartı algılanıyor…|Detecting graphics card…
Shader önerisi hazırlanıyor…|Preparing shader suggestions…
Geri dönüş noktası oluşturuluyor…|Creating restore point…
Dünya geçmişi geri yükleniyor…|Restoring world history…
Değişen dünya dosyaları yedekleniyor…|Backing up changed world files…
Geri dönüş noktası doğrulanıyor…|Verifying restore point…
Oyun hazırlanıyor…|Preparing game…
Minecraft başlatılıyor…|Launching Minecraft…
İşlem tamamlandı.|Task completed.
Minecraft kapandı.|Minecraft closed.
'''.strip().splitlines()))

# Preserve the glyph prefixes used by the sidebar.
for glyph,source in [('◈','Oyun merkezi'),('⊞','Mod atölyesi'),('⚙','Ayarlar'),('≡','Günlük'),('◇','Sunucular'),
                     ('▣','Kütüphane'),('☀','Shaderpack’ler'),('▧','Doku paketleri'),('▦','Modpack’ler'),('▣','Dünyalarım'),('↑','Güncellemeler')]:
    CATALOG[glyph+'    '+source]=glyph+'    '+CATALOG[source]


def translated(value,language):
    if language!='en' or not value:return value
    if value in CATALOG:return CATALOG[value]
    # Only known UI templates. Never translate arbitrary third-party descriptions.
    for prefix,target in (('Aktif profil: ','Active profile: '),('Kurulu sürüm: ','Installed version: '),
                          ('Dünya geçmişi · ','World history · '),('Devam ediliyor: ','Continuing: '),
                          ('Yapımcı: ','Author: '),('Gereken shader desteği: ','Required shader engine: ')):
        if value.startswith(prefix):return target+value[len(prefix):]
    match=re.fullmatch(r'([\d.,]+) indirme',value)
    if match:return match[1]+' downloads'
    match=re.fullmatch(r'İndirilen shaderpack’ler \((\d+)\)',value)
    if match:return 'Downloaded shaders ('+match[1]+')'
    match=re.fullmatch(r'(\d+) sa (\d+) dk (\d+) sn',value)
    if match:return f'{match[1]} h {match[2]} min {match[3]} s'
    match=re.fullmatch(r'Toplam RAM: (.+) GB · Kullanılabilir: (.+) GB\nÖnerilen Minecraft belleği: (.+) MB\nBoş disk: (.+) GB',value)
    if match:return f'Total RAM: {match[1]} GB · Available: {match[2]} GB\nSuggested Minecraft memory: {match[3]} MB\nFree disk: {match[4]} GB'
    if value.startswith('Veriler: '):return 'Data: '+value[9:]
    if value=='Aktif profil: Seçilmedi':return 'Active profile: None'
    match=re.fullmatch(r'(.+) • (Hafif|Dengeli|Yüksek kalite) başlangıç önerisi\. FPS veya VRAM ölçümü değildir\.',value)
    if match:return match[1]+' • '+CATALOG[match[2]]+' starting suggestion. This is not an FPS or VRAM measurement.'
    match=re.fullmatch(r'(.+)\nMinecraft (.+) / (.+)\n\nKatılmadan önce varsa mod listesi kontrol edilecek\. Devam edilsin mi\?',value)
    if match:return f'{match[1]}\nMinecraft {match[2]} / {match[3]}\n\nThe included mod list will be checked before joining. Continue?'
    return value


class Localization:
    def __init__(self,window):
        self.window=window
        self.timer=QTimer(window);self.timer.timeout.connect(self.refresh);self.timer.start(500)
        self.refresh()

    def property_text(self,widget,key,get,setter,language):
        value=get()
        last=widget.property('lang_last_'+key)
        source=widget.property('lang_source_'+key) if value==last else value
        if source is None:source=value
        result=translated(source,language)
        if value!=result:setter(result)
        widget.setProperty('lang_source_'+key,source);widget.setProperty('lang_last_'+key,result)

    def refresh(self):
        window=self.window;language=window.store.settings.get('language','tr')
        excluded=[getattr(window,n,None) for n in ('profiles','collection_select','backup_target','world_backup_choice','server_select','diagnostic_choice')]
        translated_columns={id(getattr(window,name,None)):columns for name,columns in
            (('favorites_table',{2,3,4}),('session_totals',{1,2}),('session_table',{1,2,3}))}
        for widget in window.findChildren(QWidget):
            if widget.property('user_content'):continue
            if isinstance(widget,(QLabel,QAbstractButton,QGroupBox)):
                getter=widget.title if isinstance(widget,QGroupBox) else widget.text
                setter=widget.setTitle if isinstance(widget,QGroupBox) else widget.setText
                self.property_text(widget,'text',getter,setter,language)
                if isinstance(widget,QAbstractButton):widget.setAccessibleName(re.sub(r'^[^\w]+','',getter()))
            if isinstance(widget,QLineEdit):
                self.property_text(widget,'placeholder',widget.placeholderText,widget.setPlaceholderText,language)
                if not widget.accessibleName():widget.setAccessibleName(widget.placeholderText())
            self.property_text(widget,'tooltip',widget.toolTip,widget.setToolTip,language)
            if widget.isWindow():self.property_text(widget,'title',widget.windowTitle,widget.setWindowTitle,language)
            if isinstance(widget,QComboBox) and widget not in excluded and not widget.isEditable():
                was=widget.blockSignals(True)
                try:
                    for i in range(widget.count()):
                        # Item data remains stable; user-created names are excluded above.
                        # Data-less pickers return their displayed text as the value.
                        # Translating that text would change the user's selected name/path.
                        if widget.itemData(i) is None:continue
                        self.property_text(widget,'item'+str(i),lambda i=i:widget.itemText(i),lambda v,i=i:widget.setItemText(i,v),language)
                finally:widget.blockSignals(was)
            if isinstance(widget,QTabWidget):
                for i in range(widget.count()):self.property_text(widget,'tab'+str(i),lambda i=i:widget.tabText(i),lambda v,i=i:widget.setTabText(i,v),language)
            if isinstance(widget,QTableWidget):
                for i in range(widget.columnCount()):
                    item=widget.horizontalHeaderItem(i)
                    if item:self.property_text(widget,'header'+str(i),item.text,item.setText,language)
                for row in range(widget.rowCount()):
                    for col in translated_columns.get(id(widget),set()):
                        item=widget.item(row,col)
                        if item:self.property_text(widget,f'cell{row}_{col}',item.text,item.setText,language)
            if isinstance(widget,QPlainTextEdit) and widget.isReadOnly():
                value=widget.toPlainText()
                if value in CATALOG or widget.property('lang_last_plain')==value:
                    self.property_text(widget,'plain',widget.toPlainText,widget.setPlainText,language)
