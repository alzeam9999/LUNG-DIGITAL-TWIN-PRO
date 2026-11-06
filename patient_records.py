import sys
import os
import sqlite3
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                             QTableWidgetItem, QPushButton, QLabel, QHeaderView, 
                             QAbstractItemView, QLineEdit, QApplication)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import pyqtSignal, Qt, QTimer
from PyQt5.QtWidgets import QComboBox, QMessageBox
from datetime import datetime  # لحساب العمر والوقت الحالي
from PyQt5.QtWidgets import QScrollArea

class PatientRecordsView(QWidget):
    back_requested = pyqtSignal()
    patient_selected = pyqtSignal(dict) 
    patient_to_edit = pyqtSignal(dict)
    def __init__(self):
        super().__init__()
        self.initUI()
        self.load_data()

    def showEvent(self, event):
        """تستدعى تلقائياً عند عرض الصفحة. نضمن هنا وجود الزر الكبير."""
        super().showEvent(event)
        # التأكد من أن الزر لا يزال موجوداً في التخطيط
        if self.btn_confirm not in self.findChildren(QPushButton):
            # إذا كان مفقوداً، نعيد إنشائه
            self.btn_confirm = QPushButton("✅ Select Patient & Proceed to Ventilator")
            self.btn_confirm.setObjectName("select_btn")
            self.btn_confirm.clicked.connect(self.confirm_selection)
            self.layout().addWidget(self.btn_confirm)
        # إعادة تطبيق النمط الخاص به (لأنه قد يتأثر)
        self.btn_confirm.setStyleSheet("""
            background-color: #2ecc71;
            border-radius: 8px;
            padding: 15px;
            font-weight: bold;
            font-size: 16px;
        """)
        self.btn_confirm.setVisible(True)
        
    def initUI(self):
        self.setStyleSheet("""
            QWidget { background-color: #1a1c24; color: #ecf0f1; font-family: 'Segoe UI'; }
            QLineEdit, QComboBox {
                background-color: #2c313c;
                border: 2px solid #3e4451;
                border-radius: 10px;
                padding: 10px 15px;
                color: white;
                font-size: 14px;
                margin-bottom: 10px;
            }
            QLineEdit:focus, QComboBox:focus { border: 2px solid #3498db; }
            QTableWidget { 
                background-color: #252934; border: 1px solid #34495e; 
                gridline-color: #3e4451; selection-background-color: #3498db; 
            }
            QHeaderView::section { background-color: #2c313c; padding: 10px; border: 1px solid #34495e; font-weight: bold; }
            QPushButton#back_btn { background-color: #c0392b; border-radius: 5px; font-weight: bold; }
            QPushButton#select_btn { background-color: #2ecc71; border-radius: 8px; padding: 15px; font-weight: bold; font-size: 16px; }
        """)

        # تعريف نص الوقت والتاريخ
        self.time_label = QLabel()
        self.time_label.setStyleSheet("font-size: 16px; color: #bdc3c7; margin-right: 20px; font-weight: 500;")

        # إعداد المؤقت لتحديث الوقت كل ثانية
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_live_time)
        self.timer.start(1000)
        self.update_live_time()

        # التخطيط الرئيسي (بدون QScrollArea)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)  # هوامش مناسبة
        main_layout.setSpacing(10)

        # --- 1. الشريط العلوي ---
        header = QHBoxLayout()
        title = QLabel("📋 REGISTERED PATIENTS DATABASE")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #3498db;")

        self.btn_back = QPushButton("✕ Back to Menu")
        self.btn_back.setObjectName("back_btn")
        self.btn_back.setFixedSize(120, 35)
        self.btn_back.clicked.connect(self.back_requested.emit)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.time_label)
        header.addWidget(self.btn_back)
        main_layout.addLayout(header)

        # --- 2. شريط البحث والترتيب ---
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search by Patient Name or ID...")
        self.search_input.textChanged.connect(self.filter_table)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["⬇️ Sort by: Newest First", "⬆️ Sort by: Oldest First", "⏱️ Sort by: Last Accessed"])
        self.sort_combo.setFixedWidth(250)
        self.sort_combo.currentIndexChanged.connect(self.load_data)

        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.sort_combo)
        main_layout.addLayout(search_layout)

        # --- 3. الجدول ---
        self.table = QTableWidget()
        self.table.cellDoubleClicked.connect(self.on_row_double_clicked)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Patient ID", "Full Name", "Bed Number", "Gender", "Age", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        main_layout.addWidget(self.table)

        # --- 4. زر التأكيد ---
        self.btn_confirm = QPushButton("✅ Select Patient & Proceed to Ventilator")
        self.btn_confirm.setObjectName("select_btn")
        self.btn_confirm.clicked.connect(self.confirm_selection)
        main_layout.addWidget(self.btn_confirm)

    def _fix_database_structure(self, cursor):
        # إضافة عمود الحالة إذا لم يكن موجوداً
        try: cursor.execute("ALTER TABLE patients_data ADD COLUMN patient_status VARCHAR(20) DEFAULT 'Active'")
        except: pass
        # إضافة عمود وقت الدخول إذا لم يكن موجوداً
        try: cursor.execute("ALTER TABLE patients_data ADD COLUMN last_accessed_dashboard DATETIME")
        except: pass

    def _calculate_age(self, dob_str):
        # 1. التحقق من أن النص موجود وغير فارغ
        if not dob_str or str(dob_str).strip() == "" or str(dob_str).lower() == "none":
            return "-"
        
        try:
            # 2. تحويل الأرقام العربية (١٢٣) إلى أرقام إنجليزية (123)
            # بايثون لا يفهم الأرقام الهندية/العربية في العمليات الحسابية تلقائياً
            arabic_digits = "٠١٢٣٤٥٦٧٨٩"
            english_digits = "0123456789"
            translation_table = str.maketrans(arabic_digits, english_digits)
            clean_dob = str(dob_str).translate(translation_table)

            # 3. قص الوقت وتجنب أي مسافات زائدة (نأخذ التاريخ فقط yyyy-mm-dd)
            date_only = clean_dob.strip().split(' ')[0]
            
            # 4. محاولة تحويل النص إلى كائن تاريخ (Object)
            # الآن التاريخ أصبح بصيغة "1996-02-24" بدلاً من "١٩٩٦-٠٢-٢٤"
            dob = datetime.strptime(date_only, "%Y-%m-%d")
            today = datetime.today()
            
            # 5. حساب الفرق بين السنوات
            # نتحقق إذا كان يوم الميلاد قد مر هذا العام أم لا
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            
            # 6. إرجاع النتيجة كـ نص (مع التأكد أنه ليس سالباً)
            return str(max(0, age))
            
        except Exception as e:
            # في حال حدث أي خطأ غير متوقع، نطبع نوعه ونعيد شرطة
            print(f"⚠️ Error: {e}")
            return "-"

    def load_data(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(base_dir, "ventilator_records.db")

        if not os.path.exists(db_path): return

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='patients_data'")
            if not cursor.fetchone():
                conn.close()
                return

            # 🟢 التأكد من وجود الأعمدة قبل الاستعلام لتجنب الخطأ
            self._fix_database_structure(cursor)
            conn.commit()

            sort_index = self.sort_combo.currentIndex()
            if sort_index == 0:
                order_clause = "ORDER BY created_at DESC"
            elif sort_index == 1:
                order_clause = "ORDER BY created_at ASC"
            else:
                order_clause = "ORDER BY last_accessed_dashboard DESC, created_at DESC"

            # 🟢 تعديل الاستعلام لجلب الخانات المطلوبة فقط (مع إضافة تاريخ الميلاد لحساب العمر)
            query = f"SELECT patient_id, patient_name, bed_number, gender, date_of_birth, patient_status FROM patients_data {order_clause}"
            cursor.execute(query)
            rows = cursor.fetchall()
            
            self.table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                p_id, p_name, bed, gender, dob, status = row
                
                # حساب العمر
                age = self._calculate_age(dob)
                
                # تجهيز البيانات للخلايا الـ 5 الأولى
                display_data = [p_id, p_name, bed, gender, age]
                
                for j, val in enumerate(display_data):
                    item = QTableWidgetItem(str(val if val else "-"))
                    item.setTextAlignment(Qt.AlignCenter)
                    self.table.setItem(i, j, item)
                
                # 🟢 الخانة السادسة: زر الحالة
                current_status = status if status else "Active"
                btn_status = QPushButton(current_status)
                
                if current_status == "Active":
                    btn_status.setStyleSheet("background-color: #3498db; color: white; border-radius: 5px; padding: 5px; font-weight: bold;")
                else:
                    btn_status.setStyleSheet("background-color: #7f8c8d; color: white; border-radius: 5px; padding: 5px; font-weight: bold;")
                
                btn_status.clicked.connect(lambda checked, pid=p_id, stat=current_status: self.toggle_patient_status(pid, stat))
                self.table.setCellWidget(i, 5, btn_status)
                
            conn.close()
        except Exception as e:
            print(f"❌ خطأ في قراءة قاعدة البيانات: {e}")

    def on_row_double_clicked(self, row, column):
        """جلب البيانات من ventilator_records.db عند النقر مرتين"""
        p_id = self.table.item(row, 0).text()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(base_dir, "ventilator_records.db") # 👈 التأكد من المسار الصحيح

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM patients_data WHERE patient_id = ?", (p_id,))
            row_data = cursor.fetchone()
            if row_data:
                self.patient_to_edit.emit(dict(row_data)) # إرسال البيانات للتعديل
            conn.close()
        except Exception as e:
            print(f"Error fetching for edit: {e}")
            
    def toggle_patient_status(self, patient_id, current_status):
        new_status = "Discharged" if current_status == "Active" else "Active"
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(base_dir, "ventilator_records.db")
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE patients_data SET patient_status = ? WHERE patient_id = ?", (new_status, patient_id))
            conn.commit()
            conn.close()
            self.load_data() 
        except Exception as e:
            print(f"❌ Error updating status: {e}")
                
            
    

    def filter_table(self):
        """دالة البحث الفوري (البحث في الاسم والمعرف)"""
        search_text = self.search_input.text().lower()
        for i in range(self.table.rowCount()):
            # نحصل على نص المعرف (العمود 0) ونص الاسم (العمود 1)
            id_item = self.table.item(i, 0).text().lower()
            name_item = self.table.item(i, 1).text().lower()
            
            # إذا كان نص البحث موجود في أياً منهما، أظهر الصف، وإلا اخفه
            if search_text in id_item or search_text in name_item:
                self.table.setRowHidden(i, False)
            else:
                self.table.setRowHidden(i, True)

    def confirm_selection(self):
        current_row = self.table.currentRow()
        
        # التأكد من اختيار صف
        if current_row >= 0 and not self.table.isRowHidden(current_row):
            # الحصول على المعرف من العمود الأول
            p_id = self.table.item(current_row, 0).text()
            
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, "ventilator_records.db")
            
            try:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row # هذا يسهل تحويل البيانات لقاموس (dict)
                cursor = conn.cursor()
                
                # 🟢 استخدام datetime المستوردة في أعلى الملف مباشرة
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # 1. تحديث وقت آخر دخول للمريض المختار
                cursor.execute("UPDATE patients_data SET last_accessed_dashboard = ? WHERE patient_id = ?", (current_time, p_id))
                conn.commit()

                # 2. جلب بيانات المريض كاملة لإرسالها للداشبورد
                cursor.execute("SELECT * FROM patients_data WHERE patient_id = ?", (p_id,))
                row = cursor.fetchone()
                
                if row:
                    data = dict(row) # تحويل البيانات لقاموس
                    self.patient_selected.emit(data) # إرسال البيانات للصفحة التالية
                    print(f"✅ Patient Selected: {data['patient_name']} at {current_time}")
                
                conn.close()
                self.load_data() # تحديث الجدول في الخلفية ليظهر وقت الدخول الجديد
                
            except Exception as e:
                print(f"❌ Error in selection: {e}")
        else:
            # رسالة تنبيه إذا لم يتم اختيار مريض
            QMessageBox.warning(self, "Selection Required", "Please select a patient from the list first.")
    def update_live_time(self):
        """تحديث نص الوقت والتاريخ الحالي"""
        now = datetime.now()
        # تنسيق: اليوم، التاريخ - الساعة:الدقيقة:الثانية
        current_str = now.strftime("%A, %d/%m/%Y  |  %I:%M:%S %p")
        self.time_label.setText(current_str)
        
if __name__ == "__main__":
    app = QApplication(sys.argv)
    # إنشاء نسخة من الصفحة لتجربتها بشكل مستقل
    window = PatientRecordsView()
    window.showMaximized() # أو window.show()
    sys.exit(app.exec_())