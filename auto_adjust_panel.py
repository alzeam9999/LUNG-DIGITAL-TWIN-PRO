import sys
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QFrame, QApplication, QComboBox,
                             QGraphicsDropShadowEffect, QLineEdit, QSizePolicy,
                             QGridLayout, QSpinBox, QTabWidget, QScrollArea,
                             QDoubleSpinBox, QGroupBox, QCheckBox)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt, pyqtSignal
from engines.all_engines import (
    FiO2Engine, PEEPEEngine, VtEngine, VeEngine, RREngine, ApneaRREngine,
    PIPEngine, PSEngine, PMaxEngine, TIEngine, IERatioEngine,
    RiseTimeEngine, CyclingEngine, FlowTriggerEngine, PressureTriggerEngine,
    PeakFlowEngine, FlowPatternEngine, ASVEngine, PAVGainEngine, TubeCompEngine,
    IPAPEngine, EPAPEngine, AlarmsEngine
)
from engines.all_engines import to_float

class ResponsiveMixin:
    """Mixin لتوفير وظائف التكيف مع الشاشات المختلفة"""
    
    def __init__(self):
        self.base_width = 1920
        self.base_height = 1080
        self.base_font_size = 14
        
    
    def set_patient_data(self, data):
        """استقبال بيانات المريض الحالية من الداشبورد"""
        self.patient_data = data

    
        
    def get_screen_scale(self):
        screen = QApplication.primaryScreen()
        if screen:
            available_geometry = screen.availableGeometry()
            width_scale = available_geometry.width() / self.base_width
            height_scale = available_geometry.height() / self.base_height
            return min(width_scale, height_scale)
        return 1.0
    
    def scale_size(self, size):
        return int(size * self.get_screen_scale())
    
    def scale_font(self, base_size=None):
        if base_size is None:
            base_size = self.base_font_size
        scaled_size = int(base_size * self.get_screen_scale())
        return max(8, min(scaled_size, 24))


class AutoAdjustPanel(QWidget, ResponsiveMixin):
    """لوحة الإعدادات المتقدمة المستندة إلى ملف PDF"""
    
    settings_applied = pyqtSignal(dict)
    calculation_completed = pyqtSignal(dict)  # لتمرير التحذيرات والنتائج    
    def __init__(self):
        super().__init__()
        ResponsiveMixin.__init__(self)
        self.setStyleSheet("background-color: #1c2025; color: white;")
        self.setWindowTitle("Auto-Adjust System - Clinical Parameters")
        self.patient_data = None
        self.fio2_engine = FiO2Engine()
        self.peep_engine = PEEPEEngine()
        self.vt_engine = VtEngine()
        self.ve_engine = VeEngine()
        self.rr_engine = RREngine()
        self.apnea_rr_engine = ApneaRREngine()
        self.pip_engine = PIPEngine()
        self.ps_engine = PSEngine()
        self.pmax_engine = PMaxEngine()
        self.ti_engine = TIEngine()
        self.ie_engine = IERatioEngine()
        self.rise_engine = RiseTimeEngine()
        self.cycling_engine = CyclingEngine()
        self.flow_trigger_engine = FlowTriggerEngine()
        self.pressure_trigger_engine = PressureTriggerEngine()
        self.peak_flow_engine = PeakFlowEngine()
        self.flow_pattern_engine = FlowPatternEngine()
        self.asv_engine = ASVEngine()
        self.pav_gain_engine = PAVGainEngine()
        self.tube_comp_engine = TubeCompEngine()
        self.ipap_engine = IPAPEngine()
        self.epap_engine = EPAPEngine()
        self.alarms_engine = AlarmsEngine()
        


        # حساب الحجم المناسب للشاشة
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            self.setMinimumWidth(int(available.width() * 0.7))
            self.setMinimumHeight(int(available.height() * 0.8))
        
        self.init_ui()
        self.last_values = {}

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            self.scale_size(20), self.scale_size(20),
            self.scale_size(20), self.scale_size(20)
        )
        main_layout.setSpacing(self.scale_size(15))
        
        # عنوان اللوحة
        title_frame = QFrame()
        title_frame.setStyleSheet(f"""
            background-color: #2c313c; 
            border-radius: {self.scale_size(10)}px; 
            padding: {self.scale_size(10)}px;
        """)
        title_layout = QHBoxLayout(title_frame)
        
        title = QLabel("🫁 AUTO-ADJUST SYSTEM - CLINICAL VENTILATOR SETTINGS")
        title_font = QFont()
        title_font.setPointSize(self.scale_font(20))
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #3498db; border: none;")
        title_layout.addWidget(title)
        
        # زر إغلاق
        self.btn_close = QPushButton("✕ Close")
        close_font = QFont()
        close_font.setPointSize(self.scale_font(12))
        close_font.setBold(True)
        self.btn_close.setFont(close_font)
        self.btn_close.setStyleSheet(f"""
            QPushButton {{
                background-color: #e74c3c;
                color: white;
                border-radius: {self.scale_size(5)}px;
                padding: {self.scale_size(5)}px {self.scale_size(15)}px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #c0392b; }}
        """)
        self.btn_close.clicked.connect(self.hide)
        title_layout.addWidget(self.btn_close)
        
        main_layout.addWidget(title_frame)
        
        # تبويبات رئيسية
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ 
                border: {self.scale_size(1)}px solid #3e4451; 
                border-radius: {self.scale_size(10)}px; 
                background: #111418; 
            }}
            QTabBar::tab {{ 
                background: #2c313c; 
                color: white; 
                padding: {self.scale_size(12)}px {self.scale_size(25)}px; 
                border-radius: {self.scale_size(5)}px; 
                margin: {self.scale_size(2)}px;
                font-size: {self.scale_font(12)}px;
                font-weight: bold;
            }}
            QTabBar::tab:selected {{ 
                background: #3498db; 
            }}
        """)
        
        # إنشاء التبويبات
        self.create_ventilation_mode_tab()
        self.create_oxygenation_tab()
        self.create_volume_target_tab()
        self.create_respiratory_rate_tab()
        self.create_pressure_target_tab()
        self.create_timing_trigger_tab()
        self.create_advanced_alarms_tab()
        
        main_layout.addWidget(self.tabs)
        
        # أزرار التحكم السفلية
        control_frame = QFrame()
        control_frame.setStyleSheet(f"""
            background-color: #2c313c; 
            border-radius: {self.scale_size(10)}px; 
            padding: {self.scale_size(10)}px;
        """)
        control_layout = QHBoxLayout(control_frame)
        
        self.btn_reset = QPushButton("🔄 Reset to Defaults")
        reset_font = QFont()
        reset_font.setPointSize(self.scale_font(12))
        self.btn_reset.setFont(reset_font)
        self.btn_reset.setStyleSheet(f"""
            QPushButton {{
                background-color: #2c313c;
                color: white;
                border: {self.scale_size(1)}px solid #3e4451;
                border-radius: {self.scale_size(8)}px;
                padding: {self.scale_size(8)}px {self.scale_size(15)}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #3e4451;
                border: {self.scale_size(1)}px solid #3498db;
            }}
        """)
        self.btn_reset.clicked.connect(self.reset_to_defaults)
        self.btn_calc = QPushButton("🔍 Calculate")

        calc_font = QFont()
        calc_font.setPointSize(self.scale_font(12))
        self.btn_calc.setFont(calc_font)
        self.btn_calc.setStyleSheet(f"""
            QPushButton {{
                background-color: #f39c12;
                color: white;
                border: {self.scale_size(1)}px solid #3e4451;
                border-radius: {self.scale_size(8)}px;
                padding: {self.scale_size(8)}px {self.scale_size(15)}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #e67e22;
            }}
        """)
        self.btn_calc.clicked.connect(self.calculate_recommendations)

        # أضف هذا السطر قبل control_layout.addStretch()
        control_layout.addWidget(self.btn_calc)

        self.btn_apply = QPushButton("✅ APPLY SETTINGS TO VENTILATOR")
        apply_font = QFont()
        apply_font.setPointSize(self.scale_font(16))
        apply_font.setBold(True)
        self.btn_apply.setFont(apply_font)
        self.btn_apply.setStyleSheet(f"""
            QPushButton {{
                background-color: #27ae60;
                color: white;
                border-radius: {self.scale_size(8)}px;
                padding: {self.scale_size(15)}px {self.scale_size(30)}px;
                font-weight: bold;
                font-size: {self.scale_font(16)}px;
            }}
            QPushButton:hover {{ background-color: #2ecc71; }}
        """)
        self.btn_apply.clicked.connect(self.apply_settings)
        
        
        
        main_layout.addWidget(control_frame)
    
    # دوال مساعدة لإنشاء العناصر
    def create_label(self, text, font_size=12, bold=False, color="white"):
        label = QLabel(text)
        font = QFont()
        font.setPointSize(self.scale_font(font_size))
        if bold:
            font.setBold(True)
        label.setFont(font)
        label.setStyleSheet(f"color: {color}; border: none;")
        return label
    def calculate_recommendations(self):
        if not self.patient_data:
            print("No patient data available")
            return

        # نسخة من البيانات الأصلية (التي تحتوي الآن على كل القيم من current_params)
        raw_data = self.patient_data.copy()

        # إنشاء قاموس جديد بالمفاتيح التي تتوقعها المحركات
        data = {}

        # -------------------- تعيين الحقول من قاعدة البيانات --------------------
        # Demographics
        data['height_cm'] = to_float(raw_data.get('height_cm'))
        data['gender'] = raw_data.get('gender', 'Male')
        data['lung_disease_pattern'] = raw_data.get('lung_disease_pattern', '')
        data['mvent'] = to_float(raw_data.get('mvent')) or to_float(raw_data.get('target_ve')) or 6.0

        # ABG & Oxygenation
        data['pao2'] = to_float(raw_data.get('pao2'))
        data['spo2'] = to_float(raw_data.get('spo2'))
        data['paco2'] = to_float(raw_data.get('paco2'))
        data['lactate'] = to_float(raw_data.get('lactate'))
        data['fio2'] = to_float(raw_data.get('fio2'))  # FiO2 الحالي
        data['work_of_breathing'] = raw_data.get('work_of_breathing')

        data['plateau_pressure'] = to_float(raw_data.get('plateau_pressure'))
        data['driving_pressure'] = to_float(raw_data.get('driving_pressure'))

        # CT & Imaging
        data['ct_lung_involvement_percent'] = to_float(raw_data.get('ct_lung_involvement_percent'))

        # PEEP related
        data['static_compliance'] = to_float(raw_data.get('static_compliance'))

        # إذا كان spo2 غير موجود، حاول من الحقل القديم
        if data.get('spo2') is None:
            data['spo2'] = to_float(raw_data.get('oxygen_saturation_admission'))

        # إذا كان map غير موجود، حاول من map_bp
        if data.get('map') is None:
            data['map'] = to_float(raw_data.get('map_bp'))

        # إذا كان fio2 غير موجود، حاول من fio2_max
        if data.get('fio2') is None:
            data['fio2'] = to_float(raw_data.get('fio2_max'))

        # محاولة استخراج atelectasis_percent من ct_atelectasis إذا كان رقماً، وإلا استخدام 15 كافتراضي
        atel = raw_data.get('ct_atelectasis')
        if atel and atel.replace('.', '', 1).isdigit():
            data['atelectasis_percent'] = float(atel)
        else:
            data['atelectasis_percent'] = 15.0  # قيمة افتراضية معقولة

        # Auto-PEEP: تحويل Yes/No إلى Boolean
        auto_peep_val = raw_data.get('auto_peep')
        if auto_peep_val is not None:
            data['auto_peep'] = str(auto_peep_val).lower() in ['yes', 'true', '1']
        else:
            data['auto_peep'] = False

        # Plateau و Driving (إذا كانت موجودة في قاعدة البيانات، وإلا ستبقى None)
        data['plateau_pressure'] = to_float(raw_data.get('plateau_pressure'))
        data['driving_pressure'] = to_float(raw_data.get('driving_pressure'))

        # Hemodynamics
        data['map'] = to_float(raw_data.get('map'))  # map_bp هو الاسم في قاعدة البيانات
        data['cardiac_output'] = to_float(raw_data.get('cardiac_output'))

        # Airway resistance
        data['airway_resistance'] = to_float(raw_data.get('airway_resistance'))

        # ETT size (قد يكون موجوداً في current_params)
        data['ett_size'] = to_float(raw_data.get('ett_size'))

        # Consciousness & synchrony (تؤخذ من واجهة Auto-Adjust)
        data['consciousness'] = self.consciousness_combo.currentText()
        data['synchrony'] = self.synchrony_combo.currentText()

        # ARDS severity و lung recruitability (تؤخذ من واجهة Auto-Adjust)
        data['ards'] = self.ards_combo.currentText()
        data['recruitability'] = self.recruit_combo.currentText()

        # COPD: من قاعدة البيانات (chk_copd__...) أو من checkbox
        copd_val = raw_data.get('chk_copd___chronic_obstructive_pulmonary_disease')
        if copd_val is not None:
            data['copd'] = str(copd_val).lower() in ['yes', 'true', '1']
        else:
            data['copd'] = self.copd_check.isChecked()

        # Mode (من واجهة Auto-Adjust)
        data['mode'] = self.mode_combo.currentText()

        # إضافة المعايير السريرية إلى data
        data['consciousness'] = self.consciousness_combo.currentText()
        data['synchrony'] = self.synchrony_combo.currentText()
        data['rr_wob'] = self.rr_wob_combo.currentText()
        data['sedation'] = self.sedation_combo.currentText()
        data['hemodynamics'] = self.hemodynamics_combo.currentText()
        data['alarms_response'] = self.alarms_response_combo.currentText()
        data['weaning'] = self.weaning_combo.currentText()
        data['mask_seal'] = self.mask_seal_combo.currentText()

        # --- إضافة الحقول المطلوبة من current_params (القيم الحالية) ---
        # هذه الحقول تم دمجها في patient_data عبر show_auto_adjust_panel
        data['target_vt'] = to_float(raw_data.get('target_vt')) or to_float(raw_data.get('vte'))
        data['target_ve'] = to_float(raw_data.get('target_ve')) or to_float(raw_data.get('mvent'))
        data['rr'] = to_float(raw_data.get('rr'))
        data['pip'] = to_float(raw_data.get('pip'))
        data['peep'] = to_float(raw_data.get('peep'))
        data['ti'] = to_float(raw_data.get('ti'))
        data['peak_flow'] = to_float(raw_data.get('peak_flow'))
        data['flow_trigger'] = to_float(raw_data.get('flow_trigger'))
        data['pressure_trigger'] = to_float(raw_data.get('pressure_trigger'))
        data['spontaneous_rr'] = to_float(raw_data.get('spontaneous_rr'))
        data['accessory_muscles'] = raw_data.get('accessory_muscles', 'No')
        # حقول إضافية قد تحتاجها بعض المحركات
        data['flow_starvation_detected'] = raw_data.get('flow_starvation_detected', False)
        data['peak_pressure_alarm'] = raw_data.get('peak_pressure_alarm', False)

        # -------------------- الحسابات الموحدة --------------------
        from engines.all_engines import apply_auto_settings
        result = apply_auto_settings(data)
        rec = result['recommendations']
        warnings = result['warnings']
        missing = result['missing_fields']

        # عرض التحذيرات
        if warnings:
            print("\n".join(warnings))
        if missing:
            print("Missing fields:", missing)

        # تحديث عناصر الواجهة بالقيم الجديدة (مع تطبيق حدود التغيير)

        # FiO2
        if rec.get('fio2') is not None:
            self.fio2_min.setValue(max(21, rec['fio2'] - 5))
            self.fio2_max.setValue(min(100, rec['fio2'] + 5))
            self.last_values['fio2'] = rec['fio2']
        else:
            print("FiO2: insufficient data")

        # PEEP
        if rec.get('peep') is not None:
            self.peep_min.setValue(max(0, rec['peep'] - 2))
            self.peep_max.setValue(min(25, rec['peep'] + 2))
            self.last_values['peep'] = rec['peep']
        else:
            print("PEEP: insufficient data")

        # Vt
        if rec.get('vt') is not None:
            self.vt_min.setValue(max(200, rec['vt'] - 50))
            self.vt_max.setValue(min(1000, rec['vt'] + 50))
            self.last_values['target_vt'] = rec['vt']
        else:
            print("Vt: insufficient data")

        # Minute Ventilation
        if rec.get('ve') is not None:
            self.mve_min.setValue(max(2.0, rec['ve'] - 1.0))
            self.mve_max.setValue(min(20.0, rec['ve'] + 1.0))
            self.last_values['target_ve'] = rec['ve']
        else:
            print("VE: insufficient data")

        # RR
        if rec.get('rr') is not None:
            self.rr_min.setValue(max(5, rec['rr'] - 4))
            self.rr_max.setValue(min(40, rec['rr'] + 4))
            self.last_values['rr'] = rec['rr']
        else:
            print("RR: insufficient data")

        # Apnea RR
        if rec.get('apnea_rr') is not None:
            self.apnea_rate.setValue(rec['apnea_rr'])
            self.last_values['apnea_rr'] = rec['apnea_rr']
        else:
            print("Apnea RR: insufficient data")

        # PIP
        if rec.get('pip') is not None:
            self.ip_min.setValue(max(5, rec['pip'] - 5))
            self.ip_max.setValue(min(40, rec['pip'] + 5))
            self.last_values['pip'] = rec['pip']
        else:
            print("PIP: insufficient data")

        # Pressure Support
        if rec.get('ps') is not None:
            self.ps_min.setValue(max(0, rec['ps'] - 3))
            self.ps_max.setValue(min(30, rec['ps'] + 3))
            self.last_values['ps'] = rec['ps']
        else:
            print("PS: insufficient data")

        # Pmax
        if rec.get('pmax') is not None:
            self.pmax.setValue(rec['pmax'])
            self.last_values['pmax'] = rec['pmax']
        else:
            print("Pmax: insufficient data")

        # Inspiratory Time
        if rec.get('ti') is not None:
            self.ti.setValue(rec['ti'])
            self.last_values['ti'] = rec['ti']
        else:
            print("Ti: insufficient data")

        # I:E Ratio
        if rec.get('ie_ratio') is not None:
            index = self.ie_combo.findText(rec['ie_ratio'])
            if index >= 0:
                self.ie_combo.setCurrentIndex(index)
            print(f"I:E Ratio: {rec['ie_ratio']}")

        # Rise Time
        if rec.get('rise_time') is not None:
            self.rise_time_spin.setValue(rec['rise_time'])
            print(f"Rise Time: {rec['rise_time']}")

        # Cycling Criteria
        if rec.get('cycling') is not None:
            self.cycling_spin.setValue(rec['cycling'])
            print(f"Cycling: {rec['cycling']}%")

        # Flow Trigger
        if rec.get('flow_trigger') is not None:
            self.flow_trigger.setValue(rec['flow_trigger'])
            print(f"Flow Trigger: {rec['flow_trigger']} L/min")

        # Pressure Trigger
        if rec.get('pressure_trigger') is not None:
            self.pressure_trigger.setValue(rec['pressure_trigger'])
            print(f"Pressure Trigger: {rec['pressure_trigger']} cmH2O")

        # Peak Flow
        if rec.get('peak_flow') is not None:
            self.peak_flow_min.setValue(max(20, rec['peak_flow'] - 20))
            self.peak_flow_max.setValue(min(120, rec['peak_flow'] + 20))
            self.last_values['peak_flow'] = rec['peak_flow']
        else:
            print("Peak Flow: insufficient data")

        # Flow Pattern
        if rec.get('flow_pattern') is not None:
            index = self.flow_pattern.findText(rec['flow_pattern'])
            if index >= 0:
                self.flow_pattern.setCurrentIndex(index)
            print(f"Flow Pattern: {rec['flow_pattern']}")

        # ASV Target
        if rec.get('asv_percent') is not None:
            self.asv_target.setValue(rec['asv_percent'])
            print(f"ASV Target: {rec['asv_percent']}%")

        # PAV Gain
        if rec.get('pav_gain') is not None:
            self.pav_gain.setValue(rec['pav_gain'])
            print(f"PAV Gain: {rec['pav_gain']}%")

        # Tube Compensation
        if rec.get('tube_comp') is not None:
            self.tube_comp.setValue(rec['tube_comp'])
            print(f"Tube Comp: {rec['tube_comp']}%")

        # IPAP
        if rec.get('ipap') is not None:
            self.ipap_min.setValue(max(8, rec['ipap'] - 2))
            self.ipap_max.setValue(min(25, rec['ipap'] + 2))
            self.last_values['ipap'] = rec['ipap']
        else:
            print("IPAP: insufficient data")

        # EPAP
        if rec.get('epap') is not None:
            self.epap_min.setValue(max(4, rec['epap'] - 1))
            self.epap_max.setValue(min(12, rec['epap'] + 1))
            self.last_values['epap'] = rec['epap']
        else:
            print("EPAP: insufficient data")

        # Alarms
        alarms = rec.get('alarms', {})
        if alarms.get('high_pressure') is not None:
            self.alarm_high_pressure.setValue(alarms['high_pressure'])
        if alarms.get('low_vt') is not None:
            self.alarm_low_vt.setValue(alarms['low_vt'])
        if alarms.get('high_rr') is not None:
            self.alarm_high_rr.setValue(alarms['high_rr'])
        if alarms.get('low_mv') is not None:
            self.alarm_low_mv.setValue(alarms['low_mv'])
        if alarms.get('apnea_time') is not None:
            self.apnea_time.setValue(alarms['apnea_time'])
        if alarms.get('high_fio2') is not None:
            self.alarm_high_fio2.setValue(alarms['high_fio2'])
        if alarms.get('low_fio2') is not None:
            self.alarm_low_fio2.setValue(alarms['low_fio2'])

        print(f"Alarms: HighP={alarms.get('high_pressure')}, LowVt={alarms.get('low_vt')}, HighRR={alarms.get('high_rr')}, LowMV={alarms.get('low_mv')}, ApneaTime={alarms.get('apnea_time')}")
        self.calculation_completed.emit({
        'warnings': warnings,
        'missing': missing,
        'recommendations': rec
        })

    def get_groupbox_style(self):
        return f"""
            QGroupBox {{
                color: #3498db;
                font-weight: bold;
                border: {self.scale_size(2)}px solid #3e4451;
                border-radius: {self.scale_size(8)}px;
                margin-top: {self.scale_size(10)}px;
                padding-top: {self.scale_size(10)}px;
                font-size: {self.scale_font(13)}px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: {self.scale_size(10)}px;
                padding: 0 {self.scale_size(5)}px 0 {self.scale_size(5)}px;
            }}
        """
    
    def get_combobox_style(self):
        return f"""
            QComboBox {{
                background-color: #111418;
                color: white;
                border: {self.scale_size(1)}px solid #3e4451;
                border-radius: {self.scale_size(5)}px;
                padding: {self.scale_size(5)}px;
                font-size: {self.scale_font(12)}px;
                min-width: {self.scale_size(150)}px;
            }}
            QComboBox:hover {{ border: {self.scale_size(1)}px solid #3498db; }}
        """
    
    def get_spinbox_style(self):
        return f"""
            QSpinBox, QDoubleSpinBox {{
                background-color: #111418;
                color: white;
                border: {self.scale_size(1)}px solid #3e4451;
                border-radius: {self.scale_size(5)}px;
                padding: {self.scale_size(5)}px;
                font-size: {self.scale_font(12)}px;
                min-width: {self.scale_size(80)}px;
            }}
            QSpinBox:hover, QDoubleSpinBox:hover {{ border: {self.scale_size(1)}px solid #3498db; }}
        """
    
    def configure_spinbox(self, spinbox, min_val, max_val, default):
        spinbox.setRange(min_val, max_val)
        spinbox.setValue(default)
        spinbox.setStyleSheet(self.get_spinbox_style())
        font = QFont()
        font.setPointSize(self.scale_font(12))
        spinbox.setFont(font)
    
    def configure_doublespinbox(self, spinbox, min_val, max_val, default):
        spinbox.setRange(min_val, max_val)
        spinbox.setValue(default)
        spinbox.setSingleStep(0.5)
        spinbox.setStyleSheet(self.get_spinbox_style())
        font = QFont()
        font.setPointSize(self.scale_font(12))
        spinbox.setFont(font)
    
    def add_min_max(self, layout, spin_min, spin_max, row, col):
        hbox = QHBoxLayout()
        hbox.setSpacing(self.scale_size(5))
        
        min_label = self.create_label("Min:", 11)
        max_label = self.create_label("Max:", 11)
        
        hbox.addWidget(min_label)
        hbox.addWidget(spin_min)
        hbox.addSpacing(self.scale_size(10))
        hbox.addWidget(max_label)
        hbox.addWidget(spin_max)
        layout.addLayout(hbox, row, col, 1, 3)
    
    def add_min_max_double(self, layout, spin_min, spin_max, row, col):
        hbox = QHBoxLayout()
        hbox.setSpacing(self.scale_size(5))
        
        min_label = self.create_label("Min:", 11)
        max_label = self.create_label("Max:", 11)
        
        hbox.addWidget(min_label)
        hbox.addWidget(spin_min)
        hbox.addSpacing(self.scale_size(10))
        hbox.addWidget(max_label)
        hbox.addWidget(spin_max)
        layout.addLayout(hbox, row, col, 1, 3)
    
    # إنشاء التبويبات
    def create_ventilation_mode_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(self.scale_size(15))
        layout.setAlignment(Qt.AlignTop)
        
        mode_group = QGroupBox("1. Ventilation Mode Selection")
        mode_group.setStyleSheet(self.get_groupbox_style())
        mode_layout = QVBoxLayout(mode_group)
        mode_layout.setSpacing(self.scale_size(10))
        
        lbl_mode = self.create_label("Select Ventilation Mode:", 12, True)
        
        self.mode_combo = QComboBox()
        modes = [
            "Volume Control Ventilation (VCV)",
            "Pressure Control Ventilation (PCV)", 
            "Pressure Regulated Volume Control (PRVC)",
            "Synchronized Intermittent Mandatory Ventilation (SIMV)",
            "Pressure Support Ventilation (PSV)",
            "Continuous Positive Airway Pressure (CPAP)",
            "Adaptive Support Ventilation (ASV)",
            "Proportional Assist Ventilation (PAV)",
            "Neurally Adjusted Ventilatory Assist (NAVA)",
            "Non-Invasive Ventilation (NIV)"
        ]
        self.mode_combo.addItems(modes)
        self.mode_combo.setStyleSheet(self.get_combobox_style())
        font = QFont()
        font.setPointSize(self.scale_font(12))
        self.mode_combo.setFont(font)
        
        mode_layout.addWidget(lbl_mode)
        mode_layout.addWidget(self.mode_combo)
        
        patient_status_group = QGroupBox("Patient Clinical Status")
        patient_status_group.setStyleSheet(self.get_groupbox_style())
        status_layout = QGridLayout(patient_status_group)
        status_layout.setSpacing(self.scale_size(10))
        status_layout.setColumnMinimumWidth(1, self.scale_size(200))
        
        status_layout.addWidget(self.create_label("Consciousness:", 12, True), 0, 0)
        self.consciousness_combo = QComboBox()
        self.consciousness_combo.addItems(["Alert and responsive", "Partially awake", "Sedated", "Unconscious"])
        self.consciousness_combo.setStyleSheet(self.get_combobox_style())
        self.consciousness_combo.setFont(font)
        status_layout.addWidget(self.consciousness_combo, 0, 1)
        
        status_layout.addWidget(self.create_label("Patient-Ventilator Synchrony:", 12, True), 1, 0)
        self.synchrony_combo = QComboBox()
        self.synchrony_combo.addItems(["Fully synchronized", "Mostly synchronized", "Poor synchrony", "Asynchrony"])
        self.synchrony_combo.setStyleSheet(self.get_combobox_style())
        self.synchrony_combo.setFont(font)
        status_layout.addWidget(self.synchrony_combo, 1, 1)
        
        # في create_ventilation_mode_tab، داخل patient_status_group
        row = 2  # بعد synchrony_combo

        # 1.3 Respiratory Rate / Work of Breathing
        status_layout.addWidget(self.create_label("Respiratory Rate / Work of Breathing:", 12, True), row, 0)
        self.rr_wob_combo = QComboBox()
        self.rr_wob_combo.addItems([
            "Within target range",
            "Spontaneous RR acceptable",
            "Mildly increased work of breathing",
            "Mostly supported",
            "Partially supported",
            "Fully supported",
            "Minimal support",
            "Work of breathing reduced but present"
        ])
        self.rr_wob_combo.setStyleSheet(self.get_combobox_style())
        self.rr_wob_combo.setFont(self.create_label("", 12).font())
        status_layout.addWidget(self.rr_wob_combo, row, 1)

        # 1.4 Sedation / Comfort
        row += 1
        status_layout.addWidget(self.create_label("Sedation / Comfort:", 12, True), row, 0)
        self.sedation_combo = QComboBox()
        self.sedation_combo.addItems([
            "Not needed",
            "Minimal sedation",
            "Light sedation",
            "Moderate sedation",
            "Deep sedation",
            "Comfortable / no discomfort",
            "Mild discomfort",
            "Agitated"
        ])
        self.sedation_combo.setStyleSheet(self.get_combobox_style())
        self.sedation_combo.setFont(self.create_label("", 12).font())
        status_layout.addWidget(self.sedation_combo, row, 1)

        # 1.5 Hemodynamics (BP / HR effect of ventilation)
        row += 1
        status_layout.addWidget(self.create_label("Hemodynamics (BP/HR effect):", 12, True), row, 0)
        self.hemodynamics_combo = QComboBox()
        self.hemodynamics_combo.addItems([
            "Stable",
            "Mild hypotension",
            "Hypotension",
            "Tachycardia",
            "Bradycardia",
            "Unstable"
        ])
        self.hemodynamics_combo.setStyleSheet(self.get_combobox_style())
        self.hemodynamics_combo.setFont(self.create_label("", 12).font())
        status_layout.addWidget(self.hemodynamics_combo, row, 1)

        # 1.6 Alarms / Safety Response
        row += 1
        status_layout.addWidget(self.create_label("Alarms / Safety Response:", 12, True), row, 0)
        self.alarms_response_combo = QComboBox()
        self.alarms_response_combo.addItems([
            "All alarms acknowledged and appropriate",
            "Occasional nuisance alarms",
            "Frequent alarms",
            "Critical alarms active"
        ])
        self.alarms_response_combo.setStyleSheet(self.get_combobox_style())
        self.alarms_response_combo.setFont(self.create_label("", 12).font())
        status_layout.addWidget(self.alarms_response_combo, row, 1)

        # 1.7 Weaning Readiness / Spontaneous Breathing
        row += 1
        status_layout.addWidget(self.create_label("Weaning Readiness / Spontaneous Breathing:", 12, True), row, 0)
        self.weaning_combo = QComboBox()
        self.weaning_combo.addItems([
            "Not ready",
            "Partially ready",
            "Fully ready",
            "Spontaneous breaths >8 bpm",
            "Spontaneous breaths >10 bpm",
            "Spontaneous breaths >12 bpm"
        ])
        self.weaning_combo.setStyleSheet(self.get_combobox_style())
        self.weaning_combo.setFont(self.create_label("", 12).font())
        status_layout.addWidget(self.weaning_combo, row, 1)

        # 1.8 Mask Seal / Patient Cooperation (NIV only)
        row += 1
        status_layout.addWidget(self.create_label("Mask Seal / Patient Cooperation (NIV only):", 12, True), row, 0)
        self.mask_seal_combo = QComboBox()
        self.mask_seal_combo.addItems([
            "Not applicable",
            "Fully maintained",
            "Partial leak",
            "Poor cooperation"
        ])
        self.mask_seal_combo.setStyleSheet(self.get_combobox_style())
        self.mask_seal_combo.setFont(self.create_label("", 12).font())
        status_layout.addWidget(self.mask_seal_combo, row, 1)

        layout.addWidget(mode_group)
        layout.addWidget(patient_status_group)
        layout.addStretch()
        
        self.tabs.addTab(tab, "1. Vent Mode")
    
    def create_oxygenation_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(self.scale_size(15))
        
        fio2_group = QGroupBox("2.1 FiO₂ Control Engine")
        fio2_group.setStyleSheet(self.get_groupbox_style())
        fio2_layout = QGridLayout(fio2_group)
        fio2_layout.setSpacing(self.scale_size(10))
        
        fio2_layout.addWidget(self.create_label("FiO₂ (%):", 12, True), 0, 0)
        self.fio2_min = QSpinBox()
        self.fio2_max = QSpinBox()
        self.configure_spinbox(self.fio2_min, 21, 100, 21)
        self.configure_spinbox(self.fio2_max, 21, 100, 60)
        self.add_min_max(fio2_layout, self.fio2_min, self.fio2_max, 0, 1)
        
        self.copd_check = QCheckBox("COPD Patient (Limit FiO₂ to 60%)")
        self.copd_check.setFont(self.create_label("", 12).font())
        self.copd_check.setStyleSheet("color: white; border: none;")
        fio2_layout.addWidget(self.copd_check, 1, 0, 1, 3)
        
        peep_group = QGroupBox("2.2 PEEP Control Engine")
        peep_group.setStyleSheet(self.get_groupbox_style())
        peep_layout = QGridLayout(peep_group)
        peep_layout.setSpacing(self.scale_size(10))
        
        peep_layout.addWidget(self.create_label("PEEP (cmH₂O):", 12, True), 0, 0)
        self.peep_min = QSpinBox()
        self.peep_max = QSpinBox()
        self.configure_spinbox(self.peep_min, 0, 25, 5)
        self.configure_spinbox(self.peep_max, 0, 25, 12)
        self.add_min_max(peep_layout, self.peep_min, self.peep_max, 0, 1)
        
        peep_layout.addWidget(self.create_label("ARDS Severity:", 12, True), 1, 0)
        self.ards_combo = QComboBox()
        self.ards_combo.addItems(["None", "Mild", "Moderate", "Severe"])
        self.ards_combo.setStyleSheet(self.get_combobox_style())
        self.ards_combo.setFont(self.create_label("", 12).font())
        peep_layout.addWidget(self.ards_combo, 1, 1)
        
        peep_layout.addWidget(self.create_label("Lung Recruitability:", 12, True), 2, 0)
        self.recruit_combo = QComboBox()
        self.recruit_combo.addItems(["Low", "Moderate", "High"])
        self.recruit_combo.setStyleSheet(self.get_combobox_style())
        self.recruit_combo.setFont(self.create_label("", 12).font())
        peep_layout.addWidget(self.recruit_combo, 2, 1)
        
        layout.addWidget(fio2_group)
        layout.addWidget(peep_group)
        layout.addStretch()
        
        self.tabs.addTab(tab, "2. Oxygenation")
    
    def create_volume_target_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(self.scale_size(15))
        
        vt_group = QGroupBox("3.1 Tidal Volume (Vt) Engine")
        vt_group.setStyleSheet(self.get_groupbox_style())
        vt_layout = QGridLayout(vt_group)
        vt_layout.setSpacing(self.scale_size(10))
        
        vt_layout.addWidget(self.create_label("Tidal Volume (mL):", 12, True), 0, 0)
        self.vt_min = QSpinBox()
        self.vt_max = QSpinBox()
        self.configure_spinbox(self.vt_min, 200, 1000, 400)
        self.configure_spinbox(self.vt_max, 200, 1000, 550)
        self.add_min_max(vt_layout, self.vt_min, self.vt_max, 0, 1)
        
        vt_layout.addWidget(self.create_label("Predicted Body Weight (kg):", 12, True), 1, 0)
        self.pbw = QDoubleSpinBox()
        self.pbw.setRange(30, 120)
        self.pbw.setValue(70)
        self.pbw.setStyleSheet(self.get_spinbox_style())
        self.pbw.setFont(self.create_label("", 12).font())
        vt_layout.addWidget(self.pbw, 1, 1)
        
        mve_group = QGroupBox("3.2 Target Minute Ventilation (VE) Engine")
        mve_group.setStyleSheet(self.get_groupbox_style())
        mve_layout = QGridLayout(mve_group)
        mve_layout.setSpacing(self.scale_size(10))
        
        mve_layout.addWidget(self.create_label("Minute Ventilation (L/min):", 12, True), 0, 0)
        self.mve_min = QDoubleSpinBox()
        self.mve_max = QDoubleSpinBox()
        self.configure_doublespinbox(self.mve_min, 2, 20, 5)
        self.configure_doublespinbox(self.mve_max, 2, 20, 8)
        self.add_min_max_double(mve_layout, self.mve_min, self.mve_max, 0, 1)
        
        layout.addWidget(vt_group)
        layout.addWidget(mve_group)
        layout.addStretch()
        
        self.tabs.addTab(tab, "3. Volume")
    
    def create_respiratory_rate_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(self.scale_size(15))
        
        rr_group = QGroupBox("4.1 Mandatory Respiratory Rate Engine")
        rr_group.setStyleSheet(self.get_groupbox_style())
        rr_layout = QGridLayout(rr_group)
        rr_layout.setSpacing(self.scale_size(10))
        
        rr_layout.addWidget(self.create_label("Respiratory Rate (bpm):", 12, True), 0, 0)
        self.rr_min = QSpinBox()
        self.rr_max = QSpinBox()
        self.configure_spinbox(self.rr_min, 5, 40, 10)
        self.configure_spinbox(self.rr_max, 5, 40, 16)
        self.add_min_max(rr_layout, self.rr_min, self.rr_max, 0, 1)
        
        apnea_group = QGroupBox("4.2 Apnea Backup Respiratory Rate")
        apnea_group.setStyleSheet(self.get_groupbox_style())
        apnea_layout = QGridLayout(apnea_group)
        apnea_layout.setSpacing(self.scale_size(10))
        
        apnea_layout.addWidget(self.create_label("Backup Rate (bpm):", 12, True), 0, 0)
        self.apnea_rate = QSpinBox()
        self.configure_spinbox(self.apnea_rate, 5, 40, 12)
        apnea_layout.addWidget(self.apnea_rate, 0, 1)
        
        apnea_layout.addWidget(self.create_label("Apnea Time (sec):", 12, True), 1, 0)
        self.apnea_time = QSpinBox()
        self.configure_spinbox(self.apnea_time, 10, 60, 20)
        apnea_layout.addWidget(self.apnea_time, 1, 1)
        
        layout.addWidget(rr_group)
        layout.addWidget(apnea_group)
        layout.addStretch()
        
        self.tabs.addTab(tab, "4. Rate")
    
    def create_pressure_target_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(self.scale_size(15))
        
        ip_group = QGroupBox("5.1 Inspiratory Pressure Control")
        ip_group.setStyleSheet(self.get_groupbox_style())
        ip_layout = QGridLayout(ip_group)
        ip_layout.setSpacing(self.scale_size(10))
        
        ip_layout.addWidget(self.create_label("Inspiratory Pressure (cmH₂O):", 12, True), 0, 0)
        self.ip_min = QSpinBox()
        self.ip_max = QSpinBox()
        self.configure_spinbox(self.ip_min, 5, 40, 10)
        self.configure_spinbox(self.ip_max, 5, 40, 25)
        self.add_min_max(ip_layout, self.ip_min, self.ip_max, 0, 1)
        
        ps_group = QGroupBox("5.2 Pressure Support Level")
        ps_group.setStyleSheet(self.get_groupbox_style())
        ps_layout = QGridLayout(ps_group)
        ps_layout.setSpacing(self.scale_size(10))
        
        ps_layout.addWidget(self.create_label("Pressure Support (cmH₂O):", 12, True), 0, 0)
        self.ps_min = QSpinBox()
        self.ps_max = QSpinBox()
        self.configure_spinbox(self.ps_min, 0, 30, 5)
        self.configure_spinbox(self.ps_max, 0, 30, 15)
        self.add_min_max(ps_layout, self.ps_min, self.ps_max, 0, 1)
        
        pmax_group = QGroupBox("5.3 Maximum Pressure Limit (Safety)")
        pmax_group.setStyleSheet(self.get_groupbox_style())
        pmax_layout = QGridLayout(pmax_group)
        pmax_layout.setSpacing(self.scale_size(10))
        
        pmax_layout.addWidget(self.create_label("Max Pressure (cmH₂O):", 12, True), 0, 0)
        self.pmax = QSpinBox()
        self.configure_spinbox(self.pmax, 20, 60, 40)
        pmax_layout.addWidget(self.pmax, 0, 1)
        
        layout.addWidget(ip_group)
        layout.addWidget(ps_group)
        layout.addWidget(pmax_group)
        layout.addStretch()
        
        self.tabs.addTab(tab, "5. Pressure")
    
    def create_timing_trigger_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(self.scale_size(15))

        # ===== 6. Timing Settings =====
        timing_group = QGroupBox("6. Timing Settings")
        timing_group.setStyleSheet(self.get_groupbox_style())
        timing_layout = QGridLayout(timing_group)
        timing_layout.setSpacing(self.scale_size(10))
        timing_layout.setColumnMinimumWidth(0, self.scale_size(150))

        # صف 0: Inspiratory Time
        timing_layout.addWidget(self.create_label("Inspiratory Time (sec):", 12, True), 0, 0)
        self.ti = QDoubleSpinBox()
        self.ti.setRange(0.3, 3.0)
        self.ti.setValue(1.0)
        self.ti.setSingleStep(0.1)
        self.ti.setStyleSheet(self.get_spinbox_style())
        self.ti.setFont(self.create_label("", 12).font())
        timing_layout.addWidget(self.ti, 0, 1)

        # صف 1: I:E Ratio
        timing_layout.addWidget(self.create_label("I:E Ratio:", 12, True), 1, 0)
        self.ie_combo = QComboBox()
        self.ie_combo.addItems(["1:1", "1:2", "1:3", "1:4", "2:1 (Inverse)"])
        self.ie_combo.setStyleSheet(self.get_combobox_style())
        self.ie_combo.setFont(self.create_label("", 12).font())
        timing_layout.addWidget(self.ie_combo, 1, 1)

        # صف 2: Rise Time
        timing_layout.addWidget(self.create_label("Rise Time (%):", 12, True), 2, 0)
        self.rise_time_spin = QSpinBox()
        self.rise_time_spin.setRange(1, 10)
        self.rise_time_spin.setValue(5)
        self.rise_time_spin.setSuffix(" %")
        self.rise_time_spin.setStyleSheet(self.get_spinbox_style())
        self.rise_time_spin.setFont(self.create_label("", 12).font())
        timing_layout.addWidget(self.rise_time_spin, 2, 1)

        # صف 3: Cycling Criteria
        timing_layout.addWidget(self.create_label("Cycling Criteria (%):", 12, True), 3, 0)
        self.cycling_spin = QSpinBox()
        self.cycling_spin.setRange(10, 50)
        self.cycling_spin.setValue(25)
        self.cycling_spin.setSuffix(" %")
        self.cycling_spin.setStyleSheet(self.get_spinbox_style())
        self.cycling_spin.setFont(self.create_label("", 12).font())
        timing_layout.addWidget(self.cycling_spin, 3, 1)

        layout.addWidget(timing_group)

        # ===== 7. Trigger Sensitivity =====
        trigger_group = QGroupBox("7. Trigger Sensitivity")
        trigger_group.setStyleSheet(self.get_groupbox_style())
        trigger_layout = QGridLayout(trigger_group)
        trigger_layout.setSpacing(self.scale_size(10))
        trigger_layout.setColumnMinimumWidth(0, self.scale_size(150))

        trigger_layout.addWidget(self.create_label("Flow Trigger (L/min):", 12, True), 0, 0)
        self.flow_trigger = QDoubleSpinBox()
        self.flow_trigger.setRange(0.5, 5.0)
        self.flow_trigger.setValue(2.0)
        self.flow_trigger.setSingleStep(0.5)
        self.flow_trigger.setStyleSheet(self.get_spinbox_style())
        self.flow_trigger.setFont(self.create_label("", 12).font())
        trigger_layout.addWidget(self.flow_trigger, 0, 1)

        trigger_layout.addWidget(self.create_label("Pressure Trigger (cmH₂O):", 12, True), 1, 0)
        self.pressure_trigger = QDoubleSpinBox()
        self.pressure_trigger.setRange(-5.0, -0.5)
        self.pressure_trigger.setValue(-2.0)
        self.pressure_trigger.setSingleStep(0.5)
        self.pressure_trigger.setStyleSheet(self.get_spinbox_style())
        self.pressure_trigger.setFont(self.create_label("", 12).font())
        trigger_layout.addWidget(self.pressure_trigger, 1, 1)

        layout.addWidget(trigger_group)

        # ===== 8. Flow Configuration =====
        flow_group = QGroupBox("8. Flow Configuration")
        flow_group.setStyleSheet(self.get_groupbox_style())
        flow_layout = QGridLayout(flow_group)
        flow_layout.setSpacing(self.scale_size(10))
        flow_layout.setColumnMinimumWidth(0, self.scale_size(150))

        flow_layout.addWidget(self.create_label("Peak Inspiratory Flow (L/min):", 12, True), 0, 0)
        self.peak_flow_min = QSpinBox()
        self.peak_flow_max = QSpinBox()
        self.configure_spinbox(self.peak_flow_min, 20, 120, 40)
        self.configure_spinbox(self.peak_flow_max, 20, 120, 80)
        self.add_min_max(flow_layout, self.peak_flow_min, self.peak_flow_max, 0, 1)

        flow_layout.addWidget(self.create_label("Flow Pattern:", 12, True), 1, 0)
        self.flow_pattern = QComboBox()
        self.flow_pattern.addItems(["Square", "Decelerating", "Sinusoidal"])
        self.flow_pattern.setStyleSheet(self.get_combobox_style())
        self.flow_pattern.setFont(self.create_label("", 12).font())
        flow_layout.addWidget(self.flow_pattern, 1, 1)

        layout.addWidget(flow_group)

        layout.addStretch()
        self.tabs.addTab(tab, "6. Timing/Trigger")
    
    def to_float(x):
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        if isinstance(x, str):
            try:
                return float(x.replace(',', ''))
            except:
                return None
        if isinstance(x, (tuple, list)) and len(x) == 2:
            return (x[0] + x[1]) / 2.0
        return None

    def create_advanced_alarms_tab(self):
        tab = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: transparent; border: none;")
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(self.scale_size(15))
        
        adv_group = QGroupBox("9. Advanced Support Settings")
        adv_group.setStyleSheet(self.get_groupbox_style())
        adv_layout = QGridLayout(adv_group)
        adv_layout.setSpacing(self.scale_size(10))
        
        adv_layout.addWidget(self.create_label("ASV Target (%):", 12, True), 0, 0)
        self.asv_target = QSpinBox()
        self.configure_spinbox(self.asv_target, 50, 200, 100)
        adv_layout.addWidget(self.asv_target, 0, 1)
        
        adv_layout.addWidget(self.create_label("PAV Gain (%):", 12, True), 1, 0)
        self.pav_gain = QSpinBox()
        self.configure_spinbox(self.pav_gain, 30, 80, 50)
        adv_layout.addWidget(self.pav_gain, 1, 1)
        
        adv_layout.addWidget(self.create_label("Tube Compensation (%):", 12, True), 2, 0)
        self.tube_comp = QSpinBox()
        self.configure_spinbox(self.tube_comp, 0, 100, 50)
        adv_layout.addWidget(self.tube_comp, 2, 1)
        
        niv_group = QGroupBox("NIV Settings")
        niv_group.setStyleSheet(self.get_groupbox_style())
        niv_layout = QGridLayout(niv_group)
        niv_layout.setSpacing(self.scale_size(10))
        
        niv_layout.addWidget(self.create_label("IPAP (cmH₂O):", 12, True), 0, 0)
        self.ipap_min = QSpinBox()
        self.ipap_max = QSpinBox()
        self.configure_spinbox(self.ipap_min, 8, 25, 12)
        self.configure_spinbox(self.ipap_max, 8, 25, 18)
        self.add_min_max(niv_layout, self.ipap_min, self.ipap_max, 0, 1)
        
        niv_layout.addWidget(self.create_label("EPAP (cmH₂O):", 12, True), 1, 0)
        self.epap_min = QSpinBox()
        self.epap_max = QSpinBox()
        self.configure_spinbox(self.epap_min, 4, 12, 5)
        self.configure_spinbox(self.epap_max, 4, 12, 8)
        self.add_min_max(niv_layout, self.epap_min, self.epap_max, 1, 1)
        
        alarm_group = QGroupBox("11. Alarm Configuration")
        alarm_group.setStyleSheet(self.get_groupbox_style())
        alarm_layout = QGridLayout(alarm_group)
        alarm_layout.setSpacing(self.scale_size(10))
                # 11.6 High FiO2 Alarm
        high_fio2_label = self.create_label("High FiO₂ Alarm (%):", 12, True)
        self.alarm_high_fio2 = QSpinBox()
        self.configure_spinbox(self.alarm_high_fio2, 21, 100, 80)
        alarm_layout.addWidget(high_fio2_label, 4, 0)
        alarm_layout.addWidget(self.alarm_high_fio2, 4, 1)

        # 11.7 Low FiO2 Alarm
        low_fio2_label = self.create_label("Low FiO₂ Alarm (%):", 12, True)
        self.alarm_low_fio2 = QSpinBox()
        self.configure_spinbox(self.alarm_low_fio2, 21, 100, 30)
        alarm_layout.addWidget(low_fio2_label, 5, 0)
        alarm_layout.addWidget(self.alarm_low_fio2, 5, 1)
        
        alarm_layout.addWidget(self.create_label("High Pressure Alarm (cmH₂O):", 12, True), 0, 0)
        self.alarm_high_pressure = QSpinBox()
        self.configure_spinbox(self.alarm_high_pressure, 20, 60, 40)
        alarm_layout.addWidget(self.alarm_high_pressure, 0, 1)
        
        alarm_layout.addWidget(self.create_label("Low Tidal Volume (mL):", 12, True), 1, 0)
        self.alarm_low_vt = QSpinBox()
        self.configure_spinbox(self.alarm_low_vt, 100, 500, 250)
        alarm_layout.addWidget(self.alarm_low_vt, 1, 1)
        
        alarm_layout.addWidget(self.create_label("High RR Alarm (bpm):", 12, True), 2, 0)
        self.alarm_high_rr = QSpinBox()
        self.configure_spinbox(self.alarm_high_rr, 20, 60, 35)
        alarm_layout.addWidget(self.alarm_high_rr, 2, 1)
        
        alarm_layout.addWidget(self.create_label("Low Minute Vent (L/min):", 12, True), 3, 0)
        self.alarm_low_mv = QDoubleSpinBox()
        self.alarm_low_mv.setRange(2, 10)
        self.alarm_low_mv.setValue(4)
        self.alarm_low_mv.setStyleSheet(self.get_spinbox_style())
        self.alarm_low_mv.setFont(self.create_label("", 12).font())
        alarm_layout.addWidget(self.alarm_low_mv, 3, 1)
        
        layout.addWidget(adv_group)
        layout.addWidget(niv_group)
        layout.addWidget(alarm_group)
        layout.addStretch()
        
        scroll.setWidget(content)
        tab_layout = QVBoxLayout(tab)
        tab_layout.addWidget(scroll)
        
        self.tabs.addTab(tab, "7. Advanced/Alarms")
    
    def reset_to_defaults(self):
        self.mode_combo.setCurrentIndex(0)
        self.consciousness_combo.setCurrentIndex(1)
        self.synchrony_combo.setCurrentIndex(0)
        
        self.fio2_min.setValue(21)
        self.fio2_max.setValue(60)
        self.copd_check.setChecked(False)
        self.peep_min.setValue(5)
        self.peep_max.setValue(12)
        self.ards_combo.setCurrentIndex(0)
        self.recruit_combo.setCurrentIndex(1)
        
        self.vt_min.setValue(400)
        self.vt_max.setValue(550)
        self.pbw.setValue(70)
        self.mve_min.setValue(5)
        self.mve_max.setValue(8)
        
        self.rr_min.setValue(10)
        self.rr_max.setValue(16)
        self.apnea_rate.setValue(12)
        self.apnea_time.setValue(20)
        
        self.ip_min.setValue(10)
        self.ip_max.setValue(25)
        self.ps_min.setValue(5)
        self.ps_max.setValue(15)
        self.pmax.setValue(40)
        
        self.ti.setValue(1.0)
        self.ie_combo.setCurrentIndex(1)
        self.flow_trigger.setValue(2.0)
        self.pressure_trigger.setValue(-2.0)
        self.peak_flow_min.setValue(40)
        self.peak_flow_max.setValue(80)
        self.flow_pattern.setCurrentIndex(1)

        self.rr_wob_combo.setCurrentIndex(0)
        self.sedation_combo.setCurrentIndex(0)
        self.hemodynamics_combo.setCurrentIndex(0)
        self.alarms_response_combo.setCurrentIndex(0)
        self.weaning_combo.setCurrentIndex(0)
        self.mask_seal_combo.setCurrentIndex(0)

        self.asv_target.setValue(100)
        self.pav_gain.setValue(50)
        self.tube_comp.setValue(50)
        self.ipap_min.setValue(12)
        self.ipap_max.setValue(18)
        self.epap_min.setValue(5)
        self.epap_max.setValue(8)
        self.alarm_high_pressure.setValue(40)
        self.alarm_low_vt.setValue(250)
        self.alarm_high_rr.setValue(35)
        self.alarm_low_mv.setValue(4)
        self.rise_time_spin.setValue(5)
        self.cycling_spin.setValue(25)
        self.alarm_high_fio2.setValue(80)
        self.alarm_low_fio2.setValue(30)
    
    def apply_settings(self):
        settings = {
            'mode': self.mode_combo.currentText(),
            'consciousness': self.consciousness_combo.currentText(),
            'synchrony': self.synchrony_combo.currentText(),
            'fio2': (self.fio2_min.value(), self.fio2_max.value()),
            'copd': self.copd_check.isChecked(),
            'peep': (self.peep_min.value(), self.peep_max.value()),
            'ards': self.ards_combo.currentText(),
            'recruitability': self.recruit_combo.currentText(),
            'vte': (self.vt_min.value(), self.vt_max.value()),
            'pbw': self.pbw.value(),
            'mvent': (self.mve_min.value(), self.mve_max.value()),
            'rr': (self.rr_min.value(), self.rr_max.value()),
            'apnea_rate': self.apnea_rate.value(),
            'apnea_time': self.apnea_time.value(),
            'pip': (self.ip_min.value(), self.ip_max.value()),
            'ps': (self.ps_min.value(), self.ps_max.value()),
            'pmax': self.pmax.value(),
            'ti': self.ti.value(),
            'ie_ratio': self.ie_combo.currentText(),
            'flow_trigger': self.flow_trigger.value(),
            'pressure_trigger': self.pressure_trigger.value(),
            'peak_flow': (self.peak_flow_min.value(), self.peak_flow_max.value()),
            'flow_pattern': self.flow_pattern.currentText(),
            'rise_time': self.rise_time_spin.value(),
            'cycling': self.cycling_spin.value(),
            'alarm_high_fio2': self.alarm_high_fio2.value(),
            'alarm_low_fio2': self.alarm_low_fio2.value(),
            'asv_target': self.asv_target.value(),
            'pav_gain': self.pav_gain.value(),
            'tube_comp': self.tube_comp.value(),
            'ipap': (self.ipap_min.value(), self.ipap_max.value()),
            'epap': (self.epap_min.value(), self.epap_max.value()),
            'alarm_high_pressure': self.alarm_high_pressure.value(),
            'alarm_low_vt': self.alarm_low_vt.value(),
            'alarm_high_rr': self.alarm_high_rr.value(),
            'alarm_low_mv': self.alarm_low_mv.value(),
            'rr_wob': self.rr_wob_combo.currentText(),
            'sedation': self.sedation_combo.currentText(),
            'hemodynamics': self.hemodynamics_combo.currentText(),
            'alarms_response': self.alarms_response_combo.currentText(),
            'weaning': self.weaning_combo.currentText(),
            'mask_seal': self.mask_seal_combo.currentText(),
            
        }
        self.settings_applied.emit(settings)
        self.hide()


# للتجربة المباشرة (اختياري)
if __name__ == "__main__":
    app = QApplication(sys.argv)
    panel = AutoAdjustPanel()
    panel.show()
    sys.exit(app.exec_())