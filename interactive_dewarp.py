
from __future__ import annotations
from PIL import Image
from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import QPixmap, QPainter, QPen, QBrush
from PySide6.QtWidgets import QLabel

class QuadEditor(QLabel):
    quadChanged = Signal(list)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(700,500)
        self.setAlignment(Qt.AlignCenter)
        self.setMouseTracking(True)
        self.image=None
        self.points=[]
        self.active=-1

    def set_image(self, im):
        self.image=im.copy()
        w,h=im.size
        m=int(min(w,h)*0.08)
        self.points=[(m,m),(w-m,m),(w-m,h-m),(m,h-m)]
        self.update()

    def _scale_offset(self):
        if self.image is None: return 1,0,0
        iw,ih=self.image.size
        s=min(self.width()/iw,self.height()/ih)
        dw,dh=iw*s,ih*s
        return s,(self.width()-dw)/2,(self.height()-dh)/2

    def _to_image(self,p):
        s,ox,oy=self._scale_offset()
        if not s:return (0,0)
        return ((p.x()-ox)/s,(p.y()-oy)/s)

    def _to_widget(self,p):
        s,ox,oy=self._scale_offset()
        return QPoint(int(p[0]*s+ox),int(p[1]*s+oy))

    def paintEvent(self,e):
        super().paintEvent(e)
        if self.image is None:return
        painter=QPainter(self)
        s,ox,oy=self._scale_offset()
        pix=QPixmap.fromImage(self._qimage(self.image))
        painter.drawPixmap(int(ox),int(oy),int(self.image.width()*s),int(self.image.height()*s),pix)
        pen=QPen(Qt.yellow,3); painter.setPen(pen)
        pts=[self._to_widget(p) for p in self.points]
        for i in range(4):
            painter.drawLine(pts[i],pts[(i+1)%4])
        painter.setBrush(QBrush(Qt.red))
        for p in pts:painter.drawEllipse(p,8,8)
        painter.end()

    def _qimage(self,im):
        rgba=im.convert("RGBA")
        from PySide6.QtGui import QImage
        return QImage(rgba.tobytes("raw","RGBA"),rgba.width,rgba.height,rgba.width*4,QImage.Format_RGBA8888).copy()

    def mousePressEvent(self,e):
        if self.image is None:return
        p=e.position().toPoint()
        pts=[self._to_widget(x) for x in self.points]
        ds=[(p.x()-q.x())**2+(p.y()-q.y())**2 for q in pts]
        self.active=min(range(4),key=ds.__getitem__)
        if ds[self.active] <= 22**2:
            e.accept()
        else:self.active=-1

    def mouseMoveEvent(self,e):
        if self.active<0 or self.image is None:return
        x,y=self._to_image(e.position().toPoint())
        x=max(0,min(self.image.width()-1,x)); y=max(0,min(self.image.height()-1,y))
        self.points[self.active]=(x,y)
        self.quadChanged.emit(self.points)
        self.update()

    def mouseReleaseEvent(self,e):
        self.active=-1
        e.accept()
