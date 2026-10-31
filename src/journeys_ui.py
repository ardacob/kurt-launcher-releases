"""Quick Play, favorite servers, import preview, local stats and shader guidance."""
from datetime import datetime
from pathlib import Path
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QComboBox,
    QCheckBox,QMessageBox,QFileDialog,QDialog,QTableWidgetItem,QPlainTextEdit)
from core import LauncherError,Task
from journeys import detect_gpu,gpu_tier,server_status
from management_ui import readonly_table


class Journeys:
    def install_keyboard_shortcuts(self):
        from PySide6.QtGui import QShortcut,QKeySequence
        self.shortcuts=[]
        for key,fn in (('Ctrl+1',lambda:self.navigate(0)),('Ctrl+2',lambda:self.navigate(1)),
                       ('Ctrl+3',lambda:self.navigate(9)),('Ctrl+,',lambda:self.navigate(2)),
                       ('F6',self.profiles.setFocus),('Ctrl+Return',lambda:self.play() if not self.worker else None)):
            shortcut=QShortcut(QKeySequence(key),self);shortcut.activated.connect(fn);self.shortcuts.append(shortcut)
        from PySide6.QtWidgets import QApplication
        QApplication.styleHints().colorSchemeChanged.connect(self.apply_system_theme)

    def apply_system_theme(self,scheme):
        if self.store.settings.get('theme')=='system':self.apply_appearance()

    def build_journeys(self):
        from ui import button,label,panel
        home=self.pages.widget(0).widget().layout()
        card,box=panel();self.continue_info=label('Dünyana geri dön','cardTitle');box.addWidget(self.continue_info)
        row=QHBoxLayout()
        self.continue_button=self.action(button('▶  Son dünyama devam et',self.continue_world,'primary'));row.addWidget(self.continue_button)
        row.addWidget(button('Favori sunucular',lambda:self.open_journey(3)))
        row.addWidget(button('Başka launcher’dan aktar',lambda:self.open_journey(4)))
        row.addStretch();box.addLayout(row);home.insertWidget(1,card)
        body=QWidget();box=QVBoxLayout(body);self.management_tabs.addTab(body,'Favori sunucular')
        box.addWidget(label('Sunucuyu kaydet, durumunu kontrol et ve seçtiğin profille katıl. Özel port kullanıyorsa adresin sonuna yaz.','muted',True))
        row=QHBoxLayout();self.favorite_name=QLineEdit();self.favorite_name.setPlaceholderText('Sunucu adı')
        self.favorite_address=QLineEdit();self.favorite_address.setPlaceholderText('sunucu.example:25565')
        row.addWidget(self.favorite_name);row.addWidget(self.favorite_address,1)
        row.addWidget(self.action(button('Aktif profille kaydet',self.add_favorite_server)));box.addLayout(row)
        self.favorites_table=readonly_table(['Sunucu / adres','Profil','Durum / sürüm','Oyuncular','Ping'])
        self.favorites_table.cellDoubleClicked.connect(lambda *_:self.join_favorite_server());box.addWidget(self.favorites_table)
        row=QHBoxLayout()
        for title,fn in (('Durumu kontrol et',self.ping_favorite_server),('Katıl',self.join_favorite_server),('Kaldır',self.remove_favorite_server)):
            row.addWidget(self.action(button(title,fn)))
        box.addLayout(row)
        self.favorite_info=label('Durum kontrolü yalnız seçtiğin sunucuya bağlantı kurar.','muted',True);self.favorite_info.setTextFormat(Qt.PlainText);box.addWidget(self.favorite_info)
        body=QWidget();box=QVBoxLayout(body);self.management_tabs.addTab(body,'Dışarıdan aktar')
        box.addWidget(label('Resmî .minecraft veya Prism/MultiMC oyun klasörünü seç. Dünyalar, modlar, paketler ve oyun ayarları yeni profile kopyalanır. Kaynak korunur; hesaplar ve özel başlatma komutları alınmaz.','muted',True))
        box.addWidget(self.action(button('Kaynak klasörü seç ve tara',self.discover_external)))
        self.external_table=readonly_table(['Bulunan oyun','Minecraft / yükleyici','Kaynak klasörü']);self.external_table.itemSelectionChanged.connect(self.choose_external);box.addWidget(self.external_table)
        row=QHBoxLayout();self.external_name=QLineEdit();self.external_name.setPlaceholderText('Yeni profil adı');row.addWidget(self.external_name,1)
        self.external_version=QLineEdit();self.external_version.setPlaceholderText('Minecraft sürümü');row.addWidget(self.external_version)
        self.external_loader=QComboBox()
        from core import LOADERS
        for loader in LOADERS:self.external_loader.addItem(loader.title(),loader)
        row.addWidget(self.external_loader);box.addLayout(row)
        self.external_worlds=QCheckBox('Dünyaları da aktar');self.external_worlds.setChecked(True);box.addWidget(self.external_worlds)
        box.addWidget(self.action(button('Önizlemeyi yeni profile aktar',self.import_external)))
        box.addWidget(label('Sürüm belirlenemediyse elle seç. Mod yükleyicisini kontrol et; ilk Oyna gerekli Minecraft/Java dosyalarını ortak arşive indirir.','muted',True));self.external_rows=[]
        body=QWidget();box=QVBoxLayout(body);self.management_tabs.addTab(body,'Oyun istatistikleri')
        box.addWidget(label('Bu sürümden itibaren launcher açıkken ölçülen oturum süreleri. Minecraft menüleri dahildir; launcher kapalıyken geçen süre ölçülmez. Bilgiler yalnız bu bilgisayarda tutulur.','muted',True))
        box.addWidget(button('İstatistikleri yenile',self.refresh_sessions))
        self.session_totals=readonly_table(['Profil','Toplam süre','Oturum']);box.addWidget(self.session_totals)
        self.session_table=readonly_table(['Profil / sürüm','Başlangıç','Süre','Durum']);box.addWidget(self.session_table)
        self.management_tabs.currentChanged.connect(lambda _:self.refresh_journeys())
        self.pages.widget(4).widget().layout().insertWidget(1,button('★ Favori sunuculara git',lambda:self.open_journey(3)))
        # Put the link action in the existing server page without changing its invite code field.
        self.pages.widget(4).widget().layout().insertWidget(2,self.action(button('Davet bağlantısını kopyala',self.copy_invite_link)))
        perf=self.tools_tabs.widget(4).widget().layout()
        self.gpu_info=label('Shader önerisi için ekran kartını algıla.','muted',True);perf.insertWidget(1,self.gpu_info)
        perf.insertWidget(2,self.action(button('Ekran kartını algıla ve shader öner',self.suggest_shaders)))
        shaderbox=self.shader_catalog_panel.layout()
        row=QHBoxLayout();row.addWidget(label('Performans sınıfı','muted'))
        self.shader_tier=QComboBox()
        for title,tier in (('Tüm shader’lar',''),('Hafif','low'),('Dengeli','medium'),('Yüksek kalite','high')):self.shader_tier.addItem(title,tier)
        row.addWidget(self.shader_tier);row.addWidget(self.action(button('Donanımıma göre öner',self.suggest_shaders)));row.addStretch();shaderbox.insertLayout(1,row)
        self.shader_tier.currentIndexChanged.connect(self.shader_filter_changed)
        worldbox=self.pages.widget(9).widget().layout();row=QHBoxLayout()
        row.addWidget(self.action(button('▶ Seçili dünyayı aç',self.play_selected_world)))
        row.addWidget(self.action(button('Dünya geçmişi',self.show_world_history)));worldbox.insertLayout(2,row)
        self.refresh_journeys()

    def open_journey(self,index):
        self.open_tools(7);self.management_tabs.setCurrentIndex(index);self.refresh_journeys()

    def refresh_journeys(self):
        if not hasattr(self,'favorites_table'):return
        self.refresh_favorites();self.refresh_sessions()

    def continue_world(self):
        try:
            p=self.require_profile()
            def recent(task):
                from worlds import level_metadata
                rows=[]
                for folder in list(self.launcher.worlds.folder(p).iterdir())[:1000]:
                    task.check()
                    if folder.is_dir() and not folder.is_symlink() and (folder/'level.dat').is_file():
                        self.launcher.worlds.world(p,folder.name)
                        rows.append({**level_metadata(folder/'level.dat'),'name':folder.name})
                if not rows:raise LauncherError('Bu profilde henüz dünya yok. Önce Oyna ile bir dünya oluştur.')
                return max(rows,key=lambda world:world.get('last_played',0))
            self.run_job('Son dünya bulunuyor…',recent,lambda world:self.launch_world(p,world['name'],world.get('title') or world['name']))
        except LauncherError as exc:self.report(str(exc))

    def play_selected_world(self):
        try:
            p,name=self.selected_world();self.launch_world(p,name,name)
        except LauncherError as exc:self.report(str(exc))

    def launch_world(self,p,name,title):
        if self.store.settings['login_mode']=='offline':self.save_player_name()
        self.continue_info.setText('Devam ediliyor: '+title)
        self.run_job('Dünyana dönülüyor…',lambda task:self.launcher.play(p,task,world_name=name),self.report)

    def refresh_favorites(self):
        selected=self.favorites_table.currentRow();self.favorite_rows=self.launcher.favorites.list();self.favorites_table.setRowCount(0)
        for i,row in enumerate(self.favorite_rows):
            self.favorites_table.insertRow(i)
            profile=next((p['name'] for p in self.store.profiles if p['id']==row['profile']),'Profil bulunamadı')
            status=getattr(self,'server_statuses',{}).get(row['id'],{})
            values=[row['name']+'\n'+row['address'],profile,status.get('version','Kontrol edilmedi'),
                    f"{status['online']}/{status['max']}" if 'online' in status else '—',
                    str(status['ping'])+' ms' if status.get('ping') is not None else '—']
            for j,value in enumerate(values):self.favorites_table.setItem(i,j,QTableWidgetItem(value))
        if 0<=selected<len(self.favorite_rows):self.favorites_table.selectRow(selected)

    def selected_favorite(self):
        index=self.favorites_table.currentRow()
        if not 0<=index<len(self.favorite_rows):raise LauncherError('Bir favori sunucu seçin.')
        return self.favorite_rows[index]

    def add_favorite_server(self):
        try:
            p=self.require_profile();self.launcher.favorites.add(self.favorite_name.text(),self.favorite_address.text(),p['id']);self.refresh_favorites()
        except LauncherError as exc:self.report(str(exc))

    def remove_favorite_server(self):
        try:self.launcher.favorites.remove(self.selected_favorite()['id']);self.refresh_favorites()
        except LauncherError as exc:self.report(str(exc))

    def ping_favorite_server(self):
        try:
            row=self.selected_favorite()
            def ping(task):
                try:return server_status(row['address'],task)
                except (OSError,ValueError,TypeError,KeyError) as exc:return {'version':'Ulaşılamadı','description':str(exc)}
            def done(status):
                if not hasattr(self,'server_statuses'):self.server_statuses={}
                self.server_statuses[row['id']]=status;self.refresh_favorites();self.favorite_info.setText(status.get('description',''))
            self.run_job('Sunucu durumu sorgulanıyor…',ping,done)
        except LauncherError as exc:self.report(str(exc))

    def join_favorite_server(self):
        try:
            row=self.selected_favorite();p=next((p for p in self.store.profiles if p['id']==row['profile']),None)
            if p is None:raise LauncherError('Kaydedilen profil bulunamadı. Sunucuyu aktif profille yeniden kaydet.')
            self.profiles.setCurrentIndex(self.profiles.findData(p['id']))
            if self.store.settings['login_mode']=='offline':self.save_player_name()
            self.run_job('Favori sunucuya katılınıyor…',lambda task:self.launcher.play(p,task,join_address=row['address']),self.report)
        except LauncherError as exc:self.report(str(exc))

    def discover_external(self):
        source=QFileDialog.getExistingDirectory(self,'Minecraft veya Prism oyun klasörünü seç')
        if source:self.run_job('Oyun klasörü taranıyor…',lambda task:self.launcher.external_imports.discover(source,task),self.show_external)

    def show_external(self,rows):
        self.external_rows=rows;self.external_table.setRowCount(0)
        for i,row in enumerate(rows):
            self.external_table.insertRow(i)
            for j,value in enumerate((row['name'],(row['version'] or 'Elle seç')+' / '+row['loader'].title(),row['source'])):
                self.external_table.setItem(i,j,QTableWidgetItem(value))
        if rows:self.external_table.selectRow(0)
        else:self.report('Oyun klasörü bulunamadı. İçinde saves/mods/options.txt olan klasörü seç.')

    def choose_external(self):
        i=self.external_table.currentRow()
        if 0<=i<len(self.external_rows):
            row=self.external_rows[i];self.external_name.setText(row['name']+' · Aktarılan');self.external_version.setText(row['version'])
            self.external_loader.setCurrentIndex(self.external_loader.findData(row['loader']))

    def import_external(self):
        i=self.external_table.currentRow()
        if not 0<=i<len(self.external_rows):self.report('Aktarılacak oyunu seçin.');return
        info=self.external_rows[i];name=self.external_name.text();version=self.external_version.text().strip();loader=self.external_loader.currentData();worlds=self.external_worlds.isChecked()
        self.run_job('Oyun yeni profile aktarılıyor…',lambda task:self.launcher.external_imports.install(info,name,version,loader,worlds,task),
            lambda p:(self.reload_profiles(p['id']),self.report('Aktarım tamamlandı. Oyna ile gerekli oyun dosyalarını hazırla.')))

    def refresh_sessions(self):
        if not hasattr(self,'session_table'):return
        self.session_totals.setRowCount(0)
        def duration(n):return f'{int(n)//3600} sa {(int(n)%3600)//60} dk {int(n)%60} sn'
        for i,row in enumerate(self.launcher.sessions.summary()):
            self.session_totals.insertRow(i)
            for j,value in enumerate((row['name'],duration(row['seconds']),str(row['sessions']))):self.session_totals.setItem(i,j,QTableWidgetItem(value))
        self.session_table.setRowCount(0)
        states={'running':'Oynanıyor','completed':'Tamamlandı','interrupted':'Kesintili','launcher_closed':'Launcher kapandı'}
        for i,row in enumerate(reversed(self.launcher.sessions.rows[-100:])):
            self.session_table.insertRow(i)
            values=(row['name']+' / '+row['version'],datetime.fromtimestamp(row['started']).strftime('%d.%m.%Y %H:%M'),duration(row['seconds']),states.get(row['state'],row['state']))
            for j,value in enumerate(values):self.session_table.setItem(i,j,QTableWidgetItem(value))

    def copy_invite_link(self):
        from deep_links import invite_link
        from PySide6.QtWidgets import QApplication
        try:
            if not self.relay.running or not self.server_manager.running:raise LauncherError('Önce çalışan sunucu için davet oluşturun.')
            QApplication.clipboard().setText(invite_link(self.invite_output.text().strip()));self.report('Davet bağlantısı kopyalandı.')
        except LauncherError as exc:self.report(str(exc))

    def receive_invite_link(self,value):
        from deep_links import link_code
        from invites import decode_invite
        try:
            code=link_code(value);info=decode_invite(code)
            self.showNormal();self.raise_();self.activateWindow();self.navigate(4);self.invite_input.setText(code)
            if self.worker:
                self.report('Davet hazır; geçerli işlem bitince Sunucuya katıl düğmesine bas.');return
            message=f"{info['address']}\nMinecraft {info['version']} / {info['loader'].title()}\n\nKatılmadan önce varsa mod listesi kontrol edilecek. Devam edilsin mi?"
            if QMessageBox.question(self,'Sunucu daveti',message)==QMessageBox.Yes:self.join_invitation()
        except LauncherError as exc:self.report(str(exc))

    def suggest_shaders(self):
        def work(task):
            from insights import hardware
            task.status('Ekran kartı algılanıyor…');names=detect_gpu();ram=hardware(self.store.root)['total']
            return names,gpu_tier(names,ram)
        def done(result):
            names,tier=result;self.gpu_info.setText(' / '.join(names or ['Ekran kartı belirlenemedi'])+' • '+{'low':'Hafif','medium':'Dengeli','high':'Yüksek kalite'}[tier]+' başlangıç önerisi. FPS veya VRAM ölçümü değildir.')
            self.shader_tier.setCurrentIndex(self.shader_tier.findData(tier));self.navigate(6)
            if self.autostart and self.profile and not self.worker:self.search_shaders()
        self.run_job('Shader önerisi hazırlanıyor…',work,done)

    def show_world_history(self):
        from ui import button,label
        try:p,name=self.selected_world()
        except LauncherError as exc:self.report(str(exc));return
        dialog=QDialog(self);dialog.setWindowTitle('Dünya geçmişi · '+name);dialog.resize(850,580);box=QVBoxLayout(dialog)
        box.addWidget(label('Değişmeyen dosyalar tekrar saklanmaz. Geri yüklemeden önce mevcut dünya ZIP olarak korunur. Geçmiş yalnız bu bilgisayardadır.','muted',True))
        automatic=QCheckBox('Hızlı devam ile dünyayı açmadan önce otomatik geri dönüş noktası oluştur');automatic.setChecked(self.store.settings.get('world_history_auto',True))
        automatic.toggled.connect(lambda checked:(self.store.settings.update(world_history_auto=checked),self.store.save()));box.addWidget(automatic)
        table=readonly_table(['Tarih','Dünya boyutu','Yeni saklanan','Tür']);box.addWidget(table)
        rows=[]
        def refresh():
            rows[:]=self.launcher.world_history.points(p,name);table.setRowCount(0)
            for i,row in enumerate(rows):
                table.insertRow(i)
                for j,value in enumerate((row['created'].replace('T',' ')[:19],f"{row['bytes']/1048576:.2f} MB",f"{row['new_bytes']/1048576:.2f} MB",'Otomatik' if row.get('automatic') else 'Elle')):table.setItem(i,j,QTableWidgetItem(value))
        refresh();buttons=QHBoxLayout();box.addLayout(buttons)
        def create():
            dialog.accept();self.run_job('Geri dönüş noktası oluşturuluyor…',lambda task:self.launcher.world_history.create(p,name,task),lambda _:self.report('Geri dönüş noktası oluşturuldu.'))
        def restore():
            i=table.currentRow()
            if i<0:return
            if QMessageBox.question(dialog,'Dünyayı geri yükle','Seçili tarihe dönülsün mi? Şimdiki hali ayrıca yedeklenecek.')!=QMessageBox.Yes:return
            path=rows[i]['path'];dialog.accept();self.run_job('Dünya geçmişi geri yükleniyor…',lambda task:self.launcher.world_history.restore(p,name,path,task),lambda result:(self.report(result),self.refresh_worlds()))
        buttons.addWidget(self.action(button('Yeni geri dönüş noktası',create)));buttons.addWidget(self.action(button('Seçili tarihe geri dön',restore)));buttons.addWidget(button('Kapat',dialog.accept));dialog.exec()
