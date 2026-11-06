import sys
import re
import sqlite3
import json
import os
import shutil

# استيراد من ملفاتك الخاصة
try:
    from db_manager import DatabaseManager
except ImportError:
    print("تنبيه: ملف db_manager غير موجود")
from PyQt5.QtCore import pyqtSignal, Qt, QDate, QDateTime # تأكد من وجود pyqtSignal هنا
# توحيد المكتبة إلى PyQt5 فقط ⬇️
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QGridLayout, 
                             QLabel, QLineEdit, QPushButton, QComboBox, 
                             QTabWidget, QTextEdit, QDateEdit, QDateTimeEdit, 
                             QScrollArea, QCheckBox, QGroupBox, QFormLayout, 
                             QHBoxLayout, QMessageBox, QFileDialog)
from PyQt5.QtCore import QDate, Qt, QDateTime, QRegularExpression 
from PyQt5.QtGui import QColor, QPalette, QRegularExpressionValidator

class VentilatorManualInputs(QWidget):
    back_requested = pyqtSignal()
    def __init__(self):
        super().__init__()
        self.setWindowTitle("New Patient Entry")
        self.resize(1200, 900)

        # 1. أولاً: عرّف المتغير validate_resp (قبل استدعاء الـ UI)
        # تأكد أن دالة validate_id_fields موجودة بالفعل في ملفك
        if hasattr(self, 'validate_id_fields'):
            self.validate_resp = self.validate_id_fields
        else:
            # دالة احتياطية لكي لا ينهار البرنامج إذا لم يجد الدالة الأصلية
            self.validate_resp = lambda: None 

        # 2. ثانياً: ابدأ تشغيل الداتا بيس
        self.db = None 
        try:
            from db_manager import DatabaseManager
            self.db = DatabaseManager()
        except Exception as e:
            print(f"Database error: {e}")
        # 3. ثالثاً وأخيراً: ابنِ الواجهة (التي ستبحث الآن عن validate_resp وتجده)
        self.initUI()
        self.required_fields = [
        self.pt_name,
        self.pt_id,
        self.case_id,
        self.hosp_name,
        self.icu_name,
        self.bed_num,
        self.oper_name,
        self.phys_name,
        self.dob,
        self.rr_in,
        self.spo2_in,
    ]
        
    def load_patient_data_to_form(self, data):
        """
        دالة مدمجة وشاملة لتعبئة كافة عناصر الواجهة بناءً على البيانات القادمة من قاعدة البيانات.
        تدعم: النصوص، القوائم المنسدلة، علامات الاختيار، التواريخ، والحسابات التلقائية.
        """
        if not data:
            return

        # قائمة بأنواع العناصر التي نريد البحث عنها وتعبئتها
        widget_types = (QLineEdit, QTextEdit, QComboBox, QCheckBox, QDateTimeEdit, QDateEdit)

        # المرور على كافة العناصر في الصفحة التي تنتمي للأنواع المذكورة أعلاه
        for widget in self.findChildren(widget_types):
            name = widget.objectName()
            
            # التأكد أن العنصر له اسم برمجي وأن هذا الاسم موجود كعمود في البيانات
            if not name or name not in data:
                continue

            val = data[name]
            
            # إذا كانت القيمة فارغة (Null)، نتخطى التعبئة لهذا الحقل أو نضع نصاً فارغاً
            if val is None:
                val = ""

            # --- البدء في توزيع البيانات حسب نوع العنصر ---

            # 1. النصوص البسيطة
            if isinstance(widget, QLineEdit):
                widget.setText(str(val))

            # 2. النصوص الطويلة (الملاحظات)
            elif isinstance(widget, QTextEdit):
                widget.setPlainText(str(val))

            # 3. القوائم المنسدلة (ComboBox)
            elif isinstance(widget, QComboBox):
                index = widget.findText(str(val))
                if index >= 0:
                    widget.setCurrentIndex(index)

            # 4. علامات الاختيار (CheckBox) - معالجة ذكية للقيم المنطقية
            elif isinstance(widget, QCheckBox):
                # نعتبره "مفعلاً" إذا كانت القيمة (1، true، yes) بغض النظر عن حالة الأحرف
                is_checked = str(val).lower() in ['1', 'true', 'yes']
                widget.setChecked(is_checked)

            # 5. التاريخ والوقت (DateTimeEdit)
            elif isinstance(widget, QDateTimeEdit):
                dt = QDateTime.fromString(str(val), "yyyy-MM-dd HH:mm:ss")
                if dt.isValid():
                    widget.setDateTime(dt)

            # 6. التاريخ فقط (DateEdit)
            elif isinstance(widget, QDateEdit):
                d = QDate.fromString(str(val), "yyyy-MM-dd")
                if d.isValid():
                    widget.setDate(d)

        # --- المرحلة النهائية: تحديث الحسابات التلقائية ---
        # بعد تعبئة الطول والوزن وتاريخ الميلاد، نقوم بتحديث الـ BMI والعمر تلقائياً
        if hasattr(self, 'calculate_metrics'):
            self.calculate_metrics()
            
        if hasattr(self, 'calculate_age_from_dob'):
            self.calculate_age_from_dob()
            
        print("✅ تم استيراد بيانات المريض وتحديث الحسابات التلقائية بنجاح.")
    
        

    def initUI(self):
        self.setWindowTitle('Lung Digital Twin Pro - Full Clinical Data Specification')
        self.setGeometry(30, 30, 1200, 900)
        
        # تنسيق CSS احترافي (أضفت ستايل زر الخروج فيه)
        self.setStyleSheet("""
            QWidget { 
                background-color: #1a1c24; 
                color: #ecf0f1; 
                font-family: 'Segoe UI';
            }
            QTabWidget::pane { border: 1px solid #34495e; background-color: #1a1c24; }
            QTabBar::tab { background: #2c313c; color: #aeb9c4; padding: 10px; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background: #3498db; color: white; }
            QLineEdit, QTextEdit, QComboBox, QDateEdit {
                background-color: #252934;
                border: 1px solid #34495e;
                border-radius: 5px;
                padding: 5px;
                color: white;
            }
            QGroupBox { font-weight: bold; border: 1px solid #34495e; margin-top: 20px; color: #3498db; }
            
            /* ستايل جميع الأزرار (مثل زر الحفظ) */
            QPushButton { background-color: #3498db; color: white; border-radius: 8px; padding: 12px; font-weight: bold; }
            
            /* 🟢 ستايل خاص بزر الإغلاق المدمج في التابات */
            QPushButton#exit_tab_btn {
                background-color: #c0392b; /* أحمر */
                border-radius: 4px;
                padding: 5px 15px; /* تصغير الزر ليتناسب مع التابات */
                margin-bottom: 2px;
                margin-right: 2px;
            }
            QPushButton#exit_tab_btn:hover { background-color: #e74c3c; }
        """)

        main_layout = QVBoxLayout()
        self.tabs = QTabWidget()

        # 🟢 السر هنا: إنشاء زر الرجوع ودمجه في الزاوية اليمنى للتابات
        self.btn_exit = QPushButton("✕ Return")
        self.btn_exit.setObjectName("exit_tab_btn") # لكي يأخذ الستايل الأحمر
        self.btn_exit.setCursor(Qt.PointingHandCursor)
        self.btn_exit.clicked.connect(self.back_requested.emit)
        
        # وضع الزر في أقصى يمين التابات
        self.tabs.setCornerWidget(self.btn_exit, Qt.TopRightCorner)

        # --- توزيع الأقسام الـ 15 على التبويبات (نفس كودك لم يتغير) ---
        self.add_scrollable_tab(self.create_id_tab(), "1 & 2: ID & Demographics")
        self.add_scrollable_tab(self.create_clinical_context_tab(), "3: Clinical Context")
        self.add_scrollable_tab(self.create_history_tab(), "4: Medical History")
        self.add_scrollable_tab(self.create_respiratory_status_tab(), "5, 6 & 7: Resp Status & Mechanics")
        self.add_scrollable_tab(self.create_labs_hemo_tab(), "8, 9 & 10: Labs, Hemo & O2")
        self.add_scrollable_tab(self.create_imaging_tab(), "11 & 12: Imaging (CT/X-Ray)")
        self.add_scrollable_tab(self.create_simulation_tab(), "13, 14 & 15: Sim & Notes")

        main_layout.addWidget(self.tabs)

        self.btn_save = QPushButton("Save All Data & Proceed")
        self.btn_save.clicked.connect(self.save_data)
        main_layout.addWidget(self.btn_save)
        self.setup_object_names()
        
        self.setLayout(main_layout)



    def upload_ct_image(self):
        """فتح نافذة اختيار الصورة وتخزين مسارها مؤقتاً"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select CT Image", "", "Image Files (*.png *.jpg *.jpeg *.bmp)"
        )
        
        if file_path:
            self.temp_ct_source = file_path 
            filename = os.path.basename(file_path)
            self.btn_ct_upload.setText(f"Selected 🆗: {filename}")
            self.btn_ct_upload.setStyleSheet("background-color: #e1f5fe; color: #01579b; font-weight: bold;")

    def process_and_save_image(self, patient_id):
        """نقل الصورة وإعادة تسميتها برقم المريض لحمايتها من الضياع"""
        if not hasattr(self, 'temp_ct_source') or not self.temp_ct_source:
            return "" # إذا لم يختر صورة، نرجع مساراً فارغاً

        # إنشاء مجلد للصور داخل مجلد البرنامج إذا لم يكن موجوداً
        images_dir = "patient_ct_images"
        if not os.path.exists(images_dir):
            os.makedirs(images_dir)

        # استخراج الامتداد وإنشاء اسم جديد
        _, ext = os.path.splitext(self.temp_ct_source)
        new_filename = f"CT_Scan_{patient_id}{ext}"
        dest_path = os.path.join(images_dir, new_filename)

        try:
            shutil.copy2(self.temp_ct_source, dest_path)
            self.current_ct_path = dest_path
            return dest_path
        except Exception as e:
            QMessageBox.warning(self, "Image Error", f"Failed to save image: {str(e)}")
            return ""

    
    def save_data(self):
        """دالة الحفظ الشاملة للبيانات والصور"""
        # تحديث التحقق لجميع الحقول
        self.validate_id_fields()
        self.validate_dates()  # للتأكد من adm_date أيضاً

        # التحقق من جميع الحقول الإجبارية باستخدام الحالة المخزنة
        invalid_fields = []
        for field in self.required_fields:
            state = getattr(field, '_validation_state', None)
            if state != 'good':
                # محاولة الحصول على اسم وصفي للحقل
                label = ""
                if hasattr(field, 'objectName') and field.objectName():
                    label = field.objectName().replace('_', ' ').title()
                elif hasattr(field, 'placeholderText'):
                    label = field.placeholderText() or "حقل"
                else:
                    label = "حقل إجباري"
                invalid_fields.append(label)

        if invalid_fields:
            QMessageBox.warning(
                self,
                "خطأ في التحقق",
                "لا يمكن الحفظ، الحقول التالية غير صحيحة أو ناقصة:\n• " + "\n• ".join(invalid_fields)
            )
            return

        # باقي الكود لجمع البيانات (بدون أي تحقق إضافي)
        name = self.pt_name.text().strip()
        pid = self.pt_id.text().strip()
        patient_data = {}

        def clean_key(text):
            if not text: return "unknown"
            return "".join([c if c.isalnum() else "_" for c in str(text)]).strip("_").lower()

        # 2. معالجة وحفظ الصورة
        final_image_path = self.process_and_save_image(pid)
        
        # --- إضافة سطر استخراج اسم الصورة فقط ---
        import os
        image_name = os.path.basename(final_image_path) if final_image_path else ""
        # ---------------------------------------

        # 3. سحب البيانات بدقة عالية
        for cb in self.findChildren(QComboBox):
            if cb.objectName():
                patient_data[clean_key(cb.objectName())] = cb.currentText()

        for le in self.findChildren(QLineEdit):
            if le.objectName():
                patient_data[clean_key(le.objectName())] = le.text()

        for chk in self.findChildren(QCheckBox):
            key = chk.objectName() if chk.objectName() else f"chk_{chk.text()}"
            patient_data[clean_key(key)] = "Yes" if chk.isChecked() else "No"

        for te in self.findChildren(QTextEdit):
            if te.objectName():
                patient_data[clean_key(te.objectName())] = te.toPlainText()

        for dt in self.findChildren((QDateTimeEdit, QDateEdit)):
            if dt.objectName():
                val = dt.dateTime().toString("yyyy-MM-dd HH:mm:ss") if isinstance(dt, QDateTimeEdit) else dt.date().toString("yyyy-MM-dd")
                patient_data[clean_key(dt.objectName())] = val

        # تأكيد الهوية وحفظ المسار والاسم
        patient_data["patient_id"] = pid
        patient_data["patient_name"] = name
        patient_data["ct_image_path"] = final_image_path
        patient_data["ct_image_name"] = image_name # حفظ الاسم هنا

        # 4. إرسال البيانات للداتا بيس
        success, message = self.db.save_patient(patient_data)
        
        if success:
            QMessageBox.information(self, "نجاح", f"تم حفظ بيانات ({name}) والصور بنجاح!")
            # ملاحظة: تم حذف سطر reset_all_inputs لتبقى البيانات معروضة
        else:
            QMessageBox.critical(self, "فشل", f"حدث خطأ أثناء الحفظ: {message}")

    def add_scrollable_tab(self, widget, title):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        self.tabs.addTab(scroll, title)

    def setup_object_names(self):
        """ربط الخانات بأسماء أعمدة قاعدة البيانات تماماً كما في الـ PDF"""
        # 1. Demographics & Admin
        self.pt_id.setObjectName("patient_id") # أهم خانة (مفتاح البحث)
        self.pt_name.setObjectName("patient_name")
        self.case_id.setObjectName("case_id")
        self.hosp_name.setObjectName("hospital_name")
        self.icu_name.setObjectName("icu_unit_name")
        self.bed_num.setObjectName("bed_number")
        self.sim_id.setObjectName("simulation_session_id")
        self.oper_name.setObjectName("operator_name")
        self.phys_name.setObjectName("physician_supervisor")
        self.gender_combo.setObjectName("gender")
        self.height_input.setObjectName("height_cm")
        self.weight_input.setObjectName("weight_kg")

        # 2. Resp & ABG
        self.rr_in.setObjectName("baseline_rr")
        self.spo2_in.setObjectName("oxygen_saturation_admission")
        self.ph_in.setObjectName("ph")
        self.pao2_in.setObjectName("pao2")
        self.paco2_in.setObjectName("paco2")
        self.hco3_in.setObjectName("hco3")
        self.be_in.setObjectName("base_excess")
        self.sao2_lab.setObjectName("sao2")
        self.lactate_in.setObjectName("lactate")
        self.hb_in.setObjectName("hemoglobin")
        
        

    # --- دالة مساعدة لتغيير ألوان التحقق ---
    def set_input_status(self, widget, status, message=""):
        widget._validation_state = status   # ⬅️ تخزين الحالة
        if status == "critical":
            widget.setStyleSheet("background-color: #3d1414; border: 2px solid #8B0000;") # أحمر
            widget.setToolTip(f"CRITICAL ERROR: {message}")
        elif status == "above_average":
            widget.setStyleSheet("background-color: #3d1414; border: 1px solid #8B0000; color: white;")
        elif status == "warning":
            widget.setStyleSheet("background-color: #dbac1c; color:black; border: 2px solid #8f700f;") # أصفر
            widget.setToolTip(f"WARNING: {message}")
        elif status == "good":
            widget.setStyleSheet("") # أخضر
            widget.setToolTip("Valid Input")
        else:
            widget.setStyleSheet("")

    # ---------------------------------------------------------
    # TAB 1: Identification & Demographics (Sections 1 & 2)
    # ---------------------------------------------------------
    def create_id_tab(self):
        widget = QWidget()
        layout = QFormLayout()

        layout.addRow(QLabel("<h3>1- Patient Identification & Case Management</h3>"))
        
        # 1.1 Patient Name (Strict Validation)
        self.pt_name = QLineEdit()
        self.pt_name.setMaxLength(150)
        self.pt_name.setPlaceholderText("Required: Letters, spaces, hyphens only")
        self.pt_name.textChanged.connect(self.validate_id_fields)
        layout.addRow("Patient Name:", self.pt_name)
        
        # 1.2 Patient ID (Alphanumeric)
        self.pt_id = QLineEdit()
        self.pt_id.setMaxLength(50)
        self.pt_id.setPlaceholderText("Required: Alphanumeric, unique")
        self.pt_id.textChanged.connect(self.validate_id_fields)
        layout.addRow("Patient ID:", self.pt_id)
        
        # 1.3 Case ID
        self.case_id = QLineEdit()
        self.case_id.setMaxLength(50)
        self.case_id.textChanged.connect(self.validate_id_fields)
        layout.addRow("Case ID:", self.case_id)
        
        # 1.4 Hospital Name
        self.hosp_name = QLineEdit()
        self.hosp_name.setMaxLength(150)
        self.hosp_name.textChanged.connect(self.validate_id_fields)
        layout.addRow("Hospital Name:", self.hosp_name)
        
        # 1.5 ICU Unit Name
        self.icu_name = QLineEdit()
        self.icu_name.setMaxLength(100)
        self.icu_name.textChanged.connect(self.validate_id_fields)
        layout.addRow("ICU Unit Name:", self.icu_name)
        
        # 1.6 Bed Number
        self.bed_num = QLineEdit()
        self.bed_num.setMaxLength(20)
        self.bed_num.setPlaceholderText("Req: Alphanumeric")
        self.bed_num.textChanged.connect(self.validate_id_fields)
        layout.addRow("Bed Number:", self.bed_num)
        
        # 1.7 Admission Date
        self.adm_date = QDateTimeEdit(QDateTime.currentDateTime())
        self.adm_date.setObjectName("admission_datetime")
        self.adm_date.setCalendarPopup(True)  # يفتح تقويم للاختيار
        self.adm_date.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.adm_date.dateTimeChanged.connect(self.validate_dates)
        layout.addRow("Admission Date:", self.adm_date)
        
        # 1.8 Simulation Session ID
        self.sim_id = QLineEdit()
        self.sim_id.setObjectName("simulation_session_id")
        self.sim_id.setPlaceholderText("Unique Session ID")
        self.sim_id.textChanged.connect(self.validate_id_fields)
        layout.addRow("Simulation Session ID:", self.sim_id)
        
        # 1.9 Operator Name
        self.oper_name = QLineEdit()
        self.oper_name.setMaxLength(100)
        self.oper_name.textChanged.connect(self.validate_id_fields)
        layout.addRow("Operator Name:", self.oper_name)
        
        # 1.10 Physician Supervisor
        self.phys_name = QLineEdit()
        self.phys_name.setMaxLength(100)
        self.phys_name.textChanged.connect(self.validate_id_fields)
        layout.addRow("Physician Supervisor:", self.phys_name)
        
        # 1.11 Timestamp
        self.timestamp = QLineEdit()
        self.timestamp.setReadOnly(True)
        self.timestamp.setText(QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm"))
        layout.addRow("Date and Time Stamp:", self.timestamp)
        layout.addRow(QLabel("<h3>2- Patient Demographics</h3>"))

        # 2.2 Date of Birth
        self.dob = QDateEdit(QDate.currentDate().addYears(-30)) # افتراض عمر 30 سنة
        # 2.1 Age Breakdown
        self.dob.setObjectName("date_of_birth")

        self.dob.setCalendarPopup(True) 
        self.dob.setDisplayFormat("yyyy-MM-dd")
        self.dob.setObjectName("date_of_birth")

        self.dob.dateChanged.connect(self.calculate_age_from_dob) # ربط الحساب تلقائياً
        layout.addRow("Date of Birth:", self.dob)

        # 2.1 Age Breakdown
        age_layout = QHBoxLayout()
        self.age_y = QLineEdit(); self.age_y.setPlaceholderText("Years")
        self.age_m = QLineEdit(); self.age_m.setPlaceholderText("Months")
        self.age_d = QLineEdit(); self.age_d.setPlaceholderText("Days")
        age_layout.addWidget(self.age_y); age_layout.addWidget(self.age_m); age_layout.addWidget(self.age_d)
        layout.addRow("Age:", age_layout)
        self.age_y.textChanged.connect(self.validate_id_fields)

        
        # 2.3 Gender
        self.gender_combo = QComboBox()
        self.gender_combo.setObjectName("gender")
        self.gender_combo.addItems(["Male", "Female"])
        self.gender_combo.currentTextChanged.connect(self.calculate_metrics)
        layout.addRow("Gender:", self.gender_combo)

        # 2.4 & 2.5 Height/Weight
        self.height_input = QLineEdit()
        self.height_input.setObjectName("height_cm")
        self.height_input.setPlaceholderText("")
        self.height_input.textChanged.connect(self.calculate_metrics)
        self.height_input.textChanged.connect(self.validate_id_fields)
        layout.addRow("Height (cm):", self.height_input)

        self.weight_input = QLineEdit()
        self.weight_input.setObjectName("weight_kg")
        self.weight_input.setPlaceholderText("")
        self.weight_input.textChanged.connect(self.calculate_metrics)
        self.weight_input.textChanged.connect(self.validate_id_fields)
        layout.addRow("Weight (kg):", self.weight_input)

        # 2.6 - 2.8 Auto Calculated
        self.bsa_output = QLineEdit(readOnly=True)
        self.bsa_output.setObjectName("bsa_m2")
        self.bmi_output = QLineEdit(readOnly=True)
        self.bmi_output.setObjectName("bmi")
        self.pbw_output = QLineEdit(readOnly=True)
        self.pbw_output.setObjectName("pbw_kg")
        
        layout.addRow("BSA (m²):", self.bsa_output)
        layout.addRow("BMI (kgm²):", self.bmi_output)
        layout.addRow("PBW (kg):", self.pbw_output)

        # 2.9 Ethnicity
        self.ethnicity_combo = QComboBox()
        self.ethnicity_combo.setObjectName("ethnicity") # <--- هذا هو السطر الناقص الذي يحل المشكلة!
        self.ethnicity_combo.addItems(["Prefer Not to Say", "Middle Eastern" ,"Arab", "North African","Sub-Saharan African","African American", "Caucasian / White", "European", "South Asian","East Asian","Southeast Asian","Central Asian", "Hispanic / Latino", "Native American","Pacific Islander","Mixed Ethnicity", "Other"])
        layout.addRow("Ethnicity:", self.ethnicity_combo)

        widget.setLayout(layout)
        return widget

    # 2. تصحيح دالة التحقق من التاريخ (إضافة التنسيق الجديد)
    def validate_dates(self):
        if self.adm_date.dateTime() > QDateTime.currentDateTime():
            self.set_input_status(self.adm_date, "critical", "Date cannot be in the future")
        else:
            self.set_input_status(self.adm_date, "good")

    
    def calculate_age_from_dob(self):
        birth_date = self.dob.date().toPyDate()
        today = QDate.currentDate().toPyDate()
        
        years = today.year - birth_date.year
        months = today.month - birth_date.month
        days = today.day - birth_date.day

        if days < 0:
            months -= 1
            # حساب الأيام المتبقية في الشهر السابق
            days += 30 
        if months < 0:
            years -= 1
            months += 12

        self.age_y.setText(str(years))
        self.age_m.setText(str(months))
        self.age_d.setText(str(days))
    
    def validate_logic(self, field, label, rule="alphanumeric"):
       
        text = field.text().strip()
        
        if not text:
            self.set_input_status(field, "critical", f"{label} is Required")
            return

        if rule == "alphanumeric":
            pattern = r"^[a-zA-Z0-9\u0600-\u06FF\s\-]+$"
            if not re.match(pattern, text):
                self.set_input_status(field, "critical", f"{label}: Only letters, numbers, and hyphens")
            else:
                self.set_input_status(field, "good")
                
        elif rule == "numeric":
            # يسمح بالأرقام والنقاط العشرية (مثل 70.5)
            text_fixed = text.replace('.', '', 1) # حذف نقطة واحدة للتأكد من أنه رقم
            if not text_fixed.isdigit():
                self.set_input_status(field, "critical", f"{label}: Numbers only")
            else:
                self.set_input_status(field, "good")
                
        elif rule == "any":
            # أي شيء يكتبه المستخدم مقبول طالما ليس فارغاً
            self.set_input_status(field, "good")

    def validate_id_fields(self):
        """دالة شاملة للتحقق من الهوية + البيانات الإدارية + المؤشرات التنفسية"""
        
        # --- 1. التحقق من هوية المريض والاسم ---
        name = self.pt_name.text().strip()
        name_pattern = r"^[a-zA-Z\u0600-\u06FF\s\-]+$" 
        
        if not name:
            self.set_input_status(self.pt_name, "critical", "Required Field")
        elif not re.match(name_pattern, name):
            self.set_input_status(self.pt_name, "critical", "Letters and hyphens only")
        else:
            self.set_input_status(self.pt_name, "good")

        # رقم المريض (Patient ID)
        pid = self.pt_id.text().strip()
        pid_pattern = r"^[a-zA-Z0-9\u0600-\u06FF\s\-]+$" 
        
        if not pid:
            self.set_input_status(self.pt_id, "critical", "Patient ID is Required")
        elif not re.match(pid_pattern, pid):
            self.set_input_status(self.pt_id, "critical", "Only Alphanumeric and dash (-) allowed")
        else:
            self.set_input_status(self.pt_id, "good")

        # العمر وتاريخ الميلاد
        age_val = self.age_y.text().strip()
        if not age_val or age_val == "0":
            self.set_input_status(self.dob, "critical", "Please select a valid Date of Birth")
        else:
            self.set_input_status(self.dob, "good")

        # --- 2. الخانات الإدارية (التسمية والتحقق) ---
        self.hosp_name.setObjectName("hospital_name")
        self.validate_logic(self.hosp_name, "Hospital", "any")

        # خانة الـ Case ID
        self.case_id.setObjectName("case_id")
        self.validate_logic(self.case_id, "Case ID", "alphanumeric")

        # خانة رقم السرير
        self.bed_num.setObjectName("bed_number")
        self.validate_logic(self.bed_num, "Bed Number", "alphanumeric")

        # خانة اسم المشغل
        self.oper_name.setObjectName("operator_name")
        self.validate_logic(self.oper_name, "Operator", "any")

        # خانة الطبيب المسؤول
        self.phys_name.setObjectName("physician_supervisor")
        self.validate_logic(self.phys_name, "Physician", "any")

        # خانة وحدة العناية
        self.icu_name.setObjectName("icu_unit_name")
        self.validate_logic(self.icu_name, "ICU Unit Name", "any")

         # 3. المقاييس الحيوية (Numeric)
        #self.validate_logic(self.height_input, "Height", "numeric")
        #self.validate_logic(self.weight_input, "Weight", "numeric")
        
        # --- 4. المؤشرات التنفسية (التي كانت في validate_resp سابقا) ---
        
        
        # معدل التنفس (RR): 5-60
        try:
            val = float(self.rr_in.text())
            if val < 5 or val > 60: 
                self.set_input_status(self.rr_in, "critical", "Out of range (5-60)")
            else: 
                self.set_input_status(self.rr_in, "good")
        except: 
            self.set_input_status(self.rr_in, "")

        # نسبة الأكسجين (SpO2)
        try:
            val = float(self.spo2_in.text())
            if val < 50 or val > 100: 
                self.set_input_status(self.spo2_in, "critical", "Hypoxemia (<88%)")
            
            else: 
                self.set_input_status(self.spo2_in, "good")
        except: 
            self.set_input_status(self.spo2_in, "")

        # مطاوعة الرئة (Compliance)
        try:
            val = float(self.static_comp.text())
            if val < 40: 
                self.set_input_status(self.static_comp, "warning", "Low Compliance")
            elif val > 80: 
                self.set_input_status(self.static_comp, "warning", "High Compliance")
            else: 
                self.set_input_status(self.static_comp, "good")
        except: 
            self.set_input_status(self.static_comp, "")

        try:
            val = float(self.dynamic_comp.text())
            if val < 40: 
                self.set_input_status(self.dynamic_comp, "warning", "Low Dynamic")
            elif val > 80: 
                self.set_input_status(self.dynamic_comp, "warning", "High Dynamic")
            else: 
                self.set_input_status(self.dynamic_comp, "good")
        except: 
            self.set_input_status(self.dynamic_comp, "")

        try:
            val = float(self.airway_res.text())
            if val < 10: 
                self.set_input_status(self.airway_res, "warning", "Low  Airway Resistance")
            elif val > 20: 
                self.set_input_status(self.airway_res, "warning", "High  Airway Resistance")
            else: 
                self.set_input_status(self.airway_res, "good")
        except: 
            self.set_input_status(self.airway_res, "")

        try:
            val = float(self.chest_comp.text())
            if val < 40: 
                self.set_input_status(self.chest_comp, "warning", "Low Chest Wall Compliance")
            elif val > 80: 
                self.set_input_status(self.chest_comp, "warning", "High Chest Wall Compliance")
            else: 
                self.set_input_status(self.chest_comp, "good")
        except: 
            self.set_input_status(self.chest_comp, "")

        try:
            val = (self.recruit.currentText())
            if val == "High": 
                self.set_input_status(self.recruit, "warning", "High Recruitability")
            elif val == "Low": 
                self.set_input_status(self.recruit, "warning", "Low Recruitability")
            else: 
                self.set_input_status(self.recruit, "good")
        except: 
            self.set_input_status(self.recruit, "")

        # مؤشر التيبس (Stiffness Index): 1.5 - 3
        try:
            val = float(self.stiff_idx.text())
            if val < 1.5: 
                self.set_input_status(self.stiff_idx, "warning", "Low Stiffness")
            elif val > 3: 
                self.set_input_status(self.stiff_idx, "warning", "High Stiffness")
            else: 
                self.set_input_status(self.stiff_idx, "good")
        except: 
            self.set_input_status(self.stiff_idx, "")
        
        # 1. التحقق من Air Trapping
        try:
            # لاحظ استخدمنا .currentText() وحرف Y كبير كما في القائمة
            if self.air_trap.currentText() == "Yes": 
                self.set_input_status(self.air_trap, "warning", "Air Trapping Detected")
            else: 
                self.set_input_status(self.air_trap, "good")
        except AttributeError:
            pass # في حال لم يتم إنشاء العنصر بعد

        # 2. التحقق من Auto-PEEP
        try:
            if self.auto_peep.currentText() == "Yes": 
                self.set_input_status(self.auto_peep, "warning", "Auto-PEEP Detected")
            else: 
                self.set_input_status(self.auto_peep, "good")
        except AttributeError:
            pass
           
        # معدل التنفس (RR): إجباري + رقمي + نطاق محدد
        rr_text = self.rr_in.text().strip()
        if not rr_text:
            self.set_input_status(self.rr_in, "critical", "Required Field")
        else:
            try:
                val = float(rr_text)
                if val < 5 or val > 60: 
                    self.set_input_status(self.rr_in, "critical", "Out of range (5-60)")
                else: 
                    self.set_input_status(self.rr_in, "good")
            except: 
                self.set_input_status(self.rr_in, "critical", "Numbers only")

        # نسبة الأكسجين (SpO2): إجباري + رقمي
        spo2_text = self.spo2_in.text().strip()
        if not spo2_text:
            self.set_input_status(self.spo2_in, "critical", "Required Field")
        else:
            try:
                val = float(spo2_text)
                if val < 50 or val > 100: 
                    self.set_input_status(self.spo2_in, "critical", "Invalid Range")
                else: 
                    self.set_input_status(self.spo2_in, "good")
            except: 
                self.set_input_status(self.spo2_in, "critical", "Numbers only")
        
       

        


    def calculate_metrics(self):
        # 1. تعريف متغيرات للمساعدة في ضبط الحالة
        h_valid = False
        w_valid = False
        h = None
        w = None

        # --- التعامل مع الطول ---
        h_txt = self.height_input.text().strip()
        if not h_txt:
            self.set_input_status(self.height_input, "default") # لون عادي للفارغ
        else:
            try:
                h = float(h_txt)
                # هنا الشرط الحاسم: إذا أقل من 30 أو أكثر من 300
                if h < 30 or h > 300:
                    self.set_input_status(self.height_input, "critical", "Range: 30-300 cm")
                    h = None # نعتبره غير موجود للحسابات
                else:
                    self.set_input_status(self.height_input, "good")
                    h_valid = True
            except ValueError:
                self.set_input_status(self.height_input, "critical", "Must be a number")

        # --- التعامل مع الوزن ---
        w_txt = self.weight_input.text().strip()
        if not w_txt:
            self.set_input_status(self.weight_input, "default")
        else:
            try:
                w = float(w_txt)
                # هنا الشرط الحاسم: إذا أقل من 0.5 أو أكثر من 500
                if w < 0.5 or w > 500:
                    self.set_input_status(self.weight_input, "critical", "Range: 0.5-500 kg")
                    w = None
                else:
                    self.set_input_status(self.weight_input, "good")
                    w_valid = True
            except ValueError:
                self.set_input_status(self.weight_input, "critical", "Must be a number")

        # --- الحسابات (تتم فقط إذا كان الاثنان صحيحين) ---
        if h_valid and w_valid and h and w:
            try:
                # BMI Calculation
                bmi = w / ((h / 100) ** 2)
                self.bmi_output.setText(f"{bmi:.2f}")

                # تلوين الـ BMI
                if bmi < 18.5:
                    self.set_input_status(self.bmi_output, "warning", "Underweight")
                elif 18.5 <= bmi <= 24.9:
                    self.set_input_status(self.bmi_output, "good", "Normal")
                elif 25 <= bmi <= 29.9:
                    # برتقالي غامق لزيادة الوزن
                    self.bmi_output.setStyleSheet("background-color: #2d2010; border: 1px solid #ff9800; color: white;")
                    self.bmi_output.setToolTip("Overweight")

                else:
                    self.bmi_output.setStyleSheet("background-color: #2e1a2e; border: 1px solid #a855f7; color: white;")
                    self.bmi_output.setToolTip("Obese")

                # BSA Calculation
                bsa = (h * w / 3600) ** 0.5
                self.bsa_output.setText(f"{bsa:.2f}")

                # PBW Calculation
                gender = self.gender_combo.currentText()
                base = 50 if gender == "Male" else 45.5
                pbw = base + 0.91 * (h - 152.4)
                self.pbw_output.setText(f"{max(0, pbw):.2f}")

            except ZeroDivisionError:
                pass
        else:
            # إذا كان هناك خطأ في المدخلات، نمسح النتائج حتى لا تضلل المستخدم
            self.bmi_output.clear()
            self.bsa_output.clear()
            self.pbw_output.clear()
            self.set_input_status(self.bmi_output, "default")

     # ---------------------------------------------------------
    # TAB 2: Clinical Context (Section 3)
    # ---------------------------------------------------------
    def create_clinical_context_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()

        layout.addWidget(QLabel("<h3>3- Admission Clinical Context</h3>"))
        
        # 3.1 Reason
        layout.addWidget(QLabel("3.1 Reason for ICU Admission:"))
        self.reason_input = QTextEdit(); self.reason_input.setMaximumHeight(60)
        self.reason_input.setObjectName("admission_reason") # <-- تمت إضافة الاسم البرمجي
        self.reason_input.setPlaceholderText("Describe clinical reason for ICU admission...")
        layout.addWidget(self.reason_input)
        
        # 3.2 Primary Diagnosis
        layout.addWidget(QLabel("3.2 Primary Diagnosis:"))
        self.prim_diag = QTextEdit(); self.prim_diag.setMaximumHeight(60)
        self.prim_diag.setObjectName("primary_diagnosis") # <-- تمت إضافة الاسم البرمجي
        layout.addWidget(self.prim_diag)

        # 3.3 Secondary Diagnoses
        layout.addWidget(QLabel("3.3 Secondary Diagnoses:"))
        self.sec_diag = QTextEdit(); self.sec_diag.setMaximumHeight(60)
        self.sec_diag.setObjectName("secondary_diagnoses") # <-- تمت إضافة الاسم البرمجي
        layout.addWidget(self.sec_diag)

        # 3.4 Admission Type
        layout.addWidget(QLabel("3.4 Admission Type:"))
        self.adm_type_combo = QComboBox()
        self.adm_type_combo.setObjectName("admission_type") # <-- تمت إضافة الاسم البرمجي
        self.adm_type_combo.addItems(["Medical", "Surgical", "Trauma", "Post-operative", "Other"])
        self.adm_other_note = QLineEdit(); self.adm_other_note.setPlaceholderText("Specify if Other")
        self.adm_other_note.setObjectName("admission_type_other") # <-- تمت إضافة الاسم البرمجي
        self.adm_other_note.hide()
        self.adm_type_combo.currentTextChanged.connect(lambda t: self.adm_other_note.show() if t == "Other" else self.adm_other_note.hide())
        layout.addWidget(self.adm_type_combo)
        layout.addWidget(self.adm_other_note)

        # 3.5 Mechanical Ventilation Indication
        layout.addWidget(QLabel("3.5 Mechanical Ventilation Indication:"))
        self.vent_ind_combo = QComboBox()
        self.vent_ind_combo.setObjectName("vent_indication") # <-- تمت إضافة الاسم البرمجي
        self.vent_ind_combo.addItems(["None", "Hypoxemic respiratory failure", "Hypercapnic respiratory failure", "Airway protection", "Neurological indication", "Post anesthesia support", "Other"])
        self.vent_other_note = QLineEdit(); self.vent_other_note.setPlaceholderText("Specify if Other")
        self.vent_other_note.setObjectName("vent_indication_other") # <-- تمت إضافة الاسم البرمجي
        self.vent_other_note.hide()
        self.vent_ind_combo.currentTextChanged.connect(lambda t: self.vent_other_note.show() if t == "Other" else self.vent_other_note.hide())
        layout.addWidget(self.vent_ind_combo)
        layout.addWidget(self.vent_other_note)

        widget.setLayout(layout)
        return widget

    # ---------------------------------------------------------
    # TAB 3: Medical History (Section 4)
    # ---------------------------------------------------------
    def create_history_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()

        layout.addWidget(QLabel("<h3>4- Past Medical History</h3>"))
        
        # 4.1 Pulmonary
        layout.addWidget(self.create_smart_group("4.1 Pulmonary History", [
            "COPD - Chronic Obstructive Pulmonary Disease", "Asthma", "Interstitial Lung Disease", "ARDS - Acute Respiratory Distress Syndrome", "Pneumonia", "Tuberculosis"
        ]))
        
        # 4.2 Cardiovascular
        layout.addWidget(self.create_smart_group("4.2 Cardiovascular History", [
            "Heart Failure", "Hypertension", "Ischemic Heart Disease"
        ]))
        
        # 4.3 Other Conditions
        layout.addWidget(self.create_smart_group("4.3 Other Medical Conditions", [
            "Diabetes Mellitus Type 1", "Diabetes Mellitus Type 2", "Chronic Kidney Disease", "Liver Disease", "Obesity", "Immunosuppression"
        ]))

        # --- هذا الجزء كان ناقصاً وأضفته لك لكي لا يحدث خطأ ---
        layout.addWidget(QLabel("<b>Smoking Status:</b>"))
        self.smoking_combo = QComboBox() 
        self.smoking_combo.addItems(["Never Smoked", "Ex-Smoker", "Current Smoker", "Passive Smoker"])
        self.smoking_combo.setObjectName("smoking_status") # تم إضافة الاسم البرمجي
        layout.addWidget(self.smoking_combo)
        # --------------------------------------------------------

        widget.setLayout(layout)
        return widget

    def create_smart_group(self, title, options):
        clean_title = title.replace(" ", "_").lower()
        group = QGroupBox(title)
        layout = QVBoxLayout()
        group_items = [] 

        # 1. خيار None
        none_cb = QCheckBox("None")
        none_cb.setObjectName(f"chk_none_{clean_title}")
        none_cb.setChecked(True)
        none_cb.setStyleSheet("color: #ff9800; font-weight: bold; margin-bottom: 5px;")
        layout.addWidget(none_cb)

        # 2. إضافة الخيارات مع نوت لكل منها
        extended_options = options + ["Others"]
        
        for option in extended_options:
            # === التعديل الجذري لحل مشكلة اختفاء الأوذر ===
            if option == "Others":
                clean_option = f"others_{clean_title}" # يجعل الاسم فريداً لكل قسم
            else:
                clean_option = option.replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "").lower()
            
            cb = QCheckBox(option)
            cb.setObjectName(f"chk_{clean_option}")
            
            note_input = QLineEdit()
            note_input.setObjectName(f"note_{clean_option}")
            note_input.setPlaceholderText(f"Notes for {option}...")
            note_input.setVisible(False) 
            note_input.setStyleSheet("margin-left: 20px; background-color: #252525; border: 1px solid #444; color: white;")
            note_input.setMaxLength(1000) 

            layout.addWidget(cb)
            layout.addWidget(note_input)
            group_items.append({'cb': cb, 'note': note_input})

        

        # 3. دالة المنطق (Logic)
        def handle_logic(clicked_cb):
            if clicked_cb == none_cb:
                if none_cb.isChecked():
                    for item in group_items:
                        item['cb'].blockSignals(True)
                        item['cb'].setChecked(False)
                        item['cb'].blockSignals(False)
                        item['note'].setVisible(False)
                        item['note'].clear()
                else:
                    if not any(item['cb'].isChecked() for item in group_items):
                        none_cb.blockSignals(True)
                        none_cb.setChecked(True)
                        none_cb.blockSignals(False)
            
            else:
                if clicked_cb.isChecked():
                    none_cb.blockSignals(True)
                    none_cb.setChecked(False)
                    none_cb.blockSignals(False)
                
                for item in group_items:
                    if item['cb'] == clicked_cb:
                        item['note'].setVisible(clicked_cb.isChecked())
                        if clicked_cb.isChecked():
                            item['note'].setFocus()

                if not any(item['cb'].isChecked() for item in group_items):
                    none_cb.blockSignals(True)
                    none_cb.setChecked(True)
                    none_cb.blockSignals(False)

        # ربط الـ None بالمنطق
        none_cb.toggled.connect(lambda checked: handle_logic(none_cb))


        # ربط بقية الخيارات بالمنطق
        for item in group_items:
            checkbox = item['cb']
            checkbox.toggled.connect(lambda checked, c=checkbox: handle_logic(c))


        group.setLayout(layout)
        return group

    # ---------------------------------------------------------
    # TAB 4: Resp Status & Mechanics (Sections 5, 6, 7)
    # ---------------------------------------------------------
    def create_respiratory_status_tab(self):
        widget = QWidget()
        layout = QFormLayout()

        layout.addRow(QLabel("<h3>5- Current Respiratory Status</h3>"))
        
        self.rr_in = QLineEdit(placeholderText=" 5 – 60")
        self.rr_in.setObjectName("baseline_rr")
        self.rr_in.textChanged.connect(self.validate_resp)
        layout.addRow("5.1  Baseline Respiratory Rate (breaths/min):", self.rr_in)

        self.spo2_in = QLineEdit(placeholderText=" 50 – 100%")
        self.spo2_in.setObjectName("oxygen_saturation_admission")
        self.spo2_in.textChanged.connect(self.validate_resp)
        layout.addRow("5.2 SpO2 on Admission (%):", self.spo2_in)

        self.wob = QComboBox(); self.wob.addItems(["Mild", "Moderate", "Severe"])
        self.wob.setObjectName("work_of_breathing") # تمت الإضافة
        layout.addRow("5.3 Work of Breathing:", self.wob)

        self.muscles = QComboBox(); self.muscles.addItems(["No", "Yes"])
        self.muscles.setObjectName("accessory_muscles") # تمت الإضافة
        layout.addRow("5.4 Accessory Muscles:", self.muscles)

        self.pattern = QComboBox(); self.pattern.addItems(["Regular", "Tachypnea", "Bradypnea", "Irregular"])
        self.pattern.setObjectName("breathing_pattern") # تمت الإضافة
        layout.addRow("5.5 Breathing Pattern:", self.pattern)

        self.cyanosis = QComboBox(); self.cyanosis.addItems(["No", "Yes"])
        self.cyanosis.setObjectName("cyanosis") # تمت الإضافة
        layout.addRow("5.6 Cyanosis:", self.cyanosis)

        layout.addRow(QLabel("<h3>6- Lung Disease Pattern</h3>"))
        self.disease_combo = QComboBox()
        self.disease_combo.addItems(["Normal Lung", "ARDS", "Pneumonia", "COPD", "Pulmonary Edema", "Asthma", "Pulmonary Fibrosis", "Atelectasis", "Mixed", "Other"])
        self.disease_combo.setObjectName("lung_disease_pattern") # تمت الإضافة
        layout.addRow("6.1 Disease Type:", self.disease_combo)

        self.severity_combo = QComboBox()
        self.severity_combo.addItems(["Mild", "Moderate", "Severe"])
        self.severity_combo.setObjectName("lung_disease_severity") # تمت الإضافة
        layout.addRow("Severity:", self.severity_combo)

        self.other_lung_note = QLineEdit(placeholderText="Please specify the disease...")
        self.other_lung_note.setObjectName("lung_disease_other") # تمت الإضافة
        self.other_lung_note.setVisible(False) 
        layout.addRow("Other Note:", self.other_lung_note)
        self.disease_combo.currentTextChanged.connect(lambda text: self.other_lung_note.setVisible(text == "Other"))

        layout.addRow(QLabel("<h3>7- Lung Mechanical Properties</h3>"))
        
        self.static_comp = QLineEdit(placeholderText="40 – 80")
        self.static_comp.setObjectName("static_compliance") # تمت الإضافة
        self.static_comp.textChanged.connect(self.validate_resp)
        layout.addRow("7.1 Static Compliance:", self.static_comp)
        
        self.dynamic_comp = QLineEdit(placeholderText="40 – 80")
        self.dynamic_comp.setObjectName("dynamic_compliance") # تمت الإضافة
        self.dynamic_comp.textChanged.connect(self.validate_resp)
        layout.addRow("7.2 Dynamic Compliance:", self.dynamic_comp)
        
        self.airway_res = QLineEdit(placeholderText="10 – 20")
        self.airway_res.setObjectName("airway_resistance") # تمت الإضافة
        self.airway_res.textChanged.connect(self.validate_resp)
        layout.addRow("7.3 Airway Resistance:", self.airway_res)
        
        self.chest_comp = QLineEdit(placeholderText="40 – 80")
        self.chest_comp.setObjectName("chest_wall_compliance") # تمت الإضافة
        self.chest_comp.textChanged.connect(self.validate_resp)
        layout.addRow("7.4 Chest Wall Compliance:", self.chest_comp)
        
        self.recruit = QComboBox() 
        self.recruit.addItems(["Medium", "Low", "High"])
        self.recruit.setObjectName("lung_recruitability") # تمت الإضافة
        self.recruit.currentTextChanged.connect(self.validate_resp)
        layout.addRow("7.5 Lung Recruitability:", self.recruit)
        
        self.stiff_idx = QLineEdit(placeholderText="1.5 – 3")
        self.stiff_idx.setObjectName("stiffness_index") # تمت الإضافة
        self.stiff_idx.textChanged.connect(self.validate_resp)
        layout.addRow("7.6 Stiffness Index:", self.stiff_idx)
        
        self.air_trap = QComboBox() 
        self.air_trap.addItems(["No", "Yes"])
        self.air_trap.setObjectName("air_trapping") 
        self.air_trap.currentTextChanged.connect(self.validate_resp)
        layout.addRow("7.7 Air Trapping:", self.air_trap)

        self.auto_peep = QComboBox()
        self.auto_peep.addItems(["No", "Yes"])
        self.auto_peep.setObjectName("auto_peep") 
        self.auto_peep.currentTextChanged.connect(self.validate_resp)
        layout.addRow("7.8 Auto-PEEP:", self.auto_peep)

        widget.setLayout(layout)
        return widget

    
    

    def validate_numeric_range(self, widget, low, high, low_msg, high_msg, normal_msg="Valid"):
        """دالة موحدة وذكية للتحقق من أي قيمة رقمية في البرنامج"""
        text = widget.text().strip()
        if not text:
            self.set_input_status(widget, "") # مسح التنبيه إذا كانت الخانة فارغة
            return
            
        try:
            val = float(text)
            if val < low: 
                self.set_input_status(widget, "warning", low_msg)
            elif val > high: 
                self.set_input_status(widget, "warning", high_msg)
            else: 
                self.set_input_status(widget, "good", normal_msg)
        except ValueError:
            self.set_input_status(widget, "critical", "Numbers only allowed")

    # ---------------------------------------------------------
    # TAB 5: Labs, Hemodynamics & Oxygen (Sections 8, 9, 10)
    # ---------------------------------------------------------
    # ---------------------------------------------------------
    # TAB 5: Labs, Hemodynamics & Oxygen (Sections 8, 9, 10)
    # ---------------------------------------------------------
    def create_labs_hemo_tab(self):
        widget = QWidget()
        layout = QFormLayout()

        # --- Section 8: ABG ---
        layout.addRow(QLabel("<h3>8- Blood Gas Analysis (ABG)</h3>"))
        
        self.ph_in = QLineEdit(placeholderText="7.35 – 7.45")
        self.ph_in.setObjectName("ph")
        self.ph_in.textChanged.connect(lambda t: self.validate_numeric_range(self.ph_in, 7.35, 7.45, "Acidemia", "Alkalemia"))
        layout.addRow("8.1 pH:", self.ph_in)
        
        self.pao2_in = QLineEdit(placeholderText="80 – 100")
        self.pao2_in.setObjectName("pao2")
        self.pao2_in.textChanged.connect(lambda t: self.validate_numeric_range(self.pao2_in, 80, 100, "Hypoxemia", "Hyperoxia"))
        layout.addRow("8.2 PaO2 (mmHg):", self.pao2_in)
        
        self.paco2_in = QLineEdit(placeholderText="35 – 45")
        self.paco2_in.setObjectName("paco2")
        self.paco2_in.textChanged.connect(lambda t: self.validate_numeric_range(self.paco2_in, 35, 45, "Hypocapnia", "Hypercapnia"))
        layout.addRow("8.3 PaCO2 (mmHg):", self.paco2_in)
        
        self.hco3_in = QLineEdit(placeholderText="22 – 26")
        self.hco3_in.setObjectName("hco3")
        self.hco3_in.textChanged.connect(lambda t: self.validate_numeric_range(self.hco3_in, 22, 26, "Low Bicarbonate", "High Bicarbonate"))
        layout.addRow("8.4 HCO3 (mmol/L):", self.hco3_in)
        
        self.be_in = QLineEdit(placeholderText="-2 to +2")
        self.be_in.setObjectName("base_excess")
        self.be_in.textChanged.connect(lambda t: self.validate_numeric_range(self.be_in, -2, 2, "Negative Base Excess", "Positive Base Excess"))
        layout.addRow("8.5 Base Excess:", self.be_in)
        
        self.sao2_lab = QLineEdit(placeholderText="95 – 100")
        self.sao2_lab.setObjectName("sao2")
        self.sao2_lab.textChanged.connect(lambda t: self.validate_numeric_range(self.sao2_lab, 95, 100, "Low Oxygen Saturation", "Valid"))
        layout.addRow("8.6 SaO2 (%):", self.sao2_lab)
        
        self.lactate_in = QLineEdit(placeholderText="0.5 – 2.0")
        self.lactate_in.setObjectName("lactate")
        self.lactate_in.textChanged.connect(lambda t: self.validate_numeric_range(self.lactate_in, 0.5, 2.0, "Low Lactate", "Hyperlactatemia"))
        layout.addRow("8.7 Lactate (mmol/L):", self.lactate_in)
        
        self.hb_in = QLineEdit(placeholderText="12 – 17")
        self.hb_in.setObjectName("hemoglobin")
        self.hb_in.textChanged.connect(lambda t: self.validate_numeric_range(self.hb_in, 12, 17, "Anemia", "High Hemoglobin"))
        layout.addRow("8.8 Hemoglobin (g/dL):", self.hb_in)

        # --- Section 9: Hemodynamic ---
        layout.addRow(QLabel("<h3>9- Hemodynamic Parameters</h3>"))
        
        self.hr_in = QLineEdit(placeholderText="60 - 100")
        self.hr_in.setObjectName("heart_rate") # <--- تمت الإضافة
        self.hr_in.textChanged.connect(lambda t: self.validate_numeric_range(self.hr_in, 60, 100, "Bradycardia", "Tachycardia"))
        layout.addRow("9.1 Heart Rate (bpm):", self.hr_in)
        
        self.sys_bp = QLineEdit(placeholderText="90 - 120")
        self.sys_bp.setObjectName("systolic_bp") # <--- تمت الإضافة
        self.sys_bp.textChanged.connect(lambda t: self.validate_numeric_range(self.sys_bp, 90, 120, "Hypotension", "Hypertension"))
        layout.addRow("9.2 Systolic BP (mmHg):", self.sys_bp)
        
        self.dia_bp = QLineEdit(placeholderText="60 - 80")
        self.dia_bp.setObjectName("diastolic_bp") # <--- تمت الإضافة
        self.dia_bp.textChanged.connect(lambda t: self.validate_numeric_range(self.dia_bp, 60, 80, "Low Diastolic BP", "High Diastolic BP"))
        layout.addRow("9.3 Diastolic BP (mmHg):", self.dia_bp)
        
        self.map_in = QLineEdit(placeholderText="70 - 100")
        self.map_in.setObjectName("map_bp") # <--- تمت الإضافة
        self.map_in.textChanged.connect(lambda t: self.validate_numeric_range(self.map_in, 70, 100, "Low MAP", "High MAP"))
        layout.addRow("9.4 MAP (mmHg):", self.map_in)
        
        self.cvp_in = QLineEdit(placeholderText="5 - 12")
        self.cvp_in.setObjectName("cvp") # <--- تمت الإضافة
        self.cvp_in.textChanged.connect(lambda t: self.validate_numeric_range(self.cvp_in, 5, 12, "Low CVP", "High CVP"))
        layout.addRow("9.5 CVP (mmHg):", self.cvp_in)
        
        self.co_in = QLineEdit(placeholderText="4 - 8")
        self.co_in.setObjectName("cardiac_output") # <--- تمت الإضافة
        self.co_in.textChanged.connect(lambda t: self.validate_numeric_range(self.co_in, 4, 8, "Low Cardiac Output", "High Cardiac Output"))
        layout.addRow("9.6 Cardiac Output (L/min):", self.co_in)
        
        self.pi_in = QLineEdit(placeholderText="1 - 5")
        self.pi_in.setObjectName("perfusion_index") # <--- تمت الإضافة
        self.pi_in.textChanged.connect(lambda t: self.validate_numeric_range(self.pi_in, 1, 5, "Low Perfusion", "High Perfusion"))
        layout.addRow("9.7 Perfusion Index (%):", self.pi_in)

        # --- Section 10: Oxygen Therapy ---
        layout.addRow(QLabel("<h3>10- Oxygen Therapy</h3>"))
        layout.addRow(QLabel("10.1 Delivery Method:"))
        
        # Checkboxes for combined selection
        self.o2_nc = QCheckBox("Nasal Cannula")
        self.o2_nc.setObjectName("chk_o2_nasal_cannula") 
        
        self.o2_fm = QCheckBox("Face Mask")
        self.o2_fm.setObjectName("chk_o2_face_mask") 
        
        self.o2_hfnc = QCheckBox("HFNC")
        self.o2_hfnc.setObjectName("chk_o2_hfnc") 
        
        self.o2_niv = QCheckBox("NIV")
        self.o2_niv.setObjectName("chk_o2_niv") 
        
        layout.addRow(self.o2_nc, self.o2_fm)
        layout.addRow(self.o2_hfnc, self.o2_niv)
        
        self.fio2_max = QLineEdit(placeholderText="21 - 60%")
        self.fio2_max.setObjectName("fio2_max") # <--- تمت الإضافة
        self.fio2_max.textChanged.connect(lambda t: self.validate_numeric_range(self.fio2_max, 21, 60, "Invalid FiO2", "High FiO2"))
        layout.addRow("10.2 Max FiO2 (%):", self.fio2_max)
        
        self.o2_duration = QLineEdit(placeholderText="Hours / Days")
        self.o2_duration.setObjectName("oxygen_duration") # <--- تمت الإضافة
        layout.addRow("10.3 Duration:", self.o2_duration)
        
        self.o2_failure = QLineEdit(placeholderText="Reason if escalated...")
        self.o2_failure.setObjectName("oxygen_failure_reason") # <--- تمت الإضافة
        layout.addRow("10.4 Failure Reason:", self.o2_failure)

        widget.setLayout(layout)
        return widget
    
    # ---------------------------------------------------------
    # TAB 6: Imaging (Sections 11 & 12)
    # ---------------------------------------------------------
    def create_imaging_tab(self):
        widget = QWidget()
        layout = QFormLayout()

        layout.addRow(QLabel("<h3>11- CT Scan Inputs</h3>"))
        
        self.ct_lung_inv = QLineEdit(placeholderText="% of lung involved")
        self.ct_lung_inv.setObjectName("ct_lung_involvement_percent") # تمت الإضافة
        self.ct_lung_inv.textChanged.connect(self.validate_imaging)
        layout.addRow("11.1.1 Lung Involvement %:", self.ct_lung_inv)
        
        self.ct_ggo = QComboBox(); self.ct_ggo.addItems(["No", "Yes"])
        self.ct_ggo.setObjectName("ct_ggo") # تمت الإضافة
        layout.addRow("11.1.2 Ground Glass Opacity:", self.ct_ggo)
        
        self.ct_cons = QComboBox(); self.ct_cons.addItems(["No", "Yes"])
        self.ct_cons.setObjectName("ct_consolidation") # تمت الإضافة
        layout.addRow("11.1.3 Consolidation:", self.ct_cons)
        
        self.ct_fib = QComboBox(); self.ct_fib.addItems(["No", "Yes"])
        self.ct_fib.setObjectName("ct_fibrosis") # تمت الإضافة
        layout.addRow("11.1.4 Fibrotic Changes:", self.ct_fib)
        
        self.ct_atel = QLineEdit(placeholderText="Description or %")
        self.ct_atel.setObjectName("ct_atelectasis") # تمت الإضافة
        layout.addRow("11.1.5 Atelectasis Areas:", self.ct_atel)

        layout.addRow(QLabel("11.2 Distribution Pattern:"))
        self.dist_upper = QCheckBox("Upper Lobes"); self.dist_upper.setObjectName("chk_ct_dist_upper")
        self.dist_lower = QCheckBox("Lower Lobes"); self.dist_lower.setObjectName("chk_ct_dist_lower")
        self.dist_dep = QCheckBox("Dependent Regions"); self.dist_dep.setObjectName("chk_ct_dist_dependent")
        self.dist_diff = QCheckBox("Diffuse"); self.dist_diff.setObjectName("chk_ct_dist_diffuse")
        layout.addRow(self.dist_upper, self.dist_lower)
        layout.addRow(self.dist_dep, self.dist_diff)

        self.ct_score = QLineEdit(placeholderText="e.g. 0-25 or 0-40")
        self.ct_score.setObjectName("ct_severity_score") # تمت الإضافة
        layout.addRow("11.3 CT Severity Score:", self.ct_score)
        
        self.btn_ct_upload = QPushButton("Upload Reference CT Image")
        self.btn_ct_upload.setObjectName("ct_image_path")
        self.btn_ct_upload.clicked.connect(self.upload_ct_image)
        layout.addRow("11.4 Image Upload:", self.btn_ct_upload)

        self.ct_path = ""

        layout.addRow(QLabel("<h3>12- Chest X-Ray Inputs</h3>"))
        
        self.xr_bilateral = QComboBox(); self.xr_bilateral.addItems(["No", "Yes"])
        self.xr_bilateral.setObjectName("xr_bilateral_infiltrates") # تمت الإضافة
        layout.addRow("12.1 Bilateral Infiltrates:", self.xr_bilateral)
        
        self.xr_unilateral = QComboBox(); self.xr_unilateral.addItems(["No", "Yes"])
        self.xr_unilateral.setObjectName("xr_unilateral_disease") # تمت الإضافة
        layout.addRow("12.2 Unilateral Disease:", self.xr_unilateral)
        
        self.xr_opacity = QLineEdit(placeholderText="% Opacity")
        self.xr_opacity.setObjectName("xr_lung_opacity_percent") # تمت الإضافة
        self.xr_opacity.textChanged.connect(self.validate_imaging)
        layout.addRow("12.3 Lung Opacity %:", self.xr_opacity)
        
        self.xr_effusion = QComboBox(); self.xr_effusion.addItems(["No", "Yes"])
        self.xr_effusion.setObjectName("xr_pleural_effusion") # تمت الإضافة
        layout.addRow("12.4 Pleural Effusion:", self.xr_effusion)
        
        self.xr_tube_conf = QComboBox(); self.xr_tube_conf.addItems(["No", "Yes"])
        self.xr_tube_conf.setObjectName("xr_tube_position_confirmed") # تمت الإضافة
        layout.addRow("12.5 Tube Pos Confirmation:", self.xr_tube_conf)
        
        self.xr_ett_depth = QLineEdit(placeholderText="Depth in cm")
        self.xr_ett_depth.setObjectName("xr_ett_depth") # تمت الإضافة
        layout.addRow("12.6 ETT Position Depth:", self.xr_ett_depth)

        widget.setLayout(layout)
        return widget

    # استبدل الدالة القديمة بهذا الكود في القسم الخاص بها
    def validate_imaging(self, text=None):
        def check_severity_percentage(widget):
            try:
                val = float(widget.text())
                if val <= 5: self.set_input_status(widget, "good", "Normal")
                elif val <= 25: self.set_input_status(widget, "warning", "Mild")
                elif val <= 50: self.set_input_status(widget, "warning", "Moderate")
                else: self.set_input_status(widget, "critical", "Severe")
            except ValueError:
                self.set_input_status(widget, "")

        check_severity_percentage(self.ct_lung_inv)
        check_severity_percentage(self.xr_opacity)

    # استبدل الدالة القديمة بهذا الكود في القسم الخاص بها
    def validate_sim(self, text=None):
        val = self.baro_risk.currentText()
        if val == "High":
            self.set_input_status(self.baro_risk, "critical", "High Risk of Barotrauma!")
        else:
            self.set_input_status(self.baro_risk, "good", "Normal")


    def reset_all_inputs(self):
        """تصفير جميع الخانات وإرجاع الواجهة لوضعها الافتراضي"""
        if hasattr(self, 'adm_date'): self.adm_date.setDateTime(QDateTime.currentDateTime())
        if hasattr(self, 'dob'): self.dob.setDate(QDate.currentDate().addYears(-30))

        for widget in self.findChildren(QLineEdit):
            if widget != getattr(self, 'timestamp', None): 
                widget.clear()
                self.set_input_status(widget, "")
                if widget.placeholderText() and "Notes for" in widget.placeholderText():
                    widget.setVisible(False)

        for widget in self.findChildren(QComboBox):
            widget.setCurrentIndex(0)
            self.set_input_status(widget, "")

        for widget in self.findChildren(QTextEdit):
            widget.clear()

        for chk in self.findChildren(QCheckBox):
            if chk.text() == "None":
                chk.setChecked(True)
            else:
                chk.setChecked(False)
                
        # تصفير الصورة والزر
        self.current_ct_path = ""
        self.temp_ct_source = None
        self.btn_ct_upload.setText("Upload Reference CT Image")
        self.btn_ct_upload.setStyleSheet("") # مسح التنسيق الأخضر

    # ---------------------------------------------------------
    # TAB 7: Sim & Notes (Sections 13, 14, 15)
    # ---------------------------------------------------------
    def create_simulation_tab(self):
        widget = QWidget()
        layout = QFormLayout()

        layout.addRow(QLabel("<h3>13- Ventilation Readiness</h3>"))
        
        self.rec_assess = QLineEdit(placeholderText="Description and %")
        self.rec_assess.setObjectName("sim_recruitability_assessment") # تمت الإضافة
        layout.addRow("13.1 Recruitability Assessment:", self.rec_assess)
        
        self.baro_risk = QComboBox()
        self.baro_risk.addItems(["Low", "Medium", "High"])
        self.baro_risk.setObjectName("sim_barotrauma_risk") # تمت الإضافة
        self.baro_risk.currentTextChanged.connect(self.validate_sim)
        layout.addRow("13.2 Risk of Barotrauma:", self.baro_risk)
        
        self.oxy_potential = QLineEdit(placeholderText="Expected improvement / Description")
        self.oxy_potential.setObjectName("sim_oxygenation_potential") # تمت الإضافة
        layout.addRow("13.3 Oxygenation Potential:", self.oxy_potential)
        
        self.comp_trend = QComboBox()
        self.comp_trend.addItems(["Stable", "Increasing", "Decreasing"])
        self.comp_trend.setObjectName("sim_compliance_trend") # تمت الإضافة
        layout.addRow("13.4 Expected Compliance Trend:", self.comp_trend)

        layout.addRow(QLabel("<h3>14- Simulation Scenario Control</h3>"))
        
        self.scen_type = QComboBox()
        self.scen_type.addItems(["Training", "Research", "Demonstration", "Patient Case (Real Patient)"])
        self.scen_type.setObjectName("sim_scenario_type") # تمت الإضافة
        layout.addRow("14.1 Scenario Type:", self.scen_type)
        
        self.sim_speed = QComboBox()
        self.sim_speed.addItems(["Normal", "Fast", "Slow"])
        self.sim_speed.setObjectName("sim_speed") # تمت الإضافة
        layout.addRow("14.2 Simulation Speed:", self.sim_speed)
        
        self.time_comp = QComboBox()
        self.time_comp.addItems(["1x", "2x", "5x"])
        self.time_comp.setObjectName("sim_time_compression") # تمت الإضافة
        layout.addRow("14.3 Time Compression Factor:", self.time_comp)
        
        self.scen_duration = QLineEdit(placeholderText="e.g. 2 hours or 45 mins")
        self.scen_duration.setObjectName("sim_scenario_duration") # تمت الإضافة
        layout.addRow("14.4 Scenario Duration:", self.scen_duration)
        
        self.btn_reset_scenario = QPushButton("14.5 Reset Scenario")
        self.btn_reset_scenario.setStyleSheet("background-color: #c0392b; font-weight: bold;")
        layout.addRow(self.btn_reset_scenario, QLabel(""))
        self.btn_reset_scenario.clicked.connect(self.reset_all_inputs)

        layout.addRow(QLabel("<h3>15- Operator Clinical Notes</h3>"))
        
        self.note_obs = QTextEdit()
        self.note_obs.setObjectName("operator_note_observations") # تمت الإضافة
        self.note_obs.setPlaceholderText("Patient status, vitals trends, imaging findings...")
        layout.addRow("15.1 Observations:", self.note_obs)
        
        self.note_interp = QTextEdit()
        self.note_interp.setObjectName("operator_note_interpretation") # تمت الإضافة
        self.note_interp.setPlaceholderText("Clinical interpretation, differential diagnosis...")
        layout.addRow("15.2 Interpretation:", self.note_interp)
        
        self.note_teach = QTextEdit()
        self.note_teach.setObjectName("operator_note_teaching") # تمت الإضافة
        self.note_teach.setPlaceholderText("Key teaching points, lessons learned...")
        layout.addRow("15.3 Teaching Notes:", self.note_teach)

        widget.setLayout(layout)
        return widget
    

   

    

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # تحسين عرض الخطوط للشاشات عالية الدقة
    app.setStyle("Fusion")
    
    ex = VentilatorManualInputs()
    ex.show()
    sys.exit(app.exec())