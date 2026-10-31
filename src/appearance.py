"""Named color palettes, readable theme roles and scalable application controls."""
import re
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QPalette
from PySide6.QtWidgets import QApplication

PALETTE_THEMES=(
 ('midnight_lilac','Gece Leylağı',('#2b2c6c','#6064ae','#9f92c7','#ebc9e1'),True,0,1,3,(2,3,3)),
 ('raspberry','Ahududu',('#f490b2','#f06491','#af1d5b','#901b52'),True,3,2,0,(0,1,1)),
 ('olive_garden','Zeytin Bahçesi',('#c2bb85','#dad5ab','#efefcb','#fcfce4'),False,3,0,0,(0,1,2)),
 ('pastel_earth','Pastel Toprak',('#9b6f90','#87a7a6','#d7cbb5','#f1e2cf'),False,3,1,0,(3,2,1)),
 ('coral_mint','Mercan Nane',('#b3cec5','#c9e7cf','#fed374','#f04c4d'),False,1,0,3,(0,2,3)),
 ('tropical_sunset','Tropik Gün Batımı',('#de7428','#fcb53f','#fbe59c','#66c7ce'),False,2,3,0,(0,1,3)),
 ('ember_night','Köz Gecesi',('#0b2035','#2c394c','#344756','#ef4f2d'),True,0,1,3,(3,3,3)),
 ('peach_cream','Şeftali Kreması',('#fdeef1','#f8ded1','#dad1c2','#cdbba7'),False,0,2,3,(0,1,3)),
 ('rose_charcoal','Gül Kömürü',('#020202','#bd4d4c','#efb7b8','#eeeeee'),True,0,1,2,(1,2,2)),
)
PALETTE_IDS={row[0] for row in PALETTE_THEMES}


def mix(first,second,amount):
    a,b=QColor(first),QColor(second)
    return QColor(*(round(x+(y-x)*amount) for x,y in zip(a.getRgb()[:3],b.getRgb()[:3]))).name()


def luminance(color):
    parts=QColor(color).getRgbF()[:3]
    linear=[c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in parts]
    return sum(c*w for c,w in zip(linear,(.2126,.7152,.0722)))


def contrast(first,second):
    a,b=sorted((luminance(first),luminance(second)))
    return (b+.05)/(a+.05)


def readable(color,backgrounds,minimum=4.5):
    if min(contrast(color,bg) for bg in backgrounds)>=minimum:return color
    target=max(('#000000','#ffffff'),key=lambda c:min(contrast(c,bg) for bg in backgrounds))
    for step in range(1,21):
        candidate=mix(color,target,step/20)
        if min(contrast(candidate,bg) for bg in backgrounds)>=minimum:return candidate
    return target


def gradient_samples(colors):
    return [mix(first,second,i/12) for first,second in zip(colors,colors[1:]) for i in range(13)]


def gradient_ink(colors):
    for step in range(21):
        adjusted=[mix(c,'#ffffff',step/20) for c in colors]
        samples=gradient_samples(adjusted)
        ink=max(('#000000','#ffffff'),key=lambda c:min(contrast(c,bg) for bg in samples))
        if min(contrast(ink,bg) for bg in samples)>=4.5:return adjusted,ink
    return adjusted,ink


def build_palette(row):
    key,title,colors,dark,base,secondary,accent,buttons=row
    seed,other=colors[base],colors[secondary]
    if dark:
        bg=mix(seed,'#000000',.28 if luminance(seed)>.06 else .10)
        surface=mix(seed,other,.16)
        roles=dict(bg=bg,surface=surface,side=mix(bg,'#000000',.12),field=mix(bg,'#000000',.10),
                   soft=mix(surface,other,.16),hover=mix(surface,colors[accent],.16),
                   selected=mix(surface,colors[accent],.20),border=mix(surface,other,.55),handle=mix(other,colors[accent],.30))
        text=mix(max(colors,key=luminance),'#ffffff',.80)
        muted=mix(text,other,.25)
    else:
        roles=dict(bg=mix(seed,'#ffffff',.24),surface=mix(seed,'#ffffff',.75),side=mix(seed,'#ffffff',.55),
                   field=mix(seed,'#ffffff',.36),soft=mix(seed,other,.12),hover=mix(seed,other,.22),
                   selected=mix(seed,colors[accent],.18),border=mix(seed,other,.40),handle=mix(other,colors[accent],.35))
        text=mix(min(colors,key=luminance),'#000000',.70)
        muted=mix(min(colors,key=luminance),'#000000',.46)
    backgrounds=[roles[name] for name in ('bg','surface','side','field','soft','hover','selected')]
    roles.update(text=readable(text,backgrounds),muted=readable(muted,backgrounds),
                 accent=readable(colors[accent],backgrounds),danger=readable('#ff6373' if dark else '#a82c40',backgrounds))
    stops=[colors[i] for i in buttons]
    if key=='ember_night':stops[1]=mix(stops[0],'#ffffff',.12);stops[2]=mix(stops[0],'#ffffff',.24)
    stops,ink=gradient_ink(stops)
    roles.update(primary=stops[0],primary_mid=stops[1],primary2=stops[2],onprimary=ink)
    return roles

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
PALETTES.update({row[0]:build_palette(row) for row in PALETTE_THEMES})


def theme_colors(settings):
    theme=selected_theme(settings);p=dict(PALETTES[theme])
    p.setdefault('primary_mid',mix(p['primary'],p['primary2'],.5))
    accent=settings.get('accent')
    allow_custom=theme not in PALETTE_IDS or settings.get('use_custom_accent',False)
    if accent and QColor(accent).isValid() and theme!='contrast' and allow_custom:
        p['primary']=p['primary_mid']=p['primary2']=accent
        p['onprimary']=readable('#000000',[accent])
    return p,theme


def hero_colors(theme,roles):
    preset=next((row for row in PALETTE_THEMES if row[0]==theme),None)
    if preset:
        colors=preset[2]
        return dict(sky0=colors[0],sky1=colors[1],sky2=colors[2],sun=max(colors,key=luminance),
                    sunline=colors[1],cloud=colors[2],mountain0=colors[1],mountain1=colors[2],mountain2=colors[0],
                    ground=colors[0],grass=colors[3],stone=colors[1],trunk=colors[1],tree0=colors[0],tree1=colors[2],
                    shade=roles['bg'],eyebrow=roles['accent'],title=roles['text'],muted=roles['muted'])
    if theme=='contrast':
        return dict(sky0='#000000',sky1='#111111',sky2='#333333',sun='#ffff00',sunline='#ffffff',cloud='#ffffff',
                    mountain0='#333333',mountain1='#666666',mountain2='#111111',ground='#000000',grass='#ffff00',
                    stone='#ffffff',trunk='#ffffff',tree0='#111111',tree1='#333333',shade='#000000',
                    eyebrow='#ffff00',title='#ffffff',muted='#ffffff')
    light=theme=='light'
    return dict(sky0='#f6e9df' if light else '#211e35',sky1='#f8caa6' if light else '#a04b72',
                sky2='#ffe7be' if light else '#f79e70',sun='#ffd293',sunline='#e98c8e',cloud='#efa4b1',
                mountain0='#6b365d',mountain1='#9b526d',mountain2='#442440',ground='#2d1c30',grass='#b86c76',
                stone='#4c2b42',trunk='#50304a',tree0='#251a32',tree1='#3b2547',shade='#faf4ed' if light else '#0e0f18',
                eyebrow='#99432e' if light else '#ffb078',title='#28354a' if light else '#fff0ec',muted='#5f5661' if light else '#e3becb')


def selected_theme(settings):
    name=settings.get('theme','light')
    if name=='system':return 'sunset' if QApplication.styleHints().colorScheme()==Qt.ColorScheme.Dark else 'light'
    return name if name in PALETTES else 'light'


def stylesheet(settings):
    p,theme=theme_colors(settings);scale=max(90,min(140,int(settings.get('ui_scale',100))))/100
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
QPushButton#primary { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 @primary,stop:0.5 @primary_mid,stop:1 @primary2); color: @onprimary; border: 1px solid transparent; padding: 12px 18px; font-size: 14px; font-weight: 750; }
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
QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 @primary,stop:0.5 @primary_mid,stop:1 @primary2); border-radius: 4px; }
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
    window._hero_colors=hero_colors(theme,colors)
    if hasattr(window,'theme_cards'):
        for key,card in window.theme_cards.items():card.setChecked(key==theme)
    for item in window.findChildren(QWidgetLandscape()):item.update()


def QWidgetLandscape():
    # Local import avoids the UI module importing itself during construction.
    from ui import Landscape
    return Landscape
