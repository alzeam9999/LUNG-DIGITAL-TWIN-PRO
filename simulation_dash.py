# الاستيرادات الأساسية
import math
import os
import re
import csv
import sys
import random
import struct
import logging
import threading
from datetime import datetime

# استيرادات PyQt5
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QLocale, QThread, QObject, QDateTime
from PyQt5.QtGui import QColor, QPixmap, QTextOption
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QApplication, QComboBox, QGraphicsDropShadowEffect, QLineEdit, 
    QSizePolicy, QGridLayout, QSpinBox, QStackedWidget, QTabWidget, 
    QScrollArea, QDialog, QGroupBox, QTextEdit, QDoubleSpinBox, 
    QMessageBox, QCheckBox, QFormLayout, QFileDialog
)

# استيرادات إضافية
import pyqtgraph as pg
import serial.tools.list_ports

# استيرادات المشروع
from engines.all_engines import AlarmMonitor, AlarmsEngine, TrendBuffer
from auto_adjust_panel import AutoAdjustPanel, ResponsiveMixin
from patient_entry import VentilatorManualInputs

# استيراد WebEngine (اختياري)
try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    from PyQt5.QtCore import QUrl
    WEBENGINE_AVAILABLE = True
except ImportError:
    WEBENGINE_AVAILABLE = False
    print("Warning: PyQt5-WebEngine not installed. 3D view will not be available.")
    print("Install with: pip install PyQtWebEngine")
import http.server
import socketserver
import threading
import os

class SilentHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # إلغاء الطباعة المزعجة
        pass

def start_local_server(directory, port=8000):
    os.chdir(directory)
    handler = SilentHTTPRequestHandler
    httpd = socketserver.TCPServer(("", port), handler)
    thread = threading.Thread(target=httpd.serve_forever)
    thread.daemon = True
    thread.start()
    return httpd, thread    
# --- استايل البطاقات الموحد ---
# إعداد التسجيل (logging) لتلبية متطلبات PDF
logging.basicConfig(
    filename='ventilator_log.txt',
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
def apply_card_style(widget, color="#3e4451"):
    widget.setStyleSheet(f"""
        QFrame {{
            background-color: #1c2025;
            border-radius: 15px;
            border: 1px solid {color};
        }}
    """)
    
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(20)
    shadow.setColor(QColor(0, 0, 0, 150))
    shadow.setYOffset(8)
    widget.setGraphicsEffect(shadow)

# استايل الأزرار الموحد
BUTTON_STYLE = """
    QPushButton {
        background-color: #2c313c;
        color: white;
        border: 1px solid #3e4451;
        border-radius: 8px;
        padding: 8px 15px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #3e4451;
        border: 1px solid #3498db;
    }
    QPushButton:pressed {
        background-color: #1c2025;
    }
"""

class VentilatorDataReader(QObject):
    """محرك لقراءة البيانات من جهاز Maquet Servo-i عبر منفذ تسلسلي"""
    data_updated = pyqtSignal(dict)

    def __init__(self, port="COM3", baudrate=38400, simulation_mode=True):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.simulation_mode = simulation_mode
        self.is_running = False
        self.serial_conn = None
        self._t = 0  # للتحكم في المحاكاة

    def connect(self):
        """إنشاء الاتصال بالجهاز أو تفعيل وضع المحاكاة"""
        if self.simulation_mode:
            self.is_running = True
            logging.info("Ventilator: Simulation mode activated")
            return True
        else:
            try:
                self.serial_conn = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=1,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    bytesize=serial.EIGHTBITS
                )
                self.is_running = True
                logging.info(f"Ventilator: Connected to {self.port} at {self.baudrate}")
                return True
            except Exception as e:
                logging.error(f"Ventilator: Failed to connect - {e}")
                return False

    def disconnect(self):
        """إغلاق الاتصال"""
        self.is_running = False
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()

    def _parse_ci1_frame(self, raw_bytes):
        """
        تحليل إطار بيانات وفق بروتوكول Maquet CI1.
        يفترض أن الإطار 32 بايت على الأقل.
        """
        parsed = {}
        try:
            if len(raw_bytes) < 32:
                return parsed

            raw_pressure = struct.unpack('>h', raw_bytes[4:6])[0]
            raw_flow = struct.unpack('>h', raw_bytes[6:8])[0]
            raw_volume = struct.unpack('>i', raw_bytes[8:12])[0]
            raw_pip = struct.unpack('>h', raw_bytes[12:14])[0]
            raw_peep = struct.unpack('>h', raw_bytes[14:16])[0]
            raw_vte = struct.unpack('>i', raw_bytes[16:20])[0]
            raw_rr = struct.unpack('>h', raw_bytes[20:22])[0]
            raw_fio2 = struct.unpack('>h', raw_bytes[22:24])[0]

            # تطبيق معاملات القياس (scale factors)
            parsed = {
                'airway_pressure': round(raw_pressure * 0.1, 1),
                'flow_insp': round(raw_flow * 0.1, 1),
                'volume_wave': round(raw_volume * 1.0, 1),
                'pip': round(raw_pip * 0.1, 1),
                'peep': round(raw_peep * 0.1, 1),
                'vte': int(raw_vte * 1.0),
                'rr': int(raw_rr * 1.0),
                'fio2': int(raw_fio2 * 1.0),
                # قيم محسوبة أو تقديرية
                'plateau_pressure': round(raw_pip * 0.1, 1),  # مؤقت
                'driving_pressure': round((raw_pip - raw_peep) * 0.1, 1),
                'mechanical_power': 14.5,  # قيمة افتراضية، يمكن حسابها لاحقاً
                'battery': 100,
            }
        except Exception as e:
            logging.error(f"Parse error: {e}")
        return parsed

    def run(self):
        """الحلقة الرئيسية لجلب البيانات (تُستدعى في thread)"""
        import time
        import random
        import math

        while self.is_running:
            if self.simulation_mode:
                # محاكاة البيانات
                self._t += 0.05
                resp_cycle = math.sin(self._t * 1.5)
                p_val = 5 + 20 * max(0, resp_cycle) + random.uniform(-0.5, 0.5)
                f_val = 60 * resp_cycle + random.uniform(-2, 2)
                v_val = 200 + 300 * max(0, math.sin(self._t * 1.5 - 0.5))

                data = {
                    'airway_pressure': round(p_val, 1),
                    'flow_insp': round(f_val, 1),
                    'volume_wave': round(v_val, 1),
                    'pip': 25 + random.randint(-2, 2),
                    'peep': 5 + random.randint(-1, 1),
                    'vte': 450 + random.randint(-20, 20),
                    'rr': 16 + random.randint(-1, 1),
                    'fio2': 40 + random.randint(-2, 2),
                    'plateau_pressure': 25 + random.uniform(-2, 2),
                    'driving_pressure': 15 + random.uniform(-2, 2),
                    'mechanical_power': 14.5 + random.uniform(-0.5, 0.5),
                    'static_compliance': 50 + random.randint(-2, 2),
                    'airway_resistance': 12 + random.uniform(-0.5, 0.5),
                    'battery': 95,
                    'o2_pressure': 50,
                }
                self.data_updated.emit(data)
                time.sleep(0.05)  # 20 هرتز
            else:
                # قراءة من الجهاز الحقيقي
                if self.serial_conn and self.serial_conn.is_open:
                    try:
                        if self.serial_conn.in_waiting >= 32:
                            raw = self.serial_conn.read(32)
                            data = self._parse_ci1_frame(raw)
                            if data:
                                self.data_updated.emit(data)
                    except Exception as e:
                        logging.error(f"Read error: {e}")
                time.sleep(0.01)  # تأخير قصير

class TrendsWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Trends - Last 60 Readings")
        self.setGeometry(100, 100, 800, 600)
        self.setStyleSheet("background-color: #1c2025; color: white;")
        layout = QVBoxLayout(self)

        self.plots = []
        self.curves = []
        self.titles = ["PIP (cmH2O)", "PEEP (cmH2O)", "Vt (mL)", "RR (bpm)", "Compliance", "Driving Pressure"]
        self.colors = ['#f1c40f', '#2ecc71', '#3498db', '#e74c3c', '#9b59b6', '#f39c12']
        self.data_buffers = {title: [0]*60 for title in self.titles}

        for title, color in zip(self.titles, self.colors):
            plot = pg.PlotWidget(title=title)
            plot.setBackground('#111418')
            plot.setMinimumHeight(80)
            plot.showGrid(x=True, y=True, alpha=0.2)
            plot.getAxis('left').setTextPen('w')
            plot.getAxis('bottom').setStyle(showValues=False)
            curve = plot.plot(pen=pg.mkPen(color=color, width=2))
            self.plots.append(plot)
            self.curves.append(curve)
            layout.addWidget(plot)

    def update_trends(self, data):
        """تحديث الرسوم البيانية بالبيانات الجديدة"""
        # تحديث المخازن
        for i, title in enumerate(self.titles):
            if title == "PIP (cmH2O)" and 'pip' in data:
                self.data_buffers[title].append(data['pip'])
            elif title == "PEEP (cmH2O)" and 'peep' in data:
                self.data_buffers[title].append(data['peep'])
            elif title == "Vt (mL)" and 'vte' in data:
                self.data_buffers[title].append(data['vte'])
            elif title == "RR (bpm)" and 'rr' in data:
                self.data_buffers[title].append(data['rr'])
            elif title == "Compliance" and 'compliance' in data:
                self.data_buffers[title].append(data['compliance'])
            elif title == "Driving Pressure" and 'driving' in data:
                self.data_buffers[title].append(data['driving'])
            else:
                self.data_buffers[title].append(0)
            
            # الاحتفاظ بآخر 60 قيمة
            if len(self.data_buffers[title]) > 60:
                self.data_buffers[title].pop(0)
            
            # تحديث المنحنى
            self.curves[i].setData(self.data_buffers[title])


# أضف هذا الكلاس في simulation_dash.py (بعد استيراد auto_adjust_panel)

from ai_chat import AIChatMixin

class AIChatDialog(AIChatMixin, QDialog):
    # إشارة لإرسال البيانات المدخلة إلى الداشبورد (يمكن استخدامها لاحقاً)
    data_sent = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Educational Assistant - Simulation")
        self.setMinimumSize(900, 700)
        self.setStyleSheet("background-color: #1c2025; color: white;")

        # تخطيط رئيسي
        main_layout = QVBoxLayout(self)

        # تبويبات - نعيد استخدام نفس تبويبات AutoAdjustPanel تقريباً
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #3e4451; background: #111418; }
            QTabBar::tab { background: #2c313c; color: white; padding: 8px 16px; margin: 2px; }
            QTabBar::tab:selected { background: #3498db; }
        """)

        # إنشاء التبويبات (نفس ترتيب AutoAdjustPanel)
        self.create_ventilation_mode_tab()
        self.create_oxygenation_tab()
        self.create_volume_target_tab()
        self.create_respiratory_rate_tab()
        self.create_pressure_target_tab()
        self.create_timing_trigger_tab()
        self.create_advanced_alarms_tab()

        main_layout.addWidget(self.tabs)

        # حقل إدخال النص الكبير للذكاء الاصطناعي
        ai_group = QGroupBox("AI Query")
        ai_group.setStyleSheet("QGroupBox { color: #9b59b6; font-weight: bold; border: 1px solid #3e4451; margin-top: 10px; }")
        ai_layout = QVBoxLayout(ai_group)
        self.ai_text = QTextEdit()
        self.ai_text.setPlaceholderText("Enter your clinical question or context for the AI...")
        self.ai_text.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        ai_layout.addWidget(self.ai_text)
        main_layout.addWidget(ai_group)

        # أزرار
        btn_layout = QHBoxLayout()
        btn_send = QPushButton("📤 Send to AI")
        btn_send.setStyleSheet("background-color: #3498db; color: white; padding: 10px 20px; font-weight: bold;")
        btn_send.clicked.connect(self.on_send)
        btn_close = QPushButton("✕ Close")
        btn_close.setStyleSheet("background-color: #e74c3c; color: white; padding: 10px 20px; font-weight: bold;")
        btn_close.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_send)
        btn_layout.addWidget(btn_close)
        main_layout.addLayout(btn_layout)
        self.setup_chat(main_layout, btn_send)

    # دوال إنشاء التبويبات (مقتبسة من AutoAdjustPanel مع تعديل طفيف)
    def create_ventilation_mode_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)
        layout.setAlignment(Qt.AlignTop)

        mode_group = QGroupBox("1. Ventilation Mode Selection")
        mode_group.setStyleSheet("QGroupBox { color: #3498db; font-weight: bold; border: 1px solid #3e4451; margin-top: 10px; }")
        mode_layout = QVBoxLayout(mode_group)
        mode_layout.setSpacing(10)

        lbl_mode = QLabel("Select Ventilation Mode:")
        lbl_mode.setStyleSheet("color: white;")
        self.ai_mode_combo = QComboBox()
        self.ai_mode_combo.addItems([
            "Volume Control Ventilation (VCV)", "Pressure Control Ventilation (PCV)",
            "Pressure Regulated Volume Control (PRVC)", "Synchronized Intermittent Mandatory Ventilation (SIMV)",
            "Pressure Support Ventilation (PSV)", "Continuous Positive Airway Pressure (CPAP)",
            "Adaptive Support Ventilation (ASV)", "Proportional Assist Ventilation (PAV)",
            "Neurally Adjusted Ventilatory Assist (NAVA)", "Non-Invasive Ventilation (NIV)"
        ])
        self.ai_mode_combo.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451; padding: 5px;")
        mode_layout.addWidget(lbl_mode)
        mode_layout.addWidget(self.ai_mode_combo)

        patient_status_group = QGroupBox("Patient Clinical Status")
        patient_status_group.setStyleSheet("QGroupBox { color: #3498db; font-weight: bold; border: 1px solid #3e4451; margin-top: 10px; }")
        status_layout = QGridLayout(patient_status_group)
        status_layout.setSpacing(10)
        status_layout.setColumnMinimumWidth(1, 200)

        # Consciousness
        status_layout.addWidget(QLabel("Consciousness:"), 0, 0)
        self.ai_consciousness = QComboBox()
        self.ai_consciousness.addItems(["Alert and responsive", "Partially awake", "Sedated", "Unconscious"])
        self.ai_consciousness.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451; padding: 5px;")
        status_layout.addWidget(self.ai_consciousness, 0, 1)

        # Synchrony
        status_layout.addWidget(QLabel("Patient-Ventilator Synchrony:"), 1, 0)
        self.ai_synchrony = QComboBox()
        self.ai_synchrony.addItems(["Fully synchronized", "Mostly synchronized", "Poor synchrony", "Asynchrony"])
        self.ai_synchrony.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451; padding: 5px;")
        status_layout.addWidget(self.ai_synchrony, 1, 1)

        # RR / WOB
        status_layout.addWidget(QLabel("Respiratory Rate / Work of Breathing:"), 2, 0)
        self.ai_rr_wob = QComboBox()
        self.ai_rr_wob.addItems([
            "Within target range", "Spontaneous RR acceptable", "Mildly increased work of breathing",
            "Mostly supported", "Partially supported", "Fully supported", "Minimal support",
            "Work of breathing reduced but present"
        ])
        self.ai_rr_wob.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451; padding: 5px;")
        status_layout.addWidget(self.ai_rr_wob, 2, 1)

        # Sedation
        status_layout.addWidget(QLabel("Sedation / Comfort:"), 3, 0)
        self.ai_sedation = QComboBox()
        self.ai_sedation.addItems([
            "Not needed", "Minimal sedation", "Light sedation", "Moderate sedation",
            "Deep sedation", "Comfortable / no discomfort", "Mild discomfort", "Agitated"
        ])
        self.ai_sedation.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451; padding: 5px;")
        status_layout.addWidget(self.ai_sedation, 3, 1)

        # Hemodynamics
        status_layout.addWidget(QLabel("Hemodynamics (BP/HR effect):"), 4, 0)
        self.ai_hemodynamics = QComboBox()
        self.ai_hemodynamics.addItems(["Stable", "Mild hypotension", "Hypotension", "Tachycardia", "Bradycardia", "Unstable"])
        self.ai_hemodynamics.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451; padding: 5px;")
        status_layout.addWidget(self.ai_hemodynamics, 4, 1)

        # Alarms
        status_layout.addWidget(QLabel("Alarms / Safety Response:"), 5, 0)
        self.ai_alarms = QComboBox()
        self.ai_alarms.addItems(["All alarms acknowledged and appropriate", "Occasional nuisance alarms", "Frequent alarms", "Critical alarms active"])
        self.ai_alarms.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451; padding: 5px;")
        status_layout.addWidget(self.ai_alarms, 5, 1)

        # Weaning
        status_layout.addWidget(QLabel("Weaning Readiness / Spontaneous Breathing:"), 6, 0)
        self.ai_weaning = QComboBox()
        self.ai_weaning.addItems(["Not ready", "Partially ready", "Fully ready", "Spontaneous breaths >8 bpm", "Spontaneous breaths >10 bpm", "Spontaneous breaths >12 bpm"])
        self.ai_weaning.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451; padding: 5px;")
        status_layout.addWidget(self.ai_weaning, 6, 1)

        # Mask Seal
        status_layout.addWidget(QLabel("Mask Seal / Patient Cooperation (NIV only):"), 7, 0)
        self.ai_mask = QComboBox()
        self.ai_mask.addItems(["Not applicable", "Fully maintained", "Partial leak", "Poor cooperation"])
        self.ai_mask.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451; padding: 5px;")
        status_layout.addWidget(self.ai_mask, 7, 1)

        layout.addWidget(mode_group)
        layout.addWidget(patient_status_group)
        layout.addStretch()
        self.tabs.addTab(tab, "1. Vent Mode")

    def create_oxygenation_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)

        fio2_group = QGroupBox("2.1 FiO₂ Control Engine")
        fio2_group.setStyleSheet("QGroupBox { color: #3498db; font-weight: bold; border: 1px solid #3e4451; margin-top: 10px; }")
        fio2_layout = QGridLayout(fio2_group)
        fio2_layout.setSpacing(10)

        fio2_layout.addWidget(QLabel("FiO₂ (%):"), 0, 0)
        self.ai_fio2_min = QSpinBox()
        self.ai_fio2_min.setRange(21, 100)
        self.ai_fio2_min.setValue(21)
        self.ai_fio2_min.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        fio2_layout.addWidget(self.ai_fio2_min, 0, 1)
        fio2_layout.addWidget(QLabel("Min"), 0, 2)
        self.ai_fio2_max = QSpinBox()
        self.ai_fio2_max.setRange(21, 100)
        self.ai_fio2_max.setValue(60)
        self.ai_fio2_max.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        fio2_layout.addWidget(self.ai_fio2_max, 0, 3)
        fio2_layout.addWidget(QLabel("Max"), 0, 4)

        self.ai_copd_check = QCheckBox("COPD Patient (Limit FiO₂ to 60%)")
        self.ai_copd_check.setStyleSheet("color: white;")
        fio2_layout.addWidget(self.ai_copd_check, 1, 0, 1, 5)

        peep_group = QGroupBox("2.2 PEEP Control Engine")
        peep_group.setStyleSheet("QGroupBox { color: #3498db; font-weight: bold; border: 1px solid #3e4451; margin-top: 10px; }")
        peep_layout = QGridLayout(peep_group)
        peep_layout.setSpacing(10)

        peep_layout.addWidget(QLabel("PEEP (cmH₂O):"), 0, 0)
        self.ai_peep_min = QSpinBox()
        self.ai_peep_min.setRange(0, 25)
        self.ai_peep_min.setValue(5)
        self.ai_peep_min.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        peep_layout.addWidget(self.ai_peep_min, 0, 1)
        peep_layout.addWidget(QLabel("Min"), 0, 2)
        self.ai_peep_max = QSpinBox()
        self.ai_peep_max.setRange(0, 25)
        self.ai_peep_max.setValue(12)
        self.ai_peep_max.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        peep_layout.addWidget(self.ai_peep_max, 0, 3)
        peep_layout.addWidget(QLabel("Max"), 0, 4)

        peep_layout.addWidget(QLabel("ARDS Severity:"), 1, 0)
        self.ai_ards_combo = QComboBox()
        self.ai_ards_combo.addItems(["None", "Mild", "Moderate", "Severe"])
        self.ai_ards_combo.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451; padding: 5px;")
        peep_layout.addWidget(self.ai_ards_combo, 1, 1, 1, 3)

        peep_layout.addWidget(QLabel("Lung Recruitability:"), 2, 0)
        self.ai_recruit_combo = QComboBox()
        self.ai_recruit_combo.addItems(["Low", "Moderate", "High"])
        self.ai_recruit_combo.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451; padding: 5px;")
        peep_layout.addWidget(self.ai_recruit_combo, 2, 1, 1, 3)

        layout.addWidget(fio2_group)
        layout.addWidget(peep_group)
        layout.addStretch()
        self.tabs.addTab(tab, "2. Oxygenation")

    def create_volume_target_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)

        vt_group = QGroupBox("3.1 Tidal Volume (Vt) Engine")
        vt_group.setStyleSheet("QGroupBox { color: #3498db; font-weight: bold; border: 1px solid #3e4451; margin-top: 10px; }")
        vt_layout = QGridLayout(vt_group)
        vt_layout.setSpacing(10)

        vt_layout.addWidget(QLabel("Tidal Volume (mL):"), 0, 0)
        self.ai_vt_min = QSpinBox()
        self.ai_vt_min.setRange(200, 1000)
        self.ai_vt_min.setValue(400)
        self.ai_vt_min.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        vt_layout.addWidget(self.ai_vt_min, 0, 1)
        vt_layout.addWidget(QLabel("Min"), 0, 2)
        self.ai_vt_max = QSpinBox()
        self.ai_vt_max.setRange(200, 1000)
        self.ai_vt_max.setValue(550)
        self.ai_vt_max.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        vt_layout.addWidget(self.ai_vt_max, 0, 3)
        vt_layout.addWidget(QLabel("Max"), 0, 4)

        vt_layout.addWidget(QLabel("Predicted Body Weight (kg):"), 1, 0)
        self.ai_pbw = QDoubleSpinBox()
        self.ai_pbw.setRange(30, 120)
        self.ai_pbw.setValue(70)
        self.ai_pbw.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        vt_layout.addWidget(self.ai_pbw, 1, 1, 1, 3)

        mve_group = QGroupBox("3.2 Target Minute Ventilation (VE) Engine")
        mve_group.setStyleSheet("QGroupBox { color: #3498db; font-weight: bold; border: 1px solid #3e4451; margin-top: 10px; }")
        mve_layout = QGridLayout(mve_group)
        mve_layout.setSpacing(10)

        mve_layout.addWidget(QLabel("Minute Ventilation (L/min):"), 0, 0)
        self.ai_mve_min = QDoubleSpinBox()
        self.ai_mve_min.setRange(2, 20)
        self.ai_mve_min.setValue(5)
        self.ai_mve_min.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        mve_layout.addWidget(self.ai_mve_min, 0, 1)
        mve_layout.addWidget(QLabel("Min"), 0, 2)
        self.ai_mve_max = QDoubleSpinBox()
        self.ai_mve_max.setRange(2, 20)
        self.ai_mve_max.setValue(8)
        self.ai_mve_max.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        mve_layout.addWidget(self.ai_mve_max, 0, 3)
        mve_layout.addWidget(QLabel("Max"), 0, 4)

        layout.addWidget(vt_group)
        layout.addWidget(mve_group)
        layout.addStretch()
        self.tabs.addTab(tab, "3. Volume")

    def create_respiratory_rate_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)

        rr_group = QGroupBox("4.1 Mandatory Respiratory Rate Engine")
        rr_group.setStyleSheet("QGroupBox { color: #3498db; font-weight: bold; border: 1px solid #3e4451; margin-top: 10px; }")
        rr_layout = QGridLayout(rr_group)
        rr_layout.setSpacing(10)

        rr_layout.addWidget(QLabel("Respiratory Rate (bpm):"), 0, 0)
        self.ai_rr_min = QSpinBox()
        self.ai_rr_min.setRange(5, 40)
        self.ai_rr_min.setValue(10)
        self.ai_rr_min.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        rr_layout.addWidget(self.ai_rr_min, 0, 1)
        rr_layout.addWidget(QLabel("Min"), 0, 2)
        self.ai_rr_max = QSpinBox()
        self.ai_rr_max.setRange(5, 40)
        self.ai_rr_max.setValue(16)
        self.ai_rr_max.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        rr_layout.addWidget(self.ai_rr_max, 0, 3)
        rr_layout.addWidget(QLabel("Max"), 0, 4)

        apnea_group = QGroupBox("4.2 Apnea Backup Respiratory Rate")
        apnea_group.setStyleSheet("QGroupBox { color: #3498db; font-weight: bold; border: 1px solid #3e4451; margin-top: 10px; }")
        apnea_layout = QGridLayout(apnea_group)
        apnea_layout.setSpacing(10)

        apnea_layout.addWidget(QLabel("Backup Rate (bpm):"), 0, 0)
        self.ai_apnea_rate = QSpinBox()
        self.ai_apnea_rate.setRange(5, 40)
        self.ai_apnea_rate.setValue(12)
        self.ai_apnea_rate.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        apnea_layout.addWidget(self.ai_apnea_rate, 0, 1, 1, 3)

        apnea_layout.addWidget(QLabel("Apnea Time (sec):"), 1, 0)
        self.ai_apnea_time = QSpinBox()
        self.ai_apnea_time.setRange(10, 60)
        self.ai_apnea_time.setValue(20)
        self.ai_apnea_time.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        apnea_layout.addWidget(self.ai_apnea_time, 1, 1, 1, 3)

        layout.addWidget(rr_group)
        layout.addWidget(apnea_group)
        layout.addStretch()
        self.tabs.addTab(tab, "4. Rate")

    def create_pressure_target_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)

        ip_group = QGroupBox("5.1 Inspiratory Pressure Control")
        ip_group.setStyleSheet("QGroupBox { color: #3498db; font-weight: bold; border: 1px solid #3e4451; margin-top: 10px; }")
        ip_layout = QGridLayout(ip_group)
        ip_layout.setSpacing(10)

        ip_layout.addWidget(QLabel("Inspiratory Pressure (cmH₂O):"), 0, 0)
        self.ai_ip_min = QSpinBox()
        self.ai_ip_min.setRange(5, 40)
        self.ai_ip_min.setValue(10)
        self.ai_ip_min.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        ip_layout.addWidget(self.ai_ip_min, 0, 1)
        ip_layout.addWidget(QLabel("Min"), 0, 2)
        self.ai_ip_max = QSpinBox()
        self.ai_ip_max.setRange(5, 40)
        self.ai_ip_max.setValue(25)
        self.ai_ip_max.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        ip_layout.addWidget(self.ai_ip_max, 0, 3)
        ip_layout.addWidget(QLabel("Max"), 0, 4)

        ps_group = QGroupBox("5.2 Pressure Support Level")
        ps_group.setStyleSheet("QGroupBox { color: #3498db; font-weight: bold; border: 1px solid #3e4451; margin-top: 10px; }")
        ps_layout = QGridLayout(ps_group)
        ps_layout.setSpacing(10)

        ps_layout.addWidget(QLabel("Pressure Support (cmH₂O):"), 0, 0)
        self.ai_ps_min = QSpinBox()
        self.ai_ps_min.setRange(0, 30)
        self.ai_ps_min.setValue(5)
        self.ai_ps_min.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        ps_layout.addWidget(self.ai_ps_min, 0, 1)
        ps_layout.addWidget(QLabel("Min"), 0, 2)
        self.ai_ps_max = QSpinBox()
        self.ai_ps_max.setRange(0, 30)
        self.ai_ps_max.setValue(15)
        self.ai_ps_max.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        ps_layout.addWidget(self.ai_ps_max, 0, 3)
        ps_layout.addWidget(QLabel("Max"), 0, 4)

        pmax_group = QGroupBox("5.3 Maximum Pressure Limit (Safety)")
        pmax_group.setStyleSheet("QGroupBox { color: #3498db; font-weight: bold; border: 1px solid #3e4451; margin-top: 10px; }")
        pmax_layout = QGridLayout(pmax_group)
        pmax_layout.setSpacing(10)

        pmax_layout.addWidget(QLabel("Max Pressure (cmH₂O):"), 0, 0)
        self.ai_pmax = QSpinBox()
        self.ai_pmax.setRange(20, 60)
        self.ai_pmax.setValue(40)
        self.ai_pmax.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        pmax_layout.addWidget(self.ai_pmax, 0, 1, 1, 3)

        layout.addWidget(ip_group)
        layout.addWidget(ps_group)
        layout.addWidget(pmax_group)
        layout.addStretch()
        self.tabs.addTab(tab, "5. Pressure")

    def create_timing_trigger_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)

        # 6. Timing Settings
        timing_group = QGroupBox("6. Timing Settings")
        timing_group.setStyleSheet("QGroupBox { color: #3498db; font-weight: bold; border: 1px solid #3e4451; margin-top: 10px; }")
        timing_layout = QGridLayout(timing_group)
        timing_layout.setSpacing(10)

        timing_layout.addWidget(QLabel("Inspiratory Time (sec):"), 0, 0)
        self.ai_ti = QDoubleSpinBox()
        self.ai_ti.setRange(0.3, 3.0)
        self.ai_ti.setValue(1.0)
        self.ai_ti.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        timing_layout.addWidget(self.ai_ti, 0, 1, 1, 3)

        timing_layout.addWidget(QLabel("I:E Ratio:"), 1, 0)
        self.ai_ie_combo = QComboBox()
        self.ai_ie_combo.addItems(["1:1", "1:2", "1:3", "1:4", "2:1 (Inverse)"])
        self.ai_ie_combo.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451; padding: 5px;")
        timing_layout.addWidget(self.ai_ie_combo, 1, 1, 1, 3)

        timing_layout.addWidget(QLabel("Rise Time (%):"), 2, 0)
        self.ai_rise_time = QSpinBox()
        self.ai_rise_time.setRange(1, 10)
        self.ai_rise_time.setValue(5)
        self.ai_rise_time.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        timing_layout.addWidget(self.ai_rise_time, 2, 1, 1, 3)

        timing_layout.addWidget(QLabel("Cycling Criteria (%):"), 3, 0)
        self.ai_cycling = QSpinBox()
        self.ai_cycling.setRange(10, 50)
        self.ai_cycling.setValue(25)
        self.ai_cycling.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        timing_layout.addWidget(self.ai_cycling, 3, 1, 1, 3)

        layout.addWidget(timing_group)

        # 7. Trigger Sensitivity
        trigger_group = QGroupBox("7. Trigger Sensitivity")
        trigger_group.setStyleSheet("QGroupBox { color: #3498db; font-weight: bold; border: 1px solid #3e4451; margin-top: 10px; }")
        trigger_layout = QGridLayout(trigger_group)
        trigger_layout.setSpacing(10)

        trigger_layout.addWidget(QLabel("Flow Trigger (L/min):"), 0, 0)
        self.ai_flow_trigger = QDoubleSpinBox()
        self.ai_flow_trigger.setRange(0.5, 5.0)
        self.ai_flow_trigger.setValue(2.0)
        self.ai_flow_trigger.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        trigger_layout.addWidget(self.ai_flow_trigger, 0, 1, 1, 3)

        trigger_layout.addWidget(QLabel("Pressure Trigger (cmH₂O):"), 1, 0)
        self.ai_pressure_trigger = QDoubleSpinBox()
        self.ai_pressure_trigger.setRange(-5.0, -0.5)
        self.ai_pressure_trigger.setValue(-2.0)
        self.ai_pressure_trigger.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        trigger_layout.addWidget(self.ai_pressure_trigger, 1, 1, 1, 3)

        layout.addWidget(trigger_group)

        # 8. Flow Configuration
        flow_group = QGroupBox("8. Flow Configuration")
        flow_group.setStyleSheet("QGroupBox { color: #3498db; font-weight: bold; border: 1px solid #3e4451; margin-top: 10px; }")
        flow_layout = QGridLayout(flow_group)
        flow_layout.setSpacing(10)

        flow_layout.addWidget(QLabel("Peak Inspiratory Flow (L/min):"), 0, 0)
        self.ai_peak_flow_min = QSpinBox()
        self.ai_peak_flow_min.setRange(20, 120)
        self.ai_peak_flow_min.setValue(40)
        self.ai_peak_flow_min.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        flow_layout.addWidget(self.ai_peak_flow_min, 0, 1)
        flow_layout.addWidget(QLabel("Min"), 0, 2)
        self.ai_peak_flow_max = QSpinBox()
        self.ai_peak_flow_max.setRange(20, 120)
        self.ai_peak_flow_max.setValue(80)
        self.ai_peak_flow_max.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        flow_layout.addWidget(self.ai_peak_flow_max, 0, 3)
        flow_layout.addWidget(QLabel("Max"), 0, 4)

        flow_layout.addWidget(QLabel("Flow Pattern:"), 1, 0)
        self.ai_flow_pattern = QComboBox()
        self.ai_flow_pattern.addItems(["Square", "Decelerating", "Sinusoidal"])
        self.ai_flow_pattern.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451; padding: 5px;")
        flow_layout.addWidget(self.ai_flow_pattern, 1, 1, 1, 3)

        layout.addWidget(flow_group)
        layout.addStretch()
        self.tabs.addTab(tab, "6. Timing/Trigger")

    def create_advanced_alarms_tab(self):
        tab = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: transparent; border: none;")
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(15)

        # 9. Advanced Support Settings
        adv_group = QGroupBox("9. Advanced Support Settings")
        adv_group.setStyleSheet("QGroupBox { color: #3498db; font-weight: bold; border: 1px solid #3e4451; margin-top: 10px; }")
        adv_layout = QGridLayout(adv_group)
        adv_layout.setSpacing(10)

        adv_layout.addWidget(QLabel("ASV Target (%):"), 0, 0)
        self.ai_asv_target = QSpinBox()
        self.ai_asv_target.setRange(50, 200)
        self.ai_asv_target.setValue(100)
        self.ai_asv_target.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        adv_layout.addWidget(self.ai_asv_target, 0, 1, 1, 3)

        adv_layout.addWidget(QLabel("PAV Gain (%):"), 1, 0)
        self.ai_pav_gain = QSpinBox()
        self.ai_pav_gain.setRange(30, 80)
        self.ai_pav_gain.setValue(50)
        self.ai_pav_gain.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        adv_layout.addWidget(self.ai_pav_gain, 1, 1, 1, 3)

        adv_layout.addWidget(QLabel("Tube Compensation (%):"), 2, 0)
        self.ai_tube_comp = QSpinBox()
        self.ai_tube_comp.setRange(0, 100)
        self.ai_tube_comp.setValue(50)
        self.ai_tube_comp.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        adv_layout.addWidget(self.ai_tube_comp, 2, 1, 1, 3)

        layout.addWidget(adv_group)

        # NIV Settings
        niv_group = QGroupBox("NIV Settings")
        niv_group.setStyleSheet("QGroupBox { color: #3498db; font-weight: bold; border: 1px solid #3e4451; margin-top: 10px; }")
        niv_layout = QGridLayout(niv_group)
        niv_layout.setSpacing(10)

        niv_layout.addWidget(QLabel("IPAP (cmH₂O):"), 0, 0)
        self.ai_ipap_min = QSpinBox()
        self.ai_ipap_min.setRange(8, 25)
        self.ai_ipap_min.setValue(12)
        self.ai_ipap_min.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        niv_layout.addWidget(self.ai_ipap_min, 0, 1)
        niv_layout.addWidget(QLabel("Min"), 0, 2)
        self.ai_ipap_max = QSpinBox()
        self.ai_ipap_max.setRange(8, 25)
        self.ai_ipap_max.setValue(18)
        self.ai_ipap_max.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        niv_layout.addWidget(self.ai_ipap_max, 0, 3)
        niv_layout.addWidget(QLabel("Max"), 0, 4)

        niv_layout.addWidget(QLabel("EPAP (cmH₂O):"), 1, 0)
        self.ai_epap_min = QSpinBox()
        self.ai_epap_min.setRange(4, 12)
        self.ai_epap_min.setValue(5)
        self.ai_epap_min.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        niv_layout.addWidget(self.ai_epap_min, 1, 1)
        niv_layout.addWidget(QLabel("Min"), 1, 2)
        self.ai_epap_max = QSpinBox()
        self.ai_epap_max.setRange(4, 12)
        self.ai_epap_max.setValue(8)
        self.ai_epap_max.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        niv_layout.addWidget(self.ai_epap_max, 1, 3)
        niv_layout.addWidget(QLabel("Max"), 1, 4)

        layout.addWidget(niv_group)

        # 11. Alarm Configuration
        alarm_group = QGroupBox("11. Alarm Configuration")
        alarm_group.setStyleSheet("QGroupBox { color: #3498db; font-weight: bold; border: 1px solid #3e4451; margin-top: 10px; }")
        alarm_layout = QGridLayout(alarm_group)
        alarm_layout.setSpacing(10)

        alarm_layout.addWidget(QLabel("High Pressure Alarm (cmH₂O):"), 0, 0)
        self.ai_alarm_high_pressure = QSpinBox()
        self.ai_alarm_high_pressure.setRange(20, 60)
        self.ai_alarm_high_pressure.setValue(40)
        self.ai_alarm_high_pressure.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        alarm_layout.addWidget(self.ai_alarm_high_pressure, 0, 1, 1, 3)

        alarm_layout.addWidget(QLabel("Low Tidal Volume (mL):"), 1, 0)
        self.ai_alarm_low_vt = QSpinBox()
        self.ai_alarm_low_vt.setRange(100, 500)
        self.ai_alarm_low_vt.setValue(250)
        self.ai_alarm_low_vt.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        alarm_layout.addWidget(self.ai_alarm_low_vt, 1, 1, 1, 3)

        alarm_layout.addWidget(QLabel("High RR Alarm (bpm):"), 2, 0)
        self.ai_alarm_high_rr = QSpinBox()
        self.ai_alarm_high_rr.setRange(20, 60)
        self.ai_alarm_high_rr.setValue(35)
        self.ai_alarm_high_rr.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        alarm_layout.addWidget(self.ai_alarm_high_rr, 2, 1, 1, 3)

        alarm_layout.addWidget(QLabel("Low Minute Vent (L/min):"), 3, 0)
        self.ai_alarm_low_mv = QDoubleSpinBox()
        self.ai_alarm_low_mv.setRange(2, 10)
        self.ai_alarm_low_mv.setValue(4)
        self.ai_alarm_low_mv.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        alarm_layout.addWidget(self.ai_alarm_low_mv, 3, 1, 1, 3)

        alarm_layout.addWidget(QLabel("High FiO₂ Alarm (%):"), 4, 0)
        self.ai_alarm_high_fio2 = QSpinBox()
        self.ai_alarm_high_fio2.setRange(21, 100)
        self.ai_alarm_high_fio2.setValue(80)
        self.ai_alarm_high_fio2.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        alarm_layout.addWidget(self.ai_alarm_high_fio2, 4, 1, 1, 3)

        alarm_layout.addWidget(QLabel("Low FiO₂ Alarm (%):"), 5, 0)
        self.ai_alarm_low_fio2 = QSpinBox()
        self.ai_alarm_low_fio2.setRange(21, 100)
        self.ai_alarm_low_fio2.setValue(30)
        self.ai_alarm_low_fio2.setStyleSheet("background-color: #111418; color: white; border: 1px solid #3e4451;")
        alarm_layout.addWidget(self.ai_alarm_low_fio2, 5, 1, 1, 3)

        layout.addWidget(alarm_group)
        layout.addStretch()
        scroll.setWidget(content)
        tab_layout = QVBoxLayout(tab)
        tab_layout.addWidget(scroll)
        self.tabs.addTab(tab, "7. Advanced/Alarms")

    def collect_ai_data(self):
        # تجميع جميع البيانات من الحقول
        data = {
            'mode': self.ai_mode_combo.currentText(),
            'consciousness': self.ai_consciousness.currentText(),
            'synchrony': self.ai_synchrony.currentText(),
            'rr_wob': self.ai_rr_wob.currentText(),
            'sedation': self.ai_sedation.currentText(),
            'hemodynamics': self.ai_hemodynamics.currentText(),
            'alarms_response': self.ai_alarms.currentText(),
            'weaning': self.ai_weaning.currentText(),
            'mask_seal': self.ai_mask.currentText(),
            'fio2': (self.ai_fio2_min.value(), self.ai_fio2_max.value()),
            'copd': self.ai_copd_check.isChecked(),
            'peep': (self.ai_peep_min.value(), self.ai_peep_max.value()),
            'ards': self.ai_ards_combo.currentText(),
            'recruitability': self.ai_recruit_combo.currentText(),
            'vt': (self.ai_vt_min.value(), self.ai_vt_max.value()),
            'pbw': self.ai_pbw.value(),
            'mve': (self.ai_mve_min.value(), self.ai_mve_max.value()),
            'rr': (self.ai_rr_min.value(), self.ai_rr_max.value()),
            'apnea_rate': self.ai_apnea_rate.value(),
            'apnea_time': self.ai_apnea_time.value(),
            'ip': (self.ai_ip_min.value(), self.ai_ip_max.value()),
            'ps': (self.ai_ps_min.value(), self.ai_ps_max.value()),
            'pmax': self.ai_pmax.value(),
            'ti': self.ai_ti.value(),
            'ie_ratio': self.ai_ie_combo.currentText(),
            'flow_trigger': self.ai_flow_trigger.value(),
            'pressure_trigger': self.ai_pressure_trigger.value(),
            'peak_flow': (self.ai_peak_flow_min.value(), self.ai_peak_flow_max.value()),
            'flow_pattern': self.ai_flow_pattern.currentText(),
            'asv_target': self.ai_asv_target.value(),
            'pav_gain': self.ai_pav_gain.value(),
            'tube_comp': self.ai_tube_comp.value(),
            'ipap': (self.ai_ipap_min.value(), self.ai_ipap_max.value()),
            'epap': (self.ai_epap_min.value(), self.ai_epap_max.value()),
            'alarm_high_pressure': self.ai_alarm_high_pressure.value(),
            'alarm_low_vt': self.ai_alarm_low_vt.value(),
            'alarm_high_rr': self.ai_alarm_high_rr.value(),
            'alarm_low_mv': self.ai_alarm_low_mv.value(),
            'alarm_high_fio2': self.ai_alarm_high_fio2.value(),
            'alarm_low_fio2': self.ai_alarm_low_fio2.value(),
            'ai_query': self.ai_text.toPlainText(),
        }
        # إرسال الإشارة إلى الداشبورد
        return data

class SimulationDashboard(QMainWindow, ResponsiveMixin):
    home_requested = pyqtSignal()
    manual_input_requested = pyqtSignal(dict)
    values_updated = pyqtSignal(dict)

    RULES = {
        # الموجودة سابقاً
        'pip': {'name': 'Peak Pressure', 'high': 35, 'critical': 40, 'unit': 'cmH2O'},
        'peep': {'name': 'PEEP', 'low': 5, 'high': 15, 'unit': 'cmH2O'},
        'fio2': {'name': 'FiO2', 'high': 60, 'critical': 80, 'unit': '%'},
        'mvent': {'name': 'Min. Vent', 'low': 4, 'high': 12, 'unit': 'L/min'},
        'rsbi': {'name': 'RSBI', 'high': 105, 'unit': 'b/min/L'},
        'mechanical_power': {'name': 'Mech. Power', 'high': 22, 'critical': 25, 'unit': 'J/min'},
        
        # 2.1 Peak Inspiratory Pressure (موجود كـ pip)
        # 2.2 Plateau Pressure
        'plateau_pressure': {'name': 'Plateau Pressure', 'high': 30, 'critical': 35, 'unit': 'cmH2O'},
        # 2.3 Mean Airway Pressure
        'mean_airway_pressure': {'name': 'Mean Airway Pressure', 'high': 20, 'unit': 'cmH2O'},
        # 2.4 PEEP (موجود)
        # 2.5 Auto-PEEP
        'auto_peep': {'name': 'Auto-PEEP', 'high': 5, 'unit': 'cmH2O'},
        # 2.6 Tidal Volume Inspired (نفس vte)
        # 2.8 Minute Ventilation (موجود)
        # 2.9 Respiratory Rate (موجود)
        # 2.11 Spontaneous RR
        'spontaneous_rr': {'name': 'Spontaneous RR', 'high': 30, 'unit': 'bpm'},
                # 2.12 Inspiratory Time
        'insp_time': {'name': 'Inspiratory Time', 'low': 0.8, 'high': 1.2, 'unit': 'sec'},
        # 2.13 Expiratory Time
        'exp_time': {'name': 'Expiratory Time', 'low': 1.5, 'high': 3.0, 'unit': 'sec'},
        # 7.9 Esophageal Pressure
        'esophageal_pressure': {'name': 'Esophageal Pressure', 'low': -15, 'high': 20, 'unit': 'cmH2O'},
        # 2.14 I:E Ratio
        'ie_ratio': {'name': 'I:E Ratio', 'inverse_alert': '>1:1'},  # سنعالجها كشرط خاص
        # 2.15 Peak Inspiratory Flow
        'peak_insp_flow': {'name': 'Peak Inspiratory Flow', 'high': 100, 'unit': 'L/min'},
         # 2.16 Peak Expiratory Flow
        'peak_exp_flow': {'name': 'Peak Expiratory Flow', 'low': 20, 'unit': 'L/min'},  # انخفاض يشير لانسداد

        # 2.xx Mean Inspiratory Flow 
        'mean_insp_flow': {'name': 'Mean Inspiratory Flow', 'low': 20, 'high': 60, 'unit': 'L/min'},

        # 7.4 Chest Wall Compliance
        'chest_wall_compliance': {'name': 'Chest Wall Compliance', 'low': 40, 'high': 80, 'unit': 'mL/cmH2O'},

        # 7.6 Stiffness Index
        'stiffness_index': {'name': 'Lung Stiffness Index', 'low': 1.5, 'high': 3.0, 'unit': ''},


        # 8.9 Turbine Speed
        'turbine_speed': {'name': 'Turbine Speed', 'low': 1000, 'high': 6000, 'unit': 'RPM'},  # حسب النطاق الطبيعي

        # P/F Ratio (محسوب)
        'pf_ratio': {'name': 'P/F Ratio', 'low': 300, 'critical': 200, 'unit': ''},  # مثال
        # 2.16 Peak Expiratory Flow (لا يوجد حد أعلى، انخفاضه يدل على انسداد)
        # 2.17 Static Compliance
        'static_compliance': {'name': 'Static Compliance', 'low': 40, 'unit': 'mL/cmH2O'},
        # 2.18 Dynamic Compliance
        'dynamic_compliance': {'name': 'Dynamic Compliance', 'low': 40, 'unit': 'mL/cmH2O'},
        # 2.19 Airway Resistance
        'airway_resistance': {'name': 'Airway Resistance', 'high': 20, 'unit': 'cmH2O/L/s'},
        # 2.20 Work of Breathing
        'work_of_breathing': {'name': 'Work of Breathing', 'high': 1.0, 'unit': 'J/L'},  # قيمة افتراضية
        # 2.21 Driving Pressure
        'driving_pressure': {'name': 'Driving Pressure', 'high': 15, 'critical': 20, 'unit': 'cmH2O'},
        # 2.22 Stress Index
        'stress_index': {'name': 'Stress Index', 'low': 0.9, 'high': 1.1, 'unit': ''},
        # 2.23 Patient Effort Index
        'patient_effort_index': {'name': 'Patient Effort Index', 'high': 10, 'critical': 15, 'unit': 'cmH2O'},  # افتراضي
        # 2.24 Asynchrony Index
        'asynchrony_index': {'name': 'Asynchrony Index', 'high': 10, 'unit': '%'},
        # 2.25 Trigger Delay Time
        'trigger_delay_time': {'name': 'Trigger Delay', 'high': 150, 'unit': 'ms'},
        # 2.26 Leak Volume
        'leak_volume': {'name': 'Leak Volume', 'high': 50, 'unit': 'mL'},  # قيمة تقديرية
        # 2.27 Leak Percentage
        'leak_percentage': {'name': 'Leak %', 'high': 20, 'unit': '%'},
        # 2.28 RSBI (موجود)

        # 3.2 Set Tidal Volume (في الإعدادات فقط)
        # 3.4 Set FiO2 (موجود)
        # 3.5 Set PEEP (موجود)
        # 3.6 Set Pressure Control
        'set_pc': {'name': 'Set Pressure Control', 'high': 30, 'unit': 'cmH2O'},
        # 3.7 Pressure Support
        'set_ps': {'name': 'Pressure Support', 'high': 20, 'unit': 'cmH2O'},

        # 4.1 Measured FiO2 (مثل fio2)
        # 4.2 O2 Supply Pressure
        'o2_pressure': {'name': 'O2 Supply Pressure', 'low': 35, 'high': 70, 'critical': 35, 'unit': 'psi'},
        # 4.3 Air Supply Pressure
        'air_pressure': {'name': 'Air Supply Pressure', 'low': 35, 'high': 70, 'unit': 'psi'},
        # 4.4 Total Gas Flow
        'total_gas_flow': {'name': 'Total Gas Flow', 'low': 20, 'high': 120, 'unit': 'L/min'},
        # 4.5 Gas Temperature
        'gas_temperature': {'name': 'Gas Temperature', 'low': 32, 'high': 40, 'critical': 40, 'unit': '°C'},
        # 4.6 Inspired Gas Humidity
        'inspired_humidity': {'name': 'Inspired Humidity', 'low': 85, 'high': 100, 'unit': '%RH'},
        # 4.7 Expired Gas Humidity
        'expired_humidity': {'name': 'Expired Humidity', 'low': 85, 'unit': '%RH'},

        # 7.1 Mechanical Power (موجود)
        # 7.2 Elastic Work
        'elastic_work': {'name': 'Elastic Work', 'high': 1.0, 'unit': 'J/breath'},
        # 7.3 Resistive Work
        'resistive_work': {'name': 'Resistive Work', 'high': 0.8, 'unit': 'J/breath'},
        # 7.4 Inspiratory Muscle Pressure
        'insp_muscle_pressure': {'name': 'Inspiratory Muscle Pressure', 'low': -10, 'critical': -15, 'high': -1, 'unit': 'cmH2O'},  # قيم سالبة
        # 7.5 Time Constant
        'time_constant': {'name': 'Time Constant', 'low': 0.3, 'high': 1.0, 'critical': 1.5, 'unit': 'sec'},
        # 7.6 Dead Space Estimate
        'dead_space': {'name': 'Dead Space', 'high': 200, 'critical': 250, 'unit': 'mL'},
        # 7.7 Alveolar Ventilation
        'alveolar_vent': {'name': 'Alveolar Vent', 'low': 4, 'high': 10, 'unit': 'L/min'},
        # 7.8 Ventilatory Ratio
        'ventilatory_ratio': {'name': 'Ventilatory Ratio', 'high': 1.5, 'critical': 2.0, 'unit': ''},

        # 8.6 Battery Percentage
        'battery': {'name': 'Battery', 'low': 25, 'critical': 10, 'unit': '%'},
        # 8.7 Battery Remaining Time
        'battery_time': {'name': 'Battery Time', 'low': 30, 'critical': 10, 'unit': 'min'},
        # 8.8 Device Temperature
        'device_temp': {'name': 'Device Temp', 'high': 60, 'critical': 70, 'unit': '°C'},
        # 8.9 Turbine Speed (لا يوجد حد عام)
    }

    def apply_ai_settings(self, data):
        """
        تطبيق الإعدادات القادمة من نافذة AI Chat على المحاكاة.
        """
        # تحديث وضع التهوية إذا وُجد
        if 'mode' in data:
            mode_text = data['mode']
            if not mode_text.startswith("MODE:"):
                mode_text = f"MODE: {mode_text}"
            index = self.mode_box.findText(mode_text)
            if index >= 0:
                self.mode_box.setCurrentIndex(index)

        # تحديث جميع المعاملات الممكنة في current_params
        for key, value in data.items():
            if key in self.current_params:
                if isinstance(value, tuple):
                    self.current_params[key] = value
                elif isinstance(value, (int, float)):
                    self.current_params[key] = (value, value)
                # يمكن إضافة معالجة خاصة للمفاتيح النصية مثل ie_ratio

        # معالجة خاصة لـ ie_ratio إذا كان نصاً
        if 'ie_ratio' in data and isinstance(data['ie_ratio'], str):
            ie_text = data['ie_ratio']
            ie_value = None
            if ie_text == "1:1":
                ie_value = 1.0
            elif ie_text == "1:2":
                ie_value = 0.5
            elif ie_text == "1:3":
                ie_value = 0.333
            elif ie_text == "1:4":
                ie_value = 0.25
            elif ie_text == "2:1 (Inverse)":
                ie_value = 2.0
            if ie_value is not None:
                self.current_params['ie_ratio'] = (ie_value, ie_value)
                
        # معالجة peak_flow -> peak_insp_flow
        if 'peak_flow' in data and isinstance(data['peak_flow'], tuple):
            self.current_params['peak_insp_flow'] = data['peak_flow']

        # معالجة ipap, epap
        if 'ipap' in data and isinstance(data['ipap'], tuple):
            self.current_params['ipap'] = data['ipap']
        if 'epap' in data and isinstance(data['epap'], tuple):
            self.current_params['epap'] = data['epap']

        # تخزين الحالة السريرية
        clinical_fields = [
            'consciousness', 'synchrony', 'rr_wob', 'sedation',
            'hemodynamics', 'alarms_response', 'weaning', 'mask_seal'
        ]
        for field in clinical_fields:
            if field in data:
                self.patient_full_data[field] = data[field]

        # إضافة رسالة في سجل الإنذارات
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        new_log_html = f"<div style='color: #27ae60; margin-bottom: 5px;'>• [{timestamp}] AI ASSISTANT: New clinical settings applied</div>"
        current_html = self.alarm_content.toPlainText()
        self.alarm_content.setPlainText(new_log_html + current_html)

        print("\n=== AI Settings Applied ===")
        print(f"Mode: {data.get('mode')}")
        print(f"FiO2 range: {data.get('fio2')}")
        print(f"PEEP range: {data.get('peep')}")
        print(f"VT range: {data.get('vt')}")
        print(f"RR range: {data.get('rr')}")
        print("============================\n")
    
    def __init__(self):
        super().__init__()
        ResponsiveMixin.__init__(self)
        self.alarm_flags = {}
        self.patient_full_data = {}
        self.auto_adjust_panel = AutoAdjustPanel()
        self.auto_adjust_panel.settings_applied.connect(self.apply_auto_settings)
        self.auto_adjust_panel.calculation_completed.connect(self.on_calculation_completed)
        # مؤقت لتحديث Auto-Adjust Panel كل 60 ثانية
        self.auto_update_timer = QTimer()
        self.auto_update_timer.timeout.connect(self.trigger_auto_adjust)
        self.auto_update_timer.start(60000)  # 60000 مللي ثانية = 60 ثانية
        self.trend_window = None
        self.trend_timer = QTimer()
        self.trend_timer.timeout.connect(self.update_trends)
        self.trend_timer.start(2000)  # كل ثانيتين
        self.data_source = 'simulation'  # 'simulation' أو 'real'
        self.reader = None
        self.reader_thread = None
        self.acc_volume_previous = 0
        self.acc_volume_threshold = 500  # عتبة التغير التراكمي (مل)
        self.waveform_alerts = {}  # لتخزين إعدادات التحذيرات
        # 1. حل مشكلة الأرقام (١٢٣ -> 123)
        # نضبط البرنامج ليستخدم التنسيق الإنجليزي بغض النظر عن لغة جهازك
        self.setStyleSheet("background-color: #111418;")
        self.setWindowTitle("SERVO-i | Advanced Clinical Simulation")
        self.showFullScreen()
        self.recording_active = False          # هل التسجيل قيد التشغيل؟
        self.recording_file = None              # كائن ملف CSV مفتوح
        self.recording_writer = None            # كاتب CSV
        self.recording_start_time = None        # وقت بدء الجلسة (للطابع الزمني)
        self.recording_timer = QTimer()         # مؤقت لكتابة البيانات بشكل دوري
        self.recording_timer.timeout.connect(self.write_recording_data)

        # 2. حل مشكلة البياض (تعريف واحد فقط وتلوينه)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.central_widget.setStyleSheet("background-color: #111418;")
        

        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.setSpacing(15)

        # 3. إعداد المحركات (التايمرات والبيانات)
        self.sim_timer = QTimer()
        self.sim_timer.timeout.connect(self.update_live_metrics)
        self.current_params = {
            # الأساسية
            'rr': (12, 14), 'vte': (450, 480), 'peep': (5, 5),
            'fio2': (35, 45), 'pip': (20, 25), 'spo2': (96, 99), 'mvent': (6, 8),
            'plateau_pressure': (22, 28),
            
            # جديدة من 2
            'mean_airway_pressure': (8, 15),
            'auto_peep': (0, 3),
            'mandatory_rr': (12, 14),      # نفس rr غالباً
            'spontaneous_rr': (0, 5),
            'insp_time': (0.8, 1.2),
            'exp_time': (1.5, 2.5),
            'ie_ratio': (0.3, 0.5),        # نسبة I:E كرقم (I/E)
            'peak_insp_flow': (30, 80),
            'peak_exp_flow': (20, 60),
            'mean_insp_flow': (20, 50),
            'static_compliance': (40, 60),
            'dynamic_compliance': (40, 60),
            'airway_resistance': (10, 15),
            'work_of_breathing': (0.2, 0.8),
            'stress_index': (0.9, 1.1),
            'patient_effort_index': (3, 8),
            'asynchrony_index': (0, 5),
            'trigger_delay_time': (50, 120),
            'leak_volume': (0, 20),
            'leak_percentage': (0, 5),
            
            'insp_time': (0.8, 1.2),
            'exp_time': (1.5, 2.5),
            'esophageal_pressure': (-5, 10),

            # إعدادات
            'set_pc': (10, 25),
            'set_ps': (5, 15),
            
            'peak_exp_flow': (20, 70),        # أضف
            'mean_insp_flow': (20, 60),       # أضف
            'chest_wall_compliance': (40, 80),# أضف
            'stiffness_index': (1.5, 3.0),    # أضف
            'turbine_speed': (1000, 6000),    # أضف
            
            # غاز
            'o2_pressure': (40, 60),
            'air_pressure': (40, 60),
            'total_gas_flow': (30, 100),
            'gas_temperature': (34, 37),
            'inspired_humidity': (95, 100),
            'expired_humidity': (90, 100),
            
            # متقدمة
            'mechanical_power': (10, 17),
            'elastic_work': (0.2, 0.6),
            'resistive_work': (0.1, 0.4),
            'insp_muscle_pressure': (-8, -3),
            'time_constant': (0.3, 0.8),
            'dead_space': (120, 180),
            'alveolar_vent': (4, 8),
            'ventilatory_ratio': (0.8, 1.2),
            
            # جهاز
            'battery': (30, 100),
            'battery_time': (30, 120),
            'device_temp': (30, 50),
            'turbine_speed': (1000, 5000),   # RPM
            'calibration_status': (1, 1),     # 1=Pass, 0=Fail
            'uptime': (10, 500),              # ساعات
        }    
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)
        self.alarms_engine = AlarmsEngine()
        self.monitor = AlarmMonitor(self.alarms_engine, confirmation_count=3)
        self.trend_buffer = TrendBuffer(maxlen=60) 

        # داخل __init__ بعد self.alarms_engine = AlarmsEngine() ...
        self.trend_buffer = TrendBuffer(maxlen=60)
        self.trend_dict = {
        'pip': [], 'peep': [], 'vte': [], 'rr': [], 
        'compliance': [], 'driving': [], 'fio2': [], 'leak': []
        }
        self.trend_max_size = 60
        self.trend_alerts_triggered = {}

        # 4. بناء الواجهة (استدعاء كل دوال Setup أولاً)
        self.content_layout = QHBoxLayout()
        self.setup_header()          # ينشئ btn_sim, btn_home, search_bar
        self.setup_left_panel()      # ينشئ القوائم الجانبية
        self.setup_center_view()     # ينشئ عرض الرئة
        self.setup_right_controls()  # ينشئ التنبيهات
        
        
        self.trend_max_size = 60  # عدد القراءات المحفوظة
        self.trend_alerts_triggered = {}  # لتجنب تكرار الإنذارات
        self.btn_ai.clicked.connect(self.open_ai_chat)


        self.content_layout.setSpacing(15)
        self.main_layout.addLayout(self.content_layout, stretch=5)
        
        self.setup_bottom_graphs()# ينشئ الرسوم البيانية

        # 5. الربط (Signals & Slots) - نضعها هنا في النهاية لضمان وجود الأزرار
        self.btn_home.clicked.connect(self.home_requested.emit)
        self.btn_sim.clicked.connect(self.toggle_simulation)
        self.search_bar.textChanged.connect(self.search_dashboard)

    def log_message(self, msg, error=False):
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = "#ff0000" if error else "#f39c12"
        
        cursor = self.alarm_content.textCursor()
        cursor.movePosition(cursor.End)
        
        # إدراج فاصل أسطر HTML قبل الرسالة لضمان سطر جديد
        cursor.insertHtml("<br>")
        
        # إدراج الرسالة بتنسيق HTML (بدون هوامش إضافية)
        html = f"<span style='color:{color};'>• [{timestamp}] {msg}</span>"
        cursor.insertHtml(html)
        
        self.alarm_content.ensureCursorVisible()
                # تسجيل التنبيه في ملف CSV إذا كان التسجيل نشطاً
        if self.recording_active and self.recording_writer:
            try:
                # جمع البيانات الحالية
                row = [QDateTime.currentDateTime().toString("hh:mm:ss")]
                for key in self.value_labels.keys():
                    try:
                        val = float(self.value_labels[key].text())
                    except:
                        val = 0.0
                    row.append(val)
                # إضافة رسالة التنبيه كعمود إضافي (اختياري)
                row.append(f"[{timestamp}] {msg}")
                self.recording_writer.writerow(row)
                self.recording_file.flush()
            except:
                pass


    def check_all_alarms(self, data):
        """
        فحص جميع المتغيرات في RULES بناءً على القيم الحالية في data.
        يتم إرسال إنذار عند تجاوز الحد (مع تجاهل التكرار).
        """
        for key, rule in self.RULES.items():
            if key not in data:
                continue
            value = data[key]
            if value is None:
                continue

            unit = rule.get('unit', '')

            # فحص HIGH
            if 'high' in rule:
                if value > rule['high']:
                    if not self.alarm_flags.get(f"{key}_high", False):
                        self.log_message(f"{rule['name']} HIGH: {value:.1f} {unit}", error=False)
                        self.alarm_flags[f"{key}_high"] = True
                else:
                    self.alarm_flags.pop(f"{key}_high", None)

            # فحص LOW
            if 'low' in rule:
                if value < rule['low']:
                    if not self.alarm_flags.get(f"{key}_low", False):
                        self.log_message(f"{rule['name']} LOW: {value:.1f} {unit}", error=False)
                        self.alarm_flags[f"{key}_low"] = True
                else:
                    self.alarm_flags.pop(f"{key}_low", None)

            # فحص CRITICAL HIGH
            if 'critical' in rule:
                if value > rule['critical']:
                    if not self.alarm_flags.get(f"{key}_critical", False):
                        self.log_message(f"{rule['name']} CRITICAL: {value:.1f} {unit}", error=True)
                        self.alarm_flags[f"{key}_critical"] = True
                else:
                    self.alarm_flags.pop(f"{key}_critical", None)

            # يمكن إضافة CRITICAL LOW إذا وجد في RULES (لم نضعها حالياً)
            
    def set_waveform_alerts(self, alerts_dict):
        self.waveform_alerts = alerts_dict

    def check_accumulated_volume(self, current_vol):
        """فحص التغير التراكمي في الحجم وإصدار إنذار إذا تجاوز العتبة"""
        if not hasattr(self, 'acc_volume_previous'):
            self.acc_volume_previous = 0
        diff = abs(current_vol - self.acc_volume_previous)
        if diff > self.acc_volume_threshold:
            self.log_message(f"ACCUMULATED VOLUME MISMATCH: Δ{diff:.0f} mL > threshold", error=True)
        self.acc_volume_previous = current_vol

    def open_ai_chat(self):
        dialog = AIChatDialog(self)
        dialog.exec_()

    def on_ai_data_received(self, data):
        # يمكن استخدام هذه البيانات لاحقاً (مثلاً عرضها في مكان ما)
        print("AI Data received:", data)
        # أو تحديث واجهة المستخدم بناءً عليها

    def trigger_auto_adjust(self):
        """استدعاء calculate_recommendations في لوحة Auto-Adjust إذا كانت مفتوحة"""
        if hasattr(self, 'auto_adjust_panel') and self.auto_adjust_panel.isVisible():
            self.auto_adjust_panel.calculate_recommendations()
            
    def analyze_trends(self):
        """فحص القيم المخزنة في trend_dict وإصدار إنذارات إذا لزم الأمر"""
        for param, values in self.trend_dict.items():
            if len(values) < self.trend_max_size:
                continue  # ليس لدينا بيانات كافية بعد
            
            # حساب المتوسط خلال آخر 10 قيم
            recent = values[-10:]
            avg_recent = sum(recent) / len(recent)
            
            # الحصول على القاعدة من RULES
            rule = self.RULES.get(param)
            if not rule:
                continue
            
            # فحص استمرار تجاوز الحد
            if 'high' in rule and avg_recent > rule['high']:
                if not self.trend_alerts_triggered.get(f"{param}_high", False):
                    self.log_message(f"TREND ALERT: {rule['name']} sustained high ({avg_recent:.1f} {rule['unit']})", error=True)
                    self.trend_alerts_triggered[f"{param}_high"] = True
            elif 'low' in rule and avg_recent < rule['low']:
                if not self.trend_alerts_triggered.get(f"{param}_low", False):
                    self.log_message(f"TREND ALERT: {rule['name']} sustained low ({avg_recent:.1f} {rule['unit']})", error=True)
                    self.trend_alerts_triggered[f"{param}_low"] = True
            else:
                # إعادة تعيين حالة الإنذار إذا عادت للطبيعي
                self.trend_alerts_triggered.pop(f"{param}_high", None)
                self.trend_alerts_triggered.pop(f"{param}_low", None)
        
        # فحص إضافي: انحراف عن الهدف بنسبة 15% (خاص بـ Vt)
        if 'vte' in self.trend_dict and len(self.trend_dict['vte']) >= self.trend_max_size:
            baseline = sum(self.trend_dict['vte'][:10]) / 10  # أول 10 قيم كمرجع
            recent_vt = sum(self.trend_dict['vte'][-10:]) / 10
            if baseline > 0:
                deviation = abs(recent_vt - baseline) / baseline * 100
                if deviation > 15:
                    if not self.trend_alerts_triggered.get('vte_deviation', False):
                        self.log_message(f"TREND ALERT: Tidal Volume deviation >15% from baseline ({deviation:.1f}%)", error=True)
                        self.trend_alerts_triggered['vte_deviation'] = True
                else:
                    self.trend_alerts_triggered.pop('vte_deviation', None)
                    
    def update_trends(self):
        """جمع البيانات الحالية وإرسالها لنافذة الاتجاهات"""
        if self.trend_window is None or not self.trend_window.isVisible():
            return
        data = {}
        # جمع القيم من value_labels
        for key in ['pip', 'peep', 'vte', 'rr']:
            if key in self.value_labels:
                try:
                    data[key] = float(self.value_labels[key].text())
                except:
                    data[key] = 0
        # compliance
        if 'static_compliance' in self.value_labels:
            try:
                data['compliance'] = float(self.value_labels['static_compliance'].text())
            except:
                data['compliance'] = 0
        # driving
        if 'driving_pressure' in self.value_labels:
            try:
                data['driving'] = float(self.value_labels['driving_pressure'].text())
            except:
                data['driving'] = 0
        self.trend_window.update_trends(data)

    def show_trends_window(self):
        if self.trend_window is None:
            self.trend_window = TrendsWindow(self)
        self.trend_window.show()
                    
    def on_new_ventilator_data(self, data):
        
        # تحديث value_labels
        for key, value in data.items():
            if key in self.value_labels:
                self.value_labels[key].setText(f"{value:.1f}")

        # حساب driving pressure
        if 'peep' in data and 'plateau_pressure' in data:
            driving = data['plateau_pressure'] - data['peep']
            if 'driving' in self.value_labels:
                self.value_labels['driving'].setText(f"{driving:.1f}")

        # تحديث الموجات
        if 'airway_pressure' in data:
            self.pressure_data = self.pressure_data[1:] + [data['airway_pressure']]
            self.curve_pressure.setData(self.pressure_data)
        if 'flow_insp' in data:
            self.flow_data = self.flow_data[1:] + [data['flow_insp']]
            self.curve_flow.setData(self.flow_data)
        if 'volume_wave' in data:
            self.volume_data = self.volume_data[1:] + [data['volume_wave']]
            self.curve_volume.setData(self.volume_data)
        # تحذيرات المنحنيات بناءً على الإعدادات
        if self.waveform_alerts.get('wave_overdistension', False):
            if data.get('pip', 0) > 35:  # يمكن تغيير الشرط حسب التعريف الطبي
                self.log_message("PATTERN ALERT: Overdistension detected", error=True)

        if self.waveform_alerts.get('wave_recruitment_failure', False):
            # مثال: انخفاض compliance أو عدم استجابة لـ PEEP
            if data.get('static_compliance', 100) < 40:
                self.log_message("PATTERN ALERT: Recruitment failure suspected", error=True)

        if self.waveform_alerts.get('wave_auto_peep_alert', False):
            if data.get('auto_peep', 0) > 5:
                self.log_message("PATTERN ALERT: Auto-PEEP detected", error=True)

        if self.waveform_alerts.get('wave_air_trapping', False):
            if data.get('peak_exp_flow', 100) < 20:  # انخفاض ذروة التدفق الزفيري
                self.log_message("PATTERN ALERT: Air trapping suspected", error=True)

        if self.waveform_alerts.get('wave_obstruction', False):
            if data.get('airway_resistance', 0) > 20:
                self.log_message("PATTERN ALERT: Airway obstruction suspected", error=True)

        if self.waveform_alerts.get('wave_volume_loss', False):
            if data.get('leak_percentage', 0) > 20:
                self.log_message("PATTERN ALERT: Volume loss / leak detected", error=True)

        if self.waveform_alerts.get('wave_hysteresis', False):
            # يمكن إضافة منطق معقد، ولكن مؤقتاً نستخدم قيمة افتراضية
            pass

        if self.waveform_alerts.get('wave_overdistension_loop', False):
            if data.get('pip', 0) > 35:
                self.log_message("LOOP ALERT: Overdistension on PV loop", error=True)

        if self.waveform_alerts.get('wave_recruitment_loss', False):
            if data.get('static_compliance', 0) < 40:
                self.log_message("LOOP ALERT: Recruitment loss suspected", error=True)

        if self.waveform_alerts.get('wave_obstruction_fv', False):
            if data.get('airway_resistance', 0) > 20:
                self.log_message("FV LOOP ALERT: Obstruction pattern", error=True)

        if self.waveform_alerts.get('wave_air_trapping_fv', False):
            if data.get('peak_exp_flow', 0) < 20:
                self.log_message("FV LOOP ALERT: Air trapping pattern", error=True)
        # فحص الإنذارات الأساسية
        for key, value in data.items():
            if key in self.RULES:
                self.check_alarms(key, value)

        # حساب جميع القيم المشتقة (مرة واحدة)
        self.calculate_derived_values(data)

        # فحص الإنذارات المتقدمة
        self.check_advanced_alarms(data)
        if 'wave_acc_volume' in self.value_labels:
            try:
                acc_vol = float(self.value_labels['wave_acc_volume'].text())
                self.check_accumulated_volume(acc_vol)
            except:
                pass

        if hasattr(self, 'auto_adjust_panel') and self.auto_adjust_panel.alarms_engine:
            for key in ['pip', 'vte', 'rr', 'mvent', 'fio2', 'static_compliance', 'airway_resistance', 'paco2', 'spo2']:
                if key in data:
                    self.auto_adjust_panel.alarms_engine.update_baseline(key, data[key])
                                
        # تحديث البطارية والأكسجين
        if 'battery' in data and hasattr(self, 'lbl_battery'):
            self.lbl_battery.setText(f"🔋 Battery: {data['battery']}%")
        if 'o2_pressure' in data and hasattr(self, 'lbl_o2'):
            self.lbl_o2.setText(f"💨 O2 Supply: {data['o2_pressure']} psi")
        current_data = {}
        for key, lbl in self.value_labels.items():
            try:
                current_data[key] = float(lbl.text())
            except:
                current_data[key] = 0.0
        self.check_all_alarms(data)

        self.values_updated.emit(current_data)
        self.process_alarms(data)

            
    def set_data_source(self, source):
        if source not in ['simulation', 'real']:
            return
        self.data_source = source

        # إيقاف المحاكاة القديمة إذا كانت تعمل
        if self.sim_timer.isActive():
            self.toggle_simulation()  # إيقاف المحاكاة

        if source == 'simulation':
            # إيقاف القارئ إذا كان موجودًا
            if self.reader:
                self.reader.disconnect()
                if self.reader_thread and self.reader_thread.isRunning():
                    self.reader_thread.quit()
                    self.reader_thread.wait()
                self.reader = None
                self.reader_thread = None
            # إعادة تعيين حالة الزر (تحديث النص والتمكين فقط)
            self.btn_sim.setEnabled(True)
            self.btn_sim.setText("▶ START SIMULATION")   # أو النص الذي تريده
            # إذا كانت المحاكاة متوقفة، تبقى متوقفة
            if self.sim_timer.isActive():
                self.sim_timer.stop()
                self.wave_timer.stop()

            self.lbl_mode.setText("MODE: SIMULATION")
            self.log_message("Data source set to SIMULATION")
        else:  # real
            # إنشاء قارئ جديد إذا لم يكن موجودًا
            if self.reader is None:
                self.reader = VentilatorDataReader(port="COM3", baudrate=38400, simulation_mode=False)
                self.reader.data_updated.connect(self.on_new_ventilator_data)
            if self.reader.connect():
                self.reader_thread = QThread()
                self.reader.moveToThread(self.reader_thread)
                self.reader_thread.started.connect(self.reader.run)
                self.reader_thread.start()
                self.lbl_mode.setText("MODE: REAL VENTILATOR")
                self.log_message("Data source set to REAL VENTILATOR")
            else:
                self.log_message("Failed to connect to ventilator, falling back to simulation", error=True)
                self.source_combo.setCurrentText('Simulation')
            
    def show_auto_adjust_panel(self):
        # نبدأ بنسخة من بيانات المريض الأساسية
        combined_data = self.patient_full_data.copy()

        # نضيف (أو نحدث) القيم من current_params، مع تحويل tuples إلى متوسط
        for key, value in self.current_params.items():
            if isinstance(value, tuple):
                # إذا كانت القيمة tuple نأخذ المتوسط
                val = (value[0] + value[1]) / 2.0
            else:
                val = value
            combined_data[key] = val  # هذا سيضيف أو يحدث المفتاح

        # --- إضافة الحقول المطلوبة للمحركات بأسماء موحدة ---
        if 'insp_time' in self.current_params:
            val = self.current_params['insp_time']
            combined_data['ti'] = (val[0] + val[1]) / 2.0 if isinstance(val, tuple) else val
        if 'peak_insp_flow' in self.current_params:
            val = self.current_params['peak_insp_flow']
            combined_data['peak_flow'] = (val[0] + val[1]) / 2.0 if isinstance(val, tuple) else val
        if 'flow_trigger' in self.current_params:
            val = self.current_params['flow_trigger']
            combined_data['flow_trigger'] = (val[0] + val[1]) / 2.0 if isinstance(val, tuple) else val
        if 'pressure_trigger' in self.current_params:
            val = self.current_params['pressure_trigger']
            combined_data['pressure_trigger'] = (val[0] + val[1]) / 2.0 if isinstance(val, tuple) else val
        if 'spontaneous_rr' in self.current_params:
            val = self.current_params['spontaneous_rr']
            combined_data['spontaneous_rr'] = (val[0] + val[1]) / 2.0 if isinstance(val, tuple) else val

        # تأكد من وجود الحقول المطلوبة للمحركات
        required_fields = {
            'target_vt': combined_data.get('vte'),
            'target_ve': combined_data.get('mvent'),
            'vte': combined_data.get('vte'),
            'mvent': combined_data.get('mvent'),
            'rr': combined_data.get('rr'),
            'pip': combined_data.get('pip'),
            'peep': combined_data.get('peep'),
            'ti': combined_data.get('ti'),
            'peak_flow': combined_data.get('peak_flow'),
            'flow_trigger': combined_data.get('flow_trigger'),
            'pressure_trigger': combined_data.get('pressure_trigger'),
            'spontaneous_rr': combined_data.get('spontaneous_rr', 0),
        }
        combined_data.update(required_fields)

        self.auto_adjust_panel.set_patient_data(combined_data)
        self.auto_adjust_panel.show()

        
    def apply_auto_settings(self, settings):
        """تطبيق الإعدادات من لوحة Auto-Adjust على الداشبورد"""
        # تحديث وضع التهوية
        if 'mode' in settings:
            mode_text = settings['mode']
            if not mode_text.startswith("MODE:"):
                mode_text = f"MODE: {mode_text}"
            index = self.mode_box.findText(mode_text)
            if index >= 0:
                self.mode_box.setCurrentIndex(index)
        
        # تحديث جميع المعاملات العددية التي ترد في settings
        for key, value in settings.items():
            if key in self.current_params:
                if isinstance(value, tuple):
                    self.current_params[key] = value
                elif isinstance(value, (int, float)):
                    self.current_params[key] = (float(value), float(value))
                # يمكن إضافة معالجة للنصوص إذا لزم الأمر
        
        # إضافة رسالة في سجل الإنذارات
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        new_log_html = f"<div style='color: #27ae60; margin-bottom: 5px;'>• [{timestamp}] AUTO-ADJUST: New clinical settings applied</div>"
        current_html = self.alarm_content.toPlainText()
        self.alarm_content.setPlainText(new_log_html + current_html)
        # تحديث الحالة السريرية
        self.patient_full_data['consciousness'] = settings.get('consciousness', 'Partially awake')
        self.patient_full_data['synchrony'] = settings.get('synchrony', 'Good')
        self.patient_full_data['rr_wob'] = settings.get('rr_wob', 'Within target range')
        self.patient_full_data['sedation'] = settings.get('sedation', 'Not needed')
        self.patient_full_data['hemodynamics'] = settings.get('hemodynamics', 'Stable')
        self.patient_full_data['alarms_response'] = settings.get('alarms_response', 'All alarms acknowledged and appropriate')
        self.patient_full_data['weaning'] = settings.get('weaning', 'Not ready')
        self.patient_full_data['mask_seal'] = settings.get('mask_seal', 'Not applicable')
        
        # (اختياري) تحديث consciousness في current_params إذا أردت
        # self.current_params['consciousness'] = (1, 1)
        
    def request_manual_input(self):
        # نرسل كل البيانات المخزنة لدينا (بما فيها الـ 8 بكسات والاسم والعمر..)
        self.manual_input_requested.emit(self.patient_full_data)

    def check_alarms(self, key, value):
        pass    

    def process_alarms(self, data):
        active = self.monitor.check_alarms(data)
        for alarm in active:
            color = "#ff0000" if "high" in alarm['name'] else "#f1c40f"  # أحمر للحرج، أصفر للتحذير
            self.log_message(f"ALARM: {alarm['name']} - current: {alarm['current_value']}, limit: {alarm['limit']}", error=(color=="#ff0000"))


    def check_advanced_alarms(self, data):
        # الإنذارات الحالية
        comp = data.get('static_compliance')
        if comp is not None:
            if comp < 40:
                self.log_message(f"LOW COMPLIANCE: Static Compliance = {comp:.1f} mL/cmH2O", error=True)
            elif comp > 80:
                self.log_message(f"HIGH COMPLIANCE: Static Compliance = {comp:.1f} mL/cmH2O", error=False)

        res = data.get('airway_resistance')
        if res is not None and res > 20:
            self.log_message(f"HIGH RESISTANCE: Airway Resistance = {res:.1f} cmH2O/L/s", error=True)

        driving = data.get('driving_pressure')
        if driving is not None:
            if driving > 20:
                self.log_message(f"CRITICAL DRIVING PRESSURE: {driving:.1f} cmH2O", error=True)
            elif driving > 15:
                self.log_message(f"HIGH DRIVING PRESSURE: {driving:.1f} cmH2O", error=False)

        # إنذارات جديدة
        ie = data.get('ie_ratio')
        if ie is not None and ie > 1.0:  # I:E > 1:1
            self.log_message(f"INVERSE I:E RATIO: {ie:.2f} (>1:1)", error=True)

        asy = data.get('asynchrony_index')
        if asy is not None and asy > 10:
            self.log_message(f"HIGH ASYNCHRONY: {asy:.1f}%", error=True)

        leak = data.get('leak_percentage')
        if leak is not None and leak > 20:
            self.log_message(f"HIGH LEAK: {leak:.1f}%", error=True)

        vr = data.get('ventilatory_ratio')
        if vr is not None and vr > 2.0:
            self.log_message(f"SEVERE VENTILATORY INEFFICIENCY: VR={vr:.2f}", error=True)
        elif vr is not None and vr > 1.5:
            self.log_message(f"ELEVATED VENTILATORY RATIO: {vr:.2f}", error=False)

        # يمكن إضافة المزيد...

    def calculate_derived_values(self, data):
        # Mechanical Power
        if 'pip' in data and 'peep' in data and 'rr' in data and 'vte' in data:
            mp = 0.098 * data['vte'] * data['rr'] * (data['pip'] - data['peep']) / 1000
            self.value_labels['mechanical_power'].setText(f"{mp:.1f}")
            data['mechanical_power'] = mp
            self.check_alarms('mechanical_power', mp)
        # Elastic Work
        if 'pip' in data and 'peep' in data and 'vte' in data:
            elastic_work = (data['pip'] - data['peep']) * data['vte'] / 1000
            self.value_labels['elastic_work'].setText(f"{elastic_work:.2f}")
            data['elastic_work'] = elastic_work
            self.check_alarms('elastic_work', elastic_work)
        # Time Constant
        if 'static_compliance' in data and 'airway_resistance' in data:
            time_const = data['static_compliance'] * data['airway_resistance'] / 1000
            self.value_labels['time_constant'].setText(f"{time_const:.2f}")
            data['time_constant'] = time_const
            self.check_alarms('time_constant', time_const)
        # Alveolar Ventilation
        if 'vte' in data and 'rr' in data:
            alveolar = max(0, (data['vte'] - 150) * data['rr'] / 1000)
            self.value_labels['alveolar_vent'].setText(f"{alveolar:.2f}")
            data['alveolar_vent'] = alveolar
            self.check_alarms('alveolar_vent', alveolar)
        # Resistive Work
        if 'airway_resistance' in data and 'vte' in data and 'rr' in data:
            resistive_work = data['airway_resistance'] * (data['vte'] / 1000) * (data['rr'] / 60) * 0.1
            self.value_labels['resistive_work'].setText(f"{resistive_work:.2f}")
            data['resistive_work'] = resistive_work
            self.check_alarms('resistive_work', resistive_work)
        # Inspiratory Muscle Pressure (محاكاة)
        if 'spontaneous_rr' in data and data['spontaneous_rr'] > 0:
            imp = -5 - random.uniform(0, 3)
            self.value_labels['insp_muscle_pressure'].setText(f"{imp:.1f}")
            data['insp_muscle_pressure'] = imp
            self.check_alarms('insp_muscle_pressure', imp)
        # Dead Space Estimate (محاكاة)
        dead_space = random.uniform(120, 200)
        self.value_labels['dead_space'].setText(f"{dead_space:.0f}")
        data['dead_space'] = dead_space
        self.check_alarms('dead_space', dead_space)
        # Ventilatory Ratio (محاكاة)
        vr = random.uniform(0.8, 1.5)
        self.value_labels['ventilatory_ratio'].setText(f"{vr:.2f}")
        data['ventilatory_ratio'] = vr
        self.check_alarms('ventilatory_ratio', vr)

    def on_calculation_completed(self, result):
        # result هو القاموس الذي يحتوي على 'warnings' و 'missing_fields'
        warnings = result.get('warnings', [])
        missing = result.get('missing_fields', {})
        msg = "Auto-Adjust calculation completed."
        if warnings:
            msg += f" Warnings: {len(warnings)}"
        if missing:
            msg += f" Missing fields: {len(missing)} engines."
        self.log_message(msg)
                
    def setup_header(self):
        header_card = QFrame()
        header_card.setFixedHeight(85) 
        header_card.setStyleSheet("background-color: #1c2025; border-radius: 12px; border: 1px solid #3e4451;")
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(20, 0, 20, 0)
        
        # الجزء الأيسر: معلومات المريض وشريط البحث
        patient_search_layout = QHBoxLayout()
        self.patient_info = QLabel("PATIENT: NOT SELECTED | ID: ----")
        self.patient_info.setStyleSheet("color: #3498db; font-weight: bold; font-size: 13px; border: none;")         
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Search parameters, limits, alarms...")
        self.search_bar.setFixedWidth(280) 
        self.search_bar.setStyleSheet("""
            QLineEdit {
                background: #111418; color: white; border: 1px solid #3e4451; 
                border-radius: 8px; padding: 8px; font-size: 12px;
            }
            QLineEdit:focus { border: 1px solid #f1c40f; }
        """)
        
        patient_search_layout.addWidget(self.patient_info)
        patient_search_layout.addSpacing(15)
        patient_search_layout.addWidget(self.search_bar)
        
        header_layout.addLayout(patient_search_layout, 0)  # لا يتمدد

        # الزر الأخضر الطويل (يأخذ المساحة المتبقية)
        self.btn_sim = QPushButton("▶ START SIMULATION")
        self.btn_sim.setMinimumWidth(400)
        self.btn_sim.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_sim.setStyleSheet("""
            QPushButton {
                background-color: #27ae60; color: white; border-radius: 10px; 
                font-weight: bold; font-size: 16px; padding: 15px;
            }
            QPushButton:hover { background-color: #2ecc71; }
        """)
        header_layout.addWidget(self.btn_sim, 1)  # يأخذ المساحة الإضافية

        # الجزء الأيمن: خيارات وأزرار وساعة
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(8)  # مسافة صغيرة بين العناصر

        self.source_combo = QComboBox()
        self.source_combo.addItems(["Simulation", "Real Ventilator"])
        self.source_combo.currentTextChanged.connect(self.on_source_changed)
        self.source_combo.setStyleSheet("""
            QComboBox {
                background-color: #2c313c;
                color: white;
                border: 1px solid #3e4451;
                border-radius: 5px;
                padding: 5px 10px;
                font-size: 18px;
                font-weight: bold;
                min-width: 150px;
            }
            QComboBox:hover {
                border: 1px solid #3498db;
                color: white;
                min-height: 50px;


            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
                color: white;
                min-height: 50px;


            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid white;
                margin-right: 10px;
                color: white;   
            }
        """)
        nav_layout.addWidget(self.source_combo)

        self.lbl_mode = QLabel("MODE: SIMULATION")
        self.lbl_mode.setStyleSheet("color: #4CAF50; font-weight: bold; font-size: 14px;margin-top: 22px;margin-bottom: 22px")  # لا هامش
        nav_layout.addWidget(self.lbl_mode)

        self.btn_home = QPushButton("🏠 Home")
        self.btn_settings = QPushButton("⚙ Settings")
        
        for btn in [self.btn_home, self.btn_settings]:
            btn.setStyleSheet(BUTTON_STYLE)
            nav_layout.addWidget(btn)

        self.lbl_clock = QLabel()
        self.lbl_clock.setStyleSheet("color: #3498db; font-family: 'Consolas'; font-size: 13px; font-weight: bold; border: none;")
        self.update_clock()
        nav_layout.addWidget(self.lbl_clock)

        # إضافة nav_layout إلى header_layout بدون stretch (يبقى في أقصى اليمين)
        header_layout.addLayout(nav_layout, 0)

        self.main_layout.addWidget(header_card)
        
    def closeEvent(self, event):
        if hasattr(self, 'local_httpd'):
            self.local_httpd.shutdown()
            self.server_thread.join(timeout=1)
        if self.recording_active:
            self.stop_recording()
            if self.reader_thread and self.reader_thread.isRunning():
                self.reader_thread.quit()
                self.reader_thread.wait()
        # إيقاف المؤقتات
        self.sim_timer.stop()
        self.wave_timer.stop()
        self.clock_timer.stop()
        if hasattr(self, 'trend_timer'):
            self.trend_timer.stop()
        logging.shutdown()
        event.accept()
        
    def on_source_changed(self, text):
        if text == "Simulation":
            self.set_data_source('simulation')
            self.btn_sim.setEnabled(True)
            self.btn_sim.setText("▶ START SIMULATION")
        else:
            self.set_data_source('real')
            self.btn_sim.setEnabled(False)
            self.btn_sim.setText("REAL DATA ACTIVE")   # هذه الدالة ستبدأ القارئ
                

    def update_live_metrics(self):
        if self.data_source != 'simulation':
            return

        # التأكد من وجود القيم المتقدمة في current_params
        advanced_params = {
            'pip': (20, 45),
            'rr': (12, 35),
            'mechanical_power': (10, 28),
            'rsbi': (40, 120),
            'static_compliance': (40, 60),
            'airway_resistance': (10, 15),
            'mean_airway_pressure': (8, 20),
            'auto_peep': (0, 5),
            'mandatory_rr': (12, 30),
            'spontaneous_rr': (0, 15),
            'insp_time': (0.8, 1.5),
            'exp_time': (1.5, 3.0),
            'ie_ratio': (0.3, 0.8),
            'peak_insp_flow': (30, 100),
            'peak_exp_flow': (20, 70),
            'mean_insp_flow': (20, 60),
            'dynamic_compliance': (40, 80),
            'work_of_breathing': (0.2, 1.0),
            'stress_index': (0.8, 1.2),
            'patient_effort_index': (2, 12),
            'asynchrony_index': (0, 15),
            'trigger_delay_time': (50, 200),
            'leak_volume': (0, 50),
            'leak_percentage': (0, 15),
            'set_pc': (10, 30),
            'set_ps': (5, 20),
            'o2_pressure': (35, 70),
            'air_pressure': (35, 70),
            'total_gas_flow': (20, 120),
            'gas_temperature': (32, 40),
            'inspired_humidity': (80, 100),
            'expired_humidity': (80, 100),
            'elastic_work': (0.1, 1.2),
            'resistive_work': (0.1, 0.8),
            'insp_muscle_pressure': (-15, 0),
            'time_constant': (0.2, 1.2),
            'dead_space': (100, 250),
            'alveolar_vent': (3, 12),
            'ventilatory_ratio': (0.7, 2.0),
            'battery': (10, 100),
            'battery_time': (5, 180),
            'device_temp': (30, 70),
            'turbine_speed': (1000, 6000),
            'calibration_status': (1, 1),
            'uptime': (0, 2000),
        }
        for k, v in advanced_params.items():
            if k not in self.current_params:
                self.current_params[k] = v

        data = {}
                # تحويل work_of_breathing من نص إلى رقم
        wob_text = self.current_params.get('work_of_breathing')
        if isinstance(wob_text, str):
            wob_map = {'Mild': 0.3, 'Moderate': 0.6, 'Severe': 1.0}
            self.current_params['work_of_breathing'] = (wob_map.get(wob_text, 0.5), wob_map.get(wob_text, 0.5))

        # تحديث القيم الأساسية من current_params
        for key, value in self.current_params.items():
            if isinstance(value, tuple) and key in self.value_labels:
                new_value = random.uniform(*value)
                self.value_labels[key].setText(f"{new_value:.1f}")
                data[key] = new_value
                self.check_alarms(key, new_value)  # لا تفعل شيئاً حالياً

        # حساب plateau أولاً
        if 'plateau_pressure' in self.current_params:
            plateau = random.uniform(*self.current_params['plateau_pressure'])
            self.value_labels['plateau_pressure'].setText(f"{plateau:.1f}")
            data['plateau_pressure'] = plateau

        # حساب driving pressure
        if 'peep' in data and 'plateau_pressure' in data:
            driving = data['plateau_pressure'] - data['peep']
            if 'driving_pressure' in self.value_labels:
                self.value_labels['driving_pressure'].setText(f"{driving:.1f}")
                data['driving_pressure'] = driving

        if 'pao2' in data and 'fio2' in data and data['fio2'] > 0:
            pf_ratio = data['pao2'] / (data['fio2'] / 100)
            data['pf_ratio'] = pf_ratio
            if 'pf_ratio' in self.value_labels:
                self.value_labels['pf_ratio'].setText(f"{pf_ratio:.1f}")

                # تحويل work_of_breathing النصي إلى رقم للإنذار
        wob_text = self.patient_full_data.get('work_of_breathing')
        if wob_text in ['Mild', 'Moderate', 'Severe']:
            wob_map = {'Mild': 0.3, 'Moderate': 0.6, 'Severe': 1.0}
            data['work_of_breathing'] = wob_map[wob_text]

        # حساب القيم المشتقة الأخرى وتحديث data
        self.calculate_derived_values(data)

        # إضافة البيانات إلى TrendBuffer
        self.trend_buffer.add('pip', data.get('pip', 0))
        self.trend_buffer.add('peep', data.get('peep', 0))
        self.trend_buffer.add('vte', data.get('vte', 0))
        self.trend_buffer.add('rr', data.get('rr', 0))
        self.trend_buffer.add('fio2', data.get('fio2', 0))
        if 'static_compliance' in data:
            self.trend_buffer.add('compliance', data['static_compliance'])

        # تحديث baseline في AlarmsEngine
        self.alarms_engine.update_baseline('pip', data.get('pip', 0))
        self.alarms_engine.update_baseline('peep', data.get('peep', 0))
        self.alarms_engine.update_baseline('vte', data.get('vte', 0))
        self.alarms_engine.update_baseline('rr', data.get('rr', 0))
        self.alarms_engine.update_baseline('fio2', data.get('fio2', 0))
        if 'static_compliance' in data:
            self.alarms_engine.update_baseline('static_compliance', data['static_compliance'])
        if 'airway_resistance' in data:
            self.alarms_engine.update_baseline('airway_resistance', data['airway_resistance'])
        if 'paco2' in data:
            self.alarms_engine.update_baseline('paco2', data['paco2'])
        if 'spo2' in data:
            self.alarms_engine.update_baseline('spo2', data['spo2'])

        # تحديث trend_dict للتوافق مع الدوال القديمة
        for key in ['pip', 'peep', 'vte', 'rr', 'fio2']:
            if key in data:
                self.trend_dict[key].append(data[key])
                if len(self.trend_dict[key]) > self.trend_max_size:
                    self.trend_dict[key].pop(0)

        if 'static_compliance' in data:
            self.trend_dict['compliance'].append(data['static_compliance'])
            if len(self.trend_dict['compliance']) > self.trend_max_size:
                self.trend_dict['compliance'].pop(0)

        if 'driving_pressure' in data:
            self.trend_dict['driving'].append(data['driving_pressure'])
            if len(self.trend_dict['driving']) > self.trend_max_size:
                self.trend_dict['driving'].pop(0)

        if 'leak_percentage' in data:
            self.trend_dict['leak'].append(data['leak_percentage'])
            if len(self.trend_dict['leak']) > self.trend_max_size:
                self.trend_dict['leak'].pop(0)

        # الآن فحص الإنذارات
        self.process_alarms(data)
        self.check_advanced_alarms(data)

        # تسجيل الدورة الحسابية
        log_entry = (f"Cycle: PIP={data.get('pip', 0):.1f}, PEEP={data.get('peep', 0):.1f}, "
                    f"Vt={data.get('vte', 0):.0f}, RR={data.get('rr', 0):.0f}, "
                    f"FiO2={data.get('fio2', 0):.0f}, Compliance={data.get('static_compliance', 0):.1f}")
        logging.info(log_entry)

                # إضافة جميع المتغيرات في RULES إلى trend_dict إذا كانت موجودة في data
        for key in self.RULES.keys():
            if key in data:
                self.trend_dict.setdefault(key, []).append(data[key])
                if len(self.trend_dict[key]) > self.trend_max_size:
                    self.trend_dict[key].pop(0)

        # تحليل الاتجاهات
        self.analyze_trends()
        self.values_updated.emit(data)
        

    def toggle_simulation(self):
        if self.data_source == 'simulation':
            if self.sim_timer.isActive():
                self.sim_timer.stop()
                self.wave_timer.stop()
                self.stop_recording()  # إيقاف التسجيل
                self.btn_sim.setText("▶ START/END STIMULATION AND RECORDING")
                self.btn_sim.setStyleSheet("""
                    QPushButton {
                        background-color: #27ae60; color: white; border-radius: 10px; 
                        font-weight: bold; font-size: 16px; padding: 15px;
                    }
                    QPushButton:hover { background-color: #2ecc71; }
                """)
            else:
                self.sim_timer.start(2000)
                self.wave_timer.start(50)
                self.start_recording()  # بدء التسجيل
                self.btn_sim.setText("⏸ PAUSE/STOP RECORDING")
                self.btn_sim.setStyleSheet("""
                    QPushButton {
                        background-color: #e74c3c; color: white; border-radius: 10px; 
                        font-weight: bold; font-size: 16px; padding: 15px;
                    }
                    QPushButton:hover { background-color: #c0392b; }
                """)
        else:  # real mode
            self.log_message("In real mode, data is streaming automatically.", error=False)
            # لا نقوم بأي شيء آخر
            
    def on_inspiratory_hold(self):
        """إجراء مناورة الإمساك الشهيقي"""
        if self.data_source != 'simulation':
            self.log_message("Inspiratory Hold not available in real mode", error=True)
            return

        # التحقق من شروط الأمان
        if self.current_params.get('pip', (0,0))[0] > 35:
            self.log_message("Cannot perform Inspiratory Hold: PIP too high", error=True)
            return

        self.log_message("Inspiratory Hold activated - measuring plateau pressure", error=False)

        # محاكاة إغلاق الصمام وإمساك لمدة 1 ثانية
        # في المحاكاة، نأخذ القيمة الحالية لـ plateau_pressure (إذا كانت موجودة)
        if 'plateau_pressure' in self.value_labels:
            try:
                current_plateau = float(self.value_labels['plateau_pressure'].text())
            except:
                current_plateau = None
        else:
            current_plateau = None

        # إذا لم تكن موجودة، نحسبها باستخدام Vt و Compliance و PEEP
        vt = self.current_params.get('vte', (450,450))[0]
        peep = self.current_params.get('peep', (5,5))[0]
        comp = self.current_params.get('static_compliance', (50,50))[0]
        plateau = (vt / comp) + peep if comp > 0 else 0

        # استخدام القيمة المحسوبة إذا لم تكن موجودة
        plateau = current_plateau if current_plateau is not None else plateau

        # تحديث القيمة في واجهة المستخدم
        if 'plateau_pressure' in self.value_labels:
            self.value_labels['plateau_pressure'].setText(f"{plateau:.1f}")

        # حساب compliance الجديد
        if 'vte' in self.value_labels and peep > 0:
            vt_val = float(self.value_labels['vte'].text())
            new_comp = vt_val / (plateau - peep) if (plateau - peep) > 0 else 0
            if 'static_compliance' in self.value_labels:
                self.value_labels['static_compliance'].setText(f"{new_comp:.1f}")

        self.log_message(f"Plateau Pressure = {plateau:.1f} cmH2O", error=False)

    def start_recording(self):
        if self.recording_active:
            return
        # إنشاء مجلد recordings إذا لم يكن موجوداً
        if not os.path.exists("recordings"):
            os.makedirs("recordings")

        # الحصول على اسم المريض والمعرّف من patient_full_data
        patient_name = self.patient_full_data.get('patient_name', 'Unknown')
        patient_id = self.patient_full_data.get('patient_id', 'NoID')
        
        # تنظيف الأسماء لإزالة الأحرف غير المسموح بها في أسماء الملفات
        import re
        safe_name = re.sub(r'[^\w\-_]', '_', patient_name)  # استبدال كل ما ليس حرف/رقم/شرطة بشرطة سفلية
        safe_id = re.sub(r'[^\w\-_]', '_', patient_id)
        
        # الحصول على الوقت الحالي بصيغة مناسبة
        now = QDateTime.currentDateTime()
        date_str = now.toString("yyyy-MM-dd")
        time_str = now.toString("hh-mm-ss")
        
        # بناء اسم الملف: الاسم_المعرف_التاريخ_الوقت.csv
        filename = f"recordings/{safe_name}_{safe_id}_{date_str}_{time_str}.csv"
        
        try:
            self.recording_file = open(filename, 'w', newline='', encoding='utf-8')
            self.recording_writer = csv.writer(self.recording_file)
            # كتابة رؤوس الأعمدة
            headers = ['timestamp'] + list(self.value_labels.keys())
            self.recording_writer.writerow(headers)
            self.recording_active = True
            self.recording_start_time = now
            self.log_message(f"Recording started: {filename}")
            # بدء مؤقت الكتابة (كل ثانية واحدة)
            self.recording_timer.start(1000)
        except Exception as e:
            self.log_message(f"Failed to start recording: {e}", error=True)

    def stop_recording(self):
        if not self.recording_active:
            return
        self.recording_timer.stop()
        if self.recording_file:
            self.recording_file.close()
            self.recording_file = None
            self.recording_writer = None
        self.recording_active = False
        self.log_message("Recording stopped.")

    def write_recording_data(self):
        if not self.recording_active or not self.recording_writer:
            return
        # جمع القيم الحالية من value_labels
        row = [QDateTime.currentDateTime().toString("hh:mm:ss")]
        for key in self.value_labels.keys():
            try:
                val = float(self.value_labels[key].text())
            except:
                val = 0.0
            row.append(val)
        self.recording_writer.writerow(row)
        self.recording_file.flush()  # تأكيد الكتابة الفورية
                    
    def on_expiratory_hold(self):
        """إجراء مناورة الإمساك الزفيري لقياس Auto-PEEP"""
        if self.data_source != 'simulation':
            self.log_message("Expiratory Hold not available in real mode", error=True)
            return

        self.log_message("Expiratory Hold activated - measuring auto-PEEP", error=False)

        # محاكاة auto-PEEP: عادة ما يكون أعلى من PEEP المحدد
        peep = self.current_params.get('peep', (5,5))[0]
        auto_peep = peep + random.uniform(0, 3)  # إضافة قيمة عشوائية

        # تحديث القيمة في واجهة المستخدم إذا كان هناك حقل
        if 'auto_peep' in self.value_labels:
            self.value_labels['auto_peep'].setText(f"{auto_peep:.1f}")

        self.log_message(f"Auto-PEEP ≈ {auto_peep:.1f} cmH2O", error=False)

    def on_recruitment_maneuver(self):
        """إجراء مناورة إعادة التوظيف (زيادة PEEP مؤقتاً)"""
        if self.data_source != 'simulation':
            self.log_message("Recruitment maneuver not available in real mode", error=True)
            return

        # التحقق من استقرار الدورة الدموية (محاكاة)
        hemodynamics = self.patient_full_data.get('hemodynamics', 'Stable')
        if hemodynamics in ['Hypotension', 'Unstable']:
            self.log_message("Cannot perform Recruitment Maneuver: hemodynamically unstable", error=True)
            return

        self.log_message("Recruitment Maneuver - increasing PEEP temporarily", error=False)

        # حفظ القيم القديمة
        old_peep = self.current_params.get('peep', (5,5))

        # تنفيذ المناورة: زيادة PEEP إلى 15-18
        self.current_params['peep'] = (15, 18)

        # محاكاة تحسن compliance
        if 'static_compliance' in self.current_params:
            old_comp = self.current_params['static_compliance']
            # زيادة بنسبة 10% تقريباً
            new_comp = (old_comp[0] * 1.1, old_comp[1] * 1.1)
            self.current_params['static_compliance'] = new_comp

        # بعد 30 ثانية نعيد القيم القديمة (يمكن تقليل الوقت للمحاكاة)
        QTimer.singleShot(30000, lambda: self._restore_peep(old_peep))

        self.log_message("PEEP increased to 15-18 cmH2O for 30 seconds", error=False)

    def _restore_peep(self, old_peep):
        self.current_params['peep'] = old_peep
        self.log_message("PEEP restored to original values", error=False)

    def on_o2_flush(self):
        """تشغيل فلوش أكسجين 100% لمدة محددة"""
        if self.data_source != 'simulation':
            self.log_message("O2 Flush not available in real mode", error=True)
            return

        # مدة الفلوش (بالمللي ثانية)
        flush_duration = 120000  # دقيقتان

        self.log_message("100% O2 Flush activated for 2 minutes", error=False)

        # حفظ قيمة FiO2 القديمة
        old_fio2 = self.current_params.get('fio2', (40,40))

        # ضبط FiO2 إلى 100%
        self.current_params['fio2'] = (100, 100)

        # بعد المدة المحددة، نعيد القيمة القديمة
        QTimer.singleShot(flush_duration, lambda: self._restore_fio2(old_fio2))

        self.log_message("FiO2 set to 100% for 2 minutes", error=False)

    def _restore_fio2(self, old_fio2):
        self.current_params['fio2'] = old_fio2
        self.log_message("FiO2 restored to original values", error=False)

    def _restore_triggers(self, old_flow, old_press):
        self.current_params['flow_trigger'] = (old_flow, old_flow)
        self.current_params['pressure_trigger'] = (old_press, old_press)
        self.log_message("Suction mode ended, triggers restored", error=False)

    def on_suction_mode(self):
        """تفعيل وضع الشفط (تعطيل الحساسية مؤقتاً)"""
        if self.data_source != 'simulation':
            self.log_message("Suction Mode not available in real mode", error=True)
            return

        self.log_message("Suction Mode - disabling triggers for 30 seconds", error=False)

        # حفظ إعدادات الحساسية القديمة (إذا كانت موجودة)
        old_flow = self.current_params.get('flow_trigger', (2,2))[0]
        old_press = self.current_params.get('pressure_trigger', (-2,-2))[0]

        # تعطيل الحساسية (جعلها غير حساسة)
        self.current_params['flow_trigger'] = (5, 5)  # أقصى قيمة
        self.current_params['pressure_trigger'] = (-5, -5)  # أقصى قيمة (أقل حساسية)

        # بعد 30 ثانية نعيد الإعدادات
        QTimer.singleShot(30000, lambda: self._restore_triggers(old_flow, old_press))

        self.log_message("Triggers disabled for 30 seconds (simulated)", error=False)

    def update_clock(self):
        now = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        self.lbl_clock.setText(now)

    def setup_left_panel(self):
        left_layout = QVBoxLayout()
        left_layout.setSpacing(12)

        self.value_labels = {}
        self.btn_manual = QPushButton("MANUAL INPUT")
        self.btn_vent = QPushButton("VENTILATOR INPUT")
        self.btn_manual.clicked.connect(self.request_manual_input)
        for btn in [self.btn_manual, self.btn_vent]:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #34495e; color: white; padding: 14px; 
                    border-radius: 12px; font-weight: bold; border: 1px solid #2c3e50;
                }
                QPushButton:hover { background-color: #3498db; }
            """)
            left_layout.addWidget(btn)

        monitor_card = QFrame()
        apply_card_style(monitor_card, color="#2ecc71")
        m_lay = QVBoxLayout(monitor_card)

        title = QLabel("REAL-TIME MONITOR")
        title.setStyleSheet("color: #2ecc71; font-weight: bold; border: none; font-size: 14px; margin-bottom: 5px;")
        m_lay.addWidget(title, alignment=Qt.AlignCenter)

        # جميع المعايير (15)
        metrics = [
            ("Respiratory Rate", "14", "b/min"),
            ("Tidal Volume", "480", "mL"),
            ("FiO2", "40", "%"),
            ("PEEP", "5", "cmH2O"),
            ("Ppeak (PIP)", "22", "cmH2O"),
            ("SpO2", "98", "%"),
            ("Minute Vent.", "6.7", "L/min"),
            ("Mech. Power", "12", "J/min"),
            ("RSBI", "45", "f/VT"),
            ("Plateau Pressure", "25", "cmH2O"),
            ("Driving Pressure", "10", "cmH2O"),
            ("Elastic Work", "0.0", "J/breath"),
            ("Resistive Work", "0.0", "J/breath"),
            ("Time Constant", "0.0", "sec"),
            ("Alveolar Vent", "0.0", "L/min"),
            ("Mean Airway Pressure", "10", "cmH2O"),
            ("Auto-PEEP", "0", "cmH2O"),
            ("Mandatory RR", "12", "b/min"),
            ("Spontaneous RR", "2", "b/min"),
            ("Inspiratory Time", "1.0", "sec"),
            ("Expiratory Time", "2.0", "sec"),
            ("I:E Ratio", "0.5", ""),
            ("Peak Insp Flow", "50", "L/min"),
            ("Peak Exp Flow", "30", "L/min"),
            ("Mean Insp Flow", "25", "L/min"),
            ("Static Compliance", "50", "mL/cmH2O"),
            ("Dynamic Compliance", "50", "mL/cmH2O"),
            ("Airway Resistance", "12", "cmH2O/L/s"),
            ("Work of Breathing", "0.5", "J/L"),
            ("Stress Index", "1.0", ""),
            ("Patient Effort", "5", "cmH2O"),
            ("Asynchrony Index", "2", "%"),
            ("Trigger Delay", "80", "ms"),
            ("Leak Volume", "5", "mL"),
            ("Leak %", "2", "%"),
            ("Set PC", "15", "cmH2O"),
            ("Set PS", "8", "cmH2O"),
            ("O2 Pressure", "50", "psi"),
            ("Air Pressure", "50", "psi"),
            ("Total Gas Flow", "60", "L/min"),
            ("Gas Temp", "36", "°C"),
            ("Inspired Humidity", "98", "%RH"),
            ("Expired Humidity", "95", "%RH"),
            ("Insp Muscle Pressure", "-5", "cmH2O"),
            ("Dead Space", "150", "mL"),
            ("Ventilatory Ratio", "1.0", ""),
            ("Battery", "80", "%"),
            ("Battery Time", "60", "min"),
            ("Device Temp", "40", "°C"),
            ("Turbine Speed", "3000", "RPM"),
            ("Calibration", "Pass", ""),
            ("Uptime", "100", "hrs"),
        ]

        keys = ['rr', 'vte', 'fio2', 'peep', 'pip', 'spo2', 'mvent', 'mechanical_power', 'rsbi', 'plateau_pressure', 'driving_pressure',
                'elastic_work', 'resistive_work', 'time_constant', 'alveolar_vent',
                'mean_airway_pressure', 'auto_peep', 'mandatory_rr', 'spontaneous_rr', 'insp_time', 'exp_time', 'ie_ratio',
                'peak_insp_flow', 'peak_exp_flow', 'mean_insp_flow', 'static_compliance', 'dynamic_compliance',
                'airway_resistance', 'work_of_breathing', 'stress_index', 'patient_effort_index', 'asynchrony_index',
                'trigger_delay_time', 'leak_volume', 'leak_percentage', 'set_pc', 'set_ps', 'o2_pressure', 'air_pressure',
                'total_gas_flow', 'gas_temperature', 'inspired_humidity', 'expired_humidity', 'insp_muscle_pressure',
                'dead_space', 'ventilatory_ratio', 'battery', 'battery_time', 'device_temp', 'turbine_speed',
                'calibration_status', 'uptime']


        # إنشاء جميع value_labels
        for i, (name, val, unit) in enumerate(metrics):
            v_lbl = QLabel(val)
            v_lbl.setStyleSheet("color: #2ecc71; font-size: 20px; font-weight: bold; border: none;")
            self.value_labels[keys[i]] = v_lbl

        # إضافة أول 7 معايير فقط إلى الواجهة
        for i in range(7):
            row = QHBoxLayout()
            n_lbl = QLabel(metrics[i][0])
            n_lbl.setStyleSheet("color: #aeb9c4; border: none; font-size: 12px;")
            v_lbl = self.value_labels[keys[i]]
            u_lbl = QLabel(metrics[i][2])
            u_lbl.setStyleSheet("color: #5d6d7e; border: none; font-size: 10px;")
            row.addWidget(n_lbl)
            row.addStretch()
            row.addWidget(v_lbl)
            row.addWidget(u_lbl)
            m_lay.addLayout(row)

        left_layout.addWidget(monitor_card)
        self.content_layout.addLayout(left_layout, 2)

    def setup_center_view(self):
        center_container = QVBoxLayout()
        self.mode_box = QComboBox()
        self.mode_box.addItems([
            "MODE: Volume Control Ventilation (VCV)",
            "MODE: Pressure Control Ventilation (PCV)",
            "MODE: Pressure Regulated Volume Control (PRVC)",
            "MODE: Synchronized Intermittent Mandatory Ventilation (SIMV)",
            "MODE: Pressure Support Ventilation (PSV)",
            "MODE: Continuous Positive Airway Pressure (CPAP)",
            "MODE: Adaptive Support Ventilation (ASV)",
            "MODE: Proportional Assist Ventilation (PAV)",
            "MODE: Neurally Adjusted Ventilatory Assist (NAVA)",
            "MODE: Non-Invasive Ventilation (NIV)"
        ])
        self.mode_box.setStyleSheet("background: #3498db; color: white; padding: 10px; border-radius: 8px; font-weight: bold;")
        center_container.addWidget(self.mode_box)

        view_card = QFrame()
        apply_card_style(view_card, color="#3498db")
        self.view_layout = QVBoxLayout(view_card)

        # زر تحميل الرئة (يظهر دائماً)
        self.lung_load_btn = QPushButton("🫁 Load 3D Lung")
        self.lung_load_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 14px;
                max-width: 200px;
                margin: 0 auto;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        self.lung_load_btn.clicked.connect(self.load_lung)
        self.view_layout.addWidget(self.lung_load_btn, alignment=Qt.AlignCenter)

        # تسمية حالة التحميل (مخفية)
        self.lung_loading_label = QLabel("⏳ Loading 3D lung model...")
        self.lung_loading_label.setAlignment(Qt.AlignCenter)
        self.lung_loading_label.setStyleSheet("color: #f39c12; font-size: 14px; padding: 20px;")
        self.lung_loading_label.hide()
        self.view_layout.addWidget(self.lung_loading_label)

        # عناصر الرئة (سيتم إنشاؤها لاحقاً عند الضغط على الزر)
        self.lung_3d = None
        self.lung_retry_btn = None
        self._lung_available = False
        self.lung_widget = self.lung_loading_label  # عنصر بديل للبحث

        center_container.addWidget(view_card)
        self.content_layout.addLayout(center_container, 5)

    def load_lung(self):
        if self.lung_3d is not None:
            self.retry_load_lung()
            return

        try:
            from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings
            from PyQt5.QtCore import QUrl
            import os
            import http.server
            import socketserver
            import threading

            models_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '3d_models')
            if not os.path.exists(models_dir):
                raise FileNotFoundError(f"مجلد {models_dir} غير موجود")

            # بدء خادم HTTP محلي في الخلفية
            self.local_server_port = 8000
            os.chdir(models_dir)
            handler = http.server.SimpleHTTPRequestHandler
            self.local_httpd = socketserver.TCPServer(("", self.local_server_port), handler)
            self.server_thread = threading.Thread(target=self.local_httpd.serve_forever)
            self.server_thread.daemon = True
            self.server_thread.start()

            url = QUrl(f"http://localhost:{self.local_server_port}/lung_viewer.html")

            self.lung_3d = QWebEngineView()
            # تمكين إعدادات WebEngine
            settings = self.lung_3d.settings()
            settings.setAttribute(QWebEngineSettings.WebGLEnabled, True)
            settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
            settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
            settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, True)
            settings.setAttribute(QWebEngineSettings.ErrorPageEnabled, True)
            settings.setAttribute(QWebEngineSettings.PluginsEnabled, True)
            settings.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)

            self.lung_3d.setMinimumHeight(400)
            self.lung_3d.setMaximumHeight(600)

            self.view_layout.insertWidget(2, self.lung_3d)
            self.lung_3d.hide()

            self.lung_retry_btn = QPushButton("⟳ Retry 3D")
            self.lung_retry_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border-radius: 5px;
                    padding: 8px;
                    font-weight: bold;
                    font-size: 12px;
                    max-width: 100px;
                    margin: 0 auto;
                }
                QPushButton:hover { background-color: #2980b9; }
            """)
            self.lung_retry_btn.clicked.connect(self.retry_load_lung)
            self.lung_retry_btn.hide()
            self.view_layout.insertWidget(3, self.lung_retry_btn, alignment=Qt.AlignCenter)

            self.lung_3d.loadFinished.connect(self.on_lung_loaded)
            self.lung_load_timer = QTimer(self)
            self.lung_load_timer.setSingleShot(True)
            self.lung_load_timer.timeout.connect(self.on_lung_load_timeout)

            self.lung_viewer = self.lung_3d
            self.lung_widget = self.lung_3d
            self._lung_available = True

            self.lung_load_btn.hide()
            self.lung_loading_label.show()

            self.lung_3d.setUrl(url)
            self.lung_load_timer.start(10000)

        except ImportError:
            self.lung_loading_label.setText("❌ PyQtWebEngine not installed.\nPlease install: pip install PyQtWebEngine")
            self.lung_loading_label.setStyleSheet("color: #e74c3c; font-size: 14px; padding: 20px;")
            self.lung_loading_label.show()
            self.lung_load_btn.hide()
        except Exception as e:
            self.lung_loading_label.setText(f"❌ Error: {str(e)}")
            self.lung_loading_label.setStyleSheet("color: #e74c3c; font-size: 14px; padding: 20px;")
            self.lung_loading_label.show()
            self.lung_load_btn.hide()

            
    def retry_load_lung(self):
        if self.lung_retry_btn:
            self.lung_retry_btn.hide()
        self.lung_loading_label.setText("⏳ Loading 3D lung model...")
        self.lung_loading_label.setStyleSheet("color: #f39c12; font-size: 14px; padding: 20px;")
        self.lung_loading_label.show()
        if self.lung_3d and hasattr(self, 'local_server_port'):
            url = QUrl(f"http://localhost:{self.local_server_port}/lung_viewer.html")
            self.lung_3d.setUrl(url)
            self.lung_load_timer.start(10000)

    def on_lung_loaded(self, ok):
        if self.lung_load_timer:
            self.lung_load_timer.stop()
        if ok:
            self.lung_loading_label.hide()
            if self.lung_retry_btn:
                self.lung_retry_btn.hide()
            if self.lung_3d:
                self.lung_3d.show()
        else:
            self.lung_loading_label.setText("❌ Failed to load 3D model.")
            self.lung_loading_label.setStyleSheet("color: #e74c3c; font-size: 14px; padding: 20px;")
            if self.lung_3d:
                self.lung_3d.hide()
            if self.lung_retry_btn:
                self.lung_retry_btn.show()

    def on_lung_load_timeout(self):
        if self.lung_loading_label.isVisible():
            self.lung_loading_label.setText("⚠️ 3D model loading timeout.")
            self.lung_loading_label.setStyleSheet("color: #e74c3c; font-size: 14px; padding: 20px;")
            if self.lung_3d:
                self.lung_3d.hide()
            if self.lung_retry_btn:
                self.lung_retry_btn.show()
        
    

    

    

    
        
    def setup_right_controls(self):
        right_layout = QVBoxLayout()
        right_layout.setSpacing(10)

        card = QFrame()
        apply_card_style(card)
        layout = QVBoxLayout(card)
        
        self.btn_ai = QPushButton("AI SEARCH &\nRECOMMENDATION")
        self.btn_ai.setStyleSheet("background: #9b59b6; color: white; padding: 22px; border-radius: 12px; font-weight: bold;")
        
        self.btn_auto = QPushButton("AUTO-ADJUST SYSTEM")
        self.btn_auto.setStyleSheet("background: #2c3e50; color: white; padding: 16px; border-radius: 12px; font-weight: bold;")
        self.btn_auto.clicked.connect(self.show_auto_adjust_panel)

        layout.addWidget(self.btn_ai)
        layout.addSpacing(10)
        layout.addWidget(self.btn_auto)
        layout.addSpacing(15)

        # صندوق التنبيهات
        self.alarm_box = QFrame()
        self.alarm_box.setMinimumHeight(350) 
        self.alarm_box.setStyleSheet("background: #111418; border: 2px solid #e74c3c; border-radius: 12px;")
        a_lay = QVBoxLayout(self.alarm_box)
        
        self.a_lbl = QLabel("⚠️ ALARM LOG & NOTIFICATIONS")
        self.a_lbl.setStyleSheet("color: #e74c3c; font-weight: bold; border: none; font-size: 13px; padding-bottom: 5px;")
        
        self.alarm_content = QTextEdit()
        self.alarm_content.setReadOnly(True)
        self.alarm_content.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # إخفاء شريط التمرير
        self.alarm_content.setStyleSheet("""
            QTextEdit {
                background-color: #111418;
                color: #5d6d7e;
                border: none;
                font-size: 13px;
            }
        """)
        self.alarm_content.setWordWrapMode(QTextOption.WordWrap)
        self.alarm_content.document().setMaximumBlockCount(5000)  # يحتفظ بآخر 5000 رسالة
        
        a_lay.addWidget(self.a_lbl)
        a_lay.addWidget(self.alarm_content)
        
        # مؤشرات البطارية والأكسجين
        dev_layout = QHBoxLayout()
        self.lbl_battery = QLabel("🔋 Battery: --%")
        self.lbl_battery.setStyleSheet("color: #aeb9c4; font-size: 12px;")
        self.lbl_o2 = QLabel("💨 O2 Supply: -- psi")
        self.lbl_o2.setStyleSheet("color: #aeb9c4; font-size: 12px;")
        dev_layout.addWidget(self.lbl_battery)
        dev_layout.addWidget(self.lbl_o2)
        layout.addLayout(dev_layout)

        layout.addWidget(self.alarm_box)
        right_layout.addWidget(card)
        self.content_layout.addLayout(right_layout, 2)

    # -------------------------------------------------------------
    # محرك البحث الذكي للداشبورد 🟢
    # -------------------------------------------------------------
    def search_dashboard(self, text):
        search_query = text.lower()
        
        # استخراج كل النصوص والأزرار الموجودة في الشاشة
        all_labels = self.findChildren(QLabel)
        all_buttons = self.findChildren(QPushButton)
        
        items_to_search = all_labels + all_buttons

        for item in items_to_search:
            # استثناء عناصر لا نريد تغيير شكلها (مثل الساعة، صورة الرئة، واسم المريض)
            if item in [self.lbl_clock, self.lung_widget, self.patient_info]:
                continue
                
            # حفظ التصميم الأصلي للعنصر حتى نتمكن من إرجاعه
            if not hasattr(item, 'original_style'):
                item.original_style = item.styleSheet()

            # جلب النص الموجود داخل العنصر
            item_text = item.text().lower()

            if search_query == "":
                # إذا مسح المستخدم البحث، أعد كل شيء لشكله الأصلي
                item.setStyleSheet(item.original_style)
            
            elif search_query in item_text:
                # إذا وجد تطابق، قم بتمييزه باللون الأصفر!
                item.setStyleSheet("""
                    background-color: #f1c40f; 
                    color: black; 
                    font-weight: bold; 
                    border-radius: 4px; 
                    padding: 2px;
                """)
            else:
                # إذا لم يطابق يعود لشكله الأصلي (أو يمكنك جعله باهتاً لو أردت)
                item.setStyleSheet(item.original_style)

   
    # -------------------------------------------------------------
    # تحديث بيانات المريض والصورة 📸
    # -------------------------------------------------------------
    def update_patient_data(self, data):
        try:
            if not data:
                return
            
            # توحيد أسماء الحقول القادمة من قاعدة البيانات
            if 'map_bp' in data and 'map' not in data:
                data['map'] = data['map_bp']
            if 'oxygen_saturation_admission' in data and 'spo2' not in data:
                data['spo2'] = data['oxygen_saturation_admission']
            if 'fio2_max' in data and 'fio2' not in data:
                data['fio2'] = data['fio2_max']
            
            self.patient_full_data = data
            name = data.get('patient_name', 'Unknown')
            p_id = data.get('patient_id', '----')
            self.patient_info.setText(f"PATIENT: {name} | ID: {p_id}")
            self.patient_info.setStyleSheet("color: #2ecc71; font-weight: bold; font-size: 13px; border: none;")

            # تحديث current_params بالبيانات المتاحة (القيم الرقمية فقط)
            for key in list(self.current_params.keys()):
                if key in data:
                    val = data[key]
                    if isinstance(val, (int, float)):
                        self.current_params[key] = (float(val), float(val))
                    elif isinstance(val, (tuple, list)) and len(val) == 2:
                        self.current_params[key] = (float(val[0]), float(val[1]))

            # تحديث عنوان المريض في الرئة ثلاثية الأبعاد إذا كان موجوداً
            if hasattr(self, 'lung_viewer') and hasattr(self.lung_viewer, 'setWindowTitle'):
                # يمكن إضافة اسم المريض في عنوان الرئة
                pass

            # إظهار رسالة في سجل الإنذارات
            self.log_message(f"Patient {name} (ID: {p_id}) loaded successfully")

        except Exception as e:
            print(f"Error updating patient data: {e}")

    def set_lung_model(self, model_url):
        """
        تغيير نموذج الرئة ثلاثي الأبعاد
        """
        if hasattr(self, 'lung_viewer') and hasattr(self.lung_viewer, 'setUrl'):
            from PyQt5.QtCore import QUrl
            self.lung_viewer.setUrl(QUrl(model_url))
            self.log_message(f"3D Lung model changed")
        else:
            self.log_message("3D view not available", error=True)            
    def setup_bottom_graphs(self):
        graph_layout = QHBoxLayout()
        graph_layout.setSpacing(15)

        # 1. تهيئة قوائم لحفظ البيانات (100 نقطة لكل رسمة)
        self.time_data = list(range(100))
        self.pressure_data = [0] * 100
        self.flow_data = [0] * 100
        self.volume_data = [0] * 100
        self.ptr = 0 # مؤشر الوقت

        # 2. إنشاء الرسوم البيانية الثلاثة بألوان مختلفة
        self.plot_pressure = self.create_plot("Pressure-Time (cmH2O)", "#f1c40f") # أصفر
        self.curve_pressure = self.plot_pressure.plot(pen=pg.mkPen('#f1c40f', width=2))
        
        self.plot_flow = self.create_plot("Flow-Time (L/min)", "#2ecc71") # أخضر
        self.curve_flow = self.plot_flow.plot(pen=pg.mkPen('#2ecc71', width=2))
        
        self.plot_volume = self.create_plot("Volume-Time (mL)", "#3498db") # أزرق
        self.curve_volume = self.plot_volume.plot(pen=pg.mkPen('#3498db', width=2))

        # إضافتها للشاشة
        graph_layout.addWidget(self.plot_pressure)
        graph_layout.addWidget(self.plot_flow)
        graph_layout.addWidget(self.plot_volume)

        self.main_layout.addLayout(graph_layout, stretch=3)

        # 3. إعداد تايمر سريع للرسم (50 ملي ثانية ليكون ناعماً جداً)
        self.wave_timer = QTimer()
        self.wave_timer.timeout.connect(self.update_waveforms)

    # دالة مساعدة لتصميم الرسوم البيانية لتناسب الـ Dark Theme
    def create_plot(self, title, color):
        plot = pg.PlotWidget()
        plot.setBackground('#1c2025') # نفس لون خلفية البطاقات
        plot.setTitle(title, color='#aeb9c4', size='11pt', bold=True)
        plot.showGrid(x=True, y=True, alpha=0.2)
        
        # إخفاء الأرقام من المحور السيني (لأنها تتحرك باستمرار)
        plot.getAxis('bottom').setStyle(showValues=False)
        plot.getAxis('left').setPen(color)
        plot.getAxis('bottom').setPen('#3e4451')
        return plot
    
    def update_waveforms(self):
        self.ptr += 1
        t = self.ptr * 0.1 
        
        # أخذ متوسط المدى (Min+Max)/2 للرسم البياني لتجنب التشويش البصري
        def get_avg(key, default):
            val = self.current_params.get(key, (default, default))
            if isinstance(val, tuple): return (val[0] + val[1]) / 2.0
            return default

        peep = get_avg('peep', 5)
        pip = get_avg('pip', 20)
        rr = get_avg('rr', 14)
        vte = get_avg('vte', 450)

        # التردد بناءً على معدل التنفس (RR)
        freq = rr / 60.0
        
        # 1. موجة الضغط: من PEEP إلى PIP (تنزل وتصعد)
        p_val = peep + (pip - peep) * max(0, math.sin(2 * math.pi * freq * t))
        
        # 2. موجة التدفق: شهيق (موجب) وزفير (سالب)
        f_val = 60 * math.cos(2 * math.pi * freq * t)
        
        # 3. موجة الحجم: من الصفر إلى VTe
        v_val = vte * max(0, math.sin(2 * math.pi * freq * t))

        # تحديث القوائم (نحذف أقدم قيمة من اليسار، ونضيف الجديدة من اليمين)
        self.pressure_data = self.pressure_data[1:] + [p_val]
        self.flow_data = self.flow_data[1:] + [f_val]
        self.volume_data = self.volume_data[1:] + [v_val]

        # إرسال البيانات الجديدة للرسم
        self.curve_pressure.setData(self.pressure_data)
        self.curve_flow.setData(self.flow_data)
        self.curve_volume.setData(self.volume_data)
    


# ... (احتفظ ببداية الكود كما هي حتى بداية كلاس VentilatorSettings) ...

class VentilatorSettings(QWidget):
    # إشارة نرسل فيها الإعدادات للداشبورد لما نضغط "Start"
    simulation_started = pyqtSignal(dict) 
     # إشارات للأزرار اليدوية
    inspiratory_hold_requested = pyqtSignal()
    expiratory_hold_requested = pyqtSignal()
    recruitment_maneuver_requested = pyqtSignal()
    o2_flush_requested = pyqtSignal()
    suction_mode_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: #111418; color: white; border: none;")
        self.inputs = {}
        self.setup_ui()

    def create_set_parameters_tab(self):
        tab = QWidget()
        grid = QGridLayout(tab)
        grid.setSpacing(15)

        parameters = [
            ("3.2 Set Tidal Volume (mL)", "set_vt", 200, 1000, 450),
            ("3.3 Set Respiratory Rate (bpm)", "set_rr", 5, 40, 14),
            ("3.4 Set FiO2 (%)", "set_fio2", 21, 100, 40),
            ("3.5 Set PEEP (cmH2O)", "set_peep", 0, 25, 5),
            ("3.6 Set Pressure Control (cmH2O)", "set_pc", 5, 40, 20),
            ("3.7 Pressure Support (cmH2O)", "set_ps", 0, 30, 10),
            ("3.8 Target Minute Ventilation (L/min)", "set_mv", 4, 15, 6),
            ("3.9 Set Inspiratory Time (sec)", "set_ti", 0.5, 3.0, 1.0, 10),
            ("3.10 Set I:E Ratio", "set_ie", 0.2, 2.0, 0.5, 10),
            ("3.11 Set Trigger Sensitivity - Flow (L/min)", "flow_trig", 1, 20, 2, 10),
            ("3.12 Set Trigger Sensitivity - Pressure (cmH2O)", "p_trig", 0.5, 5, 1, 10),
            ("3.13 Rise Time (% or sec)", "rise_time", 0, 100, 50),
            ("3.14 Cycling Criteria (%)", "cycling", 1, 100, 25),
            ("3.15 ASV Target (%)", "asv_tgt", 1, 100, 100),
            ("3.16.1 EPAP (cmH2O)", "epap", 4, 8, 5),
            ("3.16.2 IPAP (cmH2O)", "ipap", 8, 20, 10),
            ("3.17 Tube Compensation (%)", "tube_comp", 0, 100, 0),
            ("3.18 PAV+ Gain (%)", "pav_gain", 0, 100, 50),
        ]
        self.add_params_to_grid(grid, parameters)
        # إضافة 3.19 كنص منفصل
        row = len(parameters)
        self.add_param_row(grid, row, "3.19 Alarms Thresholds (Text)", "alarm_thresholds", 0, 1000, 0, scale=1, is_text=True)
        self.tabs.addTab(tab, "Set Parameters")

    def create_breath_by_breath_part1_tab(self):
        tab = QWidget()
        grid = QGridLayout(tab)
        grid.setSpacing(15)

        parameters = [
            ("2.1 Peak Inspiratory Pressure (PIP)", "pip", 5, 40, 20),
            ("2.2 Plateau Pressure", "plateau_pressure", 5, 35, 25),
            ("2.3 Mean Airway Pressure", "mean_airway_pressure", 0, 50, 10),
            ("2.4 PEEP (Measured)", "peep", 0, 25, 5),
            ("2.5 Auto-PEEP", "auto_peep", 0, 20, 0),
            ("2.6 Tidal Volume Inspired", "vti", 200, 1000, 450),
            ("2.7 Tidal Volume Expired", "vte", 200, 1000, 450),
            ("2.8 Minute Ventilation", "mvent", 4, 15, 6),
            ("2.9 Respiratory Rate", "rr", 5, 40, 14),
            ("2.10 Mandatory RR", "mandatory_rr", 0, 40, 12),
            ("2.11 Spontaneous RR", "spontaneous_rr", 0, 40, 0),
            ("2.12 Inspiratory Time (sec)", "insp_time", 0.5, 3.0, 1.0, 10),
            ("2.13 Expiratory Time (sec)", "exp_time", 0.5, 5.0, 2.0, 10),
            ("2.14 I:E Ratio", "ie_ratio", 0.2, 2.0, 0.5, 10),
        ]
        self.add_params_to_grid(grid, parameters)
        self.tabs.addTab(tab, "Breath‑by‑Breath (1/2)")

    def create_breath_by_breath_part2_tab(self):
        tab = QWidget()
        grid = QGridLayout(tab)
        grid.setSpacing(15)

        parameters = [
            ("2.15 Peak Inspiratory Flow (L/min)", "peak_insp_flow", 0, 200, 60),
            ("2.16 Peak Expiratory Flow (L/min)", "peak_exp_flow", 0, 200, 40),
            ("2.17 Static Compliance", "static_compliance", 10, 150, 50),
            ("2.18 Dynamic Compliance", "dynamic_compliance", 10, 150, 50),
            ("2.19 Airway Resistance", "airway_resistance", 5, 50, 12),
            ("2.20 Work of Breathing (J/L)", "work_of_breathing", 0, 5, 1, 100),
            ("2.21 Driving Pressure", "driving_pressure", 0, 30, 10),
            ("2.22 Stress Index", "stress_index", 50, 150, 100, 100),
            ("2.23 Patient Effort Index", "patient_effort_index", 0, 30, 5),
            ("2.24 Asynchrony Index (%)", "asynchrony_index", 0, 50, 5),
            ("2.25 Trigger Delay Time (ms)", "trigger_delay_time", 0, 500, 100),
            ("2.26 Leak Volume (mL)", "leak_volume", 0, 500, 10),
            ("2.27 Leak Percentage (%)", "leak_percentage", 0, 50, 5),
            ("2.28 RSBI (b/min/L)", "rsbi", 20, 200, 60),
        ]
        self.add_params_to_grid(grid, parameters)
        self.tabs.addTab(tab, "Breath‑by‑Breath (2/2)")

    def create_manual_functions_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)

        manual_group = QGroupBox("Manual Functions")
        manual_group.setStyleSheet("""
            QGroupBox {
                color: #f39c12;
                font-weight: bold;
                border: 1px solid #3e4451;
                border-radius: 8px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        manual_layout = QVBoxLayout(manual_group)

        btn_insp = QPushButton("Inspiratory Hold")
        btn_exp = QPushButton("Expiratory Hold")
        btn_rec = QPushButton("Recruitment Maneuver")
        btn_o2 = QPushButton("100% O2 Flush")
        btn_suc = QPushButton("Suction Mode")

        manual_btn_style = """
            QPushButton {
                background-color: #34495e;
                color: white;
                border: 1px solid #3e4451;
                border-radius: 5px;
                padding: 8px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #3498db;
            }
        """
        for btn in [btn_insp, btn_exp, btn_rec, btn_o2, btn_suc]:
            btn.setStyleSheet(manual_btn_style)
            btn.setCursor(Qt.PointingHandCursor)
            manual_layout.addWidget(btn)

        btn_insp.clicked.connect(self.inspiratory_hold_requested.emit)
        btn_exp.clicked.connect(self.expiratory_hold_requested.emit)
        btn_rec.clicked.connect(self.recruitment_maneuver_requested.emit)
        btn_o2.clicked.connect(self.o2_flush_requested.emit)
        btn_suc.clicked.connect(self.suction_mode_requested.emit)

        layout.addWidget(manual_group)
        layout.addStretch()
        self.tabs.addTab(tab, "Manual Functions")
    
    def create_trend_tab(self):
        tab = QWidget()
        grid = QGridLayout(tab)
        grid.setSpacing(15)

        parameters = [
            ("6.1 Trend PIP (cmH2O)", "trend_pip", 0, 100, 25),
            ("6.2 Trend PEEP (cmH2O)", "trend_peep", 0, 30, 8),
            ("6.3 Trend Tidal Volume (mL)", "trend_vt", 0, 2000, 500),
            ("6.4 Trend Minute Ventilation (L/min)", "trend_mv", 0, 30, 7),
            ("6.5 Trend Respiratory Rate (bpm)", "trend_rr", 0, 60, 16),
            ("6.6 Trend Compliance (mL/cmH2O)", "trend_compliance", 0, 200, 60),
            ("6.7 Trend Resistance (cmH2O/L/s)", "trend_resistance", 0, 50, 15),
            ("6.8 Trend FiO2 (%)", "trend_fio2", 0, 100, 40),
            ("6.9 Trend Mean Flow (L/min)", "trend_mean_flow", 0, 200, 40),
            ("6.10 Trend Leak (%)", "trend_leak", 0, 50, 5),
        ]
        self.add_params_to_grid(grid, parameters)
        self.tabs.addTab(tab, "Trend Data")
            
    def create_networking_tab(self):
        tab = QWidget()
        grid = QGridLayout(tab)
        grid.setSpacing(15)

        row = 0
        # 9.1 Timestamp
        lbl = QLabel("9.1 Timestamp (ISO 8601)")
        lbl.setStyleSheet("color: #aeb9c4;")
        self.timestamp = QLineEdit()
        self.timestamp.setPlaceholderText("2026-02-10T14:35:22")
        self.timestamp.setStyleSheet("background: #1E1E1E; color: white; border: 1px solid #444; border-radius: 4px; padding: 4px;")
        grid.addWidget(lbl, row, 0)
        grid.addWidget(self.timestamp, row, 1, 1, 4)
        self.inputs["timestamp"] = self.timestamp

        # 9.2 Packet Identifier
        row += 1
        self.add_param_row(grid, row, "9.2 Packet Identifier", "packet_id", 0, 1000000, 1, scale=1)

        # 9.3 Data Source
        row += 1
        lbl = QLabel("9.3 Data Source")
        lbl.setStyleSheet("color: #aeb9c4;")
        self.data_source = QComboBox()
        self.data_source.addItems(["Ventilator Internal Sensor", "External Monitor", "Laboratory System", "Manual Entry"])
        self.data_source.setStyleSheet("background: #1E1E1E; color: white; border: 1px solid #444; border-radius: 4px; padding: 4px;")
        grid.addWidget(lbl, row, 0)
        grid.addWidget(self.data_source, row, 1, 1, 4)
        self.inputs["data_source"] = self.data_source

        # 9.4 HL7 Message ID
        row += 1
        lbl = QLabel("9.4 HL7 Message ID")
        lbl.setStyleSheet("color: #aeb9c4;")
        self.hl7_id = QLineEdit()
        self.hl7_id.setPlaceholderText("e.g. MSG001")
        self.hl7_id.setStyleSheet("background: #1E1E1E; color: white; border: 1px solid #444; border-radius: 4px; padding: 4px;")
        grid.addWidget(lbl, row, 0)
        grid.addWidget(self.hl7_id, row, 1, 1, 4)
        self.inputs["hl7_id"] = self.hl7_id

        # 9.5 Data Sequence Number
        row += 1
        self.add_param_row(grid, row, "9.5 Data Sequence Number", "seq_num", 0, 1000000, 1, scale=1)

        # 9.6 Stream Frequency (Hz)
        row += 1
        self.add_param_row(grid, row, "9.6 Stream Frequency (Hz)", "stream_freq", 1, 1000, 50, scale=1)

        # 9.7 CRC
        row += 1
        lbl = QLabel("9.7 CRC (Hexadecimal)")
        lbl.setStyleSheet("color: #aeb9c4;")
        self.crc = QLineEdit()
        self.crc.setPlaceholderText("e.g. 0x1A2F")
        self.crc.setStyleSheet("background: #1E1E1E; color: white; border: 1px solid #444; border-radius: 4px; padding: 4px;")
        grid.addWidget(lbl, row, 0)
        grid.addWidget(self.crc, row, 1, 1, 4)
        self.inputs["crc"] = self.crc

        self.tabs.addTab(tab, "Networking")

    def create_waveform_tab(self):
        tab = QWidget()
        grid = QGridLayout(tab)
        grid.setSpacing(15)

        parameters = [
            ("1.1 Airway Pressure (cmH2O)", "wave_airway_pressure", 0, 100, 20),
            ("1.2 Flow (L/min)", "wave_flow", -150, 150, 60),
            ("1.3 Volume (mL)", "wave_volume", 0, 2000, 500),
            ("1.4 Accumulated Volume (mL)", "wave_acc_volume", 0, 10000, 0),
            ("1.5 Esophageal Pressure (cmH2O)", "wave_esophageal_pressure", -20, 50, 0),
            ("1.6 Transpulmonary Pressure (cmH2O)", "wave_transpulmonary_pressure", -10, 40, 10),
        ]
        self.add_params_to_grid(grid, parameters)

        row = len(parameters)
        lbl = QLabel("1.7 Pressure Time Curve Alerts")
        lbl.setStyleSheet("color: #aeb9c4; font-size: 13px;")
        grid.addWidget(lbl, row, 0)
        self.overdistension = QCheckBox("Overdistension")
        self.overdistension.setStyleSheet("color: white;")
        self.recruitment_failure = QCheckBox("Recruitment failure")
        self.auto_peep_alert = QCheckBox("Auto PEEP")
        grid.addWidget(self.overdistension, row, 1)
        grid.addWidget(self.recruitment_failure, row, 2)
        grid.addWidget(self.auto_peep_alert, row, 3)
        self.inputs["wave_overdistension"] = self.overdistension
        self.inputs["wave_recruitment_failure"] = self.recruitment_failure
        self.inputs["wave_auto_peep_alert"] = self.auto_peep_alert

        row += 1
        lbl = QLabel("1.8 Flow Time Curve Alerts")
        lbl.setStyleSheet("color: #aeb9c4; font-size: 13px;")
        grid.addWidget(lbl, row, 0)
        self.air_trapping = QCheckBox("Air trapping")
        self.obstruction = QCheckBox("Obstruction")
        grid.addWidget(self.air_trapping, row, 1)
        grid.addWidget(self.obstruction, row, 2)
        self.inputs["wave_air_trapping"] = self.air_trapping
        self.inputs["wave_obstruction"] = self.obstruction

        row += 1
        lbl = QLabel("1.9 Volume Time Curve Alerts")
        lbl.setStyleSheet("color: #aeb9c4; font-size: 13px;")
        grid.addWidget(lbl, row, 0)
        self.volume_loss = QCheckBox("Volume loss / leak")
        grid.addWidget(self.volume_loss, row, 1)
        self.inputs["wave_volume_loss"] = self.volume_loss

        row += 1
        lbl = QLabel("1.10 Pressure Volume Loop Alerts")
        lbl.setStyleSheet("color: #aeb9c4; font-size: 13px;")
        grid.addWidget(lbl, row, 0)
        self.hysteresis = QCheckBox("Hysteresis abnormality")
        self.overdistension_loop = QCheckBox("Overdistension")
        self.recruitment_loss = QCheckBox("Recruitment loss")
        grid.addWidget(self.hysteresis, row, 1)
        grid.addWidget(self.overdistension_loop, row, 2)
        grid.addWidget(self.recruitment_loss, row, 3)
        self.inputs["wave_hysteresis"] = self.hysteresis
        self.inputs["wave_overdistension_loop"] = self.overdistension_loop
        self.inputs["wave_recruitment_loss"] = self.recruitment_loss

        row += 1
        lbl = QLabel("1.11 Flow Volume Loop Alerts")
        lbl.setStyleSheet("color: #aeb9c4; font-size: 13px;")
        grid.addWidget(lbl, row, 0)
        self.obstruction_fv = QCheckBox("Obstruction")
        self.air_trapping_fv = QCheckBox("Air trapping")
        grid.addWidget(self.obstruction_fv, row, 1)
        grid.addWidget(self.air_trapping_fv, row, 2)
        self.inputs["wave_obstruction_fv"] = self.obstruction_fv
        self.inputs["wave_air_trapping_fv"] = self.air_trapping_fv

        self.tabs.addTab(tab, "Waveform Data")
            
    def create_advanced_analytics_tab(self):
        tab = QWidget()
        grid = QGridLayout(tab)
        grid.setSpacing(15)

        parameters = [
            ("7.1 Mechanical Power (J/min)", "mechanical_power", 0, 50, 12),
            ("7.2 Elastic Work (J/breath)", "elastic_work", 0, 5, 0.4, 100),
            ("7.3 Resistive Work (J/breath)", "resistive_work", 0, 5, 0.2, 100),
            ("7.4 Inspiratory Muscle Pressure (cmH2O)", "insp_muscle_pressure", -20, 0, -5, 10),
            ("7.5 Time Constant (sec)", "time_constant", 0, 3, 0.5, 100),
            ("7.6 Dead Space (mL)", "dead_space", 50, 500, 150),
            ("7.7 Alveolar Ventilation (L/min)", "alveolar_vent", 0, 20, 5),
            ("7.8 Ventilatory Ratio", "ventilatory_ratio", 0, 3, 1, 100),
            ("7.9 Esophageal Pressure (cmH2O)", "esophageal_pressure", -20, 20, 0, 10),
        ]
        self.add_params_to_grid(grid, parameters)
        self.tabs.addTab(tab, "Advanced Analytics")
        
    def create_alarm_outputs_tab(self):
        tab = QWidget()
        grid = QGridLayout(tab)
        grid.setSpacing(15)

        row = 0
        # 5.1 Alarm Type
        lbl = QLabel("5.1 Alarm Type")
        lbl.setStyleSheet("color: #aeb9c4;")
        self.alarm_type = QLineEdit()
        self.alarm_type.setPlaceholderText("e.g. High Airway Pressure, Apnea")
        self.alarm_type.setStyleSheet("background: #1E1E1E; color: white; border: 1px solid #444; border-radius: 4px; padding: 4px;")
        grid.addWidget(lbl, row, 0)
        grid.addWidget(self.alarm_type, row, 1, 1, 4)
        self.inputs["alarm_type"] = self.alarm_type

        # 5.2 Alarm Priority
        row += 1
        lbl = QLabel("5.2 Alarm Priority")
        lbl.setStyleSheet("color: #aeb9c4;")
        self.alarm_priority = QComboBox()
        self.alarm_priority.addItems(["High", "Medium", "Low"])
        self.alarm_priority.setStyleSheet("background: #1E1E1E; color: white; border: 1px solid #444; border-radius: 4px; padding: 4px;")
        grid.addWidget(lbl, row, 0)
        grid.addWidget(self.alarm_priority, row, 1, 1, 4)
        self.inputs["alarm_priority"] = self.alarm_priority

        # 5.3 Alarm Limit High
        row += 1
        self.add_param_row(grid, row, "5.3 Alarm Limit High", "alarm_high", 0, 1000, 40, scale=1)

        # 5.4 Alarm Limit Low
        row += 1
        self.add_param_row(grid, row, "5.4 Alarm Limit Low", "alarm_low", 0, 1000, 10, scale=1)

        # 5.5 Alarm Trigger Value
        row += 1
        self.add_param_row(grid, row, "5.5 Alarm Trigger Value", "alarm_trigger", 0, 1000, 0, scale=1)

        # 5.6 Alarm Timestamp
        row += 1
        lbl = QLabel("5.6 Alarm Timestamp (ISO 8601)")
        lbl.setStyleSheet("color: #aeb9c4;")
        self.alarm_timestamp = QLineEdit()
        self.alarm_timestamp.setPlaceholderText("2026-02-10T14:35:22Z")
        self.alarm_timestamp.setStyleSheet("background: #1E1E1E; color: white; border: 1px solid #444; border-radius: 4px; padding: 4px;")
        grid.addWidget(lbl, row, 0)
        grid.addWidget(self.alarm_timestamp, row, 1, 1, 4)
        self.inputs["alarm_timestamp"] = self.alarm_timestamp

        # 5.7 Alarm Duration
        row += 1
        self.add_param_row(grid, row, "5.7 Alarm Duration (sec)", "alarm_duration", 0, 300, 0, scale=1)

        # 5.8 Event Type
        row += 1
        lbl = QLabel("5.8 Event Type")
        lbl.setStyleSheet("color: #aeb9c4;")
        self.event_type = QLineEdit()
        self.event_type.setPlaceholderText("e.g. Apnea, Disconnection")
        self.event_type.setStyleSheet("background: #1E1E1E; color: white; border: 1px solid #444; border-radius: 4px; padding: 4px;")
        grid.addWidget(lbl, row, 0)
        grid.addWidget(self.event_type, row, 1, 1, 4)
        self.inputs["event_type"] = self.event_type

        # 5.9 Alarm Reset Flag
        row += 1
        lbl = QLabel("5.9 Alarm Reset Flag")
        lbl.setStyleSheet("color: #aeb9c4;")
        self.alarm_reset = QComboBox()
        self.alarm_reset.addItems(["False (Active)", "True (Acknowledged)"])
        self.alarm_reset.setStyleSheet("background: #1E1E1E; color: white; border: 1px solid #444; border-radius: 4px; padding: 4px;")
        grid.addWidget(lbl, row, 0)
        grid.addWidget(self.alarm_reset, row, 1, 1, 4)
        self.inputs["alarm_reset"] = self.alarm_reset

        self.tabs.addTab(tab, "Alarm Outputs")

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20) 
        main_layout.setSpacing(15)
        self.setAttribute(Qt.WA_StyledBackground, True)
        
        title = QLabel("⚙️ VENTILATOR SIMULATION PARAMETERS (WHAT IF SCENARIOS)")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #4CAF50;")
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #333; border-radius: 10px; background: #121212; }
            QTabBar::tab { background: #2c313c; color: white; padding: 10px 20px; border-radius: 5px; margin: 2px; }
            QTabBar::tab:selected { background: #3498db; font-weight: bold; }
        """)
        
        # إنشاء التبويبات (مرة واحدة فقط)
        self.create_mode_tab()                     # 3.1
        self.create_waveform_tab()                  # القسم 1
        self.create_breath_by_breath_part1_tab()    # القسم 2 (جزء 1)
        self.create_breath_by_breath_part2_tab()    # القسم 2 (جزء 2)
        self.create_set_parameters_tab()            # القسم 3
        self.create_gas_oxygen_tab()                # القسم 4
        self.create_alarm_outputs_tab()             # القسم 5
        self.create_trend_tab()                     # 6
        self.create_advanced_analytics_tab()        # القسم 7
        self.create_device_metadata_tab()           # القسم 8
        self.create_networking_tab()                # القسم 9
        self.create_manual_functions_tab()          # الأزرار اليدوية   # يحتوي على الأزرار اليدوية والمعايير المتقدمة

        main_layout.addWidget(self.tabs)

        self.btn_start = QPushButton("▶ START SIMULATION WITH THESE SETTINGS")
        self.btn_start.setFixedHeight(50)
        self.btn_start.setStyleSheet("""
            QPushButton {
                background-color: #1B5E20; color: white; 
                border-radius: 8px; font-weight: bold; font-size: 16px;
            }
            QPushButton:hover { background-color: #2E7D32; }
        """)
        self.btn_start.clicked.connect(self.start_simulation)
        main_layout.addWidget(self.btn_start)

    def create_breath_by_breath_tab(self):
        tab = QWidget()
        grid = QGridLayout(tab)
        grid.setSpacing(15)

        parameters = [
            ("2.3 Mean Airway Pressure (cmH2O)", "mean_airway_pressure", 0, 50, 10),
            ("2.5 Auto-PEEP (cmH2O)", "auto_peep", 0, 20, 0),
            ("2.10 Mandatory RR (bpm)", "mandatory_rr", 0, 60, 12),
            ("2.11 Spontaneous RR (bpm)", "spontaneous_rr", 0, 60, 0),
            ("2.12 Inspiratory Time (sec)", "insp_time", 0, 5, 1, 100),
            ("2.13 Expiratory Time (sec)", "exp_time", 0, 10, 2, 100),
            ("2.14 I:E Ratio (x100)", "ie_ratio", 10, 200, 50, 100),
            ("2.15 Peak Inspiratory Flow (L/min)", "peak_insp_flow", 0, 200, 60),
            ("2.16 Peak Expiratory Flow (L/min)", "peak_exp_flow", 0, 200, 40),
            ("2.xx Mean Inspiratory Flow (L/min)", "mean_insp_flow", 0, 150, 30),
            ("2.18 Dynamic Compliance (mL/cmH2O)", "dynamic_compliance", 10, 150, 50),
            ("2.20 Work of Breathing (J/L)", "work_of_breathing", 0, 5, 1, 100),
            ("2.22 Stress Index (x100)", "stress_index", 50, 150, 100, 100),
            ("2.23 Patient Effort Index (cmH2O)", "patient_effort_index", 0, 30, 5),
            ("2.24 Asynchrony Index (%)", "asynchrony_index", 0, 50, 5),
            ("2.25 Trigger Delay Time (ms)", "trigger_delay_time", 0, 500, 100),
            ("2.26 Leak Volume (mL)", "leak_volume", 0, 500, 10),
            ("2.27 Leak Percentage (%)", "leak_percentage", 0, 50, 5),
        ]

        self.add_params_to_grid(grid, parameters)
        self.tabs.addTab(tab, "Breath‑by‑Breath")

    def create_gas_oxygen_tab(self):
        tab = QWidget()
        grid = QGridLayout(tab)
        grid.setSpacing(15)

        parameters = [
            ("4.1 Measured FiO2 (%)", "measured_fio2", 21, 100, 40),
            ("4.2 O2 Supply Pressure (psi)", "o2_pressure", 0, 100, 50),
            ("4.3 Air Supply Pressure (psi)", "air_pressure", 0, 100, 50),
            ("4.4 Total Gas Flow (L/min)", "total_gas_flow", 0, 200, 60),
            ("4.5 Gas Temperature (°C)", "gas_temperature", 20, 50, 36),
            ("4.6 Inspired Gas Humidity (%RH)", "inspired_humidity", 0, 100, 98),
            ("4.7 Expired Gas Humidity (%RH)", "expired_humidity", 0, 100, 95),
        ]

        self.add_params_to_grid(grid, parameters)
        self.tabs.addTab(tab, "Gas & Oxygen")

    def create_device_metadata_tab(self):
        tab = QWidget()
        grid = QGridLayout(tab)
        grid.setSpacing(15)

        # أرقام
        parameters = [
            ("8.4 System Uptime (hours)", "uptime", 0, 10000, 100),
            ("8.7 Battery Remaining Time (min)", "battery_time", 0, 300, 60),
            ("8.8 Device Internal Temperature (°C)", "device_temp", 0, 100, 40),
            ("8.9 Turbine Speed (RPM)", "turbine_speed", 0, 10000, 3000),
        ]
        self.add_params_to_grid(grid, parameters)

        # نصوص
        row = len(parameters)
        text_params = [
            ("8.1 Device Serial Number", "serial"),
            ("8.2 Software Version", "software"),
            ("8.3 Firmware Version", "firmware"),
        ]
        for i, (label, key) in enumerate(text_params):
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #aeb9c4;")
            line_edit = QLineEdit()
            line_edit.setStyleSheet("background: #1E1E1E; color: white; border: 1px solid #444; border-radius: 4px; padding: 4px;")
            # تخزين line_edit في قاموس منفصل إذا أردت استخدامه
            grid.addWidget(lbl, row + i, 0)
            grid.addWidget(line_edit, row + i, 1, 1, 4)

        # قوائم منسدلة
        combo_params = [
            ("8.5 Power Source", "power_source", ["AC", "Battery"]),
            ("8.10 Calibration Status", "calibration", ["Fail", "Pass"]),
        ]
        for i, (label, key, items) in enumerate(combo_params):
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #aeb9c4;")
            combo = QComboBox()
            combo.addItems(items)
            combo.setStyleSheet("background: #1E1E1E; color: white; border: 1px solid #444; border-radius: 4px; padding: 4px;")
            grid.addWidget(lbl, row + len(text_params) + i, 0)
            grid.addWidget(combo, row + len(text_params) + i, 1, 1, 4)

        self.tabs.addTab(tab, "Device Metadata")
    # ---------------------------------------------------------
    # دوال إنشاء التبويبات وإضافة الحقول (بناءً على ملف PDF)
    # ---------------------------------------------------------
    
       

    def add_param_row(self, grid, row, label_text, key, min_allowed, max_allowed, def_val, scale=1, is_text=False):
        lbl = QLabel(label_text)
        lbl.setStyleSheet("color: #aeb9c4; font-size: 13px;")
        if is_text:
            widget = QLineEdit()
            widget.setStyleSheet("background: #1E1E1E; color: white; border: 1px solid #444; border-radius: 4px; padding: 4px;")
            self.inputs[key] = widget
            grid.addWidget(lbl, row, 0)
            grid.addWidget(widget, row, 1, 1, 4)
        else:
            spin_min = QDoubleSpinBox()
            spin_min.setRange(min_allowed, max_allowed)
            spin_min.setValue(def_val)
            spin_min.setDecimals(2)
            self.style_spinbox(spin_min)

            spin_max = QDoubleSpinBox()
            spin_max.setRange(min_allowed, max_allowed)
            spin_max.setValue(min(def_val + 5, max_allowed))
            spin_max.setDecimals(2)
            self.style_spinbox(spin_max)

            self.inputs[key] = (spin_min, spin_max, scale)
            grid.addWidget(lbl, row, 0)
            grid.addWidget(QLabel("Min:"), row, 1)
            grid.addWidget(spin_min, row, 2)
            grid.addWidget(QLabel("Max:"), row, 3)
            grid.addWidget(spin_max, row, 4)

    def create_mode_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setAlignment(Qt.AlignTop)
        
        # 1. Ventilation Mode Selection
        lbl = self.create_header_label("1.1 Ventilation Mode")
        self.mode_combo = QComboBox()
        modes = [
            "Volume Control Ventilation", "Pressure Control Ventilation", 
            "Pressure Regulated Volume Control", "Synchronized Intermittent Mandatory Ventilation",
            "Pressure Support Ventilation", "Continuous Positive Airway Pressure",
            "Adaptive Support Ventilation", "Proportional Assist Ventilation",
            "Neurally Adjusted Ventilatory Assist", "Non Invasive Ventilation"
        ]
        self.mode_combo.addItems(modes)
        self.mode_combo.setStyleSheet("background: #1E1E1E; padding: 10px; border-radius: 5px; font-size: 14px;")
        
        layout.addWidget(lbl)
        layout.addWidget(self.mode_combo)
        self.tabs.addTab(tab, "Mode Selection")

    

    

    

    def add_params_to_grid(self, grid, parameters):
        row = 0
        for param in parameters:
            if len(param) == 5:
                label_text, key, min_allowed, max_allowed, def_val = param
                scale = 1
            elif len(param) == 6:
                label_text, key, min_allowed, max_allowed, def_val, scale = param
            else:
                continue

            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #aeb9c4; font-size: 13px;")

            # استخدام QDoubleSpinBox للقيم العشرية
            spin_min = QDoubleSpinBox()
            spin_min.setRange(min_allowed, max_allowed)
            spin_min.setValue(def_val)
            spin_min.setDecimals(2)
            self.style_spinbox(spin_min)

            spin_max = QDoubleSpinBox()
            spin_max.setRange(min_allowed, max_allowed)
            spin_max.setValue(min(def_val + 5, max_allowed))
            spin_max.setDecimals(2)
            self.style_spinbox(spin_max)

            self.inputs[key] = (spin_min, spin_max, scale)

            grid.addWidget(lbl, row, 0)
            grid.addWidget(QLabel("Min:"), row, 1)
            grid.addWidget(spin_min, row, 2)
            grid.addWidget(QLabel("Max:"), row, 3)
            grid.addWidget(spin_max, row, 4)
            row += 1
            grid.setColumnStretch(0, 2)  # label
            grid.setColumnStretch(1, 0)  # "Min" label
            grid.setColumnStretch(2, 1)  # spin min
            grid.setColumnStretch(3, 0)  # "Max" label
            grid.setColumnStretch(4, 1)  # spin max
            grid.setColumnMinimumWidth(1, 30)
            grid.setColumnMinimumWidth(3, 30)

    def create_header_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #AAA;")
        return lbl

    def style_spinbox(self, spinbox):
        spinbox.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #252a33;
                color: #FFFFFF;
                border: 1px solid #3e4451;
                border-radius: 6px;
                padding: 5px 8px;
                font-size: 13px;
                selection-background-color: #3498db;
            }
            QDoubleSpinBox:hover {
                border: 1px solid #4a90e2;
                background-color: #2e3440;
            }
            QDoubleSpinBox:focus {
                border: 2px solid #3498db;
                background-color: #2e3440;
            }
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                subcontrol-origin: border;
                width: 20px;
                border: none;
                background-color: #2c313c;
                border-radius: 3px;
                margin: 2px;
            }
            QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
                background-color: #3e4451;
            }
            QDoubleSpinBox::up-arrow { image: url(none); }
            QDoubleSpinBox::down-arrow { image: url(none); }
        """)

    def start_simulation(self):
        settings = {}

        for key, value in self.inputs.items():
            if isinstance(value, tuple) and len(value) == 3:
                spin_min, spin_max, scale = value
                val_min = spin_min.value()
                val_max = spin_max.value()
                real_min = min(val_min, val_max) / scale
                real_max = max(val_min, val_max) / scale
                settings[key] = (real_min, real_max)
            elif isinstance(value, QComboBox):
                settings[key] = value.currentText()
            elif isinstance(value, QLineEdit):
                settings[key] = value.text()
            elif isinstance(value, tuple) and len(value) == 2:
                spin_min, spin_max = value
                val_min = spin_min.value()
                val_max = spin_max.value()
                real_min = min(val_min, val_max)
                real_max = max(val_min, val_max)
                settings[key] = (real_min, real_max)
            elif isinstance(value, QCheckBox):
                settings[key] = value.isChecked()
            else:
                settings[key] = value

        settings['selected_mode'] = self.mode_combo.currentText()
        self.simulation_started.emit(settings)

class AppManager(QStackedWidget):
    home_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.dash = SimulationDashboard()
        self.settings = VentilatorSettings()
        # self.manual = VentilatorManualInputs()  # <-- تم الحذف

        self.setStyleSheet("background-color: #111418;")

        # الصفحات: 0 = dash, 1 = settings
        self.addWidget(self.dash)
        self.addWidget(self.settings)
        # self.addWidget(self.manual)  # <-- تم الحذف

        # ربط الأزرار
        self.dash.btn_vent.clicked.connect(lambda: self.setCurrentIndex(1))   # يفتح صفحة الإعدادات
        self.dash.btn_settings.clicked.connect(lambda: None)                  # زر فاضي
        # self.dash.manual_input_requested.connect(self.show_manual)  # <-- تم الحذف (الربط المزدوج)
        # self.manual.back_requested.connect(lambda: self.setCurrentIndex(0))  # <-- تم الحذف
        self.settings.simulation_started.connect(self.start_sim)
        self.dash.home_requested.connect(self.home_requested.emit)

        # ربط إشارات الأزرار اليدوية من الإعدادات إلى الداشبورد
        self.settings.inspiratory_hold_requested.connect(self.dash.on_inspiratory_hold)
        self.settings.expiratory_hold_requested.connect(self.dash.on_expiratory_hold)
        self.settings.recruitment_maneuver_requested.connect(self.dash.on_recruitment_maneuver)
        self.settings.o2_flush_requested.connect(self.dash.on_o2_flush)
        self.settings.suction_mode_requested.connect(self.dash.on_suction_mode)

    # def show_manual(self, data):  # <-- تم الحذف
    #     self.manual.load_patient_data_to_form(data)
    #     self.setCurrentWidget(self.manual)

    def start_sim(self, data):
        mode = data.pop('selected_mode', None)
        if mode:
            self.dash.mode_box.setCurrentText(f"MODE: {mode}")

        # تحديث current_params بناءً على الإعدادات الجديدة
        for key, value in data.items():
            if key in self.dash.current_params:
                if isinstance(value, tuple):
                    self.dash.current_params[key] = value
                elif isinstance(value, (int, float)):
                    self.dash.current_params[key] = (float(value), float(value))

        wave_alerts = {k: v for k, v in data.items() if k.startswith('wave_')}
        self.dash.set_waveform_alerts(wave_alerts)

        self.setCurrentIndex(0)
        self.dash.toggle_simulation()
        
if __name__ == "__main__":
    app = QApplication(sys.argv)
    QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))

    # نقوم بتشغيل المانجر لأنه هو الحاوية لكل الصفحات
    manager = AppManager()
    
    # تمرير بيانات المريض للداشبورد الموجود داخل المانجر
    test_patient_data = {
    'patient_name': 'Test Patient',
    'patient_id': '55-gf3',
    'gender': 'Male',
    'height_cm': 175,
    'weight_kg': 80,
    'age': 45,
    # ABG & Oxygenation
    'pao2': 75,
    'spo2': 92,
    'fio2': 40,
    'paco2': 48,
    'lactate': 2.5,
    # CT
    'ct_lung_involvement_percent': 30,
    # PEEP related
    'static_compliance': 35,
    'atelectasis_percent': 15,
    'ards': 'Moderate',
    'recruitability': 'Moderate',
    'auto_peep': False,
    'map': 80,
    'cardiac_output': 5.5,
    'plateau_pressure': 28,
    'driving_pressure': 14,
    # Mechanical
    'airway_resistance': 12,
    # Work of Breathing (نص)
    'work_of_breathing': 'Moderate',
    # Lung disease pattern
    'lung_disease_pattern': 'ARDS',
    # Consciousness & synchrony
    'consciousness': 'Partially awake',
    'synchrony': 'Good',
    # COPD
    'copd': False,
    # Vent mode (اختياري)
    'mode': 'Volume Control Ventilation (VCV)',
    # ---- الحقول الإضافية للمحركات ----
    'target_vt': 450,          # tidal volume target
    'target_ve': 7.0,           # minute ventilation target
    'vte': 450,                 # tidal volume expired
    'mvent': 7.2,               # minute ventilation
    'rr': 16,                   # respiratory rate
    'pip': 28,                  # peak inspiratory pressure
    'peep': 8,                  # PEEP
    'ti': 1.0,                  # inspiratory time
    'flow_trigger': 2.0,        # flow trigger
    'pressure_trigger': -2.0,   # pressure trigger
    'peak_flow': 60,            # peak flow
    'ett_size': 7.5,            # endotracheal tube size
}
    manager.dash.update_patient_data(test_patient_data)
    
    manager.showFullScreen()
    sys.exit(app.exec_())