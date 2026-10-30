# 0.4.7

Oyunların launcher klasöründen bağımsız kalsın; yeni launcher sürümleri otomatik kurulsun ve açılsın.

- Otomatik kurulumdan sonra launcher penceresi görünür olarak açılır. Geri dönüş gerektiğinde önceki sürüm de görünür açılır.
- Yeni uygulama kendi kurulum klasöründen başlar; Windows eski launcher klasörünü açık tutmaz.

- Oyunlar, modlar, dünyalar ve sunucular kullanıcıya ait ortak KurtLauncher/data klasörüne kopyalanır; bütün dosyalar doğrulandıktan sonra bu konum kullanılır.
- Aktarım tamamlandıktan sonra eski launcher klasörünü silmek oyunlarını silmez. Kurulu Minecraft/Java, modlar, son profil ve kullanıcı adı korunur.
- Launcher kullanıcıya ait KurtLauncher/app klasörüne otomatik kurulur ve masaüstüne kısayol eklenir.
- Yeni sürümler otomatik indirilir, Ed25519 imzaları doğrulanır, kurulur ve yeniden açılır. Uygulama açıkken de yeni sürümler aranır.
- Oyun, sunucu veya başka bir işlem çalışıyorsa otomatik kurulum bitmesini bekler. Bu tercih Güncellemeler sayfasından kapatılabilir.
- Yeni sürüm başarıyla açıldıktan sonra eski uygulama kopyası ve geçici dosyalar temizlenir. Açılamayan sürümde önceki uygulama geri yüklenir.
- Eski bir indirme dosyasını açmak, kurulu daha yeni sürümü düşürmez.

0.4.1–0.4.4'ten ilk geçiş için Güncellemeler bölümünü veya Windows ZIP'indeki EXE'yi kullanabilirsiniz. Aktarım bitene kadar eski oyun klasörünü koruyun; sonraki açılışlarda masaüstündeki Kurt Launcher kısayolunu kullanın.
