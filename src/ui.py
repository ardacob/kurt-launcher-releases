from __future__ import annotations

import math
import os
import re
from pathlib import Path

from PySide6.QtCore import Qt, QObject, Signal, QRunnable, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QColor, QPainter, QLinearGradient, QPolygonF, QDesktopServices, QFont, QPixmap, QImageReader, QPainterPath, QIcon
from PySide6.QtCore import QPointF, QRectF, QSize
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QComboBox, QLineEdit, QFrame, QStackedWidget, QScrollArea,
    QProgressBar, QFileDialog, QSpinBox, QFormLayout, QInputDialog,
    QPlainTextEdit, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QCompleter, QMessageBox, QLayout, QDialog, QTextBrowser, QCheckBox, QTabWidget,
)

from core import APP_VERSION, LOADERS, Launcher, LauncherError, Cancelled, Store, Task, offline_account
from servers import ServerManager
from invites import PlayitManager, decode_invite
from extras_ui import Enhancements
from shader_ui import ShaderWorkshop
from workshop_ui import ContentWorkshops
from management_ui import Management
from journeys_ui import Journeys
from data_paths import DataLocationError, remember_data_folder, selected_data_folder

CATEGORY_NAMES = {
    "adventure": "Macera", "cursed": "Sıra dışı", "decoration": "Dekorasyon",
    "economy": "Ekonomi", "equipment": "Ekipman", "food": "Yiyecek",
    "game-mechanics": "Oyun mekanikleri", "library": "Kütüphane / API",
    "magic": "Büyü", "management": "Yönetim", "minigame": "Mini oyun",
    "mobs": "Yaratıklar", "optimization": "Performans", "social": "Sosyal",
    "storage": "Depolama", "technology": "Teknoloji", "transportation": "Ulaşım",
    "utility": "Yardımcı araçlar", "worldgen": "Dünya oluşturma", "cooking": "Yemek",
}


def mod_categories(hit):
    values = [CATEGORY_NAMES.get(c, c.replace("-", " ")) for c in hit.get("display_categories", hit.get("categories", []))
              if c not in LOADERS and c not in ("client", "server")]
    return " · ".join(dict.fromkeys(values)) or "Kategori belirtilmemiş"


def mod_version_text(hit):
    info = hit.get("version_info")
    if not info:
        return "Uyumlu mod sürümü doğrulanamadı"
    number = info.get("version_number") or info.get("name") or "Belirtilmemiş"
    loaders = " / ".join(s.title() for s in info.get("loaders", []))
    games = info.get("game_versions", [])
    game_text = ", ".join(games[:5]) + (f" (+{len(games) - 5})" if len(games) > 5 else "")
    return f"Sürüm {number}   •   Minecraft {game_text}   •   {loaders}"

STYLE = """
* { font-family: 'Segoe UI'; font-size: 13px; color: #f7edf1; }
QMainWindow, QWidget#root { background: #0c0b0e; }
QWidget { background: transparent; }
QFrame#sidebar { background: #121015; border-right: 1px solid #352432; }
QFrame#accountPanel { background: #1b141e; border: 1px solid #3d293a; border-radius: 10px; }
QFrame#sidebarDivider { background: #352432; min-height: 1px; max-height: 1px; }
QLabel#sectionLabel { color: #947d8c; font-size: 10px; font-weight: 700; letter-spacing: 1.7px; padding: 6px 12px; }
QLabel#brand { font-size: 24px; font-weight: 800; letter-spacing: 2px; }
QLabel#eyebrow { color: #d796a8; font-size: 11px; font-weight: 700; letter-spacing: 2px; }
QLabel#title { font-size: 28px; font-weight: 700; }
QLabel#muted { color: #b7a3b1; }
QLabel#cardTitle { font-size: 16px; font-weight: 700; }
QLabel#bigNumber { font-size: 30px; font-weight: 700; color: #ffb278; }
QLabel#compatible { color: #ffb278; font-weight: 600; }
QLabel#progressValue { color: #ffc298; font-size: 14px; font-weight: 800; padding-left: 10px; }
QLabel#badge { color: #ffc298; background: #492736; border-radius: 5px; padding: 5px 9px; font-size: 11px; }
QPushButton { background: #2a1b28; border: 1px solid #523244; border-radius: 8px; padding: 10px 17px; font-weight: 600; }
QPushButton:hover { background: #402539; border-color: #e7837c; }
QPushButton:checked { background: #512a3a; border-color: #ff9d74; color: #ffd1b0; }
QPushButton:pressed { background: #653047; }
QPushButton:disabled { background: #201820; color: #816d7b; border-color: #382735; }
QPushButton#primary { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #ffb875,stop:0.55 #ff836d,stop:1 #e96b9f); color: #28131d; border: none; padding: 13px 23px; font-size: 15px; font-weight: 800; }
QPushButton#primary:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #ffd09a,stop:1 #ff8fac); }
QPushButton#primary:disabled { background: #533041; color: #b58c9e; }
QPushButton#nav { text-align: left; padding: 13px 18px; border: none; background: transparent; color: #b19aa9; }
QPushButton#nav:checked { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #643344,stop:1 #342033); color: #ffc69d; }
QPushButton#nav:hover { background: #30202e; }
QPushButton#danger { color: #ff9b9d; }
QLineEdit, QComboBox, QSpinBox { background: #1b141d; border: 1px solid #4b3043; border-radius: 7px; padding: 9px 11px; selection-background-color: #8b485e; }
QLineEdit:focus, QComboBox:focus { border-color: #ffad7a; }
QComboBox QAbstractItemView { background: #261925; selection-background-color: #66354b; padding: 5px; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow { image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #d8afc1; margin-right: 10px; }
QFrame#panel { background: #19131c; border: 1px solid #3d293a; border-radius: 12px; }
QFrame#footer { background: #141016; border-top: 1px solid #3a2635; }
QProgressBar { background: #382132; border: none; border-radius: 4px; height: 7px; }
QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ffb875,stop:0.5 #ff816e,stop:1 #d96caa); border-radius: 4px; }
QScrollArea { border: none; }
QScrollBar:vertical { background: #141016; width: 9px; }
QScrollBar::handle:vertical { background: #704057; border-radius: 4px; min-height: 26px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QTableWidget { background: #19131c; border: 1px solid #4a2e40; border-radius: 8px; gridline-color: #372232; }
QTableWidget::item { padding: 9px; }
QTableWidget::item:selected { background: #60344d; }
QHeaderView::section { background: #2a1b28; padding: 10px; border: none; color: #d6b2c3; }
QPlainTextEdit { background: #120f16; border: 1px solid #493044; border-radius: 8px; padding: 12px; font-family: Consolas; }
QToolTip { background: #3d2337; color: #fff2ec; border: 1px solid #d77981; padding: 6px; }
QDialog, QMessageBox { background: #19131c; }
QCheckBox { spacing: 9px; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #a06478; border-radius: 4px; background: #231722; }
QCheckBox::indicator:checked { background: #ff9b78; border: 2px solid #e16f8e; }
"""


def label(text, style=None, wrap=False, translate=True):
    item = QLabel(text)
    item.setProperty('user_content',not translate)
    if style:
        item.setObjectName(style)
    item.setWordWrap(wrap)
    return item


def logo_pixmap(title, path, size):
    tile = QPixmap(size, size)
    tile.fill(Qt.transparent)
    painter = QPainter(tile)
    painter.setRenderHint(QPainter.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, size, size), 12, 12)
    painter.setClipPath(clip)
    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0, QColor("#743b53"))
    gradient.setColorAt(1, QColor("#302039"))
    painter.fillRect(tile.rect(), gradient)
    image = QPixmap()
    if path:
        reader = QImageReader(str(path))
        dimensions = reader.size()
        if dimensions.isValid() and max(dimensions.width(), dimensions.height()) <= 4096:
            reader.setScaledSize(dimensions.scaled(QSize(size - 10, size - 10), Qt.KeepAspectRatio))
            image = QPixmap.fromImage(reader.read())
    if not image.isNull():
        painter.drawPixmap((size - image.width()) // 2, (size - image.height()) // 2, image)
    else:
        painter.setPen(QColor("#ffc49a"))
        painter.setFont(QFont("Segoe UI", max(12, size // 4), QFont.Bold))
        initials = "".join(word[0] for word in title.split()[:2]).upper() or "M"
        painter.drawText(tile.rect(), Qt.AlignCenter, initials)
    painter.end()
    return tile


def mod_logo(hit, size=76):
    item = QLabel()
    item.setFixedSize(size, size)
    item.setPixmap(logo_pixmap(hit.get("title", "Mod"), hit.get("icon_path"), size))
    item.setToolTip(hit.get("title", "Mod"))
    return item


def button(text, callback, style=None):
    item = QPushButton(text)
    if style:
        item.setObjectName(style)
    item.clicked.connect(callback)
    return item


def panel():
    frame = QFrame()
    frame.setObjectName("panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 20, 22, 20)
    layout.setSpacing(12)
    return frame, layout


class Landscape(QWidget):
    """Original, code-drawn voxel landscape; no remote artwork needed."""
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(220)
        self.setMaximumHeight(240)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        clip=QPainterPath();clip.addRoundedRect(QRectF(self.rect()),18,18);p.setClipPath(clip)
        light=self.window().property('visual_theme')=='light'
        gradient = QLinearGradient(0, 0, w * .25, h)
        gradient.setColorAt(0, QColor('#f6e9df' if light else '#211e35'))
        gradient.setColorAt(.46, QColor('#f8caa6' if light else '#a04b72'))
        gradient.setColorAt(1, QColor('#ffe7be' if light else '#f79e70'))
        p.fillRect(self.rect(), gradient)
        p.setPen(Qt.NoPen)
        p.fillRect(QRectF(w * .80 - 7, 44, 76, 76), QColor(255, 173, 122, 38))
        p.fillRect(QRectF(w * .80, 51, 62, 62), QColor("#ffd293"))
        p.fillRect(QRectF(w * .80, 94, 62, 5), QColor("#e98c8e"))
        p.fillRect(QRectF(w * .65, 36, 48, 8), QColor(239, 164, 177, 100))
        p.fillRect(QRectF(w * .87, 29, 68, 9), QColor(239, 164, 177, 100))
        for points, color in [([(.37,.76),(.57,.16),(.77,.77)], "#6b365d"),
                               ([(.56,.8),(.78,.29),(1,.81)], "#9b526d"),
                               ([(.75,.85),(.94,.12),(1.18,.85)], "#442440")]:
            p.setBrush(QColor(color))
            # Steps on the mountain ridgeline echo blocks rather than smooth peaks.
            p.drawPolygon(QPolygonF([QPointF(x*w,y*h) for x,y in points]))
        for i in range(19):
            x = w*.46 + i*w*.034
            top = h*.73 + math.sin(i*.65)*h*.055
            p.fillRect(QRectF(x, top, w*.035+1, h-top), QColor("#2d1c30"))
            p.fillRect(QRectF(x, top, w*.035+1, 9), QColor("#b86c76"))
            for j in range(3):
                if (i+j)%3==0:
                    p.fillRect(QRectF(x+4,top+25+j*19,8,6),QColor("#4c2b42"))
        for x, y, scale in [(w*.69,h*.58,1), (w*.91,h*.48,1.2), (w*.57,h*.66,.7)]:
            p.fillRect(QRectF(x,y,9*scale,48*scale),QColor("#50304a"))
            p.fillRect(QRectF(x-17*scale,y-13*scale,44*scale,29*scale),QColor("#251a32"))
            p.fillRect(QRectF(x-9*scale,y-29*scale,28*scale,28*scale),QColor("#3b2547"))
        shade = QLinearGradient(0, 0, w*.74, 0)
        shade.setColorAt(0, QColor(250,244,237,250) if light else QColor(14,15,24,250))
        shade.setColorAt(.62, QColor(250,244,237,218) if light else QColor(14,15,24,218))
        shade.setColorAt(1, QColor(250,244,237,0) if light else QColor(14,15,24,0))
        p.fillRect(self.rect(), shade)
        p.setPen(QColor('#99432e' if light else '#ffb078'))
        p.setFont(QFont("Segoe UI", 9, QFont.Bold))
        english=getattr(self.window(),'store',None) and self.window().store.settings.get('language')=='en'
        p.drawText(28, 35, 'YOUR GAME. YOUR WORLD.' if english else 'SENİN OYUNUN. SENİN DÜNYAN.')
        p.setPen(QColor('#28354a' if light else '#fff0ec'))
        p.setFont(QFont('Segoe UI',23,QFont.Bold))
        p.drawText(QRectF(26,54,w*.66,100), Qt.AlignLeft, 'One world.\nEndless possibilities.' if english else 'Bir dünya.\nBinlerce olasılık.')
        p.setPen(QColor('#5f5661' if light else '#e3becb'))
        p.setFont(QFont("Segoe UI", 11))
        p.drawText(QRectF(28,h-48,w*.74,42),Qt.AlignLeft|Qt.TextWordWrap,'Pick a version. Add your mods. Make it yours.' if english else 'Sürümünü seç. Modlarını ekle. Kendi maceranı kur.')


class Signals(QObject):
    progress = Signal(str, object, object)
    done = Signal(object)
    error = Signal(str)
    cancelled = Signal(str)


class Worker(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.signals = Signals()
        self.task = Task(self.signals.progress.emit)
        self.function = function

    def run(self):
        try:
            self.signals.done.emit(self.function(self.task))
        except Cancelled as exc:
            self.signals.cancelled.emit(str(exc))
        except LauncherError as exc:
            self.signals.error.emit(str(exc))
        except Exception as exc:
            # Raw authentication responses may include tokens. Show a safe diagnosis.
            messages = {
                "AzureAppNotPermitted": "Microsoft uygulamasının Minecraft API izni yok. Ayarlardaki geliştirici bağlantısını inceleyin.",
                "AccountNotOwnMinecraft": "Bu Microsoft hesabında Minecraft Java Edition lisansı bulunamadı.",
                "InvalidRefreshToken": "Oturum süresi dolmuş. Microsoft hesabına yeniden giriş yapın.",
                "XErr": "Xbox hesabı doğrulanamadı. Xbox profilini ve hesap izinlerini kontrol edin.",
                "UnsupportedVersion": "Seçilen yükleyici bu Minecraft sürümünü desteklemiyor.",
                "ConnectionError": "Ağa bağlanılamadı. İnternet bağlantısını kontrol edin.",
                "Timeout": "Bağlantı zaman aşımına uğradı. Yeniden deneyin.",
            }
            name = type(exc).__name__
            self.signals.error.emit(messages.get(name, f"İşlem tamamlanamadı ({name}). Bağlantıyı, dosya izinlerini ve ayarları kontrol edin."))


class Window(Journeys, Management, ContentWorkshops, ShaderWorkshop, Enhancements, QMainWindow):
    def __init__(self, data_root=None, autostart=True):
        super().__init__()
        self.store = Store(data_root)
        self.launcher = Launcher(self.store)
        self.server_manager = ServerManager(self.launcher)
        self.relay = PlayitManager(self.launcher)
        self.close_after_server = False
        self.server_was_running = False
        self.worker = None
        self.autostart = autostart
        self.manifest = {"versions": []}
        self.offset, self.total, self.last_query = 0, 0, ""
        self.last_sort = "downloads"
        self._progress_known, self._progress_position = False, 0
        self.actions = []
        self.setWindowTitle(f"Kurt Launcher · {APP_VERSION}")
        self.resize(1240, 850)
        self.setMinimumSize(1040, 740)
        self.setStyleSheet(STYLE)
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0,0,0,0)
        outer.setSpacing(0)
        self.build_sidebar(outer)
        column = QVBoxLayout()
        column.setSpacing(0)
        outer.addLayout(column,1)
        header = QHBoxLayout()
        header.setContentsMargins(28,20,28,18)
        self.breadcrumb = label("OYUN MERKEZİ", "eyebrow")
        header.addWidget(self.breadcrumb)
        header.addStretch()
        header.addWidget(label("AKTİF PROFİL", "eyebrow"))
        self.profiles = QComboBox()
        self.profiles.setMinimumWidth(230)
        self.profiles.currentIndexChanged.connect(self.profile_changed)
        header.addWidget(self.profiles)
        column.addLayout(header)
        self.pages = QStackedWidget()
        column.addWidget(self.pages,1)
        self.build_home()
        self.build_mods()
        self.build_settings()
        self.build_logs()
        self.build_servers()
        self.build_footer(column)
        self.build_tools()
        self.build_shaders()
        self.build_content_workshops()
        self.build_management()
        self.build_journeys()
        from localization import Localization
        self.localization = Localization(self)
        self.install_keyboard_shortcuts()
        self.reload_profiles()
        self.refresh_account()
        self.reload_servers()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_game)
        self.timer.start(1500)
        self.transfer_timer = QTimer(self)
        self.transfer_timer.timeout.connect(self.refresh_transfer_stats)
        self.transfer_timer.start(200)
        self.game_active = False
        if autostart:
            QTimer.singleShot(100, self.refresh_versions)
            QTimer.singleShot(2500, self.check_updates_background)
            self.launcher_update_timer = QTimer(self)
            self.launcher_update_timer.timeout.connect(self.check_updates_background)
            self.launcher_update_timer.start(5 * 60 * 1000)

    @property
    def profile(self):
        index = self.profiles.currentIndex()
        return self.store.profiles[index] if 0 <= index < len(self.store.profiles) else None

    def action(self, item):
        self.actions.append(item)
        return item

    def build_sidebar(self, outer):
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(204)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(14,24,14,16)
        layout.setSpacing(5)
        layout.addWidget(label("◈  KURT", "brand"))
        layout.addWidget(label("   JAVA EDITION", "eyebrow"))
        layout.addSpacing(20)
        layout.addWidget(label("OYUN ALANI", "sectionLabel"))
        self.nav = []
        for index, text in enumerate(["◈    Oyun merkezi", "⊞    Mod atölyesi", "⚙    Ayarlar", "≡    Günlük", "◇    Sunucular", "▣    Kütüphane", "☀    Shaderpack’ler", "▧    Doku paketleri", "▦    Modpack’ler", "▣    Dünyalarım"]):
            item = button(text, lambda checked=False, i=index: self.navigate(i), "nav")
            item.setCheckable(True)
            item.setChecked(index==0)
            item.setProperty("page_index", index)
            self.nav.append(item)
        self.main_navigation = QVBoxLayout()
        self.main_navigation.setSpacing(3)
        self.main_navigation.setContentsMargins(0,0,0,0)
        for index in (0, 1, 7, 6, 8, 9, 5, 4):
            self.nav[index].setStyleSheet('padding: 7px 10px;')
            self.main_navigation.addWidget(self.nav[index])
        navigation_body = QWidget()
        navigation_body.setLayout(self.main_navigation)
        navigation_scroll = QScrollArea()
        navigation_scroll.setWidgetResizable(True)
        navigation_scroll.setMinimumHeight(100)
        navigation_scroll.setFrameShape(QFrame.NoFrame)
        navigation_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        navigation_scroll.setWidget(navigation_body)
        layout.addWidget(navigation_scroll, 1)
        divider = QFrame()
        divider.setObjectName("sidebarDivider")
        layout.addWidget(divider)
        layout.addWidget(label("UYGULAMA", "sectionLabel"))
        self.utility_navigation = QVBoxLayout()
        self.utility_navigation.setSpacing(2)
        self.sidebar_updates = button("↑    Güncellemeler", self.open_launcher_updates, "nav")
        self.sidebar_updates.setCheckable(True)
        self.utility_navigation.addWidget(self.sidebar_updates)
        for index in (3, 2):
            self.utility_navigation.addWidget(self.nav[index])
        layout.addLayout(self.utility_navigation)
        layout.addSpacing(9)
        account_panel = QFrame()
        account_panel.setObjectName("accountPanel")
        account_box = QVBoxLayout(account_panel)
        account_box.setContentsMargins(10,12,10,12)
        account_box.setSpacing(7)
        account_box.addWidget(label("OYUNCU", "eyebrow"))
        self.account_label = label("Hesap bağlı değil", "cardTitle")
        self.account_label.setWordWrap(True)
        account_box.addWidget(self.account_label)
        self.account_mode = self.action(QComboBox())
        self.account_mode.addItem("Kullanıcı adıyla", "offline")
        self.account_mode.addItem("Microsoft hesabı", "microsoft")
        self.account_mode.setCurrentIndex(0 if self.store.settings["login_mode"] == "offline" else 1)
        self.account_mode.currentIndexChanged.connect(self.change_login_mode)
        account_box.addWidget(self.account_mode)
        self.username = self.action(QLineEdit(self.store.settings.get("offline_username", "")))
        self.username.setMaxLength(16)
        self.username.setPlaceholderText("Kullanıcı adını yaz")
        self.username.setToolTip("3–16 karakter: İngilizce harf, rakam ve _")
        self.username.editingFinished.connect(self.save_player_name)
        self.username.returnPressed.connect(self.play)
        account_box.addWidget(self.username)
        self.login_button = self.action(button("Microsoft ile giriş", self.login))
        account_box.addWidget(self.login_button)
        layout.addWidget(account_panel)
        layout.addWidget(label(f"v{APP_VERSION}  •  Java Edition", "muted"))
        outer.addWidget(side)

    def page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
        layout.setContentsMargins(28,4,28,24)
        layout.setSpacing(18)
        scroll.setWidget(body)
        self.pages.addWidget(scroll)
        return layout

    def build_home(self):
        layout = self.page()
        hero = Landscape()
        layout.addWidget(hero)
        row = QHBoxLayout()
        row.addWidget(label("Oynamaya hazır mısın?", "title"))
        row.addStretch()
        self.version_count = label("Sürümler yükleniyor…", "muted")
        row.addWidget(self.version_count)
        layout.addLayout(row)
        frame, box = panel()
        line = QHBoxLayout()
        self.profile_title = label("İlk profilini oluştur", "cardTitle")
        line.addWidget(self.profile_title)
        line.addStretch()
        self.mod_count = label("", "muted")
        line.addWidget(self.mod_count)
        box.addLayout(line)
        self.profile_info = label("Her profilin dünyaları, ayarları ve modları ayrı tutulur.", "muted", True)
        box.addWidget(self.profile_info)
        row = QHBoxLayout()
        row.addWidget(self.action(button("▶  OYNA", self.play, "primary")))
        row.addWidget(self.action(button("↓  Kur / onar", self.install)))
        row.addWidget(self.action(button("Modları yönet", lambda: self.navigate(1))))
        row.addStretch()
        row.addWidget(button("Klasörü aç ↗", self.open_instance))
        box.addLayout(row)
        layout.addWidget(frame)
        frame, box = panel()
        top = QHBoxLayout()
        top.addWidget(label("Yeni bir başlangıç", "cardTitle"))
        top.addStretch()
        top.addWidget(self.action(button("↻  Sürümleri yenile", self.refresh_versions)))
        box.addLayout(top)
        box.addWidget(label("Kararlı sürümler, snapshot'lar ve resmî arşivdeki alpha/beta sürümleri.", "muted", True))
        row = QHBoxLayout()
        self.channel = QComboBox()
        for title, value in [("Kararlı sürümler", "release"), ("Snapshot / ön sürüm", "snapshot"), ("Eski beta", "old_beta"), ("Eski alpha", "old_alpha"), ("Bütün sürümler", "all")]:
            self.channel.addItem(title,value)
        self.channel.currentIndexChanged.connect(self.filter_versions)
        self.version = QComboBox()
        self.version.setEditable(True)
        self.version.setInsertPolicy(QComboBox.NoInsert)
        self.version.setMinimumWidth(150)
        self.loader = QComboBox()
        for item in LOADERS:
            self.loader.addItem(item.title(),item)
        row.addWidget(self.channel,2)
        row.addWidget(self.version,2)
        row.addWidget(self.loader,1)
        row.addWidget(self.action(button("+  Profil oluştur", self.create_profile)))
        box.addLayout(row)
        layout.addWidget(frame)
        layout.addWidget(label("Mod uyumluluğu Minecraft ve yükleyici sürümüne bağlıdır. Eski sürümlerde ek Java ayarı gerekebilir.", "muted", True))
        layout.addStretch()

    def build_mods(self):
        layout = self.page()
        layout.addWidget(label("Mod atölyesi", "title"))
        self.mod_subtitle = label("Bir mod yükleyicili profil seçerek başla.","muted",True)
        layout.addWidget(self.mod_subtitle)
        tabs = QHBoxLayout()
        self.discover_tab = button("Mod keşfet", lambda: self.set_mod_view(False))
        self.installed_tab = button("Kurulu modlar", lambda: self.set_mod_view(True))
        for item in (self.discover_tab, self.installed_tab):
            item.setCheckable(True)
            tabs.addWidget(item)
        self.discover_tab.setChecked(True)
        tabs.addStretch()
        layout.addLayout(tabs)
        frame, box = panel()
        row = QHBoxLayout()
        row.addWidget(label("Kurulu modlar", "cardTitle"))
        row.addStretch()
        row.addWidget(self.action(button("+  .jar dosyası ekle", self.import_mods)))
        box.addLayout(row)
        self.installed = QTableWidget(0,4)
        self.installed.setHorizontalHeaderLabels(["Mod", "Sürüm", "Uyumluluk", "Durum"])
        self.installed.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        for column in (1,2,3):
            self.installed.horizontalHeader().setSectionResizeMode(column,QHeaderView.ResizeToContents)
        self.installed.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.installed.setSelectionMode(QAbstractItemView.SingleSelection)
        self.installed.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.installed.verticalHeader().hide()
        self.installed.setIconSize(QSize(34,34))
        self.installed.verticalHeader().setDefaultSectionSize(48)
        self.installed.setMinimumHeight(155)
        self.installed.setMaximumHeight(210)
        box.addWidget(self.installed)
        row = QHBoxLayout()
        row.addWidget(self.action(button("Etkinleştir / kapat", self.toggle_mod)))
        row.addWidget(self.action(button("Kaldır", self.remove_mod, "danger")))
        row.addWidget(self.action(button("Bilgileri güncelle", self.update_mod_info)))
        row.addStretch()
        row.addWidget(button("↻  Yenile", self.refresh_mods))
        row.addWidget(button("Mod klasörü ↗", self.open_mods))
        box.addLayout(row)
        layout.addWidget(frame)
        self.installed_panel = frame
        self.installed_panel.hide()
        self.catalog_panel = QWidget()
        layout.addWidget(self.catalog_panel)
        layout = QVBoxLayout(self.catalog_panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        self.catalog_buttons = {}
        row = QHBoxLayout()
        row.addWidget(label("Modrinth'te keşfet", "cardTitle"))
        row.addStretch()
        self.search_count = label("Sürüm ve yükleyici uyumluluğu kontrol edilir.","muted")
        row.addWidget(self.search_count)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Mod ara… ör. Sodium, Create, JEI")
        self.search_input.returnPressed.connect(self.search_mods)
        row.addWidget(self.search_input,1)
        self.mod_sort = self.action(QComboBox())
        for title, value in (("En çok indirilen", "downloads"), ("En yeni", "newest"),
                             ("Son güncellenen", "updated"), ("Aramaya göre", "relevance")):
            self.mod_sort.addItem(title, value)
        self.mod_sort.setMinimumWidth(190)
        self.mod_sort.setToolTip("Tüm Modrinth sonuçlarını seçilen sırayla getirir.")
        self.mod_sort.currentIndexChanged.connect(self.change_mod_sort)
        row.addWidget(self.mod_sort)
        row.addWidget(self.action(button("Ara",self.search_mods)))
        layout.addLayout(row)
        self.results = QVBoxLayout()
        self.results.setSpacing(10)
        layout.addLayout(self.results)
        self.empty_result = label("Modları görmek için Ara'ya bas. İndirilen dosyalar SHA-512 ile doğrulanır.","muted",True)
        self.results.addWidget(self.empty_result)
        row = QHBoxLayout()
        self.previous = self.action(button("←  Önceki",lambda:self.search_mods(max(0,self.offset-20))))
        self.next = self.action(button("Sonraki  →",lambda:self.search_mods(self.offset+20)))
        row.addWidget(self.previous)
        row.addStretch()
        row.addWidget(self.next)
        layout.addLayout(row)
        layout.addStretch()

    def set_mod_view(self, installed):
        self.installed_panel.setVisible(installed)
        self.catalog_panel.setVisible(not installed)
        self.discover_tab.setChecked(not installed)
        self.installed_tab.setChecked(installed)
        if installed:
            self.refresh_mods()

    def build_settings(self):
        layout = self.page()
        layout.addWidget(label("Her şey senin ayarında", "title"))
        layout.addWidget(label("Oyun, hesap ve görünüm ayarlarını buradan yönet.","muted"))
        self.settings_tabs=QTabWidget()
        self.settings_tabs.setMinimumHeight(520)
        layout.addWidget(self.settings_tabs,1)
        general=QScrollArea();general.setWidgetResizable(True)
        body=QWidget();layout=QVBoxLayout(body)
        layout.setContentsMargins(18,18,18,18);layout.setSpacing(18)
        general.setWidget(body);self.settings_tabs.addTab(general,'Genel')
        frame, box = panel()
        box.addWidget(label("Oyun ayarları", "cardTitle"))
        form = QFormLayout()
        form.setSpacing(18)
        self.ram = QSpinBox()
        self.ram.setRange(1024,65536)
        self.ram.setSingleStep(512)
        self.ram.setSuffix(" MB")
        self.ram.setValue(int(self.store.settings.get("ram",4096)))
        form.addRow("En fazla RAM",self.ram)
        self.java_path = QLineEdit(self.store.settings.get("java",""))
        self.java_path.setPlaceholderText("Otomatik — sürüme uygun Java indirilir")
        row = QHBoxLayout()
        row.addWidget(self.java_path,1)
        row.addWidget(button("Seç…",self.pick_java))
        form.addRow("Java çalıştırıcısı",row)
        box.addLayout(form)
        box.addWidget(label("Bilgisayarın belleğinin tamamını oyuna ayırma. Özel Java seçimi bütün profillere uygulanır.","muted",True))
        layout.addWidget(frame)
        frame, box = panel()
        box.addWidget(label("Microsoft hesabı", "cardTitle"))
        box.addWidget(label("Kullanıcı adıyla oynamak için bu bölüm gerekli değildir. Microsoft hesabıyla giriş seçeneği için launcher'a ait uygulama kimliği ve Minecraft API erişim onayı gerekir.","muted",True))
        self.client_id = QLineEdit(self.store.settings.get("client_id",""))
        self.client_id.setPlaceholderText("Application (client) ID — ör. xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        box.addWidget(self.client_id)
        box.addWidget(label("Public client / masaüstü uygulaması • kişisel Microsoft hesapları • dönüş adresi: http://localhost/callback. Şifre tarayıcıda girilir; yenileme anahtarı Windows Kimlik Bilgisi Yöneticisi'nde tutulur.","muted",True))
        row = QHBoxLayout()
        row.addWidget(button("Geliştirici kurulum rehberi ↗",lambda:QDesktopServices.openUrl(QUrl("https://minecraft-launcher-lib.readthedocs.io/en/stable/tutorial/microsoft_login.html"))))
        row.addWidget(self.action(button("Hesaptan çık",self.logout)))
        row.addStretch()
        box.addLayout(row)
        layout.addWidget(frame)
        row = QHBoxLayout()
        row.addWidget(self.action(button("Ayarları kaydet",self.save_settings,"primary")))
        row.addStretch()
        self.previous_games = self.action(button("Eski oyun klasörünü seç…", self.pick_previous_games))
        row.addWidget(self.previous_games)
        row.addWidget(button("Veri klasörü ↗",lambda:self.open_path(self.store.root)))
        layout.addLayout(row)
        layout.addWidget(label("Veriler: " + str(self.store.root),"muted",True))
        layout.addWidget(label("Oyunlar, modlar ve dünyalar launcher'dan bağımsız ortak klasörde tutulur. Eski launcher klasörünü kaldırmak oyunlarını silmez.","muted",True))
        layout.addWidget(label("Kurt Launcher bağımsız bir projedir. Mojang veya Microsoft ile bağlantılı değildir.","muted",True))
        layout.addStretch()

    def build_logs(self):
        layout = self.page()
        layout.addWidget(label("İşlem günlüğü", "title"))
        layout.addWidget(label("İndirme ve kurulum durumunu buradan takip edebilirsin.","muted"))
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMaximumBlockCount(1200)
        layout.addWidget(self.logs,1)
        row = QHBoxLayout()
        row.addWidget(button("Günlüğü temizle",self.logs.clear))
        row.addWidget(button("Oyun günlüğünü aç ↗",self.open_game_log))
        row.addStretch()
        layout.addLayout(row)

    def build_footer(self,column):
        footer = QFrame()
        footer.setObjectName("footer")
        box = QVBoxLayout(footer)
        box.setContentsMargins(28,13,28,13)
        row = QHBoxLayout()
        self.status = label("Hazır", "muted")
        self.status.setWordWrap(True)
        row.addWidget(self.status,1)
        self.progress_value = label("Hazır", "progressValue")
        self.progress_value.setMinimumWidth(125)
        self.progress_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.progress_value.setToolTip("Yüzde geçerli indirme veya kurulum aşamasını gösterir. Yeni aşamada yeniden başlar.")
        row.addWidget(self.progress_value)
        self.cancel = button("İptal",self.cancel_job)
        self.cancel.hide()
        row.addWidget(self.cancel)
        self.pause_download = button('Duraklat', self.toggle_download_pause)
        self.pause_download.hide()
        row.addWidget(self.pause_download)
        box.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(8)
        self.progress.setRange(0,100)
        self.progress.setValue(0)
        box.addWidget(self.progress)
        column.addWidget(footer)

    def build_servers(self):
        layout = self.page()
        layout.addWidget(label("Arkadaşlarınla aynı dünyada", "title"))
        layout.addWidget(label("Bilgisayarında Vanilla veya Fabric sunucusu oluştur. Dünyan ayrı klasörde saklanır.", "muted", True))
        frame, box = panel()
        row = QHBoxLayout()
        row.addWidget(label("Port açmadan, davet koduyla oyna", "cardTitle"))
        row.addStretch()
        row.addWidget(label("ÜCRETSİZ · MINECRAFT JAVA", "badge"))
        box.addLayout(row)
        box.addWidget(label("Sunucu sahibi bir kez ücretsiz Playit bağlantısını tarayıcıda onaylar. Arkadaşlarının Playit kurması veya hesap açması gerekmez. Ücretli paket satın alınmaz.","muted",True))
        row = QHBoxLayout()
        row.addWidget(self.action(button("1  Ücretsiz bağlantıyı kur",self.setup_relay)))
        row.addWidget(self.action(button("2  Davet oluştur",self.publish_invite)))
        row.addWidget(self.action(button("Paylaşımı kapat",self.stop_relay)))
        row.addWidget(button("Ücretsiz panel ↗",lambda:QDesktopServices.openUrl(QUrl("https://playit.gg/account/tunnels"))))
        box.addLayout(row)
        self.relay_status = label("Sunucunu başlat; hazır olduğunda Davet oluştur düğmesini kullan.","muted",True)
        box.addWidget(self.relay_status)
        row = QHBoxLayout()
        self.invite_output = QLineEdit()
        self.invite_output.setReadOnly(True)
        self.invite_output.setPlaceholderText("Ücretsiz tünel hazır olduğunda davet kodun burada görünür")
        row.addWidget(self.invite_output,1)
        row.addWidget(button("Kodu kopyala",self.copy_invite))
        box.addLayout(row)
        row = QHBoxLayout()
        self.invite_input = self.action(QLineEdit())
        self.invite_input.setPlaceholderText("Arkadaşının KURT1- veya KURT2- davet kodunu buraya yapıştır")
        self.invite_input.setMaxLength(180000)
        self.invite_input.returnPressed.connect(self.join_invitation)
        row.addWidget(self.invite_input,1)
        row.addWidget(self.action(button("Davetle katıl",self.join_invitation,"primary")))
        box.addLayout(row)
        box.addWidget(label("Kod doğru Minecraft/Fabric profilini seçer ve oyunu sunucuya bağlar. Gerekli modlar iki tarafta da kurulu olmalı. Sunucu sahibi bilgisayarını, launcher'ı ve ücretsiz bağlantıyı açık tutar.","muted",True))
        layout.addWidget(frame)
        frame, box = panel()
        box.addWidget(label("Yeni sunucu", "cardTitle"))
        row = QHBoxLayout()
        self.server_name = QLineEdit()
        self.server_name.setPlaceholderText("Sunucu adı")
        self.server_version = QComboBox()
        self.server_loader = QComboBox()
        self.server_loader.addItem("Vanilla", "vanilla")
        self.server_loader.addItem("Fabric", "fabric")
        row.addWidget(self.server_name, 2)
        row.addWidget(self.server_version, 1)
        row.addWidget(self.server_loader, 1)
        box.addLayout(row)
        row = QHBoxLayout()
        self.server_port = QSpinBox()
        self.server_port.setRange(1024,65535)
        self.server_port.setValue(25565)
        self.server_ram = QSpinBox()
        self.server_ram.setRange(1024,65536)
        self.server_ram.setSingleStep(512)
        self.server_ram.setValue(2048)
        self.server_ram.setSuffix(" MB")
        self.server_slots = QSpinBox()
        self.server_slots.setRange(1,100)
        self.server_slots.setValue(8)
        for text, field in (("Port",self.server_port),("RAM",self.server_ram),("Oyuncu",self.server_slots)):
            row.addWidget(label(text,"muted"))
            row.addWidget(field)
        row.addWidget(self.action(button("+  Oluştur",self.create_server)))
        box.addLayout(row)
        self.server_offline = QCheckBox("Kullanıcı adıyla katılıma izin ver — Microsoft hesabı doğrulanmaz")
        self.server_offline.setChecked(self.store.settings["login_mode"]=="offline")
        box.addWidget(self.server_offline)
        layout.addWidget(frame)
        frame, box = panel()
        row = QHBoxLayout()
        row.addWidget(label("Sunucularım", "cardTitle"))
        self.server_select = self.action(QComboBox())
        self.server_select.setMinimumWidth(200)
        self.server_select.currentIndexChanged.connect(self.server_changed)
        row.addWidget(self.server_select,1)
        self.server_state = label("Sunucu seçilmedi", "compatible")
        row.addWidget(self.server_state)
        box.addLayout(row)
        self.server_eula = self.action(QCheckBox("Minecraft EULA'sını okudum ve kabul ediyorum"))
        row = QHBoxLayout()
        row.addWidget(self.server_eula,1)
        row.addWidget(button("EULA'yı oku ↗",lambda:QDesktopServices.openUrl(QUrl("https://www.minecraft.net/eula"))))
        box.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(self.action(button("▶  Başlat", self.start_server, "primary")))
        self.server_stop = button("■  Durdur", self.stop_server)
        self.server_stop.setEnabled(False)
        row.addWidget(self.server_stop)
        row.addWidget(self.action(button("Kur / onar",self.prepare_server)))
        row.addWidget(button("Klasör ↗",self.open_server_folder))
        row.addWidget(self.action(button("+  Mod .jar",self.import_server_mod)))
        box.addLayout(row)
        self.server_addresses = label("Sunucu oluşturduğunda bağlantı adresleri burada görünür.","muted",True)
        self.server_addresses.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box.addWidget(self.server_addresses)
        row = QHBoxLayout()
        row.addWidget(button("Kendi adresimi kopyala",lambda:self.copy_server_address(False)))
        row.addWidget(button("Arkadaşlar için LAN adresi",lambda:self.copy_server_address(True)))
        row.addStretch()
        box.addLayout(row)
        box.addWidget(label("Aynı ağdan doğrudan bağlantı için yukarıdaki LAN adresini kullanın. Farklı ağdaki arkadaşların için üstteki ücretsiz davet bağlantısını açabilirsin; modemden port yönlendirme gerekmez.","muted",True))
        layout.addWidget(frame)
        layout.addWidget(label("Canlı sunucu konsolu", "cardTitle"))
        self.server_console = QPlainTextEdit()
        self.server_console.setReadOnly(True)
        self.server_console.setMaximumBlockCount(1500)
        self.server_console.setMinimumHeight(200)
        layout.addWidget(self.server_console)
        row = QHBoxLayout()
        self.server_command = QLineEdit()
        self.server_command.setPlaceholderText("Komut: list, say Merhaba, op OyuncuAdi, whitelist add OyuncuAdi")
        self.server_command.returnPressed.connect(self.send_server_command)
        row.addWidget(self.server_command,1)
        row.addWidget(button("Gönder",self.send_server_command))
        layout.addLayout(row)

    @property
    def selected_server(self):
        index = self.server_select.currentIndex()
        if not 0 <= index < len(self.store.servers):
            raise LauncherError("Önce bir sunucu oluşturun veya seçin.")
        return self.store.servers[index]

    def reload_servers(self, selected=None):
        self.server_select.blockSignals(True)
        self.server_select.clear()
        for item in self.store.servers:
            self.server_select.addItem(item["name"],item["id"])
        if selected:
            self.server_select.setCurrentIndex(self.server_select.findData(selected))
        self.server_select.blockSignals(False)
        self.server_changed()

    def server_changed(self):
        try:
            server = self.selected_server
        except LauncherError:
            return
        self.server_eula.setChecked(server.get("eula_accepted",False))
        lan = ", ".join(self.server_manager.lan_addresses(server["port"])) or "Yerel IP bulunamadı"
        self.server_addresses.setText(f"{server['version']} / {server['loader'].title()}  •  {server['ram']} MB RAM  •  {server['slots']} oyuncu\nBu bilgisayar: localhost:{server['port']}\nAynı ağdaki arkadaşların: {lan}")
        self.check_servers()
        if hasattr(self, "server_difficulty"):
            self.load_server_controls()

    def create_server(self):
        try:
            if self.server_manager.running:
                raise LauncherError("Yeni bir sunucu oluşturmadan önce çalışan sunucuyu durdurun.")
            version = self.server_version.currentText()
            if version not in {v["id"] for v in self.manifest["versions"]}:
                raise LauncherError("Listeden bir Minecraft sürümü seçin.")
            item = self.server_manager.create(self.server_name.text(),version,self.server_loader.currentData(),
                        self.server_port.value(),self.server_ram.value(),self.server_offline.isChecked(),self.server_slots.value())
            self.reload_servers(item["id"])
            self.report("Sunucu profili oluşturuldu. EULA onayından sonra Başlat düğmesini kullanın.")
        except LauncherError as exc:
            self.report(str(exc))

    def start_server(self):
        try:
            server = self.selected_server
            accepted = self.server_eula.isChecked()
            if not accepted and not server.get("eula_accepted"):
                raise LauncherError("Önce Minecraft EULA onay kutusunu işaretleyin.")
            self.server_console.clear()
            def started(message):
                self.server_was_running = True
                self.report(message)
                self.check_servers()
            self.run_job("Sunucu hazırlanıyor…",lambda task:self.server_manager.start(server,task,accepted),started)
        except LauncherError as exc:
            self.report(str(exc))

    def prepare_server(self):
        try:
            server = self.selected_server
            accepted = self.server_eula.isChecked()
            def prepare(task):
                self.server_manager.prepare(server,task,accepted)
                return "Sunucu kurulumu tamamlandı. Başlat düğmesiyle açabilirsiniz."
            self.run_job("Sunucu kuruluyor…",prepare)
        except LauncherError as exc:
            self.report(str(exc))

    def stop_server(self):
        try:
            self.server_manager.stop()
            self.report("Sunucu dünyayı kaydederek kapanıyor…")
        except LauncherError as exc:
            self.report(str(exc))

    def send_server_command(self):
        try:
            text = self.server_command.text()
            self.server_manager.command(text)
            self.server_console.appendPlainText("> " + text)
            self.server_command.clear()
        except LauncherError as exc:
            self.report(str(exc))

    def copy_server_address(self, lan):
        try:
            server = self.selected_server
            addresses = self.server_manager.lan_addresses(server["port"]) if lan else [f"localhost:{server['port']}"]
            if not addresses:
                raise LauncherError("Yerel ağ adresi bulunamadı.")
            QApplication.clipboard().setText(addresses[0])
            self.report("Bağlantı adresi kopyalandı: " + addresses[0])
        except LauncherError as exc:
            self.report(str(exc))

    def open_server_folder(self):
        try:
            self.open_path(self.store.directory(self.selected_server))
        except LauncherError as exc:
            self.report(str(exc))

    def import_server_mod(self):
        try:
            server = self.selected_server
            if self.server_manager.running and self.server_manager.active_id==server["id"]:
                raise LauncherError("Mod eklemeden önce sunucuyu durdurun.")
            files,_ = QFileDialog.getOpenFileNames(self,"Sunucu modlarını seç","","Minecraft modları (*.jar)")
            if files:
                self.run_job("Sunucu modları ekleniyor…",lambda task:self.launcher.mods.import_local(server,files,task))
        except LauncherError as exc:
            self.report(str(exc))

    def check_servers(self):
        manager = self.server_manager
        if hasattr(self, "server_players"):
            self.server_players.setText("Bağlı oyuncular: " + (", ".join(manager.players) if manager.running and manager.players else "Yok / bilgi bekleniyor"))
        for line in manager.drain():
            self.server_console.appendPlainText(line)
        self.server_stop.setEnabled(manager.running and not manager.stopping)
        self.server_select.setEnabled(not manager.running and self.worker is None)
        if self.relay.sharing_server_id and (not manager.running or not self.relay.running or manager.active_id != self.relay.sharing_server_id):
            self.stop_relay()
        if manager.running:
            self.server_was_running = True
            self.server_state.setText("Kapanıyor…" if manager.stopping else "● Çalışıyor" if manager.ready.is_set() else "● Başlatılıyor…")
        else:
            self.server_state.setText("Durduruldu")
            if self.server_was_running:
                self.server_was_running = False
                code = manager.process.returncode
                self.report("Sunucu kapandı." if code==0 else "Sunucu hata ile kapandı. Canlı konsolu kontrol edin.")
                if code == 0 and self.store.settings.get("auto_backup", True) and not self.worker:
                    server = next((s for s in self.store.servers if s["id"] == manager.active_id), None)
                    if server:
                        def backed_up(path):
                            self.report("Sunucu kapandı; son dünya durumu yedeklendi.")
                            if self.close_after_server:
                                self.close_after_server = False
                                self.close()
                        self.run_job("Sunucu kapanış yedeği alınıyor…", lambda task: self.launcher.snapshots.create(server, task, "Sunucu kapanışı sonrası", automatic=True), backed_up)
                        return
            if self.close_after_server:
                self.close_after_server = False
                self.close()

    def setup_relay(self):
        self.run_job("Ücretsiz bağlantı hazırlanıyor…", lambda task:self.relay.setup(task), self.relay_ready)

    def relay_ready(self, message):
        self.relay_status.setText(message)
        self.report(message)

    def publish_invite(self):
        try:
            server = self.selected_server
            if not self.server_manager.running or self.server_manager.active_id != server["id"] or not self.server_manager.ready.is_set():
                raise LauncherError("Önce sunucuyu başlatın. Konsolda Done mesajı göründükten sonra davet oluşturabilirsiniz.")
            def published(code):
                self.invite_output.setText(code)
                self.relay_status.setText("● Ücretsiz internet bağlantısı açık. Kodu arkadaşlarına gönderebilirsin.")
                self.report("Davet kodu hazır. Port yönlendirme gerekmez.")
            self.invite_output.clear()
            def publish(task):
                metadata = self.packs.describe_mods(server, task)
                return self.relay.publish({**server, "mod_manifest": metadata}, task)
            self.run_job("Ücretsiz Minecraft Java tüneli açılıyor…",publish,published)
        except LauncherError as exc:
            self.report(str(exc))

    def stop_relay(self):
        self.relay.stop()
        self.invite_output.clear()
        self.relay_status.setText("İnternet paylaşımı kapalı. Sunucu yerel ağda çalışmaya devam edebilir.")

    def copy_invite(self):
        if not self.invite_output.text() or not self.relay.running or not self.server_manager.running:
            self.report("Önce çalışan sunucu için bir davet oluşturun.")
            return
        QApplication.clipboard().setText(self.invite_output.text())
        self.report("Davet kodu kopyalandı.")

    def join_invitation(self):
        try:
            code = self.invite_input.text().strip()
            if code.lower().startswith('kurt:'):
                from deep_links import link_code
                code=link_code(code)
            info = decode_invite(code)
            if self.store.settings["login_mode"] == "offline":
                offline_account(self.username.text())
                self.save_player_name()
            elif not self.store.account:
                raise LauncherError("Microsoft hesabına giriş yapın veya Kullanıcı adıyla seçeneğine geçin.")
            def joined(result):
                message, profile_id = result
                self.reload_profiles(profile_id)
                self.report(message + " Davet sunucusuna bağlanılıyor.")
            if info.get("mod_manifest"):
                def prepare(task):
                    p = self.launcher.invite_profile(info)
                    return p, self.packs.compare(p, info["mod_manifest"])
                def prepared(result):
                    p, comparison = result
                    self.reload_profiles(p["id"])
                    self.show_comparison(p, info["mod_manifest"], comparison,
                        after=lambda: self.run_job("Arkadaş sunucusuna katılınıyor…", lambda task: self.launcher.join_invite(code, task), joined))
                self.run_job("Davetin modları kontrol ediliyor…", prepare, prepared)
            else:
                self.run_job("Arkadaşının sunucusuna katılım hazırlanıyor…",lambda task:self.launcher.join_invite(code,task),joined)
        except LauncherError as exc:
            self.report(str(exc))

    def navigate(self,index):
        self.pages.setCurrentIndex(index)
        self.breadcrumb.setText(["OYUN MERKEZİ","MOD ATÖLYESİ","AYARLAR","İŞLEM GÜNLÜĞÜ","SUNUCULAR","KÜTÜPHANE VE ARAÇLAR","SHADERPACK ATÖLYESİ","DOKU PAKETİ ATÖLYESİ","MODPACK KATALOĞU","DÜNYALARIM"][index])
        for i,item in enumerate(self.nav):
            item.setChecked(i==index)
        self.sync_sidebar_selection()
        if index == 5:
            self.refresh_extras()
        if index==1:
            self.refresh_mods()
            if self.autostart and self.profile and self.profile["loader"] != "vanilla" and not self.worker and not self.results.count():
                self.search_mods()
        if index == 6:
            self.refresh_shaders()
            if self.autostart and self.profile and not self.worker and self.shader_query_state is None:
                self.search_shaders()
        if index in (7,8):
            catalog = self.resource_catalog if index == 7 else self.modpacks_catalog_widget
            if index == 7: self.refresh_resources()
            if self.autostart and not self.worker and catalog.query_state is None and (self.profile or index == 8):
                catalog.search()
        if index == 9 and self.autostart and self.profile and not self.worker:
            self.refresh_worlds()

    def log(self,message):
        from datetime import datetime
        self.logs.appendPlainText(datetime.now().strftime("%H:%M:%S") + "  " + str(message))

    def run_job(self, title, function, done=None):
        if self.worker:
            return
        self.active_job = (title, function, done)
        self.retry_button.hide()
        self.log(title)
        self.status.setText(title)
        self.worker = Worker(function)
        worker = self.worker
        worker.task.rate_limit = max(0, int(self.store.settings.get('download_limit_kib',0))) * 1024
        worker.task.download_cache = self.store.root / 'cache/downloads'
        def success(result):
            self.end_job()
            if done:
                try:
                    done(result)
                except LauncherError as exc:
                    self.job_error(str(exc))
            elif isinstance(result,str):
                self.report(result)
            self.refresh_mods()
            self.refresh_shaders()
            self.refresh_resources()
            self.refresh_diagnostics()
            self.refresh_account()
        worker.signals.done.connect(success)
        worker.signals.error.connect(self.job_error)
        worker.signals.cancelled.connect(self.job_cancelled)
        worker.signals.progress.connect(self.on_progress)
        for item in self.actions:
            item.setEnabled(False)
        self.profiles.setEnabled(False)
        self.search_input.setEnabled(False)
        self.cancel.setText("İptal")
        self.cancel.setEnabled(True)
        self.cancel.show()
        self._progress_known, self._progress_position = False, 0
        self.progress_value.setText("Başlatılıyor…")
        self.progress.setRange(0,0)
        QThreadPool.globalInstance().start(worker)

    def end_job(self, state="completed"):
        self.worker = None
        self.cancel.hide()
        self.pause_download.hide()
        self.progress.setRange(0,1000)
        if state == "completed":
            self._progress_known, self._progress_position = True, 1000
            self.progress_value.setText("%100")
        else:
            prefix = "İptal" if state == "cancelled" else "Hata"
            self.progress_value.setText(prefix + (f" · %{self._progress_position // 10}" if self._progress_known else ""))
        self.progress.setValue(self._progress_position if self._progress_known else 0)
        for item in self.actions:
            item.setEnabled(True)
        self.profiles.setEnabled(True)
        self.search_input.setEnabled(True)
        self.refresh_shaders()
        self.refresh_resources()
        self.refresh_diagnostics()

    def job_error(self,message):
        self.close_after_server = False
        self.last_failed_job = self.active_job
        self.end_job("failed")
        self.retry_button.show()
        self.report(message)

    def job_cancelled(self,message):
        self.end_job("cancelled")
        self.report(message)

    def report(self,message):
        self.status.setText(message)
        self.log(message)

    def refresh_transfer_stats(self):
        active = bool(self.worker and self.worker.task.transfer.unit == 'bytes')
        self.pause_download.setVisible(active)
        self.pause_download.setText('Devam et' if active and self.worker.task.paused.is_set() else 'Duraklat')
        if hasattr(self,'downloads_pause'):
            self.downloads_pause.setEnabled(active)
            self.downloads_pause.setText(self.pause_download.text())
        if self.worker:
            self.transfer_detail.setText(self.worker.task.transfer.text())
            if self.worker.task.paused.is_set(): self.transfer_detail.setText('Duraklatıldı • '+self.transfer_detail.text())
        else:
            self.transfer_detail.setText("")
        if hasattr(self, "downloads_text"):
            if self.worker:
                stats = self.worker.task.transfer
                pending = "\n".join(list(stats.pending)[:200]) or "Bu aşamada bekleyen dosya listesi yok."
                value = self.status.text() + "\n" + self.progress_value.text() + "\n" + stats.text() + "\n\nBekleyen dosyalar:\n" + pending
            else:
                value = self.status.text() + "\n\nDevam eden işlem yok."
            if self.downloads_text.toPlainText() != value:
                self.downloads_text.setPlainText(value)

    def on_progress(self,message,value,maximum):
        if self.status.text()!=message:
            self.log(message)
        self.status.setText(message)
        if maximum>0:
            # Byte counts can exceed Qt's 32-bit integer range.
            self._progress_known = True
            self._progress_position = max(0, min(1000, int(value * 1000 // maximum)))
            self.progress.setRange(0,1000)
            self.progress.setValue(self._progress_position)
            self.progress_value.setText(f"%{self._progress_position // 10}")
        else:
            self._progress_known, self._progress_position = False, 0
            self.progress_value.setText("İşleniyor…")
            self.progress.setRange(0,0)

    def cancel_job(self):
        if self.worker:
            self.worker.task.cancel.set()
            self.cancel.setEnabled(False)
            self.cancel.setText("Bekleniyor…")
            self.progress_value.setText("İptal bekleniyor…")
            self.status.setText("İptal bekleniyor… Mevcut dosya veya ağ işleminin bitmesi gerekebilir.")

    def toggle_download_pause(self):
        import time
        if not self.worker or self.worker.task.transfer.unit != 'bytes': return
        task=self.worker.task
        if task.paused.is_set():
            task.transfer.started += max(0,time.monotonic()-getattr(task,'paused_at',time.monotonic()))
            task.paused.clear()
        else:
            task.paused_at=time.monotonic();task.paused.set()
        self.refresh_transfer_stats()

    def save_download_limit(self,value):
        self.store.settings['download_limit_kib']=value;self.store.save()
        if self.worker:self.worker.task.rate_limit=max(0,value)*1024

    def refresh_versions(self):
        self.run_job("Resmî Minecraft sürümleri alınıyor…",lambda task:self.launcher.versions(),self.loaded_versions)

    def loaded_versions(self,result):
        self.manifest,cached = result
        count = len(self.manifest["versions"])
        self.version_count.setText(f"{count} resmî sürüm" + (" • önbellek" if cached else " • güncel"))
        self.filter_versions()
        previous = self.server_version.currentText()
        self.server_version.clear()
        self.server_version.addItems([v["id"] for v in self.manifest["versions"] if v["type"] == "release"])
        if previous:
            self.server_version.setCurrentText(previous)
        elif self.profile and self.profile["version"] in [self.server_version.itemText(i) for i in range(self.server_version.count())]:
            self.server_version.setCurrentText(self.profile["version"])
        self.report("Sürüm listesi " + ("önbellekten yüklendi; internet bağlantısı yok." if cached else "güncellendi."))

    def filter_versions(self):
        old = self.version.currentText()
        channel = self.channel.currentData()
        self.version.clear()
        ids = [v["id"] for v in self.manifest["versions"] if channel=="all" or v["type"]==channel]
        self.version.addItems(ids)
        if old in ids:
            self.version.setCurrentText(old)
        self.version.completer().setFilterMode(Qt.MatchContains)
        self.version.completer().setCompletionMode(QCompleter.PopupCompletion)

    def create_profile(self):
        version = self.version.currentText().strip()
        if version not in {v["id"] for v in self.manifest["versions"]}:
            self.report("Listeden geçerli bir Minecraft sürümü seçin.")
            return
        loader = self.loader.currentData()
        name,ok = QInputDialog.getText(self,"Yeni profil","Profil adı:",text=f"{version} · {loader.title()}")
        if not ok:
            return
        def create(task):
            if loader!="vanilla":
                from core import mc
                task.status("Yükleyici desteği kontrol ediliyor…")
                if not mc.mod_loader.get_mod_loader(loader).is_minecraft_version_supported(version):
                    raise LauncherError(f"{loader.title()} bu Minecraft sürümünü desteklemiyor. Başka sürüm/yükleyici seçin.")
            task.check()
            return self.store.create(name,version,loader)
        self.run_job("Profil oluşturuluyor…",create,lambda p:self.reload_profiles(p["id"]))

    def reload_profiles(self,selected=None):
        selected = selected or (self.profile["id"] if self.profile else self.store.settings.get("last_profile"))
        self.profiles.blockSignals(True)
        self.profiles.clear()
        for p in self.store.profiles:
            self.profiles.addItem(p["name"],p["id"])
        if selected:
            index=self.profiles.findData(selected)
            if index>=0:
                self.profiles.setCurrentIndex(index)
        self.profiles.blockSignals(False)
        self.profile_changed()

    def profile_changed(self):
        p=self.profile
        if p:
            self.store.settings["last_profile"]=p["id"]
            self.store.save()
        self.clear_results()
        self.offset,self.total=0,0
        self.search_count.setText("Seçilen sürüm ve yükleyiciye göre filtrelenir.")
        self.refresh_mods()
        self.clear_shader_results()
        self.shader_query_state = None
        self.shader_offset = self.shader_total = 0
        self.shader_search_count.setText('Minecraft sürümüne ve shader desteğine göre filtrelenir.')
        self.refresh_shaders()
        self.refresh_resources()
        self.refresh_diagnostics()
        if hasattr(self,'resource_catalog'):
            for catalog in (self.resource_catalog,self.modpacks_catalog_widget):
                catalog.query_state=None;catalog.offset=0;catalog.total=0;catalog.table.setRowCount(0)
        if hasattr(self,'world_table'):
            self.world_table.setRowCount(0);self.world_rows=[];self.world_backup_choice.clear()
        if hasattr(self, "tools_tabs"):
            self.update_rows = []
            self.updates_table.setRowCount(0)
            self.refresh_extras()

    def refresh_mods(self):
        if not hasattr(self,"installed"):
            return
        p=self.profile
        self.installed.setRowCount(0)
        if not p:
            self.profile_title.setProperty('user_content',False)
            self.profile_title.setText("İlk profilini oluştur")
            self.mod_count.setText("")
            return
        self.profile_title.setProperty('user_content',True)
        self.profile_title.setText(p["name"])
        self.profile_info.setText(f"Minecraft {p['version']}   /   {p['loader'].title()}" + (f" {p['loader_version']}" if p.get("loader_version") else "") + ("   •   Kurulu" if p.get("installed") else "   •   Henüz kurulmadı"))
        self.mod_subtitle.setText(f"{p['name']}  •  {p['version']} / {p['loader'].title()}" + (" — Mod kurmak için yükleyicili profil oluştur." if p["loader"]=="vanilla" else " — Uyumlu modlar ve gerekli bağımlılıkları."))
        files=sorted(f.name for f in self.store.mods(p).iterdir() if f.is_file() and f.name.endswith((".jar",".jar.disabled")))
        records = {entry["file"]: entry for entry in self.store.mod_lock(p).values()}
        for i,name in enumerate(files):
            self.installed.insertRow(i)
            entry = records.get(name.removesuffix(".disabled"), {})
            item = QTableWidgetItem(entry.get("name", name))
            item.setIcon(QIcon(logo_pixmap(entry.get("name", name), self.store.cached_icon(entry.get("icon_url")), 34)))
            item.setData(Qt.UserRole, name)
            item.setToolTip(name)
            self.installed.setItem(i,0,item)
            self.installed.setItem(i,1,QTableWidgetItem(entry.get("version_number") or "—"))
            if entry.get("game_versions") and entry.get("loaders"):
                matches = p["version"] in entry["game_versions"] and p["loader"] in entry["loaders"]
                compatibility = "Paket seçimi" if entry.get('pack_compatibility_note') else "Uyumlu" if matches else "Uyumsuz"
            else:
                compatibility = "Bilinmiyor"
            item = QTableWidgetItem(compatibility)
            item.setToolTip("Minecraft: " + ", ".join(entry.get("game_versions", [])) + "\nYükleyici: " + ", ".join(entry.get("loaders", [])) if entry else "Yerel JAR sürümü ve bağımlılıkları elle kontrol edilmeli.")
            if entry.get('pack_compatibility_note'): item.setToolTip(item.toolTip()+'\n'+entry['pack_compatibility_note'])
            self.installed.setItem(i,2,item)
            self.installed.setItem(i,3,QTableWidgetItem("Kapalı" if name.endswith(".disabled") else "Etkin"))
        self.mod_count.setText(f"{sum(not n.endswith('.disabled') for n in files)} etkin mod")
        self.installed_tab.setText(f"Kurulu modlar ({len(files)})")
        lock = self.store.mod_lock(p)
        for project, (install, version_id) in self.catalog_buttons.items():
            record = lock.get(project)
            install.setEnabled(bool(version_id) and not record)
            install.setText("✓ Kurulu" if record and record["version_id"] == version_id else "Başka sürüm kurulu" if record else "↓  Kur")

    def require_profile(self):
        if not self.profile:
            raise LauncherError("Önce Oyun merkezi bölümünden bir profil oluşturun.")
        return self.profile

    def install(self):
        try:
            p=self.require_profile()
            self.run_job("Oyun kuruluyor / onarılıyor…",lambda task:self.launcher.install(p,task))
        except LauncherError as exc:
            self.report(str(exc))

    def play(self):
        try:
            p=self.require_profile()
            if self.store.settings["login_mode"] == "offline":
                offline_account(self.username.text())
                self.save_player_name()
            elif not self.store.account:
                self.report("Microsoft hesabıyla giriş yapın veya Kullanıcı adıyla seçeneğine geçin.")
                return
            self.run_job("Oyun hazırlanıyor…",lambda task:self.launcher.play(p,task))
        except LauncherError as exc:
            self.report(str(exc))

    def clear_results(self):
        self.catalog_buttons = {}
        while self.results.count():
            item=self.results.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def search_mods(self,offset=0):
        if self.worker:
            return
        # clicked(bool) must not become a pagination offset.
        if isinstance(offset,bool):
            offset=0
        try:
            p=self.require_profile()
            query=self.search_input.text().strip()
            sort=self.mod_sort.currentData()
            if query!=self.last_query or sort!=self.last_sort:
                offset=0
            self.last_query=query
            self.last_sort=sort
            self.run_job("Uyumlu modlar aranıyor…",lambda task:self.launcher.mods.catalog(p,query,offset,task,sort=sort),lambda result:self.show_results(result,offset))
        except LauncherError as exc:
            self.report(str(exc))

    def change_mod_sort(self):
        self.offset = 0
        if not self.worker and self.profile and self.profile["loader"] != "vanilla":
            self.search_mods()

    def show_results(self,result,offset):
        self.clear_results()
        self.offset,self.total=offset,result["total_hits"]
        hits=result["hits"]
        self.previous.setEnabled(offset > 0)
        self.next.setEnabled(offset + len(hits) < self.total)
        self.search_count.setText(f"{self.total:,} sonuç • {offset+1 if hits else 0}–{offset+len(hits)}".replace(",","."))
        if not hits:
            self.results.addWidget(label("Bu sürüm ve yükleyici için sonuç bulunamadı.","muted"))
        for hit in hits:
            frame,box=panel()
            compact = self.store.settings.get("compact_mods", False)
            frame.setMinimumHeight(160 if compact else 230)
            card = QHBoxLayout()
            card.setSpacing(18)
            card.addWidget(mod_logo(hit, 52 if compact else 76), 0, Qt.AlignTop)
            content = QVBoxLayout()
            content.setSpacing(10)
            card.addLayout(content, 1)
            box.addLayout(card)
            box = content
            row=QHBoxLayout()
            row.addWidget(label(hit["title"],"cardTitle",translate=False))
            info = hit.get("version_info")
            if info:
                channels = {"release": "Kararlı", "beta": "Beta", "alpha": "Alpha"}
                row.addWidget(label(channels.get(info.get("version_type"), "Sürüm"), "badge"))
            row.addStretch()
            row.addWidget(label(f"{hit['downloads']:,} indirme".replace(",","."),"muted"))
            install=button("↓  Kur",lambda checked=False,pid=hit["project_id"],vid=info.get("id") if info else None:self.install_mod(pid,vid))
            install.setEnabled(bool(info))
            self.catalog_buttons[hit["project_id"]] = (install, info.get("id") if info else None)
            if not info:
                install.setToolTip(hit.get("version_error", "Bu profil için uyumlu sürüm bilgisi alınamadı."))
            # Dynamic buttons consult the common worker guard rather than entering actions.
            row.addWidget(install)
            box.addLayout(row)
            box.addWidget(label(hit["description"],"muted",True,translate=False))
            version_label = label(mod_version_text(hit), "compatible" if info else "muted", True)
            if info:
                version_label.setToolTip("Desteklenen Minecraft sürümleri: " + ", ".join(info.get("game_versions", [])))
            box.addWidget(version_label)
            if not compact:
                box.addWidget(label("İçerik: " + mod_categories(hit), "muted", True))
            if info and not compact:
                required = sum(d.get("dependency_type") == "required" for d in info.get("dependencies", []))
                details = f"✓ Seçili profille uyumlu   •   {required} zorunlu bağımlılık"
                date = info.get("date_published", "").split("T")[0]
                if date:
                    details += "   •   Yayın: " + date
                box.addWidget(label(details, "muted", True))
            row=QHBoxLayout()
            row.addWidget(label("Yapımcı: "+hit["author"],"muted"))
            row.addStretch()
            row.addWidget(button("☆ Kaydet", lambda checked=False, mod=hit: self.save_collection_mod(mod)))
            row.addWidget(button("Ayrıntılar",lambda checked=False,mod=hit:self.open_mod_details(mod)))
            row.addWidget(button("Mod sayfası ↗",lambda checked=False,pid=hit["project_id"]:QDesktopServices.openUrl(QUrl("https://modrinth.com/mod/"+pid))))
            box.addLayout(row)
            self.results.addWidget(frame)
        self.report("Mod araması tamamlandı.")

    def open_mod_details(self, hit):
        if self.worker:
            return
        def details(task):
            project = self.launcher.mods.project_details(hit["project_id"])
            project["gallery_paths"] = []
            for entry in project.get("gallery", [])[:6]:
                path = self.launcher.api.icon(entry.get("url"), self.store.icon_cache, task)
                if path: project["gallery_paths"].append(path)
            return project
        self.run_job("Mod içeriği alınıyor…", details,
                     lambda project: self.show_mod_details(hit, project))

    def show_mod_details(self, hit, project):
        dialog = QDialog(self)
        dialog.setWindowTitle(hit["title"] + " · Mod ayrıntıları")
        dialog.resize(820, 680)
        box = QVBoxLayout(dialog)
        box.setContentsMargins(24,24,24,24)
        box.setSpacing(14)
        header = QHBoxLayout()
        header.setSpacing(18)
        header.addWidget(mod_logo(hit, 88))
        title = QVBoxLayout()
        title.addWidget(label(hit["title"], "title",translate=False))
        title.addWidget(label(hit["description"], "muted", True,translate=False))
        header.addLayout(title, 1)
        box.addLayout(header)
        box.addWidget(label(mod_version_text(hit), "compatible" if hit.get("version_info") else "muted", True))
        box.addWidget(label("İçerik: " + mod_categories(hit), "muted", True))
        if project.get("gallery_paths"):
            gallery = QScrollArea()
            gallery.setWidgetResizable(True)
            gallery.setFixedHeight(145)
            body = QWidget()
            gallery_row = QHBoxLayout(body)
            for path in project["gallery_paths"]:
                preview = QLabel()
                preview.setPixmap(QPixmap(path).scaled(220, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                preview.setToolTip("Görseli açmak için çift tıkla")
                preview.mouseDoubleClickEvent = lambda event, file=path: self.open_path(file)
                gallery_row.addWidget(preview)
            gallery.setWidget(body)
            box.addWidget(gallery)
        browser = QTextBrowser()
        browser.setStyleSheet("QTextBrowser { background: #120f16; border: 1px solid #4b3043; border-radius: 8px; padding: 16px; }")
        browser.document().setDefaultStyleSheet("a { color: #ffad7e; }")
        browser.setOpenLinks(False)
        browser.anchorClicked.connect(lambda url: QDesktopServices.openUrl(url) if url.scheme() in ("https", "http") else None)
        body = project.get("body", "İçerik açıklaması eklenmemiş.")[:250000]
        body = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", lambda m: "[" + (m[1] or "Görseli aç") + "](" + m[2] + ")", body)
        body = re.sub(r"<img\b[^>]*>", "", body, flags=re.I)
        browser.setMarkdown(body)
        box.addWidget(browser,1)
        box.addWidget(label("Uyumluluk mod yapımcısının yayımladığı bilgilere dayanır. Yerel dosyalar ve diğer modlarla oluşabilecek tüm çakışmalar önceden belirlenemez.","muted",True))
        row = QHBoxLayout()
        row.addWidget(button("Modrinth sayfası ↗", lambda: QDesktopServices.openUrl(QUrl("https://modrinth.com/mod/" + hit["project_id"]))))
        row.addStretch()
        row.addWidget(button("Kapat", dialog.accept))
        box.addLayout(row)
        self.mod_details_dialog = dialog
        dialog.open()

    def update_mod_info(self):
        try:
            p = self.require_profile()
            self.run_job("Mod bilgileri yenileniyor…", lambda task: self.launcher.mods.refresh_metadata(p, task))
        except LauncherError as exc:
            self.report(str(exc))

    def install_mod(self,project,version_id=None):
        if self.worker:
            return
        try:
            self.launcher.ensure_idle()
            p=self.require_profile()
            self.run_job("Mod kurulumu hazırlanıyor…",lambda task:self.launcher.mods.install(project,p,task,version_id))
        except LauncherError as exc:
            self.report(str(exc))

    def import_mods(self):
        try:
            self.launcher.ensure_idle()
            p=self.require_profile()
            if p["loader"]=="vanilla":
                raise LauncherError("Yerel mod eklemek için yükleyicili bir profil seçin.")
            files,_=QFileDialog.getOpenFileNames(self,"Mod dosyalarını seç", "", "Minecraft modları (*.jar)")
            if files:
                self.run_job("Yerel modlar ekleniyor…",lambda task:self.launcher.mods.import_local(p,files,task))
        except LauncherError as exc:
            self.report(str(exc))

    def selected_mod(self):
        row=self.installed.currentRow()
        if row<0:
            raise LauncherError("Tablodan bir mod seçin.")
        return self.installed.item(row,0).data(Qt.UserRole)

    def change_login_mode(self):
        self.store.settings["login_mode"] = self.account_mode.currentData()
        self.store.save()
        self.refresh_account()

    def save_player_name(self):
        self.store.settings["offline_username"] = self.username.text().strip()
        self.store.save()
        self.refresh_account()

    def toggle_mod(self):
        try:
            self.launcher.ensure_idle()
            p, name = self.require_profile(), self.selected_mod()
            self.run_job("Mod durumu değiştiriliyor…", lambda task: self.launcher.mods.toggle(p,name,task),
                         lambda result: self.report("Mod durumu değiştirildi."))
        except (LauncherError,OSError) as exc:
            self.report(str(exc))

    def remove_mod(self):
        try:
            self.launcher.ensure_idle()
            p, name = self.require_profile(), self.selected_mod()
            self.run_job("Mod kaldırılıyor…", lambda task: self.launcher.mods.remove(p,name,task),
                         lambda result: self.report("Mod kaldırıldı. Dosya profilin removed-mods klasöründe saklanıyor."))
        except (LauncherError,OSError) as exc:
            self.report(str(exc))

    def save_settings(self):
        client=self.client_id.text().strip()
        if client!=self.store.settings.get("client_id","") and self.store.account:
            try:
                self.launcher.account.logout()
            except Exception:
                self.report("Önce mevcut hesaptan çıkın; ardından uygulama kimliğini değiştirin.")
                return
        self.store.settings.update(ram=self.ram.value(),java=self.java_path.text().strip(),client_id=client)
        self.store.save()
        self.refresh_account()
        self.report("Ayarlar kaydedildi.")

    def pick_java(self):
        file,_=QFileDialog.getOpenFileName(self,"Java çalıştırıcısını seç", "", "Java (java.exe javaw.exe)")
        if file:
            self.java_path.setText(file)

    def pick_previous_games(self):
        if self.worker or (self.launcher.process and self.launcher.process.poll() is None) or self.server_manager.running:
            self.report("Önce oyunu, sunucuyu ve devam eden işlemi kapatın.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Eski Kurt Launcher oyun klasörünü seç", str(self.store.root.parent))
        if not folder:
            return
        try:
            selected = selected_data_folder(folder)
            Store(selected)
            def migrate(task):
                from data_migration import ensure_shared_data
                def progress(message, value, maximum):
                    task.check()
                    if task.message != message:
                        task.status(message)
                    if task.maximum != maximum:
                        task.set_max(maximum)
                    task.progress(value)
                root = ensure_shared_data(selected, progress=progress)
                Store(root)
                remember_data_folder(root)
                return root
            self.run_job("Eski oyunlar ortak klasöre aktarılıyor…", migrate,
                         lambda root: self.report("Oyunların ortak klasöre kopyalanıp doğrulandı. Launcher'ı yeniden açtığında bu arşiv kullanılacak; eski launcher klasörünü silebilirsin."))
        except (DataLocationError, LauncherError, OSError) as exc:
            self.report(str(exc))

    def login(self):
        if self.store.settings["login_mode"] == "offline":
            try:
                player = offline_account(self.username.text())
                self.save_player_name()
                self.report("Kullanıcı adıyla giriş yapıldı: " + player["name"] + ". Oyna düğmesini kullanabilirsin.")
            except LauncherError as exc:
                self.report(str(exc))
            return
        if not self.store.settings.get("client_id"):
            self.navigate(2)
            self.report("Giriş için Microsoft uygulama kimliğini kaydedin. Ayarlar bölümündeki kurulum rehberi gerekli adımları açıklıyor.")
            return
        def logged_in(result):
            self.account_mode.setCurrentIndex(1)
            self.report("Hoş geldin, " + result["name"] + "!")
        self.run_job("Microsoft hesabı bağlanıyor…",lambda task:self.launcher.account.login(task),logged_in)

    def logout(self):
        def logout(task):
            self.launcher.account.logout()
            return "Microsoft hesabından çıkış yapıldı."
        self.run_job("Hesap kapatılıyor…",logout)

    def refresh_account(self):
        name=self.store.account.get("name")
        offline = self.store.settings["login_mode"] == "offline"
        if offline:
            try:
                nickname = offline_account(self.store.settings.get("offline_username", ""))["name"]
                self.account_label.setProperty('user_content',True)
            except LauncherError:
                nickname = "Kullanıcı adıyla giriş"
                self.account_label.setProperty('user_content',False)
            self.account_label.setText(nickname)
        else:
            self.account_label.setProperty('user_content',bool(name))
            self.account_label.setText(name or "Hesap bağlı değil")
        self.username.setVisible(offline)
        self.login_button.setText("Giriş yap" if offline else "Hesabı değiştir" if name else "Microsoft ile giriş")

    def open_path(self,path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_instance(self):
        try:
            self.open_path(self.store.directory(self.require_profile()))
        except LauncherError as exc:
            self.report(str(exc))

    def open_mods(self):
        try:
            self.open_path(self.store.mods(self.require_profile()))
        except LauncherError as exc:
            self.report(str(exc))

    def open_game_log(self):
        try:
            file=self.store.directory(self.require_profile())/"launcher-game.log"
            if not file.exists():
                raise LauncherError("Oyun günlüğü henüz oluşmadı.")
            self.open_path(file)
        except LauncherError as exc:
            self.report(str(exc))

    def check_game(self):
        self.check_servers()
        process=self.launcher.process
        self.launcher.sessions.update(process)
        if process and process.poll() is None:
            self.game_active=True
        elif process and self.game_active:
            self.game_active=False
            self.report("Minecraft kapandı." if process.returncode==0 else f"Minecraft hata ile kapandı (kod {process.returncode}). Günlük bölümünden oyun günlüğünü açın.")
            if process.returncode != 0 and not self.worker:
                failed_profile = next((p for p in self.store.profiles if p["id"] == self.launcher.active_profile_id), None)
                QTimer.singleShot(0, lambda: self.show_diagnosis(False, failed_profile))
        self.maybe_auto_update()

    def closeEvent(self,event):
        if self.worker:
            self.report("Bir işlem sürüyor. Önce İptal'e basıp işlemin bitmesini bekleyin.")
            event.ignore()
        elif self.server_manager.running:
            self.close_after_server = True
            if not self.server_manager.stopping:
                self.stop_server()
            event.ignore()
        else:
            self.launcher.sessions.update(self.launcher.process, closing=True)
            if getattr(self, "update_checker", None):
                self.update_checker.task.cancel.set()
            self.relay.stop()
            event.accept()
