"""Modern light, sunset, system and high-contrast palettes with scalable controls."""
import re
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QPalette
from PySide6.QtWidgets import QApplication

PALETTES={
 'light':dict(bg='#f3f5fa',surface='#ffffff',side='#fafbfe',field='#f7f8fc',border='#dce2ee',
              text='#1d2b43',muted='#5f6c81',soft='#edf1f8',hover='#e6ecf7',selected='#fce7dd',
              accent='#b74329',primary='#f49a65',primary2='#f3bc8f',onprimary='#372014',danger='#b82e48',handle='#b4bfd2'),
 'sunset':dict(bg='#10141f',surface='#191f2d',side='#141a27',field='#111724',border='#303b50',
              text='#edf1fa',muted='#a6b2c7',soft='#232c3e',hover='#2b374e',selected='#473131',
              accent='#ffb17b',primary='#ffb17b',primary2='#f18c93',onprimary='#281b19',danger='#ff9d9f',handle='#56647c'),
 'contrast':dict(bg='#000000',surface='#000000',side='#000000',field='#000000',border='#ffffff',
              text='#ffffff',muted='#ffffff',soft='#111111',hover='#333333',selected='#002b48',
              accent='#ffff00',primary='#ffff00',primary2='#ffff00',onprimary='#000000',danger='#ffb7b7',handle='#ffffff')}


def selected_theme(settings):
    name=settings.get('theme','light')
    if name=='system':return 'sunset' if QApplication.styleHints().colorScheme()==Qt.ColorScheme.Dark else 'light'
    return name if name in PALETTES else 'light'


def stylesheet(settings):
    theme=selected_theme(settings);p=dict(PALETTES[theme]);scale=max(90,min(140,int(settings.get('ui_scale',100))))/100
    accent=settings.get('accent')
    if accent and QColor(accent).isValid() and theme!='contrast':
        # User accent affects decoration, while text keeps the palette's readable contrast.
        p['primary']=accent
        color=QColor(accent);luminance=.2126*color.redF()+.7152*color.greenF()+.0722*color.blueF()
        p['onprimary']='#172033' if luminance>.55 else '#ffffff'
        p['primary2']=accent
    css="""
* { font-family: 'Segoe UI'; font-size: 13px; color: @text; }
QMainWindow, QWidget#root { background: @bg; }
QWidget { background: transparent; }
QFrame#sidebar { background: @side; border-right: 1px solid @border; }
QFrame#accountPanel { background: @surface; border: 1px solid @border; border-radius: 14px; }
QFrame#sidebarDivider { background: @border; min-height: 1px; max-height: 1px; }
QLabel#brand { font-size: 24px; font-weight: 800; letter-spacing: 2px; }
QLabel#sectionLabel { color: @muted; font-size: 10px; font-weight: 700; letter-spacing: 1px; padding: 6px 10px; }
QLabel#eyebrow { color: @muted; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QLabel#title { font-size: 27px; font-weight: 750; }
QLabel#cardTitle { font-size: 16px; font-weight: 700; }
QLabel#muted { color: @muted; }
QLabel#bigNumber { font-size: 30px; color: @accent; font-weight: 700; }
QLabel#compatible, QLabel#progressValue { color: @accent; font-weight: 700; }
QLabel#badge { color: @accent; background: @selected; padding: 5px 9px; border-radius: 6px; }
QFrame#panel { background: @surface; border: 1px solid @border; border-radius: 16px; }
QFrame#footer { background: @side; border-top: 1px solid @border; }
QPushButton { background: @soft; border: 1px solid @border; border-radius: 9px; padding: 9px 14px; font-weight: 600; }
QPushButton:hover { background: @hover; border-color: @handle; }
QPushButton:pressed, QPushButton:checked { background: @selected; color: @accent; border-color: @accent; }
QPushButton:disabled { color: @muted; background: @field; }
QPushButton:focus, QCheckBox:focus, QTabBar::tab:focus { border: 2px solid @accent; }
QPushButton#primary { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 @primary,stop:1 @primary2); color: @onprimary; border: 1px solid transparent; padding: 12px 18px; font-size: 14px; font-weight: 750; }
QPushButton#primary:hover { border-color: @accent; }
QPushButton#primary:focus { border: 2px solid @text; }
QPushButton#primary:disabled { background: @soft; color: @muted; }
QPushButton#nav { text-align: left; background: transparent; border: 1px solid transparent; padding: 10px 12px; color: @muted; }
QPushButton#nav:hover { background: @soft; color: @text; }
QPushButton#nav:checked { background: @selected; color: @accent; border: 1px solid @border; }
QPushButton#nav:focus { border: 2px solid @accent; }
QPushButton#danger { color: @danger; }
QLineEdit, QComboBox, QSpinBox { background: @field; border: 1px solid @border; border-radius: 8px; padding: 9px 10px; selection-background-color: @selected; selection-color: @text; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 2px solid @accent; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: @surface; color: @text; selection-background-color: @selected; selection-color: @text; border: 1px solid @border; padding: 5px; }
QScrollArea { border: none; }
QScrollBar:vertical { background: @bg; width: 10px; }
QScrollBar::handle:vertical { background: @handle; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: @bg; height: 10px; }
QScrollBar::handle:horizontal { background: @handle; min-width: 30px; border-radius: 5px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QTableWidget, QListWidget { background: @surface; alternate-background-color: @field; border: 1px solid @border; border-radius: 10px; gridline-color: @border; }
QTableWidget::item { padding: 8px; }
QTableWidget::item:selected, QListWidget::item:selected { background: @selected; color: @text; }
QHeaderView::section { background: @soft; color: @muted; padding: 9px; border: none; border-bottom: 1px solid @border; font-weight: 600; }
QTableCornerButton::section { background: @soft; border: none; }
QTabWidget::pane { background: @surface; border: 1px solid @border; border-radius: 10px; top: -1px; }
QTabBar::tab { background: @soft; color: @muted; padding: 9px 12px; border: 1px solid transparent; border-top-left-radius: 8px; border-top-right-radius: 8px; }
QTabBar::tab:selected { color: @accent; background: @surface; border-color: @border; border-bottom-color: @surface; }
QTabBar::tab:hover { color: @text; }
QPlainTextEdit, QTextBrowser, QTextEdit { background: @field; color: @text; border: 1px solid @border; border-radius: 10px; padding: 12px; selection-background-color: @selected; selection-color: @text; }
QPlainTextEdit { font-family: Consolas; }
QProgressBar { background: @border; border: none; border-radius: 4px; height: 7px; }
QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 @primary,stop:1 @primary2); border-radius: 4px; }
QToolTip { background: @surface; color: @text; border: 1px solid @border; padding: 8px; }
QDialog, QMessageBox, QMenu { background: @surface; }
QMenu::item:selected { background: @selected; }
QCheckBox { spacing: 8px; padding: 2px; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid @handle; border-radius: 5px; background: @field; }
QCheckBox::indicator:checked { background: @accent; border: 4px solid @selected; }
QSplitter::handle { background: @border; }
"""
    for key in sorted(p,key=len,reverse=True):css=css.replace('@'+key,p[key])
    css=re.sub(r'font-size: (\d+)px',lambda m:f'font-size: {round(int(m[1])*scale)}px',css)
    return css,p,theme


def apply(window):
    css,colors,theme=stylesheet(window.store.settings)
    window.setStyleSheet(css)
    palette=QPalette()
    for role,key in ((QPalette.Window,'bg'),(QPalette.WindowText,'text'),(QPalette.Base,'field'),
                     (QPalette.AlternateBase,'soft'),(QPalette.Text,'text'),(QPalette.Button,'soft'),
                     (QPalette.ButtonText,'text'),(QPalette.Highlight,'selected'),(QPalette.HighlightedText,'text'),
                     (QPalette.ToolTipBase,'surface'),(QPalette.ToolTipText,'text'),(QPalette.Link,'accent')):
        palette.setColor(role,QColor(colors[key]))
    window.setPalette(palette)
    # Modal dialogs and popups are top-level widgets; give them the same palette.
    QApplication.instance().setPalette(palette)
    window.setProperty('visual_theme',theme)
    for item in window.findChildren(QWidgetLandscape()):item.update()


def QWidgetLandscape():
    # Local import avoids the UI module importing itself during construction.
    from ui import Landscape
    return Landscape
