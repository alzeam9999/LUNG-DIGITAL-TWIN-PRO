import sqlite3
import json

class DatabaseManager:
    def __init__(self, db_name="ventilator_records.db"):
        self.db_name = db_name
        self.init_table()

    def init_table(self):
        """تأسيس قاعدة البيانات بترتيب مطابق تماماً لأقسام الواجهة الـ 15"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # إنشاء الجدول بالترتيب المنطقي للواجهة لضمان هيكلة احترافية
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS patients_data (
                -- 1. Patient Admin Info
                patient_id VARCHAR(50) PRIMARY KEY,
                patient_name VARCHAR(150) NOT NULL,
                case_id VARCHAR(50),
                hospital_name VARCHAR(150),
                icu_unit_name VARCHAR(100),
                bed_number VARCHAR(20),
                admission_datetime DATETIME,
                simulation_session_id VARCHAR(50),
                operator_name VARCHAR(100),
                physician_supervisor VARCHAR(100),

                -- 2. Demographics & 3. Physical Exam
                date_of_birth DATE,
                gender VARCHAR(10),
                height_cm DECIMAL(5,2),
                weight_kg DECIMAL(5,2),
                bsa_m2 DECIMAL(4,2),
                bmi DECIMAL(5,2),
                pbw_kg DECIMAL(5,2),

                -- 4. Medical History (Smart Groups & Smoking)
                smoking_status VARCHAR(50),
                -- ملاحظة: خانات الـ Smart Groups (مثل chk_heart_failure) تضاف ديناميكياً عند الحفظ

                -- 5. Current Respiratory Status
                baseline_rr INT,
                oxygen_saturation_admission DECIMAL(5,2),
                work_of_breathing VARCHAR(50),
                accessory_muscles VARCHAR(10),
                breathing_pattern VARCHAR(50),
                cyanosis VARCHAR(10),

                -- 6. Lung Disease Pattern
                lung_disease_pattern VARCHAR(100),
                lung_disease_severity VARCHAR(50),
                lung_disease_other TEXT,

                -- 7. Lung Mechanical Properties
                static_compliance DECIMAL(5,2),
                dynamic_compliance DECIMAL(5,2),
                airway_resistance DECIMAL(5,2),
                chest_wall_compliance DECIMAL(5,2),
                lung_recruitability VARCHAR(50),
                stiffness_index DECIMAL(4,2),
                air_trapping VARCHAR(10),
                auto_peep VARCHAR(10),

                -- 8. Blood Gas Analysis (ABG)
                ph DECIMAL(4,2),
                pao2 DECIMAL(5,2),
                paco2 DECIMAL(5,2),
                hco3 DECIMAL(5,2),
                base_excess DECIMAL(4,2),
                sao2 DECIMAL(5,2),
                lactate DECIMAL(4,2),
                hemoglobin DECIMAL(4,2),

                -- 9. Hemodynamic Parameters
                heart_rate INT,
                systolic_bp INT,
                diastolic_bp INT,
                map_bp INT,
                cvp INT,
                cardiac_output DECIMAL(4,2),
                perfusion_index DECIMAL(4,2),

                -- 10. Oxygen Therapy
                fio2_max INT,
                oxygen_duration VARCHAR(100),
                oxygen_failure_reason TEXT,

                -- 11. CT Scan Inputs
                ct_lung_involvement_percent DECIMAL(5,2),
                ct_ggo VARCHAR(10),
                ct_consolidation VARCHAR(10),
                ct_fibrosis VARCHAR(10),
                ct_atelectasis TEXT,
                ct_severity_score VARCHAR(50),
                ct_image_path TEXT,
                ct_image_name TEXT,

                -- 12. Chest X-Ray Inputs
                xr_bilateral_infiltrates VARCHAR(10),
                xr_unilateral_disease VARCHAR(10),
                xr_lung_opacity_percent DECIMAL(5,2),
                xr_pleural_effusion VARCHAR(10),
                xr_tube_position_confirmed VARCHAR(10),
                xr_ett_depth VARCHAR(50),

                -- 13. Ventilation Readiness (Sim)
                sim_recruitability_assessment TEXT,
                sim_barotrauma_risk VARCHAR(50),
                sim_oxygenation_potential TEXT,
                sim_compliance_trend VARCHAR(50),

                -- 14. Simulation Scenario Control
                sim_scenario_type VARCHAR(50),
                sim_speed VARCHAR(20),
                sim_time_compression VARCHAR(20),
                sim_scenario_duration VARCHAR(50),

                -- 15. Operator Clinical Notes
                operator_note_observations TEXT,
                operator_note_interpretation TEXT,
                operator_note_teaching TEXT,

                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                patient_status VARCHAR(20) DEFAULT 'Active',
                last_accessed_dashboard DATETIME
            )
        ''')
        # 🟢 كود لتحديث الجدول القديم إن كان موجوداً ولا يحتوي على الخانات الجديدة
        try:
            cursor.execute("ALTER TABLE patients_data ADD COLUMN patient_status VARCHAR(20) DEFAULT 'Active'")
            cursor.execute("ALTER TABLE patients_data ADD COLUMN last_accessed_dashboard DATETIME")
        except sqlite3.OperationalError:
            pass # الأعمدة موجودة مسبقاً، تجاهل الخطأ

        conn.commit()
        conn.close()

    def save_patient(self, patient_data):
        """حفظ البيانات مع دعم إضافة الأعمدة الديناميكية (Smart Groups)"""
        patient_id = patient_data.get("patient_id")
        if not patient_id:
            return False, "Error: Patient ID is missing."

        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            # التحقق من وجود الأعمدة الحالية في الملف
            cursor.execute("PRAGMA table_info(patients_data)")
            existing_columns = [col[1] for col in cursor.fetchall()]

            # إذا كانت هناك بيانات من خانات ديناميكية (مثل الملاحظات الجانبية) غير موجودة كأعمدة، يتم إضافتها
            for key in patient_data.keys():
                if key not in existing_columns:
                    try:
                        cursor.execute(f"ALTER TABLE patients_data ADD COLUMN [{key}] TEXT")
                    except sqlite3.OperationalError:
                        pass # في حال كان العمود موجوداً بالفعل

            # إعداد جملة SQL للحفظ أو التحديث
            columns = ", ".join([f"[{k}]" for k in patient_data.keys()])
            placeholders = ", ".join(["?" for _ in patient_data])
            
            # معالجة القيم (تحويل القوائم إلى نصوص JSON)
            processed_values = []
            for v in patient_data.values():
                if isinstance(v, (dict, list)):
                    processed_values.append(json.dumps(v))
                else:
                    processed_values.append(v)

            sql = f"INSERT OR REPLACE INTO patients_data ({columns}) VALUES ({placeholders})"
            cursor.execute(sql, tuple(processed_values))
            
            conn.commit()
            return True, "All clinical data saved successfully."
        except Exception as e:
            return False, f"Critical Database Error: {str(e)}"
        finally:
            conn.close()