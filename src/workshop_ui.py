"""Catalog pages for resource packs and ready-made modpacks."""
from PySide6.QtCore import Qt, QUrl, QSize
from PySide6.QtGui import QIcon, QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox,
    QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QFileDialog,
    QDialog, QLabel)
from core import LauncherError
from content import ModpackCatalog


class Catalog(QWidget):
    def __init__(self, window, kind):
        from ui import button, label
        super().__init__()
        self.window, self.kind, self.offset, self.total = window, kind, 0, 0
        self.query_state = None
        self.buttons = {}
        box = QVBoxLayout(self); box.setContentsMargins(0,0,0,0)
        self.count = label('Arama için Ara’ya basın.', 'muted'); box.addWidget(self.count)
        row = QHBoxLayout()
        self.query = window.action(QLineEdit()); self.query.setPlaceholderText('Doku paketi ara…' if kind == 'resourcepack' else 'Hazır modpack ara…')
        self.query.returnPressed.connect(self.search); row.addWidget(self.query, 1)
        self.sort = window.action(QComboBox())
        for name, value in (('En çok indirilen','downloads'),('En yeni','newest'),('Son güncellenen','updated'),('Aramaya göre','relevance')):
            self.sort.addItem(name,value)
        self.sort.currentIndexChanged.connect(self.changed); row.addWidget(self.sort)
        row.addWidget(window.action(button('Ara', self.search))); box.addLayout(row)
        if kind == 'modpack':
            row = QHBoxLayout()
            self.current_game = window.action(QCheckBox('Aktif Minecraft sürümüne göre filtrele'))
            self.current_game.toggled.connect(self.changed); row.addWidget(self.current_game)
            self.loader = window.action(QComboBox())
            self.loader.addItem('Tüm yükleyiciler','')
            for value in ('fabric','forge','neoforge','quilt','vanilla'): self.loader.addItem(value.title(),value)
            self.loader.currentIndexChanged.connect(self.changed); row.addWidget(self.loader)
            row.addStretch(); box.addLayout(row)
        self.table = QTableWidget(0,5)
        self.table.setHorizontalHeaderLabels(['Görsel','Paket / Açıklama','Sürüm / Uyumluluk','İndirme','İşlem'])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch)
        for column, width in ((0,90),(2,180),(3,100),(4,160)): self.table.setColumnWidth(column,width)
        self.table.verticalHeader().hide(); self.table.setIconSize(QSize(72,72)); self.table.setMinimumHeight(360)
        box.addWidget(self.table)
        row = QHBoxLayout()
        self.previous = window.action(button('← Önceki', lambda:self.search(max(0,self.offset-20))))
        self.next = window.action(button('Sonraki →', lambda:self.search(self.offset+20)))
        row.addWidget(self.previous); row.addStretch(); row.addWidget(self.next); box.addLayout(row)

    def changed(self):
        self.offset = 0
        if self.window.autostart and not self.window.worker: self.search()

    def search(self, offset=0):
        w = self.window
        if w.worker: return
        offset = 0 if isinstance(offset,bool) else offset
        try:
            query, sort = self.query.text().strip(), self.sort.currentData()
            if self.kind == 'resourcepack':
                profile = w.require_profile()
                state = (query,sort,profile['id'])
                function = lambda task:w.launcher.resources.catalog(profile,query,offset,task,sort=sort)
            else:
                game = w.require_profile()['version'] if self.current_game.isChecked() else ''
                loader = self.loader.currentData(); state = (query,sort,game,loader)
                def function(task):
                    result = w.modpack_catalog.search(query,offset,sort,game,loader)
                    task.status('Modpack görselleri alınıyor…'); task.set_max(len(result['hits']))
                    for index, hit in enumerate(result['hits'],1):
                        hit['icon_path'] = w.launcher.api.icon(hit.get('icon_url'),w.store.icon_cache,task)
                        task.progress(index)
                    return result
            if state != self.query_state:
                offset = 0
            self.query_state = state
            w.run_job('Doku paketleri aranıyor…' if self.kind == 'resourcepack' else 'Hazır modpack’ler aranıyor…', function,
                      lambda result:self.show_result(result,offset))
        except LauncherError as exc: w.report(str(exc))

    def show_result(self, result, offset):
        from ui import logo_pixmap, button
        w = self.window; self.offset,self.total = offset,result.get('total_hits',0)
        hits = result.get('hits',[]); self.table.setRowCount(0)
        self.buttons = {}
        self.count.setText(f'{self.total:,} sonuç • {offset+1 if hits else 0}–{offset+len(hits)}'.replace(',','.'))
        for row, hit in enumerate(hits):
            self.table.insertRow(row); self.table.setRowHeight(row,125)
            image = QTableWidgetItem(); image.setIcon(QIcon(logo_pixmap(hit['title'],hit.get('icon_path'),72)))
            self.table.setItem(row,0,image)
            self.table.setItem(row,1,QTableWidgetItem(hit['title']+'\n'+hit.get('description','')+'\nYapımcı: '+hit.get('author','—')))
            info = hit.get('version_info')
            if self.kind == 'resourcepack':
                text = (info.get('version_number','—')+'\nMinecraft '+w.profile['version']+' uyumlu') if info else hit.get('version_error','Sürüm doğrulanamadı')
            else:
                versions = hit.get('versions',[])
                text = 'Minecraft: '+', '.join(versions[-4:])+'\nPaket sürümünü seç'
            self.table.setItem(row,2,QTableWidgetItem(text))
            self.table.setItem(row,3,QTableWidgetItem(f"{hit.get('downloads',0):,}".replace(',','.')))
            actions = QWidget(); buttons = QVBoxLayout(actions)
            if self.kind == 'resourcepack':
                profile = w.profile
                action = button('↓ İndir',lambda checked=False,pid=hit['project_id'],vid=info.get('id') if info else None:w.download_resource(pid,vid))
                action.setEnabled(bool(info)); buttons.addWidget(action)
                self.buttons[hit['project_id']] = (action, bool(info))
            else:
                buttons.addWidget(button('Sürüm seç ve kur',lambda checked=False,pid=hit['project_id']:w.choose_modpack(pid)))
            buttons.addWidget(button('Paket sayfası ↗',lambda checked=False,pid=hit['project_id']:QDesktopServices.openUrl(QUrl('https://modrinth.com/'+self.kind+'/'+pid))))
            self.table.setCellWidget(row,4,actions)
        self.previous.setEnabled(offset>0); self.next.setEnabled(offset+len(hits)<self.total)
        if self.kind == 'resourcepack': w.refresh_resources()
        w.report('Doku paketi araması tamamlandı.' if self.kind=='resourcepack' else 'Modpack araması tamamlandı.')


class ContentWorkshops:
    def build_content_workshops(self):
        from ui import label, button
        self.modpack_catalog = ModpackCatalog(self.launcher)
        layout = self.page(); layout.addWidget(label('Doku paketi atölyesi','title'))
        layout.addWidget(label('Seçili Minecraft sürümü için paketleri keşfet. Paket sıralamasında son satır daha yüksek önceliklidir.','muted',True))
        row = QHBoxLayout()
        self.resource_discover = button('Doku paketi keşfet',lambda:self.resource_view(False))
        self.resource_downloaded = button('İndirilenler ve sıra',lambda:self.resource_view(True))
        self.resource_discover.setCheckable(True); self.resource_downloaded.setCheckable(True)
        self.resource_discover.setChecked(True)
        row.addWidget(self.resource_discover); row.addWidget(self.resource_downloaded); row.addStretch(); layout.addLayout(row)
        self.resource_catalog = Catalog(self,'resourcepack'); layout.addWidget(self.resource_catalog)
        self.resource_panel = QWidget(); box = QVBoxLayout(self.resource_panel); box.setContentsMargins(0,0,0,0)
        self.resource_table = QTableWidget(0,4); self.resource_table.setHorizontalHeaderLabels(['Seçili','Doku paketi','Sürüm','Minecraft'])
        self.resource_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch)
        self.resource_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.resource_table.setSelectionBehavior(QAbstractItemView.SelectRows); self.resource_table.verticalHeader().hide()
        self.resource_table.setMinimumHeight(300); box.addWidget(self.resource_table)
        row = QHBoxLayout()
        for title, fn in (('+ .zip ekle',self.import_resources),('↑ Yukarı',lambda:self.move_resource(-1)),('↓ Aşağı',lambda:self.move_resource(1)),
                          ('Seçimi ve sırayı uygula',self.apply_resource_selection),('Kaldır',self.remove_resource)):
            row.addWidget(self.action(button(title,fn)))
        box.addLayout(row)
        box.addWidget(button('Doku paketi klasörü ↗',self.open_resource_folder))
        self.resource_panel.hide(); layout.addWidget(self.resource_panel); layout.addStretch()
        layout = self.page(); layout.addWidget(label('Hazır modpack kataloğu','title'))
        layout.addWidget(label('Paketler yeni ve ayrı profile kurulur. Mevcut profilin ve dünyaların korunur. Kurmadan önce oyun/yükleyici ve indirme boyutunu incele.','muted',True))
        self.modpacks_catalog_widget = Catalog(self,'modpack'); layout.addWidget(self.modpacks_catalog_widget)

    def resource_view(self, installed):
        self.resource_panel.setVisible(installed); self.resource_catalog.setVisible(not installed)
        self.resource_discover.setChecked(not installed); self.resource_downloaded.setChecked(installed)
        self.refresh_resources()

    def refresh_resources(self):
        if not hasattr(self,'resource_table'): return
        self.resource_table.setRowCount(0)
        if not self.profile: return
        manager = self.launcher.resources; folder=manager.folder(self.profile)
        enabled = manager.order(self.profile)
        names = [p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower()=='.zip']
        names.sort(key=lambda n:(n not in enabled, enabled.index(n) if n in enabled else n.casefold()))
        records={v['file']:v for v in manager.records(self.profile).values()}
        for row,name in enumerate(names):
            self.resource_table.insertRow(row)
            check=QTableWidgetItem(); check.setCheckState(Qt.Checked if name in enabled else Qt.Unchecked)
            check.setData(Qt.UserRole,name); self.resource_table.setItem(row,0,check)
            record=records.get(name,{})
            self.resource_table.setItem(row,1,QTableWidgetItem(record.get('name',name)))
            self.resource_table.setItem(row,2,QTableWidgetItem(record.get('version_number','Yerel ZIP')))
            self.resource_table.setItem(row,3,QTableWidgetItem('Uyumlu' if self.profile['version'] in record.get('game_versions',[]) else 'Kontrol edilmeli'))
        self.resource_downloaded.setText(f'İndirilenler ve sıra ({len(names)})')
        by_project = manager.records(self.profile)
        for project,(button,compatible) in self.resource_catalog.buttons.items():
            record=by_project.get(project,{})
            present=bool(record and (folder/record.get('file','')).is_file())
            button.setText('✓ İndirildi' if present else '↓ İndir')
            button.setEnabled(compatible and not present and not self.worker)

    def move_resource(self, delta):
        if self.worker: return
        row=self.resource_table.currentRow(); target=row+delta
        if row<0 or not 0<=target<self.resource_table.rowCount(): return
        for column in range(4):
            a,b=self.resource_table.takeItem(row,column),self.resource_table.takeItem(target,column)
            self.resource_table.setItem(target,column,a);self.resource_table.setItem(row,column,b)
        self.resource_table.selectRow(target)

    def apply_resource_selection(self):
        try:
            p=self.require_profile(); self.launcher.ensure_idle()
            names=[self.resource_table.item(i,0).data(Qt.UserRole) for i in range(self.resource_table.rowCount()) if self.resource_table.item(i,0).checkState()==Qt.Checked]
            self.run_job('Doku paketi sırası kaydediliyor…',lambda task:self.launcher.resources.apply_order(p,names,task))
        except LauncherError as exc:self.report(str(exc))

    def download_resource(self,project,version_id):
        if self.worker or not version_id:return
        try:
            p=self.require_profile();self.launcher.ensure_idle()
            self.run_job('Doku paketi indiriliyor…',lambda task:self.launcher.resources.install(project,p,task,version_id))
        except LauncherError as exc:self.report(str(exc))

    def import_resources(self):
        try:
            p=self.require_profile();self.launcher.ensure_idle()
            files,_=QFileDialog.getOpenFileNames(self,'Doku paketi ZIP dosyaları','','Doku paketi (*.zip)')
            if files:self.run_job('Doku paketleri ekleniyor…',lambda task:self.launcher.resources.import_local(p,files,task))
        except LauncherError as exc:self.report(str(exc))

    def remove_resource(self):
        if self.worker:return
        try:
            p=self.require_profile();self.launcher.ensure_idle();row=self.resource_table.currentRow()
            if row<0:raise LauncherError('Tablodan bir doku paketi seçin.')
            name=self.resource_table.item(row,0).data(Qt.UserRole)
            self.run_job('Doku paketi kaldırılıyor…',lambda task:self.launcher.resources.remove(p,name,task))
        except LauncherError as exc:self.report(str(exc))

    def open_resource_folder(self):
        try:self.open_path(self.launcher.resources.folder(self.require_profile()))
        except LauncherError as exc:self.report(str(exc))

    def choose_modpack(self,project):
        if self.worker:return
        try:
            game=self.require_profile()['version'] if self.modpacks_catalog_widget.current_game.isChecked() else ''
            loader=self.modpacks_catalog_widget.loader.currentData()
            self.run_job('Modpack sürümleri alınıyor…',lambda task:self.modpack_catalog.versions(project,game,loader),lambda values:self.show_modpack_versions(project,values))
        except LauncherError as exc:self.report(str(exc))

    def show_modpack_versions(self,project,values):
        from ui import button,label
        if not values:self.report('Seçilen filtrelerle kurulabilir mrpack sürümü yok.');return
        dialog=QDialog(self);dialog.setWindowTitle('Modpack sürümünü seç');dialog.resize(620,300)
        box=QVBoxLayout(dialog);combo=QComboBox()
        for v in values:combo.addItem(v.get('version_number',v['id'])+' • '+', '.join(v.get('game_versions',[])[:4]),v['id'])
        box.addWidget(combo);detail=label('','muted',True);box.addWidget(detail)
        def refresh():
            v=values[combo.currentIndex()];detail.setText('Yükleyici: '+', '.join(v.get('loaders',[]))+'\nYayın: '+v.get('date_published','').split('T')[0])
        combo.currentIndexChanged.connect(refresh);refresh()
        def begin():
            if self.worker:return
            vid=combo.currentData();dialog.accept()
            self.run_job('Modpack indiriliyor ve doğrulanıyor…',lambda task:self.modpack_catalog.download(project,vid,task),lambda result:self.preview_pack(result['source'],result['info']))
        box.addWidget(button('İndir ve kurulumu incele',begin));box.addWidget(button('Vazgeç',dialog.reject))
        self.modpack_versions_dialog=dialog;dialog.open()
