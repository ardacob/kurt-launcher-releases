"""Launcher tools and dialogs; all operations use the shared worker/idle guards."""
from __future__ import annotations
import json
import os
import shutil
import sys
import time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QCheckBox, QSpinBox, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QTabWidget, QFormLayout, QFileDialog, QMessageBox, QInputDialog,
    QDialog, QPlainTextEdit, QColorDialog, QScrollArea, QFrame)
from core import APP_VERSION, LauncherError, Task, atomic_json, read_json
from snapshots import digest
from packs import Packs, ModUpdates
from insights import Collections, hardware, apply_preset, diagnose, read_logs, redact
from updater import Updater


def text(value, wrap=True):
    widget = QLabel(value)
    widget.setWordWrap(wrap)
    widget.setTextFormat(Qt.PlainText)
    return widget


def table(headers):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    for i in range(1, len(headers)):
        widget.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
    widget.setSelectionBehavior(QAbstractItemView.SelectRows)
    widget.setSelectionMode(QAbstractItemView.SingleSelection)
    widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
    widget.verticalHeader().hide()
    widget.setMinimumHeight(170)
    return widget


class Enhancements:
    def tools_button(self, title, fn, row=None):
        item = QPushButton(title)
        item.clicked.connect(fn)
        self.action(item)
        if row is not None: row.addWidget(item)
        return item

    def tools_tab(self, title):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        box = QVBoxLayout(body)
        box.setContentsMargins(18, 18, 18, 18)
        box.setSpacing(14)
        scroll.setWidget(body)
        self.tools_tabs.addTab(scroll, title)
        return box

    def build_tools(self):
        self.packs = Packs(self.launcher)
        self.mod_updates = ModUpdates(self.launcher)
        self.collections = Collections(self.store)
        self.updater = Updater(self.store)
        self.update_rows = []
        self.last_failed_job = None
        self.retrying_job = None
        self.active_job = None
        self.update_checker = None
        self.online_release = None
        self.auto_update_busy = False
        self.auto_update_failed_version = None
        self.pending_update_stage = None
        self.force_auto_update = False
        self.recent_rows = []
        layout = self.page()
        title = text("Kütüphane ve araçlar")
        title.setObjectName("title")
        layout.addWidget(title)
        layout.addWidget(text("Yedeklerin, paylaşılan paketlerin ve profil araçların tek yerde."))
        self.tools_tabs = QTabWidget()
        self.tools_tabs.currentChanged.connect(self.sync_sidebar_selection)
        self.tools_tabs.setMinimumHeight(565)
        layout.addWidget(self.tools_tabs, 1)
        self.build_backup_tools()
        self.build_pack_tools()
        self.build_update_tools()
        self.build_collection_tools()
        self.build_performance_tools()
        self.build_appearance_tools()
        self.build_launcher_update_tools()
        self.extend_existing_pages()
        self.refresh_extras()
        self.apply_appearance()

    def build_backup_tools(self):
        box = self.tools_tab("Yedekler")
        box.addWidget(text("Profil veya sunucu seç. Çalışan oyun/sunucu durdurulmadan yedek alınmaz veya geri yüklenmez."))
        self.backup_target = self.action(QComboBox())
        self.backup_target.currentIndexChanged.connect(self.refresh_backups)
        box.addWidget(self.backup_target)
        row = QHBoxLayout()
        self.auto_backup = QCheckBox("Değişikliklerden ve sunucu açılışından önce otomatik yedekle")
        self.auto_backup.setChecked(self.store.settings.get("auto_backup", True))
        self.auto_backup.toggled.connect(self.save_backup_options)
        row.addWidget(self.auto_backup)
        self.backup_keep = QSpinBox()
        self.backup_keep.setRange(1, 20)
        self.backup_keep.setValue(self.store.settings.get("backup_keep", 5))
        self.backup_keep.valueChanged.connect(self.save_backup_options)
        row.addWidget(text("Saklanacak otomatik yedek:"))
        row.addWidget(self.backup_keep)
        box.addLayout(row)
        box.addWidget(text("Elle alınan ve geri yükleme öncesi alınan güvenlik yedekleri otomatik temizlenmez. Yedekler bu bilgisayarda saklanır."))
        self.backup_table = table(["Tarih / neden", "Boyut"])
        box.addWidget(self.backup_table, 1)
        row = QHBoxLayout()
        self.tools_button("Şimdi yedekle", self.make_backup, row)
        self.tools_button("Seçili yedeği geri yükle", self.restore_backup, row)
        self.tools_button("Listeyi yenile", self.refresh_backups, row)
        self.tools_button("Yedek klasörünü aç", self.open_backup_folder, row)
        box.addLayout(row)

    def backup_profile(self):
        identifier = self.backup_target.currentData()
        profile = next((p for p in self.store.profiles + self.store.servers if p["id"] == identifier), None)
        if not profile: raise LauncherError("Bir profil veya sunucu seçin.")
        return profile

    def save_backup_options(self):
        if not hasattr(self, "backup_keep"): return
        self.store.settings.update(auto_backup=self.auto_backup.isChecked(), backup_keep=self.backup_keep.value())
        self.store.save()

    def refresh_backups(self):
        if not hasattr(self, "backup_table"): return
        self.backup_table.setRowCount(0)
        try:
            for i, item in enumerate(self.launcher.snapshots.list(self.backup_profile())):
                self.backup_table.insertRow(i)
                cell = QTableWidgetItem(item["created"][:19].replace("T", " ") + " UTC · " + item.get("reason", "Yedek"))
                cell.setData(Qt.UserRole, item["path"])
                self.backup_table.setItem(i, 0, cell)
                self.backup_table.setItem(i, 1, QTableWidgetItem(f"{item['size']/1048576:.1f} MB"))
        except LauncherError:
            pass

    def make_backup(self):
        try:
            p = self.backup_profile()
            self.launcher.ensure_profile_idle(p)
            self.run_job("Yedek alınıyor…", lambda task: self.launcher.snapshots.create(p, task),
                         lambda path: (self.refresh_backups(), self.report("Yedek kaydedildi: " + str(path))))
        except LauncherError as exc: self.report(str(exc))

    def restore_backup(self):
        try:
            p = self.backup_profile()
            row = self.backup_table.currentRow()
            if row < 0: raise LauncherError("Listeden bir yedek seçin.")
            source = self.backup_table.item(row, 0).data(Qt.UserRole)
            self.launcher.ensure_profile_idle(p)
            if QMessageBox.question(self, "Yedeği geri yükle", f"{p['name']} seçilen yedeğe döndürülecek. Güncel durum önce ayrıca yedeklenecek. Devam edilsin mi?") != QMessageBox.Yes: return
            self.run_job("Yedek geri yükleniyor…", lambda task: self.launcher.snapshots.restore(p, source, task),
                         lambda msg: (self.reload_profiles(), self.reload_servers(), self.refresh_backups(), self.report(msg)))
        except LauncherError as exc: self.report(str(exc))

    def open_backup_folder(self):
        try: self.open_path(self.launcher.snapshots.folder(self.backup_profile()))
        except LauncherError as exc: self.report(str(exc))

    def build_pack_tools(self):
        box = self.tools_tab("Paket paylaş")
        box.addWidget(text("Mod paketini ayrı bir profile kur veya aktif profilindeki mod listesini arkadaşınla paylaş. Oyun dosyaları, dünyalar ve hesap bilgileri dışa aktarılmaz."))
        row = QHBoxLayout()
        self.tools_button(".mrpack içe aktar", self.import_pack_dialog, row)
        self.tools_button("Aktif profili .mrpack olarak paylaş", self.export_pack_dialog, row)
        box.addLayout(row)
        self.share_config = QCheckBox("Dışa aktarırken config klasörünü de ekle (paylaşmadan önce içeriğini kontrol et)")
        box.addWidget(self.share_config)
        box.addWidget(text("Yerel/değiştirilmiş JAR'lar izinli indirme kaynağı bulunmadan pakete eklenmez. İçe aktarılan modlar ve betikler oyun içinde kod çalıştırabilir; güvendiğin paketleri seç."))
        box.addWidget(text("Sunucuyla modlarım uyumlu mu?"))
        box.addWidget(text("Sunucu sahibi mod listesi dosyasını paylaşabilir. Aktif profilinle karşılaştırıp eksikleri onayından sonra kurabilirsin."))
        row = QHBoxLayout()
        self.tools_button("Sunucu mod listesi oluştur", self.export_server_mods, row)
        self.tools_button("Mod listesiyle karşılaştır", self.compare_file, row)
        box.addLayout(row)
        box.addStretch()

    def import_pack_dialog(self):
        source, _ = QFileDialog.getOpenFileName(self, "Mod paketi seç", "", "Modrinth paketi (*.mrpack)")
        if not source: return
        self.run_job("Mod paketi inceleniyor…", lambda task: self.packs.inspect(source), lambda info: self.preview_pack(source, info))

    def preview_pack(self, source, info):
        dialog = QDialog(self)
        dialog.setWindowTitle("Paket kurulumu")
        dialog.resize(600, 360)
        box = QVBoxLayout(dialog)
        box.addWidget(text(info["name"]))
        box.addWidget(text(f"Minecraft {info['version']} · {info['loader'].title()} {info.get('loader_version') or ''}\n{info['count']} dosya · {info['size']/1048576:.1f} MB indirme\nYeni ve ayrı bir profil oluşturulacak."))
        optional = QCheckBox("İsteğe bağlı istemci dosyalarını da kur")
        box.addWidget(optional)
        box.addWidget(text("Bu paketin kaynağına güveniyorsan kurulumu başlat. Modlar SHA-512 ile doğrulanır."))
        box.addWidget(text('Paket yapımcısının mod sürümleri sabit tutulur. Tekil mod etiketleri paket sürümünden farklıysa Kurulu modlar tablosunda Paket seçimi olarak gösterilir.'))
        row = QHBoxLayout()
        install = QPushButton("Onayla ve kur")
        def begin():
            include = optional.isChecked()
            dialog.accept()
            self.run_job("Mod paketi kuruluyor…", lambda task: self.packs.import_pack(source, task, info, include),
                         lambda p: (self.reload_profiles(p["id"]), self.refresh_extras(), self.report("Paket ayrı profile kuruldu. Oyna ile oyun/yükleyici kurulumu tamamlanır.")))
        install.clicked.connect(begin)
        row.addWidget(install)
        cancel = QPushButton("Vazgeç")
        cancel.clicked.connect(dialog.reject)
        row.addWidget(cancel)
        box.addLayout(row)
        self.pack_dialog = dialog
        dialog.open()

    def export_pack_dialog(self):
        try:
            p = self.require_profile()
            self.launcher.ensure_profile_idle(p)
            target, _ = QFileDialog.getSaveFileName(self, "Mod paketini kaydet", "Kurt-paket.mrpack", "Modrinth paketi (*.mrpack)")
            config = self.share_config.isChecked()
            if target: self.run_job("Mod paketi hazırlanıyor…", lambda task: self.packs.export(p, target, task, config))
        except LauncherError as exc: self.report(str(exc))

    def export_server_mods(self):
        try:
            server = self.selected_server
            target, _ = QFileDialog.getSaveFileName(self, "Sunucu mod listesini paylaş", "sunucu.kurtmods.json", "Mod listesi (*.json)")
            if not target: return
            def export(task):
                metadata = self.packs.describe_mods(server, task)
                atomic_json(Path(target), metadata)
                return "Sunucu mod listesi kaydedildi. JAR dosyaları paylaşılmadı."
            self.run_job("Sunucu mod listesi hazırlanıyor…", export)
        except LauncherError as exc: self.report(str(exc))

    def compare_file(self):
        try:
            p = self.require_profile()
            source, _ = QFileDialog.getOpenFileName(self, "Sunucu mod listesini seç", "", "Mod listesi (*.json)")
            if not source: return
            if Path(source).stat().st_size > 2 * 1024 * 1024: raise LauncherError("Mod listesi çok büyük.")
            description = read_json(Path(source), {})
            self.run_job("Modlar karşılaştırılıyor…", lambda task: self.packs.compare(p, description),
                         lambda result: self.show_comparison(p, description, result))
        except LauncherError as exc: self.report(str(exc))

    def show_comparison(self, profile, description, result, after=None):
        dialog = QDialog(self)
        dialog.setWindowTitle("Sunucuyla mod uyumluluğu")
        dialog.resize(820, 580)
        box = QVBoxLayout(dialog)
        box.addWidget(text(f"{profile['name']} ↔ Minecraft {description.get('version')} / {description.get('loader')} {description.get('loader_version') or ''}"))
        box.addWidget(text("Oyun/yükleyici sürümleri eşleşiyor." if result["profile_matches"] else "Oyun/yükleyici sürümü farklı. Uygun bir profil seçerek yeniden karşılaştırın."))
        rows = table(["Mod", "Durum", "Otomatik kurulum"])
        for i, record in enumerate(result["rows"]):
            rows.insertRow(i)
            for j, value in enumerate((record["file"], record["state"], "Var" if record["installable"] else "Yerel kaynak gerekli")):
                rows.setItem(i, j, QTableWidgetItem(value))
        box.addWidget(rows, 1)
        box.addWidget(text("Fazladan yerel modlar: " + (", ".join(result["extras"][:30]) or "Yok") + ". İstemciye özel modlar normal olabilir; diğerleri çakışabilir."))
        row = QHBoxLayout()
        install = QPushButton("Eksik modları onayla ve kur")
        missing = [r for r in result["rows"] if r["state"] != "Eşleşiyor"]
        install.setEnabled(result["profile_matches"] and bool(missing) and all(r["installable"] for r in missing))
        def sync():
            dialog.accept()
            def synced(message):
                self.report(message)
                self.run_job("Kurulan modlar yeniden karşılaştırılıyor…", lambda task: self.packs.compare(profile, description),
                             lambda updated: self.show_comparison(profile, description, updated, after=after))
            self.run_job("Sunucu modları eşleştiriliyor…", lambda task: self.packs.sync(profile, description, task),
                         synced)
        install.clicked.connect(sync)
        row.addWidget(install)
        if after and result["profile_matches"] and not missing:
            join = QPushButton("Mod listesi eşleşiyor · oyuna katıl")
            join.clicked.connect(lambda: (dialog.accept(), after()))
            row.addWidget(join)
        close = QPushButton("Kapat")
        close.clicked.connect(dialog.reject)
        row.addWidget(close)
        box.addLayout(row)
        self.comparison_dialog = dialog
        dialog.open()

    def build_update_tools(self):
        box = self.tools_tab("Mod güncellemeleri")
        self.updates_profile = text("Aktif profil için kararlı ve uyumlu sürümler kontrol edilir.")
        box.addWidget(self.updates_profile)
        row = QHBoxLayout()
        self.tools_button("Güncellemeleri kontrol et", self.scan_updates, row)
        self.tools_button("Seçili modun değişiklikleri", self.show_changelog, row)
        box.addLayout(row)
        self.updates_table = table(["Mod", "Kurulu → yeni", "Seçim"])
        box.addWidget(self.updates_table, 1)
        box.addWidget(text("Sabitlenmiş modlar otomatik seçilmez. Güncelleme geçici klasörde hazırlanır; bağımlılık sorunu olursa mevcut kurulum korunur."))
        row = QHBoxLayout()
        self.tools_button("İşaretli güncellemeleri uygula", self.apply_mod_updates, row)
        box.addLayout(row)

    def scan_updates(self):
        try:
            p = self.require_profile()
            self.run_job("Mod güncellemeleri aranıyor…", lambda task: self.mod_updates.scan(p, task), self.show_updates)
        except LauncherError as exc: self.report(str(exc))

    def show_updates(self, rows):
        self.update_rows = rows
        self.updates_table.setRowCount(0)
        for i, row in enumerate(rows):
            self.updates_table.insertRow(i)
            self.updates_table.setItem(i, 0, QTableWidgetItem(row["old"]["name"]))
            self.updates_table.setItem(i, 1, QTableWidgetItem(f"{row['old'].get('version_number', '?')} → {row['new'].get('version_number', '?')}"))
            check = QTableWidgetItem("Sabitlenmiş" if row["pinned"] else "Güncelle")
            check.setFlags(check.flags() | Qt.ItemIsUserCheckable)
            check.setCheckState(Qt.Unchecked if row["pinned"] else Qt.Checked)
            if row["pinned"]: check.setFlags(check.flags() & ~Qt.ItemIsEnabled)
            self.updates_table.setItem(i, 2, check)
        self.report(f"{len(rows)} farklı mod sürümü bulundu." if rows else "Uyumlu modlar güncel.")

    def show_changelog(self):
        index = self.updates_table.currentRow()
        if not 0 <= index < len(self.update_rows): return self.report("Bir güncelleme seçin.")
        row = self.update_rows[index]
        self.text_dialog("Mod değişiklikleri", row["new"].get("changelog") or "Yapımcı değişiklik açıklaması eklememiş.")

    def apply_mod_updates(self):
        try:
            p = self.require_profile()
            selected = [v for i, v in enumerate(self.update_rows) if self.updates_table.item(i, 2).checkState() == Qt.Checked]
            if not selected: raise LauncherError("Güncellenecek bir mod işaretleyin.")
            self.run_job("Mod güncellemeleri hazırlanıyor…", lambda task: self.mod_updates.apply(p, selected, task),
                         lambda message: (self.show_updates([]), self.report(message)))
        except LauncherError as exc: self.report(str(exc))

    def pin_selected_mod(self):
        try:
            p = self.require_profile()
            self.launcher.ensure_profile_idle(p)
            pinned = self.mod_updates.pin(p, self.selected_mod())
            self.report("Mod sürümü sabitlendi." if pinned else "Mod sürüm sabitlemesi kaldırıldı.")
        except LauncherError as exc: self.report(str(exc))

    def build_collection_tools(self):
        box = self.tools_tab("Koleksiyonlar")
        box.addWidget(text("Mod keşfet ekranındaki ☆ Kaydet ile favori veya kişisel koleksiyon oluştur."))
        self.collection_select = QComboBox()
        self.collection_select.currentIndexChanged.connect(self.refresh_collection)
        box.addWidget(self.collection_select)
        self.collection_table = table(["Mod", "Açıklama"])
        box.addWidget(self.collection_table, 1)
        row = QHBoxLayout()
        self.tools_button("Seçili modu keşfette aç", self.discover_collection_mod, row)
        self.tools_button("Koleksiyondan çıkar", self.remove_collection_mod, row)
        box.addLayout(row)

    def save_collection_mod(self, hit):
        name, ok = QInputDialog.getItem(self, "Koleksiyona kaydet", "Koleksiyon seç veya yeni ad yaz:", list(self.collections.data), 0, True)
        if ok:
            try:
                self.collections.add(name, hit)
                self.refresh_extras()
                self.report("Mod koleksiyona kaydedildi: " + name)
            except LauncherError as exc: self.report(str(exc))

    def refresh_collection(self):
        if not hasattr(self, "collection_table"): return
        self.collection_table.setRowCount(0)
        for i, (pid, item) in enumerate(self.collections.data.get(self.collection_select.currentText(), {}).items()):
            self.collection_table.insertRow(i)
            cell = QTableWidgetItem(item.get("title", pid))
            cell.setData(Qt.UserRole, pid)
            self.collection_table.setItem(i, 0, cell)
            self.collection_table.setItem(i, 1, QTableWidgetItem(item.get("description", "")))

    def selected_collection_mod(self):
        row = self.collection_table.currentRow()
        if row < 0: raise LauncherError("Bir koleksiyon modu seçin.")
        return self.collection_table.item(row, 0).data(Qt.UserRole)

    def discover_collection_mod(self):
        try:
            pid = self.selected_collection_mod()
            hit = self.collections.data[self.collection_select.currentText()][pid]
            self.navigate(1)
            self.set_mod_view(False)
            self.search_input.setText(hit.get("title", pid))
            self.search_mods()
        except LauncherError as exc: self.report(str(exc))

    def remove_collection_mod(self):
        try:
            self.collections.remove(self.collection_select.currentText(), self.selected_collection_mod())
            self.refresh_collection()
        except LauncherError as exc: self.report(str(exc))

    def build_performance_tools(self):
        box = self.tools_tab("Performans")
        self.hardware_label = text("")
        box.addWidget(self.hardware_label)
        row = QHBoxLayout()
        self.tools_button("Bilgisayar bilgisini yenile", self.refresh_hardware, row)
        self.tools_button("Önerilen RAM'i uygula", self.use_ram_recommendation, row)
        box.addLayout(row)
        box.addWidget(text("Bu öneri toplam ve kullanılabilir belleğe dayanır. Büyük mod paketleri farklı ayar gerektirebilir; FPS artışı garantisi değildir."))
        self.graphics_preset = QComboBox()
        for title, key in (("Düşük · 6 chunk / 60 FPS sınırı", "low"), ("Dengeli · 10 chunk / 120 FPS sınırı", "balanced"), ("Yüksek · 16 chunk / 120 FPS sınırı", "high")):
            self.graphics_preset.addItem(title, key)
        self.graphics_preset.setCurrentIndex(1)
        box.addWidget(self.graphics_preset)
        box.addWidget(self.tools_button("Aktif profile görüntü ayarını uygula", self.use_graphics_preset))
        box.addWidget(text("Görüntü ayarları options.txt dosyasına yazılır. Eski sürümler bazı ayarları tanımayabilir. Diğer kullanıcı ayarları korunur; işlemden önce otomatik yedek alınır."))
        box.addStretch()
        self.refresh_hardware()

    def refresh_hardware(self):
        self.hardware_info = hardware(self.store.root)
        h = self.hardware_info
        self.hardware_label.setText(f"Toplam RAM: {h['total']/1024:.1f} GB · Kullanılabilir: {h['available']/1024:.1f} GB\nÖnerilen Minecraft belleği: {h['recommended']} MB\nBoş disk: {h['disk_free']/1024**3:.1f} GB")

    def use_ram_recommendation(self):
        self.refresh_hardware()
        self.ram.setValue(self.hardware_info["recommended"])
        self.store.settings["ram"] = self.hardware_info["recommended"]
        self.store.save()
        self.report("Önerilen RAM kaydedildi; sonraki oyun açılışında uygulanır.")

    def use_graphics_preset(self):
        try:
            p = self.require_profile()
            key = self.graphics_preset.currentData()
            def apply(task):
                self.launcher.snapshots.before_change(p, task, "Görüntü ayarı öncesi")
                apply_preset(self.store, p, key)
                return "Görüntü ayarları kaydedildi."
            self.run_job("Görüntü ayarları uygulanıyor…", apply)
        except LauncherError as exc: self.report(str(exc))

    def build_appearance_tools(self):
        box = self.tools_tab("Görünüm")
        box.addWidget(text("Açık, sunset, sistem veya yüksek kontrast görünümünü seç. Yazı ve kontrolleri birlikte ölçekle."))
        self.theme_choice=QComboBox()
        for title,value in (('Açık · Gün doğumu','light'),('Koyu · Sunset','sunset'),('Sistem teması','system'),('Yüksek kontrast','contrast')):
            self.theme_choice.addItem(title,value)
        self.theme_choice.setCurrentIndex(max(0,self.theme_choice.findData(self.store.settings.get('theme','light'))))
        box.addWidget(self.theme_choice)
        self.language_choice=QComboBox();self.language_choice.addItem('Türkçe','tr');self.language_choice.addItem('English','en')
        self.language_choice.setCurrentIndex(max(0,self.language_choice.findData(self.store.settings.get('language','tr'))));box.addWidget(self.language_choice)
        self.interface_scale=QSpinBox();self.interface_scale.setRange(90,140);self.interface_scale.setSingleStep(10);self.interface_scale.setSuffix(' %')
        self.interface_scale.setValue(int(self.store.settings.get('ui_scale',100)));box.addWidget(text('Arayüz ölçeği'));box.addWidget(self.interface_scale)
        self.tools_button('Görünümü ve dili uygula',self.save_interface,box)
        box.addWidget(text('Kısayollar: Ctrl+1 Oyun merkezi · Ctrl+2 Modlar · Ctrl+3 Dünyalar · Ctrl+, Ayarlar · F6 Profil seç · Ctrl+Enter Oyna. Tab ile kontroller arasında ilerle.'))
        row = QHBoxLayout()
        self.tools_button("Sunset vurgu rengini seç", self.pick_accent, row)
        self.tools_button("Varsayılan sunset", self.reset_accent, row)
        box.addLayout(row)
        self.compact_mods = QCheckBox("Kompakt mod listesi")
        self.compact_mods.setChecked(self.store.settings.get("compact_mods", False))
        self.compact_mods.toggled.connect(self.save_compact)
        box.addWidget(self.compact_mods)
        row = QHBoxLayout()
        self.tools_button("Aktif profilin kapağını seç", self.pick_cover, row)
        self.tools_button("Profil kapağını kaldır", self.remove_cover, row)
        box.addLayout(row)
        box.addWidget(text("Kapak ve vurgu rengi bu bilgisayarda saklanır. Mod ekran görüntüleri Ayrıntılar penceresinde açılır."))
        box.addStretch()

    def pick_accent(self):
        color = QColorDialog.getColor(QColor(self.store.settings.get("accent", "#ffb875")), self, "Vurgu rengi")
        if color.isValid():
            self.store.settings["accent"] = color.name()
            self.store.save()
            self.apply_appearance()

    def reset_accent(self):
        self.store.settings.pop("accent", None)
        self.store.save()
        self.apply_appearance()

    def apply_appearance(self):
        from appearance import apply
        apply(self)
        if hasattr(self,'localization'):self.localization.refresh()

    def save_interface(self):
        self.store.settings.update(theme=self.theme_choice.currentData(),language=self.language_choice.currentData(),ui_scale=self.interface_scale.value())
        self.store.save();self.apply_appearance()

    def save_compact(self):
        self.store.settings["compact_mods"] = self.compact_mods.isChecked()
        self.store.save()
        self.clear_results()
        self.report("Liste görünümü değişti. Modları yeniden arayın.")

    def pick_cover(self):
        try:
            p = self.require_profile()
            source, _ = QFileDialog.getOpenFileName(self, "Profil kapağı seç", "", "Görsel (*.png *.jpg *.jpeg *.webp)")
            if not source: return
            from PySide6.QtGui import QImageReader
            reader = QImageReader(source)
            size = reader.size()
            if not size.isValid() or max(size.width(), size.height()) > 8192 or Path(source).stat().st_size > 15 * 1024 * 1024:
                raise LauncherError("Kapak okunamıyor veya boyutu çok büyük.")
            reader.setScaledSize(size.scaled(QSize(1200, 600), Qt.KeepAspectRatio))
            image = reader.read()
            if image.isNull(): raise LauncherError("Görsel okunamadı.")
            folder = self.store.root / "covers"
            folder.mkdir(exist_ok=True)
            if not image.save(str(folder / (p["id"] + ".png")), "PNG"): raise LauncherError("Kapak kaydedilemedi.")
            self.refresh_recent()
        except LauncherError as exc: self.report(str(exc))

    def remove_cover(self):
        try:
            p = self.require_profile()
            (self.store.root / "covers" / (p["id"] + ".png")).unlink(missing_ok=True)
            self.refresh_recent()
        except LauncherError as exc: self.report(str(exc))

    def build_launcher_update_tools(self):
        box = self.tools_tab("Launcher güncellemesi")
        box.addWidget(text(f"Kurulu sürüm: {APP_VERSION}\nYalnızca bu yayıncının anahtarıyla imzalanmış paketler kabul edilir. Oyunlar, modlar, dünyalar ve hesap verileri güncelleme paketine dahil edilmez."))
        self.launcher_update_status = text("Ücretsiz GitHub Releases kanalı. İlk çevrimiçi yayın bekleniyor; yerel imzalı paket de seçebilirsin.")
        box.addWidget(self.launcher_update_status)
        self.automatic_update_check = QCheckBox("Açılışta güncellemeleri arka planda kontrol et")
        self.automatic_update_check.setChecked(self.store.settings.get("auto_update_check", True))
        self.automatic_update_check.toggled.connect(self.save_update_preferences)
        box.addWidget(self.automatic_update_check)
        self.automatic_update_install = QCheckBox("Yeni sürümü otomatik indir, kur ve yeniden aç")
        self.automatic_update_install.setChecked(self.store.settings.get("auto_install_updates", True))
        self.automatic_update_install.toggled.connect(self.save_update_preferences)
        box.addWidget(self.automatic_update_install)
        box.addWidget(text("Yeni sürüm imzası doğrulanarak otomatik kurulur. Oyun, sunucu veya başka bir işlem çalışıyorsa kapanması beklenir. Başarılı açılıştan sonra eski uygulama dosyaları temizlenir. Oyunların ortak klasörde korunur."))
        row = QHBoxLayout()
        self.tools_button("Güncellemeleri kontrol et", self.check_launcher_updates, row)
        self.tools_button("İmzalı .kurtupdate paketi seç", self.select_launcher_update, row)
        box.addLayout(row)
        box.addWidget(text("Uygulama güncelleme için kapanır. Yeni sürüm açılamazsa önceki uygulama dosyaları geri yüklenir. İşlem günlüğü data/updates altında saklanır."))
        box.addStretch()

    def check_launcher_updates(self):
        def result(info):
            self.show_online_release(info)
            if info["available"]:
                self.review_online_update()
        self.run_job("Launcher sürümü kontrol ediliyor…", self.updater.check_feed, result)

    def save_update_preferences(self):
        self.store.settings["auto_update_check"] = self.automatic_update_check.isChecked()
        self.store.settings["auto_install_updates"] = self.automatic_update_install.isChecked()
        self.auto_update_failed_version = None
        self.store.save()
        if not self.automatic_update_check.isChecked() and self.update_checker:
            self.update_checker.task.cancel.set()

    def check_updates_background(self):
        if not self.store.settings.get("auto_update_check", True) or self.update_checker:
            return
        from ui import Worker
        from PySide6.QtCore import QThreadPool
        worker = Worker(self.updater.check_feed)
        self.update_checker = worker
        def done(info):
            self.update_checker = None
            self.show_online_release(info)
        def failed(message):
            self.update_checker = None
            self.launcher_update_status.setText("Otomatik kontrol tamamlanamadı. İnternete bağlanınca tekrar kontrol edebilirsin.")
        worker.signals.done.connect(done)
        worker.signals.error.connect(failed)
        worker.signals.cancelled.connect(failed)
        QThreadPool.globalInstance().start(worker)

    def show_online_release(self, info):
        self.launcher_update_status.setText(info["message"])
        if info.get("available"):
            self.online_release = info["manifest"]
            self.update_notification_label.setText("Kurt Launcher " + self.online_release["version"] + " hazır.")
            self.update_notification.show()
            self.sidebar_updates.setText("↑    Güncelleme var")
            if self.autostart:
                QTimer.singleShot(0, self.maybe_auto_update)
        else:
            self.online_release = None
            self.update_notification.hide()
            self.sidebar_updates.setText("↑    Güncellemeler")

    def review_online_update(self):
        if not self.online_release:
            return
        if self.store.settings.get("auto_install_updates", True):
            self.maybe_auto_update(force=True)
            return
        self.open_tools(6)
        info = dict(self.online_release)
        notes = info.get("notes", "")[:1500]
        question = f"Kurt Launcher {info['version']} indirilsin mi?\n\n" + notes
        if QMessageBox.question(self, "Yeni launcher sürümü", question) == QMessageBox.Yes:
            self.run_job("Launcher güncellemesi indiriliyor…", lambda task: self.updater.download_release(info, task), self.inspect_launcher_update)

    def select_launcher_update(self):
        source, _ = QFileDialog.getOpenFileName(self, "İmzalı güncelleme seç", "", "Kurt güncellemesi (*.kurtupdate)")
        if source: self.inspect_launcher_update(source)

    def inspect_launcher_update(self, source):
        self.run_job("Güncelleme imzası inceleniyor…", lambda task: self.updater.inspect(source), lambda info: self.confirm_launcher_update(source, info))

    def confirm_launcher_update(self, source, info):
        try:
            if self.store.settings.get("auto_install_updates", True):
                if not getattr(sys, "frozen", False):
                    raise LauncherError("Otomatik kurulum paketlenmiş Windows uygulamasında yapılır.")
                self.run_job("İmzalı güncelleme hazırlanıyor…", lambda task: self.updater.stage(source, task, info), self.auto_update_prepared)
                return
            self.launcher.ensure_idle()
            if self.server_manager.running: raise LauncherError("Güncellemeden önce sunucuyu durdurun.")
            if not getattr(sys, "frozen", False): raise LauncherError("Kaynak koduyla çalıştırılan uygulamada otomatik değiştirme yapılmaz. Windows EXE paketini kullanın.")
            if QMessageBox.question(self, "Launcher güncellemesi", f"{APP_VERSION} → {info['version']}\nUygulama kapanarak güncellenecek. Oyun verileri korunacak. Devam edilsin mi?") != QMessageBox.Yes: return
            self.run_job("İmzalı güncelleme hazırlanıyor…", lambda task: self.updater.stage(source, task, info), self.apply_launcher_update)
        except LauncherError as exc: self.report(str(exc))

    def automatic_update_failed(self, message):
        self.auto_update_busy = False
        self.auto_update_failed_version = self.online_release.get("version") if self.online_release else "local"
        self.launcher_update_status.setText("Otomatik güncelleme tamamlanamadı. Güncellemeyi incele düğmesiyle yeniden deneyebilirsin.")

    def auto_update_prepared(self, stage):
        self.auto_update_busy = False
        self.pending_update_stage = stage
        self.maybe_auto_update()

    def maybe_auto_update(self, force=False):
        if force:
            self.force_auto_update = True
            self.auto_update_failed_version = None
        if (not self.store.settings.get("auto_install_updates", True) or not getattr(sys, "frozen", False)
                or getattr(self, "maintenance_pending", False)):
            return
        if self.worker or self.auto_update_busy or QApplication.activeModalWidget() is not None:
            return
        if self.server_manager.running or (self.launcher.process and self.launcher.process.poll() is None):
            if self.online_release or self.pending_update_stage:
                self.launcher_update_status.setText("Güncelleme hazır; oyun ve sunucu kapandığında otomatik kurulacak.")
            return
        if self.pending_update_stage:
            stage = self.pending_update_stage
            try:
                self.apply_launcher_update(stage)
                self.pending_update_stage = None
            except (LauncherError, OSError) as exc:
                self.auto_update_failed_version = self.online_release.get("version") if self.online_release else "local"
                self.pending_update_stage = None
                self.report("Otomatik kurulum başlatılamadı: " + str(exc))
            return
        if not self.online_release:
            return
        info = dict(self.online_release)
        if self.auto_update_failed_version == info["version"] and not self.force_auto_update:
            return
        failure = self.store.root / "updates/last-failure.json"
        try:
            previous = json.loads(failure.read_text(encoding="utf-8-sig")) if failure.is_file() else {}
        except (OSError, ValueError):
            previous = {}
        if previous.get("version") == info["version"] and not self.force_auto_update:
            self.launcher_update_status.setText("Önceki güncelleme açılamadı ve eski sürüm geri yüklendi. Yeniden denemek için Güncellemeyi incele'yi seçebilirsin.")
            return
        self.force_auto_update = False
        self.auto_update_busy = True
        def prepare(task):
            package = Path(self.updater.download_release(info, task))
            try:
                return self.updater.stage(package, task)
            finally:
                package.unlink(missing_ok=True)
        self.run_job("Yeni launcher sürümü otomatik hazırlanıyor…", prepare, self.auto_update_prepared)
        if self.worker:
            self.worker.signals.error.connect(self.automatic_update_failed)
            self.worker.signals.cancelled.connect(self.automatic_update_failed)

    def apply_launcher_update(self, stage):
        self.launcher.ensure_idle()
        if self.server_manager.running: raise LauncherError("Önce sunucuyu durdurun.")
        self.relay.stop()
        self.updater.launch_helper(stage)
        self.close()

    def extend_existing_pages(self):
        # Add discoverable entry points without changing existing page indexes.
        self.update_notification = QFrame()
        self.update_notification.setObjectName("panel")
        notice = QHBoxLayout(self.update_notification)
        notice.setContentsMargins(18,10,18,10)
        self.update_notification_label = text("")
        notice.addWidget(self.update_notification_label, 1)
        self.tools_button("Güncellemeyi incele", self.review_online_update, notice)
        dismiss = QPushButton("Daha sonra")
        dismiss.clicked.connect(self.update_notification.hide)
        notice.addWidget(dismiss)
        column = self.centralWidget().layout().itemAt(1).layout()
        column.insertWidget(1, self.update_notification)
        self.update_notification.hide()
        home = self.pages.widget(0).widget().layout()
        row = QHBoxLayout()
        self.tools_button("Yedekler ve paket paylaşımı", lambda: self.open_tools(0), row)
        self.tools_button("Profil sürümünü değiştir", self.change_profile_version, row)
        self.tools_button("Görünüm / kapak", lambda: self.open_tools(5), row)
        home.insertLayout(3, row)
        self.recent_table = table(["Son kullanılan profiller", "Oyun / yükleyici"])
        self.recent_table.setMaximumHeight(190)
        self.recent_table.setIconSize(QSize(96, 48))
        self.recent_table.verticalHeader().setDefaultSectionSize(56)
        self.recent_table.cellDoubleClicked.connect(self.activate_recent)
        home.insertWidget(home.count() - 1, self.recent_table)
        mods = self.installed_panel.layout()
        row = QHBoxLayout()
        self.tools_button("Güncellemeler", lambda: self.open_tools(2), row)
        self.tools_button("Sürümü sabitle / bırak", self.pin_selected_mod, row)
        self.tools_button("Paket paylaş", lambda: self.open_tools(1), row)
        mods.addLayout(row)
        logs = self.pages.widget(3).widget().layout()
        row = QHBoxLayout()
        self.tools_button("Oyun hatasını incele", lambda: self.show_diagnosis(False), row)
        self.tools_button("Sunucu hatasını incele", lambda: self.show_diagnosis(True), row)
        logs.addLayout(row)
        self.build_server_control()
        self.transfer_detail = text("")
        self.transfer_detail.setObjectName("muted")
        self.status.parentWidget().layout().insertWidget(1, self.transfer_detail)
        self.retry_button = self.tools_button("Tekrar dene", self.retry_job)
        self.retry_button.hide()
        self.status.parentWidget().layout().itemAt(0).layout().addWidget(self.retry_button)
        queue = QPushButton("İndirmeler")
        queue.clicked.connect(self.open_downloads)
        self.status.parentWidget().layout().itemAt(0).layout().addWidget(queue)

    def open_tools(self, tab=0):
        self.navigate(5)
        self.tools_tabs.setCurrentIndex(tab)
        self.sync_sidebar_selection()

    def sync_sidebar_selection(self):
        index = self.pages.currentIndex()
        updates = index == 5 and hasattr(self, "tools_tabs") and self.tools_tabs.currentIndex() == 6
        for i, item in enumerate(self.nav):
            item.setChecked(i == index and not updates)
        self.sidebar_updates.setChecked(updates)

    def refresh_extras(self):
        if not hasattr(self, "backup_target"): return
        selected = self.backup_target.currentData() or (self.profile["id"] if self.profile else None)
        self.backup_target.blockSignals(True)
        self.backup_target.clear()
        for p in self.store.profiles + self.store.servers:
            self.backup_target.addItem(("Sunucu · " if p.get("kind") == "server" else "Profil · ") + p["name"], p["id"])
        index = self.backup_target.findData(selected)
        if index >= 0: self.backup_target.setCurrentIndex(index)
        self.backup_target.blockSignals(False)
        self.refresh_backups()
        selected = self.collection_select.currentText()
        self.collection_select.blockSignals(True)
        self.collection_select.clear()
        self.collection_select.addItems(list(self.collections.data))
        if selected in self.collections.data: self.collection_select.setCurrentText(selected)
        self.collection_select.blockSignals(False)
        self.refresh_collection()
        self.refresh_recent()
        self.updates_profile.setText("Aktif profil: " + (self.profile["name"] if self.profile else "Seçilmedi"))

    def refresh_recent(self):
        if not hasattr(self, "recent_table"): return
        self.recent_rows = sorted(self.store.profiles, key=lambda p: p.get("last_played", 0), reverse=True)[:6]
        self.recent_table.setRowCount(0)
        for i, p in enumerate(self.recent_rows):
            self.recent_table.insertRow(i)
            item = QTableWidgetItem(p["name"])
            item.setToolTip("Profili seçmek için çift tıkla")
            cover = self.store.root / "covers" / (p["id"] + ".png")
            if cover.is_file(): item.setIcon(QIcon(str(cover)))
            self.recent_table.setItem(i, 0, item)
            self.recent_table.setItem(i, 1, QTableWidgetItem(p["version"] + " / " + p["loader"].title()))

    def activate_recent(self, row, column=0):
        if self.worker: return
        if 0 <= row < len(self.recent_rows): self.profiles.setCurrentIndex(self.profiles.findData(self.recent_rows[row]["id"]))

    def change_profile_version(self):
        try:
            p = self.require_profile()
            self.launcher.ensure_profile_idle(p)
            versions = [v["id"] for v in self.manifest.get("versions", [])]
            if not versions: raise LauncherError("Önce sürüm listesini yenileyin.")
            version, ok = QInputDialog.getItem(self, "Profil sürümü", "Minecraft sürümü:", versions, versions.index(p["version"]) if p["version"] in versions else 0, False)
            if not ok or version == p["version"]: return
            if QMessageBox.question(self, "Sürüm değişikliği", "Dünya ve modlar önce yedeklenecek. Eski modlar removed-mods altında saklanacak; yeni sürüme uygun modlar ayrıca kurulmalı. Özellikle eski Minecraft sürümüyle dünya açmak verileri etkileyebilir. Devam edilsin mi?") != QMessageBox.Yes: return
            def change(task):
                self.launcher.ensure_profile_idle(p)
                if p["loader"] != "vanilla":
                    from core import mc
                    if not mc.mod_loader.get_mod_loader(p["loader"]).is_minecraft_version_supported(version):
                        raise LauncherError("Seçili yükleyici bu Minecraft sürümünü desteklemiyor.")
                self.launcher.snapshots.create(p, task, "Minecraft sürüm değişikliği öncesi")
                task.check()
                directory = self.store.directory(p)
                mods = self.store.mods(p)
                previous = dict(p)
                previous_lock = self.store.mod_lock(p)
                saved = None
                try:
                    if any(mods.iterdir()):
                        import uuid
                        saved = directory / "removed-mods" / ("version-" + uuid.uuid4().hex)
                        saved.parent.mkdir(exist_ok=True)
                        mods.rename(saved)
                        mods.mkdir()
                    atomic_json(directory / "mods.lock.json", {})
                    p.update(version=version, loader_version=None, installed=None)
                    self.store.save()
                except Exception:
                    p.clear()
                    p.update(previous)
                    if saved and saved.exists():
                        shutil.rmtree(mods, ignore_errors=True)
                        saved.rename(mods)
                    atomic_json(directory / "mods.lock.json", previous_lock)
                    atomic_json(self.store.root / "profiles.json", self.store.profiles)
                    raise
                return "Profil sürümü değişti. Kur / onar ile yeni sürümü kurun; eski duruma yedekten dönebilirsiniz."
            self.run_job("Profil sürümü değiştiriliyor…", change, lambda msg: (self.reload_profiles(p["id"]), self.refresh_extras(), self.report(msg)))
        except LauncherError as exc: self.report(str(exc))

    def build_server_control(self):
        layout = self.pages.widget(4).widget().layout()
        layout.addWidget(text("Sunucu ayarları ve oyuncular"))
        self.server_players = text("Bağlı oyuncu yok / sunucu kapalı")
        layout.addWidget(self.server_players)
        self.server_allowed_players = text("İzin listesi: henüz oyuncu yok")
        layout.addWidget(self.server_allowed_players)
        form = QFormLayout()
        self.server_difficulty = QComboBox()
        for title, value in (("Barışçıl", "peaceful"), ("Kolay", "easy"), ("Normal", "normal"), ("Zor", "hard")): self.server_difficulty.addItem(title, value)
        self.server_gamemode = QComboBox()
        for title, value in (("Hayatta kalma", "survival"), ("Yaratıcı", "creative"), ("Macera", "adventure"), ("İzleyici", "spectator")): self.server_gamemode.addItem(title, value)
        self.server_whitelist = QCheckBox("Yalnızca izin verilen oyuncular")
        self.edit_server_ram = QSpinBox()
        self.edit_server_ram.setRange(1024, 65536)
        self.edit_server_ram.setSingleStep(512)
        self.edit_server_ram.setSuffix(" MB")
        self.edit_server_slots = QSpinBox()
        self.edit_server_slots.setRange(1, 100)
        self.server_view = QSpinBox()
        self.server_view.setRange(2, 32)
        for title, widget in (("Zorluk", self.server_difficulty), ("Oyun modu", self.server_gamemode), ("Görüş uzaklığı", self.server_view), ("RAM", self.edit_server_ram), ("Oyuncu sınırı", self.edit_server_slots), ("Katılım", self.server_whitelist)): form.addRow(title, widget)
        layout.addLayout(form)
        row = QHBoxLayout()
        self.tools_button("Ayarları yükle", self.load_server_controls, row)
        self.tools_button("Ayarları kaydet (sunucu kapalıyken)", self.save_server_controls, row)
        self.tools_button("Sunucu yedekleri", self.open_server_backups, row)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.whitelist_name = QLineEdit()
        self.whitelist_name.setPlaceholderText("Oyuncu adı")
        row.addWidget(self.whitelist_name)
        self.tools_button("İzin listesine ekle", lambda: self.change_whitelist(True), row)
        self.tools_button("Listeden çıkar", lambda: self.change_whitelist(False), row)
        self.tools_button("Oyuncuları yenile", self.request_players, row)
        layout.addLayout(row)
        layout.addWidget(text("Kullanıcı adıyla katılımda oyuncu kimliği doğrulanmaz; izin listesi bu modda kimlik doğrulama sağlamaz."))

    def load_server_controls(self):
        try:
            server = self.selected_server
            config = self.server_manager.configuration(server)
            for widget, key in ((self.server_difficulty, "difficulty"), (self.server_gamemode, "gamemode")):
                index = widget.findData(config[key])
                if index >= 0: widget.setCurrentIndex(index)
            self.server_whitelist.setChecked(config["white-list"] == "true")
            self.server_view.setValue(int(config["view-distance"]))
            self.edit_server_ram.setValue(server["ram"])
            self.edit_server_slots.setValue(server["slots"])
            entries = read_json(self.store.directory(server) / "whitelist.json", [])
            self.server_allowed_players.setText("İzin listesi: " + (", ".join(v.get("name", "?") for v in entries) or "Boş"))
        except (LauncherError, ValueError) as exc: self.report(str(exc))

    def save_server_controls(self):
        try:
            server = self.selected_server
            values = {"difficulty": self.server_difficulty.currentData(), "gamemode": self.server_gamemode.currentData(),
                      "white-list": str(self.server_whitelist.isChecked()).lower(), "view-distance": str(self.server_view.value())}
            ram, slots = self.edit_server_ram.value(), self.edit_server_slots.value()
            self.run_job("Sunucu ayarları kaydediliyor…", lambda task: self.server_manager.configure(server, values, ram, slots, task),
                         lambda message: (self.server_changed(), self.report(message)))
        except LauncherError as exc: self.report(str(exc))

    def change_whitelist(self, add):
        try:
            self.report(self.server_manager.whitelist(self.selected_server, self.whitelist_name.text().strip(), add))
            self.load_server_controls()
        except LauncherError as exc: self.report(str(exc))

    def request_players(self):
        try: self.server_manager.command("list")
        except LauncherError as exc: self.report(str(exc))

    def open_server_backups(self):
        try:
            server = self.selected_server
            self.open_tools(0)
            self.backup_target.setCurrentIndex(self.backup_target.findData(server["id"]))
        except LauncherError as exc: self.report(str(exc))

    def show_diagnosis(self, server=False, profile=None):
        try:
            p = profile or (self.selected_server if server else self.require_profile())
            content = read_logs(self.store.directory(p))
            findings = diagnose(content)
            report = "\n\n".join(v["title"] + "\n" + v["advice"] for v in findings)
            self.text_dialog("Türkçe hata yardımcısı", report + "\n\n--- Kişisel bilgiler filtrelenmiş kayıt ---\n" + (redact(content) or "Henüz oyun/sunucu kaydı yok."), save=True)
        except LauncherError as exc: self.report(str(exc))

    def text_dialog(self, title, content, save=False):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(820, 620)
        box = QVBoxLayout(dialog)
        field = QPlainTextEdit()
        field.setReadOnly(True)
        field.setPlainText(content)
        box.addWidget(field)
        if save:
            hint = text("Rapor otomatik gönderilmez. Filtre her kişisel bilgiyi yakalayamayabilir; paylaşmadan önce inceleyin.")
            box.addWidget(hint)
            export = QPushButton("İncelediğim raporu dosyaya kaydet")
            def write():
                target, _ = QFileDialog.getSaveFileName(dialog, "Tanı raporunu kaydet", "Kurt-tani.txt", "Metin (*.txt)")
                if target: Path(target).write_text(content, encoding="utf-8")
            export.clicked.connect(write)
            box.addWidget(export)
        close = QPushButton("Kapat")
        close.clicked.connect(dialog.accept)
        box.addWidget(close)
        self.info_dialog = dialog
        dialog.open()

    def retry_job(self):
        if self.worker or not self.last_failed_job: return
        title, function, done = self.last_failed_job
        self.run_job(title, function, done)

    def open_downloads(self):
        if hasattr(self, "downloads_dialog") and self.downloads_dialog.isVisible():
            self.downloads_dialog.raise_()
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("İndirmeler ve işlem kuyruğu")
        dialog.resize(720, 450)
        box = QVBoxLayout(dialog)
        box.addWidget(text("Boyutu bilinen dosyalarda hız ve kalan süre gösterilir. Mod/paket kurulumlarında bekleyen dosyalar aşağıda listelenir."))
        self.downloads_text = QPlainTextEdit()
        self.downloads_text.setReadOnly(True)
        box.addWidget(self.downloads_text, 1)
        row=QHBoxLayout()
        self.downloads_pause=QPushButton('Duraklat');self.downloads_pause.clicked.connect(self.toggle_download_pause)
        row.addWidget(self.downloads_pause)
        row.addWidget(text('Hız sınırı (KiB/sn):'))
        limit=QSpinBox();limit.setRange(0,1048576);limit.setSpecialValueText('Sınırsız')
        limit.setValue(int(self.store.settings.get('download_limit_kib',0)))
        limit.valueChanged.connect(self.save_download_limit);row.addWidget(limit);box.addLayout(row)
        box.addWidget(text('Bağlantı kesilirse Tekrar dene ile, HTTP Range destekleyen sunucularda doğrulanmış kısmi dosyadan devam edilir.'))
        close = QPushButton("Kapat")
        close.clicked.connect(dialog.accept)
        box.addWidget(close)
        self.downloads_dialog = dialog
        self.refresh_transfer_stats()
        dialog.open()
