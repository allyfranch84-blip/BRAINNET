import sys
# Importante: QtWebEngineWidgets deve vir antes de QApplication
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtCore import Qt

class TestHotbar(QMainWindow):
    def __init__(self):
        super().__init__()
        # Flags mágicas para sobreposição e transparência
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Tamanho
        self.resize(1080, 64)
        
        # Componente Web (React rodaria aqui no futuro)
        self.web_view = QWebEngineView(self)
        self.setCentralWidget(self.web_view)
        
        html = """
        <html>
        <body style="margin:0; padding:0; background: transparent; display: flex; align-items: center; justify-content: center;">
            <div style="width: 100%; height: 100%; background: #0d0d14; border-radius: 12px; border: 1px solid rgba(255,255,255,0.2); color: white; display: flex; align-items: center; justify-content: space-around; font-family: sans-serif; box-shadow: 0 0 20px rgba(127,240,224,0.2);">
                <span style="cursor: grab;">🎤 MIC</span>
                <span>🔍 BUSCAR</span>
                <span>⚙️ GUI</span>
                <span style="color: #ff6f8e;">❌ SAIR</span>
            </div>
        </body>
        </html>
        """
        self.web_view.setHtml(html)

        # Centralizar na parte inferior
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = screen.height() - self.height() - 60
        self.move(x, y)

    # Lógica de arraste nativo do Windows
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragPos = event.globalPos()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(self.pos() + event.globalPos() - self.dragPos)
            self.dragPos = event.globalPos()
            event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    hotbar = TestHotbar()
    hotbar.show()
    sys.exit(app.exec_())