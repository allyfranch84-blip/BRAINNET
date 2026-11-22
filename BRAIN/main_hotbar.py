import os
import sys
import time
import ctypes

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-sandbox --enable-transparent-visuals --disable-software-rasterizer"
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"

from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtCore import Qt, QCoreApplication, QUrl
from PySide6.QtGui import QColor

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

user32 = ctypes.windll.user32
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080

class CustomWebEnginePage(QWebEnginePage):
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)

    def acceptNavigationRequest(self, url, _type, isMainFrame):
        if url.scheme() == 'aios' and url.host() in ('close', 'expand'):
            QApplication.quit()
            return False
        return super().acceptNavigationRequest(url, _type, isMainFrame)

class HotbarWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.resize(1000, 120)
        
        # Desativa o cache HTTP do Chromium
        profile = QWebEngineProfile.defaultProfile()
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        
        self.web_view = QWebEngineView(self)
        self.web_view.setPage(CustomWebEnginePage(profile, self.web_view))
        self.web_view.page().setBackgroundColor(QColor(Qt.GlobalColor.transparent))
        self.setCentralWidget(self.web_view)
        
        # Sem ?widget=true, carrega a raiz, que agora só tem a Hotbar
        url = f"http://localhost:5174/?t={int(time.time())}"
        self.web_view.setUrl(QUrl(url))
        
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2, screen.height() - self.height() - 10)

        hwnd = int(self.winId())
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    hotbar = HotbarWindow()
    hotbar.show()
    sys.exit(app.exec())
