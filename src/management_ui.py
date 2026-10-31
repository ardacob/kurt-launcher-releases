"""Worlds, profile copies, guided mod tests and explicit storage cleanup."""
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QLineEdit, QCheckBox, QComboBox, QPlainTextEdit, QTabWidget,
    QInputDialog, QFileDialog, QMessageBox)
from core import LauncherError


def readonly_table(headers):
    table=QTableWidget(0,len(headers));table.setHorizontalHeaderLabels(headers)
    table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.verticalHeader().hide();table.setMinimumHeight(180)
    return table


class Management:
    def build_management(self):
        from ui import label,button
        layout=self.page();layout.addWidget(label('Dünyalarım','title'))
        layout.addWidget(label('Dünya sürümü, son oynanma, görsel ve boyut bilgilerini gör; dünyaya özel yedekle, kopyala, dışa aktar veya geri yükle.','muted',True))
        layout.addWidget(self.action(button('Dünyaları yenile',self.refresh_worlds)))
        self.world_table=readonly_table(['Dünya','Son sürüm','Son oynanma','Boyut'])
        self.world_table.setIconSize(QSize(52,52));self.world_table.verticalHeader().setDefaultSectionSize(66)
        self.world_table.itemSelectionChanged.connect(self.select_world);layout.addWidget(self.world_table)
        self.world_info=label('Bir dünya seçin.','muted',True);layout.addWidget(self.world_info)
        self.world_info.setTextFormat(Qt.PlainText)
        row=QHBoxLayout()
        for name,fn in (('Yedekle',self.backup_world),('Kopyala',self.copy_world),('ZIP dışa aktar',self.export_world),('Klasörü aç ↗',self.open_world)):
            row.addWidget(self.action(button(name,fn)))
        layout.addLayout(row)
        row=QHBoxLayout();self.world_backup_choice=QComboBox();row.addWidget(self.world_backup_choice,1)
        row.addWidget(self.action(button('Seçili yedeği geri yükle',self.restore_world)));layout.addLayout(row);layout.addStretch()
        self.world_rows=[]
        box=self.tools_tab('Yönetim')
        tabs=QTabWidget();self.management_tabs=tabs;box.addWidget(tabs)
        tabs.setUsesScrollButtons(True)
        body=QWidget();profile_box=QVBoxLayout(body);tabs.addTab(body,'Profil kopyala')
        profile_box.addWidget(label('Aktif profilin modları, shader/doku paketleri ve ayarları doğrulanarak yeni profile kopyalanır. Minecraft ve Java indirmeleri ortak kullanılmaya devam eder.','muted',True))
        self.clone_name=self.action(QLineEdit());self.clone_name.setPlaceholderText('Yeni profil adı');profile_box.addWidget(self.clone_name)
        self.clone_worlds=self.action(QCheckBox('Dünyaları da kopyala'));profile_box.addWidget(self.clone_worlds)
        profile_box.addWidget(self.action(button('Profili kopyala',self.clone_profile)));profile_box.addStretch()
        body=QWidget();test_box=QVBoxLayout(body);tabs.addTab(body,'Mod sorunu bul')
        test_box.addWidget(label('Modlar ayrı ve dünyasız bir test profilinde gruplar halinde denenir. Gerekli bağımlılıklar birlikte açık tutulur. Her denemeden sonra oyunu kapatıp sonucu belirt. Mod etkileşimleri ve ortak bağımlılıklar nedeniyle sonuç olası adayları gösterir.','muted',True))
        test_box.addWidget(self.action(button('Aktif profilden yeni mod testi başlat',self.begin_mod_test)))
        self.diagnostic_choice=QComboBox();self.diagnostic_choice.currentIndexChanged.connect(self.show_diagnostic);test_box.addWidget(self.diagnostic_choice)
        self.diagnostic_text=QPlainTextEdit();self.diagnostic_text.setReadOnly(True);test_box.addWidget(self.diagnostic_text)
        row=QHBoxLayout()
        self.diagnostic_play=self.action(button('Test profilini başlat',self.play_mod_trial));row.addWidget(self.diagnostic_play)
        self.diagnostic_failed=self.action(button('Aynı sorun oluştu',lambda:self.mod_trial_result(True)));row.addWidget(self.diagnostic_failed)
        self.diagnostic_passed=self.action(button('Sorun oluşmadı',lambda:self.mod_trial_result(False)));row.addWidget(self.diagnostic_passed)
        test_box.addLayout(row)
        body=QWidget();disk_box=QVBoxLayout(body);tabs.addTab(body,'Depolama')
        disk_box.addWidget(label('Oyun arşivindeki disk kullanımını incele. Temizleme yalnız seçtiğin yeniden indirilebilir önbellek dosyalarını kaldırır. İndirme devam verisini temizlersen o dosya yeniden baştan indirilir.','muted',True))
        disk_box.addWidget(self.action(button('Disk kullanımını tara',self.scan_storage)))
        self.storage_groups=readonly_table(['İçerik','Boyut']);disk_box.addWidget(self.storage_groups)
        self.storage_files=readonly_table(['Seçili önbellek dosyası','Boyut']);disk_box.addWidget(self.storage_files)
        row=QHBoxLayout()
        row.addWidget(button('Tüm önbelleği seç / bırak',self.select_all_cache))
        row.addWidget(self.action(button('Seçileni temizle',self.clean_storage,'danger')));disk_box.addLayout(row)
        self.storage_result=None
        self.refresh_diagnostics()

    def refresh_worlds(self):
        if self.worker:return
        try:
            p=self.require_profile()
            self.run_job('Dünyalar taranıyor…',lambda task:self.launcher.worlds.list(p,task),self.show_worlds)
        except LauncherError as exc:self.report(str(exc))

    def show_worlds(self,rows):
        from ui import logo_pixmap
        self.world_rows=rows;self.world_table.setRowCount(0)
        for index,world in enumerate(rows):
            self.world_table.insertRow(index)
            item=QTableWidgetItem(world['title']);item.setData(Qt.UserRole,world['name'])
            item.setIcon(QIcon(logo_pixmap(world['title'],world.get('icon'),52)));self.world_table.setItem(index,0,item)
            self.world_table.setItem(index,1,QTableWidgetItem(world['version']))
            played=world.get('last_played',0)
            try: date=datetime.fromtimestamp(played/1000).strftime('%d.%m.%Y %H:%M') if played else 'Bilinmiyor'
            except (ValueError,OSError,OverflowError):date='Bilinmiyor'
            self.world_table.setItem(index,2,QTableWidgetItem(date))
            self.world_table.setItem(index,3,QTableWidgetItem(f"{world['size']/1048576:.1f} MB"))
        self.world_backup_choice.clear()
        self.report(f'{len(rows)} dünya bulundu.')

    def selected_world(self):
        p=self.require_profile();row=self.world_table.currentRow()
        if row<0:raise LauncherError('Listeden bir dünya seçin.')
        return p,self.world_table.item(row,0).data(Qt.UserRole)

    def select_world(self):
        row=self.world_table.currentRow();self.world_backup_choice.clear()
        if row<0 or row>=len(self.world_rows) or not self.profile:return
        world=self.world_rows[row]
        self.world_info.setText(f"Klasör: {world['name']} • Tohum: {world.get('seed') if world.get('seed') is not None else 'Bilinmiyor'}")
        for backup in self.launcher.worlds.backups(self.profile,world['name']):
            self.world_backup_choice.addItem(backup['created'].replace('T',' ')[:19]+f" • {backup['size']/1048576:.1f} MB",backup['path'])

    def backup_world(self):
        try:
            p,name=self.selected_world()
            self.run_job('Dünya yedekleniyor…',lambda task:self.launcher.worlds.backup(p,name,task),lambda result:(self.select_world(),self.report('Dünya yedeği oluşturuldu.')))
        except LauncherError as exc:self.report(str(exc))

    def copy_world(self):
        try:
            p,name=self.selected_world();new,ok=QInputDialog.getText(self,'Dünya kopyala','Yeni klasör adı:',text=name+'-kopya')
            if ok:self.run_job('Dünya kopyalanıyor…',lambda task:self.launcher.worlds.copy(p,name,new,task),lambda result:(self.report(result),self.refresh_worlds()))
        except LauncherError as exc:self.report(str(exc))

    def export_world(self):
        try:
            p,name=self.selected_world();target,_=QFileDialog.getSaveFileName(self,'Dünyayı ZIP olarak kaydet',name+'.zip','Dünya (*.zip)')
            if target:self.run_job('Dünya dışa aktarılıyor…',lambda task:self.launcher.worlds.export(p,name,target,task))
        except LauncherError as exc:self.report(str(exc))

    def restore_world(self):
        try:
            p,name=self.selected_world();source=self.world_backup_choice.currentData()
            if not source:raise LauncherError('Geri yüklenecek bir dünya yedeği seçin.')
            if QMessageBox.question(self,'Dünya yedeğini geri yükle','Mevcut halinin yeni yedeği alınıp seçili yedek geri yüklensin mi?')!=QMessageBox.Yes:return
            self.run_job('Dünya geri yükleniyor…',lambda task:self.launcher.worlds.restore(p,name,source,task),lambda result:(self.report(result),self.refresh_worlds()))
        except LauncherError as exc:self.report(str(exc))

    def open_world(self):
        try:
            p,name=self.selected_world();self.open_path(self.launcher.worlds.world(p,name))
        except LauncherError as exc:self.report(str(exc))

    def clone_profile(self):
        try:
            p=self.require_profile();name=self.clone_name.text();worlds=self.clone_worlds.isChecked()
            self.run_job('Profil doğrulanarak kopyalanıyor…',lambda task:self.launcher.copies.clone(p,name,worlds,task),
                         lambda clone:(self.reload_profiles(clone['id']),self.report('Yeni profil hazır: '+clone['name'])))
        except LauncherError as exc:self.report(str(exc))

    def begin_mod_test(self):
        try:
            p=self.require_profile()
            self.run_job('Dünyasız mod test profili hazırlanıyor…',lambda task:self.launcher.diagnostics.start(p,task),self.mod_test_started)
        except LauncherError as exc:self.report(str(exc))

    def mod_test_started(self,session):
        self.reload_profiles(session['test_profile']);self.refresh_diagnostics(session['id'])
        self.report('Test profili hazır. Oyunu açıp aynı işlemi dene, kapattıktan sonra sonucu belirt.')

    def refresh_diagnostics(self,selected=None):
        if not hasattr(self,'diagnostic_choice'):return
        selected=selected or self.diagnostic_choice.currentData()
        self.diagnostic_choice.blockSignals(True);self.diagnostic_choice.clear()
        for session in self.launcher.diagnostics.sessions():
            self.diagnostic_choice.addItem(session['source_name']+' • Deneme '+str(session['round']),session['id'])
        index=self.diagnostic_choice.findData(selected)
        if index>=0:self.diagnostic_choice.setCurrentIndex(index)
        self.diagnostic_choice.blockSignals(False);self.show_diagnostic()

    def show_diagnostic(self):
        session_id=self.diagnostic_choice.currentData()
        session=None
        if session_id:
            try:session,profile=self.launcher.diagnostics.get(session_id)
            except LauncherError:pass
        if not session:
            self.diagnostic_text.setPlainText('Henüz mod testi yok.')
        else:
            candidates='\n'.join(session['candidates']) or 'Aday kalmadı; sorun mod etkileşiminden veya başka bir nedenden kaynaklanabilir.'
            self.diagnostic_text.setPlainText(f"Deneme {session['round']} • Açık mod: {len(session['active'])}/{len(session['all'])}\n"+
                ('Olası adaylar / ayrılamayan bağımlılık grubu:\n' if session['complete'] else 'Daraltılan adaylar:\n')+candidates+
                '\n\nAsıl profil ve dünyaları korunur. Sonuç kesin hata teşhisi değildir.')
        self.diagnostic_play.setEnabled(bool(session) and not self.worker)
        for button in (self.diagnostic_failed,self.diagnostic_passed):button.setEnabled(bool(session and not session['complete']) and not self.worker)

    def play_mod_trial(self):
        if self.worker:return
        try:
            session,p=self.launcher.diagnostics.get(self.diagnostic_choice.currentData())
            self.reload_profiles(p['id'])
            self.run_job('Mod test profili başlatılıyor…',lambda task:self.launcher.play(p,task))
        except LauncherError as exc:self.report(str(exc))

    def mod_trial_result(self,crashed):
        if self.worker:return
        try:
            session_id=self.diagnostic_choice.currentData()
            self.run_job('Bir sonraki mod grubu hazırlanıyor…',lambda task:self.launcher.diagnostics.result(session_id,crashed,task),
                         lambda result:self.refresh_diagnostics(result['id']))
        except LauncherError as exc:self.report(str(exc))

    def scan_storage(self):
        self.run_job('Disk kullanımı taranıyor…',lambda task:self.launcher.storage.scan(task),self.show_storage)

    def show_storage(self,result):
        self.storage_result=result;self.storage_groups.setRowCount(0);self.storage_files.setRowCount(0)
        for index,(name,size) in enumerate(result['groups'].items()):
            self.storage_groups.insertRow(index);self.storage_groups.setItem(index,0,QTableWidgetItem(name))
            self.storage_groups.setItem(index,1,QTableWidgetItem(f'{size/1048576:.1f} MB'))
        for index,record in enumerate(result['cleanup']):
            self.storage_files.insertRow(index);item=QTableWidgetItem(record['path']);item.setData(Qt.UserRole,record)
            item.setCheckState(Qt.Unchecked);self.storage_files.setItem(index,0,item)
            self.storage_files.setItem(index,1,QTableWidgetItem(f"{record['size']/1048576:.2f} MB"))
        self.report(f"Toplam {result['total']/1048576:.1f} MB • Temizlenebilir önbellek {result['reclaimable']/1048576:.1f} MB")

    def select_all_cache(self):
        if self.worker:return
        items=[self.storage_files.item(i,0) for i in range(self.storage_files.rowCount())]
        checked=not all(item.checkState()==Qt.Checked for item in items)
        for item in items:item.setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def clean_storage(self):
        if self.worker:return
        records=[self.storage_files.item(i,0).data(Qt.UserRole) for i in range(self.storage_files.rowCount()) if self.storage_files.item(i,0).checkState()==Qt.Checked]
        if not records:self.report('Temizlenecek önbellek dosyalarını seçin.');return
        size=sum(r['size'] for r in records)/1048576
        if QMessageBox.question(self,'Önbelleği temizle',f'{len(records)} dosya ({size:.1f} MB) silinecek. Gerektiğinde yeniden indirilebilir. Temizlensin mi?')!=QMessageBox.Yes:return
        self.run_job('Önbellek temizleniyor…',lambda task:self.launcher.storage.clean(records,task),lambda result:(self.report(result),self.scan_storage()))
