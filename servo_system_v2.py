import sys
import os
import sqlite3
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QLineEdit, QFrame, 
                             QStackedWidget, QApplication, QMessageBox, QGraphicsDropShadowEffect)
from PyQt5.QtGui import QPixmap, QFont, QColor
from PyQt5.QtCore import Qt, QPoint

# --- 1. قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect("medical_users.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (therapist_id TEXT PRIMARY KEY, password TEXT)''')
    conn.commit()
    conn.close()

# --- 2. واجهة تسجيل الدخول ---
class LoginWidget(QWidget):
    def __init__(self, parent_app):
        super().__init__()
        self.app = parent_app
        
        # التخطيط الرئيسي للواجهة (لضمان التوسيط)
        self.outer_layout = QVBoxLayout(self)
        self.outer_layout.setAlignment(Qt.AlignCenter)

        # بطاقة تسجيل الدخول
        self.card = QFrame()
        self.card.setFixedSize(450, 650)
        self.card.setStyleSheet("""
            QFrame {
                background-color: #1c2025;
                border-radius: 30px;
                border: 1px solid #3e4451;
            }
        """)
        
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(50)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setYOffset(15)
        self.card.setGraphicsEffect(shadow)

        # محتوى البطاقة
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(45, 45, 45, 45)
        card_layout.setSpacing(0) # تصفير الـ spacing للتحكم الدقيق بالمسافات

        # اللوقو
        self.logo = QLabel()
        pixmap = QPixmap("Image 2026 Photoroom.png")
        if not pixmap.isNull():
            self.logo.setPixmap(pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.logo.setText("🏥")
            self.logo.setStyleSheet("color: #3498db; font-size: 50px; border: none;")
        self.logo.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.logo)
        card_layout.addSpacing(20) # مسافة تحت اللوقو

        # نص الترحيب
        welcome_lbl = QLabel("SYSTEM ACCESS")
        welcome_lbl.setStyleSheet("color: #ffffff; font-size: 20px; font-weight: bold; letter-spacing: 3px; border: none;")
        welcome_lbl.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(welcome_lbl)
        card_layout.addSpacing(40) # مسافة تحت العنوان

        # تصميم الحقول
        input_style = """
            QLineEdit {
                background-color: #2c313c;
                color: white;
                padding: 15px;
                border-radius: 12px;
                border: 2px solid #2c313c;
                font-size: 14px;
            }
            QLineEdit:focus { border: 2px solid #3498db; background-color: #1e2227; }
        """
        self.txt_id = QLineEdit(); self.txt_id.setPlaceholderText("Therapist ID")
        self.txt_pass = QLineEdit(); self.txt_pass.setPlaceholderText("Password")
        self.txt_pass.setEchoMode(QLineEdit.Password)
        self.txt_id.setStyleSheet(input_style); self.txt_pass.setStyleSheet(input_style)
        
        card_layout.addWidget(self.txt_id)
        card_layout.addSpacing(15) # مسافة بين الحقلين
        card_layout.addWidget(self.txt_pass)
        card_layout.addSpacing(30) # مسافة قبل زر الدخول

        # أزرار العمليات
        btn_login = QPushButton("LOGIN")
        btn_login.setCursor(Qt.PointingHandCursor)
        btn_login.setStyleSheet("""
            QPushButton { background-color: #3498db; color: white; font-weight: bold; padding: 15px; border-radius: 12px; font-size: 15px; border: none; }
            QPushButton:hover { background-color: #2980b9; }
        """)
        btn_login.clicked.connect(self.handle_login)
        card_layout.addWidget(btn_login)
        card_layout.addSpacing(15)

        # روابط التنقل
        links_box = QHBoxLayout()
        btn_signup = QPushButton("Sign Up"); btn_forgot = QPushButton("Forgot ID/Pass?")
        for b in [btn_signup, btn_forgot]:
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("color: #aeb9c4; border: none; font-size: 12px; text-decoration: underline; background: transparent;")
        
        btn_signup.clicked.connect(lambda: self.app.switch_page(2))
        
        links_box.addWidget(btn_signup); links_box.addStretch(); links_box.addWidget(btn_forgot)
        card_layout.addLayout(links_box)

        card_layout.addStretch() # دفع البايباس للأسفل

        # زر الممر الخلفي
        btn_backdoor = QPushButton("Admin Bypass 🔓")
        btn_backdoor.setStyleSheet("color: #4b5262; border: none; font-size: 11px; background: transparent;")
        btn_backdoor.clicked.connect(self.app.login_success)
        card_layout.addWidget(btn_backdoor, 0, Qt.AlignCenter)

        self.outer_layout.addWidget(self.card)

    def handle_login(self):
        tid, pw = self.txt_id.text(), self.txt_pass.text()
        conn = sqlite3.connect("medical_users.db")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE therapist_id=? AND password=?", (tid, pw))
        user = cursor.fetchone()
        conn.close()
        if user: self.app.login_success()
        else: QMessageBox.critical(self, "Access Denied", "Invalid ID or Password!")

# --- 3. واجهة التسجيل (Signup) ---
class SignupWidget(QWidget):
    def __init__(self, parent_app):
        super().__init__()
        self.app = parent_app
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        
        container = QFrame()
        container.setFixedSize(450, 550)
        container.setStyleSheet("background: #1c2025; border-radius: 25px; border: 1px solid #3e4451;")
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(45,45,45,45)
        
        header = QLabel("CREATE ACCOUNT")
        header.setStyleSheet("color: #2ecc71; font-size: 22px; font-weight: bold; border: none;")
        header.setAlignment(Qt.AlignCenter)
        c_layout.addWidget(header)
        c_layout.addSpacing(40)

        input_style = "background: #2c313c; color: white; padding: 15px; border-radius: 12px; border: none;"
        self.new_id = QLineEdit(); self.new_id.setPlaceholderText("New Therapist ID")
        self.new_pw = QLineEdit(); self.new_pw.setPlaceholderText("New Password")
        self.new_id.setStyleSheet(input_style); self.new_pw.setStyleSheet(input_style)
        
        c_layout.addWidget(self.new_id)
        c_layout.addSpacing(15)
        c_layout.addWidget(self.new_pw)
        c_layout.addSpacing(30)

        btn_save = QPushButton("REGISTER")
        btn_save.setStyleSheet("background: #2ecc71; color: white; font-weight: bold; padding: 15px; border-radius: 12px; border: none;")
        btn_save.clicked.connect(self.register_user)
        
        btn_back = QPushButton("Back to Login")
        btn_back.clicked.connect(lambda: self.app.switch_page(0))
        btn_back.setStyleSheet("color: #aeb9c4; border: none; background: transparent; text-decoration: underline;")

        c_layout.addWidget(btn_save)
        c_layout.addSpacing(10)
        c_layout.addWidget(btn_back)
        layout.addWidget(container)

    def register_user(self):
        tid, pw = self.new_id.text(), self.new_pw.text()
        if tid and pw:
            try:
                conn = sqlite3.connect("medical_users.db")
                cursor = conn.cursor()
                cursor.execute("INSERT INTO users VALUES (?, ?)", (tid, pw))
                conn.commit()
                conn.close()
                QMessageBox.information(self, "Success", "Account registered!")
                self.app.switch_page(0)
            except: QMessageBox.warning(self, "Error", "ID already exists!")
        else: QMessageBox.warning(self, "Error", "Fill all fields!")

# --- 4. التطبيق الرئيسي (نسخة واحدة موحدة) ---
class MainApplication(QMainWindow):
    def __init__(self):
        super().__init__()
        init_db()
        
        self.setWindowTitle("MAQUET SERVO-i | Digital Twin OS")
        self.setStyleSheet("QMainWindow { background-color: #111418; }")

        # 1. الحاوية المركزية
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # 2. التخطيط الرئيسي
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # 3. مكدس الواجهات
        self.stack = QStackedWidget()
        self.main_layout.addWidget(self.stack)

        # 4. إنشاء الصفحات
        self.login_page = LoginWidget(self)
        self.signup_page = SignupWidget(self)
        self.stack.addWidget(self.login_page)
        self.stack.addWidget(QWidget()) # Index 1 (فارغة)
        self.stack.addWidget(self.signup_page)

        # 5. إنشاء زر الخروج
        self.btn_exit = QPushButton("EXIT ✕", self.central_widget)
        self.btn_exit.setFixedSize(100, 40)
        self.btn_exit.setCursor(Qt.PointingHandCursor)
        self.btn_exit.setStyleSheet("""
            QPushButton { 
                background: transparent; 
                color: #e74c3c; 
                border: 1px solid #e74c3c; 
                border-radius: 12px; 
                font-weight: bold; 
            }
            QPushButton:hover { background: #e74c3c; color: white; }
        """)
        self.btn_exit.clicked.connect(self.close)
        
        # 6. تفعيل الشاشة الكاملة
        self.showFullScreen()

    def resizeEvent(self, event):
        # تحريك زر الخروج إلى الزاوية اليمنى العلوية
        if hasattr(self, 'btn_exit') and self.btn_exit:
            margin = 30
            self.btn_exit.move(self.width() - self.btn_exit.width() - margin, margin)
            self.btn_exit.raise_()
        super().resizeEvent(event)

    def switch_page(self, index):
        self.stack.setCurrentIndex(index)

    def login_success(self):
        try:
            from home_screen import MainMenuWindow
            self.home_window = MainMenuWindow()
            self.home_window.show()
            self.close()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainApplication()
    window.show()
    sys.exit(app.exec_())