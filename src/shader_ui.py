"""Shader workshop using the launcher's shared worker, progress and idle guards."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, QSize
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QVBoxLayout, QWidget, QLineEdit, QComboBox,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QFileDialog)

from core import LauncherError
from shaders import ENGINES


def shader_text(value, style='muted'):
    from ui import label
    item = label(str(value), style, True)
    item.setTextFormat(Qt.PlainText)
    return item


class ShaderWorkshop:
    def build_shaders(self):
        from ui import button, panel, label
        self.shader_offset = 0
        self.shader_total = 0
        self.shader_query_state = None
        self.shader_catalog_buttons = {}
        layout = self.page()
        layout.addWidget(label('Shaderpack atölyesi', 'title'))
        self.shader_subtitle = shader_text('Bir oyuncu profili seçerek başla.')
        layout.addWidget(self.shader_subtitle)
        frame, box = panel()
        box.addWidget(shader_text('Dünyana yeni bir ışık kat', 'cardTitle'))
        box.addWidget(shader_text('Iris / OptiFine shaderpack’lerini keşfet. İndirilen ZIP’ler seçili profilin shaderpacks klasöründe tutulur. Kullanmak için Minecraft → Video ayarları → Shader Packs bölümünden paketi seç.'))
        row = QHBoxLayout()
        self.shader_iris = self.action(button('Iris’i kur', self.install_shader_iris))
        self.shader_iris.setMaximumWidth(180)
        row.addWidget(self.shader_iris)
        row.addWidget(shader_text('Iris için uyumlu Fabric veya NeoForge profili gerekir. OptiFine kullanacaksan kurulumunu ayrıca yapabilirsin.'), 1)
        box.addLayout(row)
        layout.addWidget(frame)
        row = QHBoxLayout()
        self.shader_discover_tab = button('Shaderpack keşfet', lambda: self.set_shader_view(False))
        self.shader_installed_tab = button('İndirilen shaderpack’ler', lambda: self.set_shader_view(True))
        for item in (self.shader_discover_tab, self.shader_installed_tab):
            item.setCheckable(True)
            row.addWidget(item)
        self.shader_discover_tab.setChecked(True)
        row.addStretch()
        layout.addLayout(row)
        self.shader_catalog_panel = QWidget()
        box = QVBoxLayout(self.shader_catalog_panel)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(14)
        self.shader_search_count = shader_text('Minecraft sürümüne ve shader desteğine göre filtrelenir.')
        box.addWidget(self.shader_search_count)
        row = QHBoxLayout()
        self.shader_search_input = self.action(QLineEdit())
        self.shader_search_input.setPlaceholderText('Shaderpack ara… ör. Complementary, BSL, MakeUp')
        self.shader_search_input.returnPressed.connect(self.search_shaders)
        row.addWidget(self.shader_search_input, 1)
        self.shader_engine = self.action(QComboBox())
        for title, engine in (('Iris / OptiFine', ''), ('Iris', 'iris'), ('OptiFine', 'optifine')):
            self.shader_engine.addItem(title, engine)
        row.addWidget(self.shader_engine)
        self.shader_sort = self.action(QComboBox())
        for title, value in (('En çok indirilen', 'downloads'), ('En yeni', 'newest'),
                             ('Son güncellenen', 'updated'), ('Aramaya göre', 'relevance')):
            self.shader_sort.addItem(title, value)
        row.addWidget(self.shader_sort)
        self.shader_engine.currentIndexChanged.connect(self.shader_filter_changed)
        self.shader_sort.currentIndexChanged.connect(self.shader_filter_changed)
        row.addWidget(self.action(button('Ara', self.search_shaders)))
        box.addLayout(row)
        self.shader_results = QVBoxLayout()
        self.shader_results.setSpacing(14)
        self.shader_results.addWidget(shader_text('Shaderpack’leri görmek için Ara’ya bas.'))
        box.addLayout(self.shader_results)
        row = QHBoxLayout()
        self.shader_previous = self.action(button('← Önceki', lambda: self.search_shaders(max(0, self.shader_offset - 20))))
        self.shader_next = self.action(button('Sonraki →', lambda: self.search_shaders(self.shader_offset + 20)))
        row.addWidget(self.shader_previous)
        row.addStretch()
        row.addWidget(self.shader_next)
        box.addLayout(row)
        layout.addWidget(self.shader_catalog_panel)
        self.shader_installed_panel, box = panel()
        row = QHBoxLayout()
        row.addWidget(label('İndirilen shaderpack’ler', 'cardTitle'))
        row.addStretch()
        row.addWidget(self.action(button('+ .zip ekle', self.import_shaderpacks)))
        box.addLayout(row)
        self.shader_installed = QTableWidget(0, 4)
        self.shader_installed.setHorizontalHeaderLabels(['Shaderpack', 'Paket sürümü', 'Minecraft', 'Shader desteği'])
        self.shader_installed.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in (1, 2, 3):
            self.shader_installed.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.shader_installed.verticalHeader().hide()
        self.shader_installed.verticalHeader().setDefaultSectionSize(48)
        self.shader_installed.setIconSize(QSize(34, 34))
        self.shader_installed.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.shader_installed.setSelectionMode(QAbstractItemView.SingleSelection)
        self.shader_installed.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.shader_installed.setMinimumHeight(210)
        box.addWidget(self.shader_installed)
        box.addWidget(shader_text('İndirilmiş olması oyunda seçili olduğu anlamına gelmez. Etkin paketi Minecraft’ın Shader Packs menüsünden seçebilirsin. Yerel ZIP’lerin sürüm uyumluluğunu yapımcısından kontrol et.'))
        row = QHBoxLayout()
        row.addWidget(self.action(button('Kaldır', self.remove_shaderpack, 'danger')))
        row.addStretch()
        row.addWidget(button('Yenile', self.refresh_shaders))
        row.addWidget(button('Shaderpack klasörü ↗', self.open_shader_folder))
        box.addLayout(row)
        self.shader_installed_panel.hide()
        layout.addWidget(self.shader_installed_panel)
        layout.addStretch()

    def clear_shader_results(self):
        self.shader_catalog_buttons = {}
        while self.shader_results.count():
            item = self.shader_results.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def set_shader_view(self, installed):
        self.shader_catalog_panel.setVisible(not installed)
        self.shader_installed_panel.setVisible(installed)
        self.shader_discover_tab.setChecked(not installed)
        self.shader_installed_tab.setChecked(installed)
        self.refresh_shaders()

    def refresh_shaders(self):
        from ui import logo_pixmap
        if not hasattr(self, 'shader_installed'):
            return
        self.shader_installed.setRowCount(0)
        self.shader_previous.setEnabled(not self.worker and self.shader_offset > 0)
        self.shader_next.setEnabled(not self.worker and self.shader_offset + 20 < self.shader_total)
        p = self.profile
        self.shader_iris.setEnabled(bool(p and p['loader'] in ('fabric', 'neoforge')) and not self.worker)
        if not p:
            self.shader_subtitle.setText('Bir oyuncu profili seçerek başla.')
            self.shader_installed_tab.setText('İndirilen shaderpack’ler (0)')
            return
        self.shader_subtitle.setText(f"{p['name']} • Minecraft {p['version']} • Iris / OptiFine paketleri")
        folder = self.launcher.shaders.folder(p)
        records = self.launcher.shaders.records(p)
        files = sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == '.zip')
        by_file = {v.get('file'): v for v in records.values()}
        for row, path in enumerate(files):
            record = by_file.get(path.name, {})
            self.shader_installed.insertRow(row)
            title = record.get('name', path.stem)
            item = QTableWidgetItem(title)
            item.setData(Qt.UserRole, path.name)
            item.setToolTip(path.name)
            item.setIcon(QIcon(logo_pixmap(title, self.store.cached_icon(record.get('icon_url')), 34)))
            self.shader_installed.setItem(row, 0, item)
            self.shader_installed.setItem(row, 1, QTableWidgetItem(record.get('version_number') or 'Yerel ZIP'))
            matches = p['version'] in record.get('game_versions', [])
            self.shader_installed.setItem(row, 2, QTableWidgetItem('Uyumlu' if matches else 'Kontrol edilmeli'))
            engines = ' / '.join(ENGINES[v] for v in record.get('loaders', []) if v in ENGINES)
            self.shader_installed.setItem(row, 3, QTableWidgetItem(engines or 'Bilinmiyor'))
        self.shader_installed_tab.setText(f'İndirilen shaderpack’ler ({len(files)})')
        for project, (button, version_id) in self.shader_catalog_buttons.items():
            record = records.get(project)
            present = bool(record and (folder / record.get('file', '')).is_file())
            button.setText('✓ İndirildi' if present else 'Kayıt var • kaldırıp tekrar indir' if record else '↓ İndir')
            button.setEnabled(not self.worker and bool(version_id) and not record)

    def shader_filter_changed(self):
        self.shader_offset = 0
        if self.profile and not self.worker:
            self.search_shaders()

    def search_shaders(self, offset=0):
        if self.worker:
            return
        offset = 0 if isinstance(offset, bool) else offset
        try:
            p = self.require_profile()
            query, sort, engine = self.shader_search_input.text().strip(), self.shader_sort.currentData(), self.shader_engine.currentData()
            state = (p['id'], query, sort, engine)
            if state != self.shader_query_state:
                offset = 0
            self.shader_query_state = state
            self.run_job('Shaderpack’ler aranıyor…',
                lambda task: self.launcher.shaders.catalog(p, query, offset, task, sort=sort, engine=engine),
                lambda result: self.show_shader_results(result, offset))
        except LauncherError as exc:
            self.report(str(exc))

    def show_shader_results(self, result, offset):
        from ui import button, panel, mod_logo
        self.clear_shader_results()
        hits = result.get('hits', [])
        self.shader_offset, self.shader_total = offset, result.get('total_hits', 0)
        self.shader_previous.setEnabled(offset > 0)
        self.shader_next.setEnabled(offset + len(hits) < self.shader_total)
        self.shader_search_count.setText(f"{self.shader_total:,} sonuç • {offset + 1 if hits else 0}–{offset + len(hits)}".replace(',', '.'))
        if not hits:
            self.shader_results.addWidget(shader_text('Seçili Minecraft sürümü ve shader desteği için sonuç bulunamadı.'))
        for hit in hits:
            frame, box = panel()
            row = QHBoxLayout()
            if hit.get('preview_path'):
                preview = QLabel()
                preview.setFixedSize(200, 132)
                preview.setPixmap(QPixmap(hit['preview_path']).scaled(200, 132, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                row.addWidget(preview, 0, Qt.AlignTop)
            else:
                row.addWidget(mod_logo(hit, 84), 0, Qt.AlignTop)
            content = QVBoxLayout()
            title_row = QHBoxLayout()
            title_row.addWidget(shader_text(hit['title'], 'cardTitle'), 1)
            title_row.addWidget(shader_text(f"{hit.get('downloads', 0):,} indirme".replace(',', '.')))
            content.addLayout(title_row)
            content.addWidget(shader_text(hit.get('description', '')))
            info = hit.get('version_info')
            if info:
                engines = ' / '.join(ENGINES[v] for v in info.get('loaders', []) if v in ENGINES)
                content.addWidget(shader_text(f"Sürüm {info.get('version_number', info.get('name', '—'))} • Minecraft {self.profile['version']} uyumlu", 'compatible'))
                content.addWidget(shader_text('Gereken shader desteği: ' + engines))
                date = info.get('date_published', '').split('T')[0]
                channel = {'release': 'Kararlı', 'beta': 'Beta', 'alpha': 'Alpha'}.get(info.get('version_type'), 'Sürüm')
                content.addWidget(shader_text(f"{channel} • Yayın: {date or 'Belirtilmemiş'} • Yapımcı: {hit.get('author', '—')}"))
            else:
                content.addWidget(shader_text(hit.get('version_error', 'Uyumlu sürüm doğrulanamadı.')))
            actions = QHBoxLayout()
            actions.addWidget(button('Ayrıntılar ve görseller ↗', lambda checked=False, pid=hit['project_id']: QDesktopServices.openUrl(QUrl('https://modrinth.com/shader/' + pid))))
            actions.addStretch()
            version_id = info.get('id') if info else None
            download = button('↓ İndir', lambda checked=False, pid=hit['project_id'], vid=version_id: self.install_shaderpack(pid, vid))
            download.setEnabled(bool(version_id))
            self.shader_catalog_buttons[hit['project_id']] = (download, version_id)
            actions.addWidget(download)
            content.addLayout(actions)
            row.addLayout(content, 1)
            box.addLayout(row)
            self.shader_results.addWidget(frame)
        self.refresh_shaders()
        self.report('Shaderpack araması tamamlandı.')

    def install_shaderpack(self, project, version_id):
        if self.worker or not version_id:
            return
        try:
            self.launcher.ensure_idle()
            p, engine = self.require_profile(), self.shader_engine.currentData()
            self.run_job('Shaderpack indiriliyor…', lambda task: self.launcher.shaders.install(project, p, task, version_id, engine))
        except LauncherError as exc:
            self.report(str(exc))

    def install_shader_iris(self):
        if not self.worker:
            self.install_mod('iris')

    def import_shaderpacks(self):
        try:
            self.launcher.ensure_idle()
            p = self.require_profile()
            files, _ = QFileDialog.getOpenFileNames(self, 'Shaderpack ZIP dosyalarını seç', '', 'Shaderpack (*.zip)')
            if files:
                self.run_job('Shaderpack’ler ekleniyor…', lambda task: self.launcher.shaders.import_local(p, files, task))
        except LauncherError as exc:
            self.report(str(exc))

    def remove_shaderpack(self):
        if self.worker:
            return
        try:
            self.launcher.ensure_idle()
            p = self.require_profile()
            row = self.shader_installed.currentRow()
            if row < 0:
                raise LauncherError('Tablodan bir shaderpack seçin.')
            name = self.shader_installed.item(row, 0).data(Qt.UserRole)
            self.run_job('Shaderpack kaldırılıyor…', lambda task: self.launcher.shaders.remove(p, name, task))
        except LauncherError as exc:
            self.report(str(exc))

    def open_shader_folder(self):
        try:
            self.open_path(self.launcher.shaders.folder(self.require_profile()))
        except LauncherError as exc:
            self.report(str(exc))
