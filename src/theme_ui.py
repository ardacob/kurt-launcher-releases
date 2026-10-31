"""Keyboard-accessible palette cards, drawn with Qt using the reference swatches."""
from PySide6.QtCore import Qt,QRectF,QSize
from PySide6.QtGui import QPainterPath,QColor,QPalette,QPainter
from PySide6.QtWidgets import QPushButton,QStylePainter,QStyleOptionButton,QStyle


class ThemeCard(QPushButton):
    def __init__(self,key,title,swatches,parent=None):
        super().__init__(title,parent)
        self.theme_key=key;self.swatches=swatches
        self.setCheckable(True);self.setMinimumHeight(86);self.setMinimumWidth(170)
        self.setObjectName('themeCard');self.setToolTip(' · '.join(swatches))
        self.setAccessibleName(title)

    def sizeHint(self):
        size=super().sizeHint()
        return QSize(max(190,size.width()+20),max(86,self.fontMetrics().height()+58))

    def paintEvent(self,event):
        painter=QStylePainter(self);option=QStyleOptionButton();self.initStyleOption(option)
        option.text='';painter.drawControl(QStyle.CE_PushButton,option)
        painter.setRenderHint(QPainter.Antialiasing)
        strip=QRectF(12,12,self.width()-24,28);clip=QPainterPath();clip.addRoundedRect(strip,6,6)
        painter.save();painter.setClipPath(clip)
        width=strip.width()/4
        for i,color in enumerate(self.swatches):
            painter.fillRect(QRectF(strip.x()+i*width,strip.y(),width+1,strip.height()),QColor(color))
        painter.restore()
        painter.drawItemText(self.rect().adjusted(8,44,-8,-7),Qt.AlignCenter,option.palette,
                             self.isEnabled(),self.text(),QPalette.ButtonText)
