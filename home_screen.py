import sys
import os
import sys
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QToolButton, QLabel, QPushButton, QFrame, 
                             QGraphicsDropShadowEffect, QApplication, QStackedWidget, QMessageBox)
from PyQt5.QtGui import QIcon, QFont, QColor
from PyQt5.QtCore import Qt, QSize, QTimer
from simulation_dash import AppManager  
from patient_records import PatientRecordsView
from patient_entry import VentilatorManualInputs
import serial.tools.list_ports  # لإضافة فحص المنافذ
QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

# --- 1. كلاس الزر (يبقى كما هو) ---
class MedicalButton(QToolButton):
    def __init__(self, title, subtext, color, icon_name, emoji_fallback):
        super().__init__()
        self.setFixedSize(240, 220)
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        
        icon_path = os.path.join("icons", icon_name)
        if os.path.exists(icon_path):
            self.setIcon(QIcon(icon_path))
            self.setIconSize(QSize(65, 65))
        else:
            title = f"{emoji_fallback}\n\n{title}"
            
        self.setText(f"{title}\n{subtext}")
        self.setFont(QFont("Segoe UI", 12, QFont.Bold))
        
        self.accent = color
        self.default_style = f"""
            QToolButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2c313c, stop:1 #1e2227);
                color: #ffffff;
                border: 1px solid #3e4451;
                border-radius: 25px;
                padding: 20px;
                outline: none;
            }}
            QToolButton:hover {{
                border: 2px solid {self.accent};
                background: #2c313c;
            }}
        """
        self.setStyleSheet(self.default_style)
        
        self.shadow = QGraphicsDropShadowEffect()
        self.shadow.setBlurRadius(20)
        self.shadow.setColor(QColor(0, 0, 0, 150))
        self.shadow.setYOffset(10)
        self.setGraphicsEffect(self.shadow)

    def enterEvent(self, event):
        self.setStyleSheet(self.default_style.replace("#3e4451", self.accent))
        self.shadow.setColor(QColor(self.accent))
        self.shadow.setBlurRadius(30)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet(self.default_style)
        self.shadow.setColor(QColor(0, 0, 0, 150))
        self.shadow.setBlurRadius(20)
        super().leaveEvent(event)

# --- 2. كلاس النافذة الرئيسية ---
class MainMenuWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.patient_view = None
        self.setWindowTitle("MAQUET SERVO-i | Advanced Digital Twin")
        
        self.current_selected_patient = None 
        self.previous_index_before_entry = None  # لحفظ فهرس الصفحة قبل فتح الإدخال
        
        self.showFullScreen() 
        self.setStyleSheet("QMainWindow { background-color: #111418; }")

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        # إنشاء صفحة القائمة الرئيسية
        self.home_page = QWidget()
        self.main_layout = QVBoxLayout(self.home_page)
        self.main_layout.setContentsMargins(60, 40, 60, 40)

        self.setup_header()
        self.main_layout.addStretch(1)
        self.setup_title_section()
        self.main_layout.addSpacing(50)
        self.setup_buttons_grid()
        self.main_layout.addStretch(2)

        footer = QLabel("System v4.0.2 | Secured Medical Connection | 2026")
        footer.setStyleSheet("color: #4b5262; font-size: 11px;")
        footer.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(footer)

        self.stacked_widget.addWidget(self.home_page)

        # إنشاء المدير الرئيسي مرة واحدة وإضافته للـ Stack (لكن في الصفحة الثانية)
        self.manager = AppManager()
        self.stacked_widget.addWidget(self.manager)

        # ربط إشارات المدير
        self.manager.home_requested.connect(self.return_to_main)
        self.manager.dash.manual_input_requested.connect(self.handle_dash_edit_request)

        # بدء مؤقت لفحص حالة الاتصال (كل 5 ثوانٍ)
        self.connection_timer = QTimer()
        self.connection_timer.timeout.connect(self.update_connection_status)
        self.connection_timer.start(5000)  # 5000 مللي = 5 ثوانٍ
        self.update_connection_status()  # تحديث فوري عند البدء

    def update_connection_status(self):
        """التحقق من وجود المنفذ COM3 (كمثال) وتحديث حالة الاتصال"""
        ports = [port.device for port in serial.tools.list_ports.comports()]
        # يمكنك تعديل الشرط ليتناسب مع منفذ جهازك الحقيقي
        if "COM3" in ports:
            self.dot.setStyleSheet("color: #2ecc71; font-size: 18px;")  # أخضر
            self.status_text.setText("VENTILATOR CONNECTED")
            self.status_text.setStyleSheet("color: #aeb9c4; font-weight: bold; font-size: 10px;")
        else:
            self.dot.setStyleSheet("color: #e74c3c; font-size: 18px;")  # أحمر
            self.status_text.setText("VENTILATOR DISCONNECTED")
            self.status_text.setStyleSheet("color: #aeb9c4; font-weight: bold; font-size: 10px;")

    def logout(self):
        reply = QMessageBox.question(self, 'Logout', 'Are you sure you want to logout?',
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.hide()  # إخفاء النافذة الحالية فوراً
            from servo_system_v2 import MainApplication
            self.login_window = MainApplication()
            self.login_window.show()
            # جدولة إتلاف النافذة القديمة بعد ظهور الجديدة (200 ملي ثانية كافية)
            QTimer.singleShot(200, self.deleteLater)
            
    def handle_patient_selection(self, data):
        try:
            self.current_selected_patient = data
            # تحديث بيانات المريض في المدير الموجود
            self.manager.dash.update_patient_data(data)
            # الانتقال إلى صفحة المدير (التي تحتوي على الداشبورد)
            self.stacked_widget.setCurrentWidget(self.manager)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load patient to dashboard: {e}")

    def setup_header(self):
        header_layout = QHBoxLayout()
        status_box = QFrame()
        status_box.setStyleSheet("background: #1c2025; border-radius: 10px; padding: 5px;")
        status_layout = QHBoxLayout(status_box)
        self.dot = QLabel("●")
        self.dot.setStyleSheet("color: #2ecc71; font-size: 18px;")  # افتراضي أخضر
        self.status_text = QLabel("VENTILATOR CONNECTED")
        self.status_text.setStyleSheet("color: #aeb9c4; font-weight: bold; font-size: 10px;")
        status_layout.addWidget(self.dot)
        status_layout.addWidget(self.status_text)
        
        # إنشاء إطار للأزرار
        btn_frame = QFrame()
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(10)

        # زر تسجيل الخروج
        self.logout_btn = QPushButton("⇤ LOGOUT")
        self.logout_btn.setFixedSize(120, 40)
        self.logout_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #f39c12; border: 1px solid #f39c12; border-radius: 12px; font-weight: bold; }
            QPushButton:hover { background: #f39c12; color: white; }
        """)
        self.logout_btn.clicked.connect(self.logout)

        # زر الخروج من النظام (كما هو)
        self.exit_btn = QPushButton("✕ EXIT SYSTEM")
        self.exit_btn.setFixedSize(140, 40)
        self.exit_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #e74c3c; border: 1px solid #e74c3c; border-radius: 12px; font-weight: bold; }
            QPushButton:hover { background: #e74c3c; color: white; }
        """)
        self.exit_btn.clicked.connect(self.close)

        btn_layout.addWidget(self.logout_btn)
        btn_layout.addWidget(self.exit_btn)

        header_layout.addWidget(status_box)
        header_layout.addStretch()
        header_layout.addWidget(btn_frame)
        self.main_layout.addLayout(header_layout)

    
    def setup_title_section(self):
        title = QLabel("SERVO-i INTERFACE")
        title.setStyleSheet("color: #ffffff; font-size: 45px; font-weight: bold; letter-spacing: 8px;")
        title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel("Select clinical module to proceed with patient care")
        subtitle.setStyleSheet("color: #636d83; font-size: 16px; font-weight: 300;")
        subtitle.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(title)
        self.main_layout.addWidget(subtitle)

    def setup_buttons_grid(self):
        grid_layout = QHBoxLayout()
        grid_layout.setSpacing(25)
        grid_layout.setAlignment(Qt.AlignCenter)
        
        self.btn_new = MedicalButton("NEW PATIENT", "Register & Setup", "#3498db", "add.png", "👤")
        self.btn_db = MedicalButton("RECORDS", "Patient Database", "#2ecc71", "db.png", "📂")
        
        self.btn_dash = MedicalButton("DASHBOARD", "Patient Overview", "#9b59b6", "dash.png", "📊")

        # ربط الأزرار
        self.btn_new.clicked.connect(self.open_patient_entry)
        self.btn_db.clicked.connect(self.open_records_view)
        self.btn_dash.clicked.connect(self.open_dashboard_view)

        grid_layout.addWidget(self.btn_new)
        grid_layout.addWidget(self.btn_db)
        grid_layout.addWidget(self.btn_dash) 
        
        self.main_layout.addLayout(grid_layout)

    def open_dashboard_view(self):
        try:
            # الانتقال إلى المدير الموجود (لا ننشئ نسخة جديدة)
            self.stacked_widget.setCurrentWidget(self.manager)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load Dashboard: {e}")

    def handle_dash_edit_request(self, data):
        """عند الضغط على MANUAL INPUT من الداشبورد: نعرض الصفحة ونحدث البيانات"""
        if not data:
            QMessageBox.warning(self, "No Data", "No patient data found to edit.")
            return
        # فتح صفحة الإدخال (بدون إنشاء جديد إذا كانت موجودة)
        self.open_patient_entry()
        # تحديث البيانات في الصفحة
        if self.patient_view is not None:
            self.patient_view.load_patient_data_to_form(data)
            
    def open_records_view(self):
        try:
            self.records_view = PatientRecordsView()
            self.records_view.back_requested.connect(self.return_to_main)
            self.records_view.patient_selected.connect(self.handle_patient_selection)
            self.records_view.patient_to_edit.connect(self.handle_edit_patient)
            
            self.stacked_widget.addWidget(self.records_view)
            self.stacked_widget.setCurrentWidget(self.records_view)
        except Exception as e:
            print(f"Error loading records: {e}")

    def handle_edit_patient(self, data):
        """فتح صفحة الإدخال وتعبئة البيانات المسحوبة (النقر المزدوج على سجل)"""
        self.open_patient_entry()
        if hasattr(self, 'patient_view'):
            self.patient_view.load_patient_data_to_form(data)
            
    def open_patient_entry(self):
        """فتح صفحة الإدخال (إنشاء مرة واحدة فقط)"""
        if self.patient_view is None:
            try:
                self.patient_view = VentilatorManualInputs()
                # ربط إشارة الرجوع بدالة العودة الذكية (بدلاً من العودة المباشرة للهوم)
                self.patient_view.back_requested.connect(self.return_from_entry)
                self.stacked_widget.addWidget(self.patient_view)
            except Exception as e:
                print(f"Error loading entry: {e}")
                return
        # حفظ الصفحة الحالية قبل الانتقال
        self.previous_index_before_entry = self.stacked_widget.currentIndex()
        self.stacked_widget.setCurrentWidget(self.patient_view)

    def return_from_entry(self):
        """العودة إلى الصفحة التي كانت مفتوحة قبل فتح الإدخال"""
        if self.previous_index_before_entry is not None:
            self.stacked_widget.setCurrentIndex(self.previous_index_before_entry)
            self.previous_index_before_entry = None  # إعادة التعيين بعد العودة
        else:
            # في حالة عدم وجود فهرس سابق (خطأ)، نعود للصفحة الرئيسية
            self.stacked_widget.setCurrentWidget(self.home_page)
            
    def return_to_main(self):
        """العودة إلى الصفحة الرئيسية مع حذف الصفحات المؤقتة (عدا الثابتة)"""
        self.stacked_widget.setCurrentWidget(self.home_page)
        for i in range(self.stacked_widget.count() - 1, 0, -1):
            widget = self.stacked_widget.widget(i)
            if widget not in (self.home_page, self.patient_view, self.manager):
                self.stacked_widget.removeWidget(widget)
                widget.deleteLater()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainMenuWindow()
    window.show()
    sys.exit(app.exec_())