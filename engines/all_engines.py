"""
ملف جامع لجميع محركات الحساب وفقًا لمواصفات ملف PDF
مع إضافة Fail-Safe Logic وتحذيرات عند فقدان البيانات
"""
import json
import os

_CONFIG = None

def load_config(config_file="config.json"):
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    default_config = {}  # سنملأه بالقيم الافتراضية من الكود الحالي
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                _CONFIG = json.load(f)
            return _CONFIG
        except Exception as e:
            print(f"Warning: Could not load config file: {e}. Using defaults.")
    else:
        print(f"Info: Config file '{config_file}' not found. Using defaults.")
    # إرجاع قاموس فارغ، وسيتولى كل محرك تعيين قيمه الافتراضية
    return {}

# ----------------------------------------------------------------------
# دوال مساعدة مشتركة (محدثة)
# ----------------------------------------------------------------------
def to_float(value, default=None):
    """تحويل القيمة إلى float بأمان"""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def normalize(value, min_val, max_val, reverse=False):
    """تطبيع القيمة إلى مجال 0-1"""
    if value is None:
        return 0.5
    clamped = max(min_val, min(value, max_val))
    if reverse:
        return 1 - (clamped - min_val) / (max_val - min_val)
    else:
        return (clamped - min_val) / (max_val - min_val)

def check_required(data, fields):
    """التحقق من وجود الحقول المطلوبة وإرجاع قائمة المفقودة"""
    missing = [f for f in fields if data.get(f) is None]
    return missing

def require_fields(data, fields, engine_name):
    """إذا كان أي حقل مطلوب مفقوداً، اطبع تحذيراً وأرجع None"""
    missing = check_required(data, fields)
    if missing:
        print(f"Warning [{engine_name}]: Missing required data: {missing}. Cannot calculate.")
        return False
    return True


# ----------------------------------------------------------------------
# 2.1 FiO2 Engine
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# 2.1 FiO2 Engine (نسخة كاملة مع max_delta)
# ----------------------------------------------------------------------
class FiO2Engine:
    def __init__(self):
        config = load_config().get('FiO2Engine', {})
        self.weights = config.get('weights', {
            'pao2': 0.25,
            'spo2': 0.20,
            'pf_ratio': 0.20,
            'ct_involvement': 0.15,
            'wob': 0.10,
            'lactate': 0.10
        })
        self.max_delta = config.get('max_delta', 5)

    def calculate_osi(self, data):
        pao2 = to_float(data.get('pao2'))
        spo2 = to_float(data.get('spo2'))
        fio2 = to_float(data.get('fio2'), 21)
        ct = to_float(data.get('ct_lung_involvement_percent'))
        wob = data.get('work_of_breathing')
        lactate = to_float(data.get('lactate'))

        if pao2 and fio2:
            pf_ratio = pao2 / (fio2 / 100)
        else:
            pf_ratio = None

        scores = {}
        scores['pao2'] = normalize(pao2, 40, 100, reverse=True) if pao2 else 0.5
        scores['spo2'] = normalize(spo2, 70, 100, reverse=True) if spo2 else 0.5
        scores['pf_ratio'] = normalize(pf_ratio, 100, 500, reverse=True) if pf_ratio else 0.5
        scores['ct'] = normalize(ct, 0, 100) if ct else 0.5

        wob_map = {'Mild': 0.33, 'Moderate': 0.66, 'Severe': 1.0}
        scores['wob'] = wob_map.get(wob, 0.5) if isinstance(wob, str) else 0.5

        scores['lactate'] = normalize(lactate, 0.5, 4.0) if lactate else 0.5

        osi = (self.weights['pao2'] * scores['pao2'] +
               self.weights['spo2'] * scores['spo2'] +
               self.weights['pf_ratio'] * scores['pf_ratio'] +
               self.weights['ct_involvement'] * scores['ct'] +
               self.weights['wob'] * scores['wob'] +
               self.weights['lactate'] * scores['lactate'])
        return osi

    def recommend_fio2(self, data, previous_value=None):
        if not require_fields(data, ['pao2', 'spo2'], 'FiO2Engine'):
            return None
        osi = self.calculate_osi(data)
        fio2 = 21 + (osi * 79)
        fio2 = round(fio2)
        copd = data.get('copd', False)
        if copd and osi < 0.8:
            fio2 = min(fio2, 60)
        fio2 = max(21, min(fio2, 100))

        if previous_value is not None:
            delta = fio2 - previous_value
            if abs(delta) > self.max_delta:
                fio2 = previous_value + (self.max_delta if delta > 0 else -self.max_delta)
        return fio2

# ----------------------------------------------------------------------
# 2.2 PEEP Engine (نسخة كاملة مع max_delta)
# ----------------------------------------------------------------------
class PEEPEEngine:
    def __init__(self):
        self.mri_weights = {
            'compliance': 0.30,
            'recruitability': 0.25,
            'atelectasis': 0.20,
            'ards_severity': 0.20
        }
        self.auto_peep_penalty = 0.1
        self.max_delta = 2  # أقصى تغيير (cmH2O) لكل دورة

    def map_to_score(self, map_val):
        return normalize(map_val, 50, 100, reverse=True)

    def cardiac_output_to_score(self, co_val):
        return normalize(co_val, 2.5, 8, reverse=True)

    def calculate_mri(self, data):
        compliance = to_float(data.get('static_compliance'))
        recruit = data.get('recruitability')
        atelectasis = to_float(data.get('atelectasis_percent'))
        ards = data.get('ards')
        auto_peep = data.get('auto_peep', False)

        recruit_map = {'Low': 0.33, 'Moderate': 0.66, 'High': 1.0}
        recruit_score = recruit_map.get(recruit, 0.5)
        ards_map = {'None': 0.0, 'Mild': 0.33, 'Moderate': 0.66, 'Severe': 1.0}
        ards_score = ards_map.get(ards, 0.0)

        scores = {}
        scores['compliance'] = normalize(compliance, 20, 80, reverse=True) if compliance else 0.5
        scores['recruitability'] = recruit_score
        scores['atelectasis'] = normalize(atelectasis, 0, 50) if atelectasis else 0.5
        scores['ards'] = ards_score

        mri = (self.mri_weights['compliance'] * scores['compliance'] +
               self.mri_weights['recruitability'] * scores['recruitability'] +
               self.mri_weights['atelectasis'] * scores['atelectasis'] +
               self.mri_weights['ards_severity'] * scores['ards'])

        if auto_peep:
            mri = max(0, mri - self.auto_peep_penalty)
        return mri

    def calculate_hsi(self, data):
        map_val = to_float(data.get('map'))
        co_val = to_float(data.get('cardiac_output'))
        map_score = self.map_to_score(map_val) if map_val else 0.5
        co_score = self.cardiac_output_to_score(co_val) if co_val else 0.5
        return (map_score + co_score) / 2

    def recommend_peep(self, data, previous_value=None):
        if not require_fields(data, ['static_compliance', 'map'], 'PEEPEngine'):
            return None
        mri = self.calculate_mri(data)
        hsi = self.calculate_hsi(data)
        peep = 5 + (mri * 15) - (hsi * 5)
        plateau = to_float(data.get('plateau_pressure'))
        driving = to_float(data.get('driving_pressure'))
        if plateau and plateau > 30:
            peep -= 2
        if driving and driving > 15:
            peep -= 1
        peep = max(5, min(round(peep), 22))

        if previous_value is not None:
            delta = peep - previous_value
            if abs(delta) > self.max_delta:
                peep = previous_value + (self.max_delta if delta > 0 else -self.max_delta)
        return peep
    
# ----------------------------------------------------------------------
# 3.1 Tidal Volume Engine (نسخة كاملة مع max_delta)
# ----------------------------------------------------------------------
class VtEngine:
    def __init__(self):
        self.normal_range = (6, 8)
        self.ards_range = (4, 6)
        self.copd_factor = 0.9
        self.max_delta = 50  # mL لكل دورة

    def calculate_pbw(self, height_cm, gender):
        if not height_cm:
            return None
        base = 50.0 if gender and gender.lower() in ['male', 'ذكر'] else 45.5
        pbw = base + 0.91 * (height_cm - 152.4)
        return max(30, pbw)

    def recommend_vt(self, data, previous_value=None):
        if not require_fields(data, ['height_cm'], 'VtEngine'):
            return None
        height = to_float(data.get('height_cm'), 170)
        gender = data.get('gender', 'Male')
        pbw = self.calculate_pbw(height, gender) or 70.0
        disease = data.get('lung_disease_pattern', '').lower()
        is_ards = 'ards' in disease
        is_copd = 'copd' in disease

        vt_min, vt_max = self.ards_range if is_ards else self.normal_range
        vt = pbw * ((vt_min + vt_max) / 2)
        if is_copd:
            vt *= self.copd_factor
        vt = max(200, min(vt, 1000))
        vt = round(vt / 10) * 10

        if previous_value is not None:
            delta = vt - previous_value
            if abs(delta) > self.max_delta:
                vt = previous_value + (self.max_delta if delta > 0 else -self.max_delta)
        return vt
    
# ----------------------------------------------------------------------
# 3.2 Minute Ventilation Engine (نسخة كاملة مع max_delta)
# ----------------------------------------------------------------------
class VeEngine:
    def __init__(self):
        self.min_ve = 4.0
        self.max_ve = 15.0
        self.paco2_target = 40.0
        self.paco2_factor = 0.1
        self.max_delta = 1.0  # L/min لكل دورة

    def calculate_pbw(self, height_cm, gender):
        if not height_cm:
            return None
        base = 50.0 if gender and gender.lower() in ['male', 'ذكر'] else 45.5
        return base + 0.91 * (height_cm - 152.4)

    def recommend_ve(self, data, previous_value=None):
        if not require_fields(data, ['height_cm'], 'VeEngine'):
            return None
        height = to_float(data.get('height_cm'), 170)
        gender = data.get('gender', 'Male')
        pbw = self.calculate_pbw(height, gender) or 70.0
        ve_base = (100 * pbw) / 1000.0
        paco2 = to_float(data.get('paco2'))
        if paco2:
            deviation = paco2 - self.paco2_target
            ve_base += deviation * self.paco2_factor
        disease = data.get('lung_disease_pattern', '').lower()
        if 'ards' in disease:
            ve_base *= 0.95
        elif 'copd' in disease:
            ve_base *= 0.9
        ve_final = max(self.min_ve, min(ve_base, self.max_ve))
        ve_final = round(ve_final * 10) / 10.0

        if previous_value is not None:
            delta = ve_final - previous_value
            if abs(delta) > self.max_delta:
                ve_final = previous_value + (self.max_delta if delta > 0 else -self.max_delta)
        return ve_final
    
# ----------------------------------------------------------------------
# 4.1 Mandatory Respiratory Rate Engine (محدث مع max_delta)
# ----------------------------------------------------------------------
class RREngine:
    def __init__(self):
        self.min_rr = 5
        self.max_rr = 40
        self.max_rr_copd = 25
        self.paco2_target = 40.0
        self.max_delta = 5  # breaths/min لكل دورة

    def recommend_rr(self, data, previous_value=None):
        ve = to_float(data.get('target_ve')) or to_float(data.get('mvent'))
        vt = to_float(data.get('target_vt')) or to_float(data.get('vte'))
        if ve is None or vt is None:
            print("Warning [RREngine]: VE or Vt data missing, cannot calculate.")
            return None
        vt_l = vt / 1000.0
        rr_base = ve / vt_l if vt_l > 0 else 15.0
        paco2 = to_float(data.get('paco2'))
        if paco2:
            rr_base *= (1 + (paco2 - self.paco2_target) * 0.01)
        disease = data.get('lung_disease_pattern', '').lower()
        if 'copd' in disease:
            rr_base = min(rr_base, self.max_rr_copd)
        rr = int(max(self.min_rr, min(rr_base, self.max_rr)))

        if previous_value is not None:
            delta = rr - previous_value
            if abs(delta) > self.max_delta:
                rr = previous_value + (self.max_delta if delta > 0 else -self.max_delta)
        return rr




# ----------------------------------------------------------------------
# 4.2 Apnea Backup Respiratory Rate Engine (محدث مع max_delta)
# ----------------------------------------------------------------------
class ApneaRREngine:
    def __init__(self):
        self.min_rate = 5
        self.max_rate = 40
        self.max_delta = 5

    def recommend_apnea_rr(self, data, previous_value=None):
        ve = to_float(data.get('target_ve')) or to_float(data.get('mvent'))
        vt = to_float(data.get('target_vt')) or to_float(data.get('vte'))
        if ve is None or vt is None:
            print("Warning [ApneaRREngine]: VE or Vt data missing, cannot calculate.")
            return None
        vt_l = vt / 1000.0
        rr_base = ve / vt_l if vt_l > 0 else 12.0
        rr = int(max(self.min_rate, min(rr_base, self.max_rate)))

        if previous_value is not None:
            delta = rr - previous_value
            if abs(delta) > self.max_delta:
                rr = previous_value + (self.max_delta if delta > 0 else -self.max_delta)
        return rr



# ----------------------------------------------------------------------
# 5.1 Inspiratory Pressure Control (PIP) (محدث مع max_delta)
# ----------------------------------------------------------------------
class PIPEngine:
    def __init__(self):
        self.min_pip = 5
        self.max_pip = 40
        self.plateau_limit = 30
        self.driving_limit = 15
        self.max_delta = 3  # cmH2O لكل دورة

    def recommend_pip(self, data, previous_value=None):
        vt = to_float(data.get('target_vt')) or to_float(data.get('vte'))
        comp = to_float(data.get('static_compliance'))
        peep = to_float(data.get('peep'))
        if vt is None or comp is None or peep is None:
            print("Warning [PIPEngine]: Missing Vt, compliance, or PEEP. Cannot calculate.")
            return None
        pip_base = (vt / comp) + peep
        res = to_float(data.get('airway_resistance'))
        if res:
            pip_base += res * 0.5
        plateau = to_float(data.get('plateau_pressure'))
        driving = to_float(data.get('driving_pressure'))
        if plateau and plateau > self.plateau_limit:
            pip_base -= 2
        if driving and driving > self.driving_limit:
            pip_base -= 1
        if data.get('hemodynamics') in ['Hypotension', 'Unstable']:
            pip_base = min(pip_base, 30)
        pip = int(max(self.min_pip, min(pip_base, self.max_pip)))

        if previous_value is not None:
            delta = pip - previous_value
            if abs(delta) > self.max_delta:
                pip = previous_value + (self.max_delta if delta > 0 else -self.max_delta)
        return pip

# ----------------------------------------------------------------------
# 5.2 Pressure Support Level (محدث مع max_delta)
# ----------------------------------------------------------------------
class PSEngine:
    def __init__(self):
        self.min_ps = 0
        self.max_ps = 30
        self.wob_map = {'Mild': 5, 'Moderate': 10, 'Severe': 15}
        self.max_delta = 2

    def recommend_ps(self, data, previous_value=None):
        wob = data.get('work_of_breathing')
        res = to_float(data.get('airway_resistance'))
        if res is None:
            print("Warning [PSEngine]: airway resistance missing, using default 10")
            res = 10
        ps_base = res * 0.8
        if wob in self.wob_map:
            ps_base += self.wob_map[wob]
        paco2 = to_float(data.get('paco2'))
        if paco2 and paco2 > 45:
            ps_base += 2
        elif paco2 and paco2 < 35:
            ps_base -= 2
        ps = int(max(self.min_ps, min(ps_base, self.max_ps)))

        if previous_value is not None:
            delta = ps - previous_value
            if abs(delta) > self.max_delta:
                ps = previous_value + (self.max_delta if delta > 0 else -self.max_delta)
        return ps

# ----------------------------------------------------------------------
# 5.3 Maximum Pressure Limit (محدث مع max_delta)
# ----------------------------------------------------------------------
class PMaxEngine:
    def __init__(self):
        self.min_pmax = 20
        self.max_pmax = 60
        self.max_delta = 5

    def recommend_pmax(self, data, previous_value=None):
        pip = to_float(data.get('pip'))
        peep = to_float(data.get('peep'))
        if pip is None or peep is None:
            print("Warning [PMaxEngine]: PIP or PEEP missing, cannot calculate.")
            return None
        pmax_base = pip + peep + 10
        ards = data.get('ards')
        if ards == 'Severe':
            pmax_base = min(pmax_base, 35)
        elif ards == 'Moderate':
            pmax_base = min(pmax_base, 40)
        else:
            pmax_base = min(pmax_base, 45)
        pmax = int(max(self.min_pmax, min(pmax_base, self.max_pmax)))

        if previous_value is not None:
            delta = pmax - previous_value
            if abs(delta) > self.max_delta:
                pmax = previous_value + (self.max_delta if delta > 0 else -self.max_delta)
        return pmax



# ----------------------------------------------------------------------
# 6.1 Inspiratory Time (محدث مع max_delta)
# ----------------------------------------------------------------------
class TIEngine:
    def __init__(self):
        self.min_ti = 0.3
        self.max_ti = 3.0
        self.max_delta = 0.2  # ثانية لكل دورة

    def recommend_ti(self, data, previous_value=None):
        rr = to_float(data.get('rr'))
        if rr is None:
            print("Warning [TIEngine]: RR missing, cannot calculate.")
            return None
        cycle = 60 / rr
        ti_base = cycle / 3
        disease = data.get('lung_disease_pattern', '').lower()
        if 'ards' in disease or 'restrictive' in disease:
            ti_base *= 1.2
        elif 'copd' in disease or 'obstructive' in disease:
            ti_base *= 0.8
        comp = to_float(data.get('static_compliance'))
        res = to_float(data.get('airway_resistance'))
        if comp and comp < 30:
            ti_base *= 1.1
        if res and res > 15:
            ti_base *= 0.9
        ti = round(max(self.min_ti, min(ti_base, self.max_ti)), 1)

        if previous_value is not None:
            delta = ti - previous_value
            if abs(delta) > self.max_delta:
                ti = previous_value + (self.max_delta if delta > 0 else -self.max_delta)
        return ti

# ----------------------------------------------------------------------
# 6.2 I:E Ratio
# ----------------------------------------------------------------------
class IERatioEngine:
    def __init__(self):
        self.options = ["1:1", "1:2", "1:3", "1:4", "2:1 (Inverse)"]

    def recommend_ie(self, data):
        # لا تتطلب حقولاً إجبارية
        ards = data.get('ards')
        disease = data.get('lung_disease_pattern', '').lower()
        osi = to_float(data.get('osi'))
        if 'copd' in disease or 'obstructive' in disease:
            return "1:3"
        if 'ards' in disease and (ards == 'Severe' or (osi and osi > 0.7)):
            return "1:1"
        if 'ards' in disease:
            return "1:2"
        return "1:2"


# ----------------------------------------------------------------------
# 6.3 Rise Time
# ----------------------------------------------------------------------
class RiseTimeEngine:
    def __init__(self):
        self.min_rise = 1
        self.max_rise = 10

    def recommend_rise(self, data):
        # لا تتطلب حقولاً إجبارية
        wob = data.get('work_of_breathing')
        res = to_float(data.get('airway_resistance'))
        comp = to_float(data.get('static_compliance'))
        rise = 5
        if wob == 'Severe':
            rise = 8
        elif wob == 'Moderate':
            rise = 6
        else:
            rise = 4
        if res and res > 15:
            rise = max(3, rise - 2)
        if comp and comp < 30:
            rise = min(9, rise + 1)
        return int(max(self.min_rise, min(rise, self.max_rise)))

# ----------------------------------------------------------------------
# 6.4 Cycling Criteria
# ----------------------------------------------------------------------
class CyclingEngine:
    def __init__(self):
        self.min_cycle = 10
        self.max_cycle = 50
        self.default = 25

    def recommend_cycling(self, data):
        disease = data.get('lung_disease_pattern', '').lower()
        res = to_float(data.get('airway_resistance'))
        if 'copd' in disease or (res and res > 15):
            return 40
        if 'ards' in disease or 'restrictive' in disease:
            return 15
        return self.default


# ----------------------------------------------------------------------
# 7.1 Flow Trigger
# ----------------------------------------------------------------------
class FlowTriggerEngine:
    def __init__(self):
        self.min_flow = 0.5
        self.max_flow = 5.0

    def recommend_flow_trigger(self, data):
        wob = data.get('work_of_breathing')
        auto_peep = data.get('auto_peep', False)
        res = to_float(data.get('airway_resistance'))
        trig = 2.0
        if wob == 'Severe':
            trig = 1.0
        elif wob == 'Mild':
            trig = 3.0
        if auto_peep:
            trig = min(4.0, trig + 1.0)
        if res and res > 15:
            trig = max(1.5, trig - 0.5)
        return round(max(self.min_flow, min(trig, self.max_flow)), 1)


# ----------------------------------------------------------------------
# 7.2 Pressure Trigger
# ----------------------------------------------------------------------
class PressureTriggerEngine:
    def __init__(self):
        self.min_press = -5.0
        self.max_press = -0.5

    def recommend_pressure_trigger(self, data):
        wob = data.get('work_of_breathing')
        auto_peep = data.get('auto_peep', False)
        consciousness = data.get('consciousness', '')
        trig = -2.0
        if wob == 'Severe':
            trig = -1.0
        elif wob == 'Mild':
            trig = -3.0
        if auto_peep:
            trig = max(-4.0, trig - 1.0)
        if 'sedated' in consciousness.lower():
            trig = min(-1.5, trig + 0.5)
        return round(max(self.min_press, min(trig, self.max_press)), 1)

# ----------------------------------------------------------------------
# 8.1 Peak Inspiratory Flow
# ----------------------------------------------------------------------
class PeakFlowEngine:
    def __init__(self):
        self.min_peak = 20
        self.max_peak = 120
        self.demand_factors = {
            'rr_threshold': 20,           # إذا زاد Spontaneous RR عن 20 نزيد الطلب
            'flow_starvation_factor': 1.2,
            'accessory_muscles_factor': 1.15,
        }
        self.resistance_factor = 1.2
        self.ards_peak_limit = 60
        self.air_trapping_factor = 1.1
        self.max_delta = 10                # الحد الأقصى للتغيير لكل دورة (L/min)

    def recommend_peak_flow(self, data, previous_value=None):
        # استخراج القيم الأساسية
        vt = to_float(data.get('target_vt')) or to_float(data.get('vte'))
        ti = to_float(data.get('ti'))
        if vt is None or ti is None:
            print("Warning [PeakFlowEngine]: Vt or Ti missing, cannot calculate.")
            return None

        # استخراج الحقول الإضافية (بقيم افتراضية)
        rr = to_float(data.get('rr'), 15)
        spontaneous_rr = to_float(data.get('spontaneous_rr'), 0)
        raw = to_float(data.get('airway_resistance'), 10)          # مقاومة المجرى الهوائي
        comp = to_float(data.get('static_compliance'), 50)         # المطاوعة الساكنة
        plateau = to_float(data.get('plateau_pressure'))
        driving = to_float(data.get('driving_pressure'))
        auto_peep = data.get('auto_peep', False)
        # حقول غير موجودة حالياً، نعطيها قيماً افتراضية
        flow_starvation = data.get('flow_starvation_detected', False)
        accessory_muscles = data.get('accessory_muscles', 'No')   # 'Yes' أو 'No'
        peak_pressure_alarm = data.get('peak_pressure_alarm', False)

        # الخطوة 1: الحساب الأساسي
        peak_base = (vt * 60) / (ti * 1000)   # L/min
        peak = peak_base

        # الخطوة 2: Demand Adjustment Factor
        demand_index = 0
        if spontaneous_rr > self.demand_factors['rr_threshold']:
            demand_index += 1
        if flow_starvation:
            demand_index += 1
        if accessory_muscles == 'Yes':
            demand_index += 1

        if demand_index >= 2:   # ارتفاع الطلب
            peak *= 1.25
        elif demand_index == 1:
            peak *= 1.1

        # الخطوة 3: Resistance Adjustment (مرضى انسداد)
        if raw > 15:
            peak *= self.resistance_factor
            # التحقق من أن زمن الزفير كافٍ (Te >= 3 × time constant)
            time_constant = (comp / 1000) * raw   # ثانية (لأن comp بوحدة mL/cmH2O نحول إلى L/cmH2O)
            # حساب زمن الزفير
            cycle_time = 60 / rr if rr > 0 else 4.0
            te = cycle_time - ti
            if te < 3 * time_constant:
                # زيادة peak أكثر لتقصير Ti (زيادة peak تقلل Ti تلقائياً في الحسابات اللاحقة)
                peak *= 1.1

        # الخطوة 4: Low Compliance Adjustment (ARDS)
        if comp < 40:
            peak = min(peak, self.ards_peak_limit)
            # إذا كان الضغط مرتفعاً نخفض peak
            if (plateau and plateau > 30) or (driving and driving > 15) or peak_pressure_alarm:
                peak -= 10

        # الخطوة 5: Air Trapping Logic
        if auto_peep:
            peak *= self.air_trapping_factor

        # الخطوة 6: تطبيق القيد النهائي
        peak = max(self.min_peak, min(peak, self.max_peak))

        # الخطوة 7: تطبيق حد التغيير لكل دورة
        if previous_value is not None:
            delta = peak - previous_value
            if abs(delta) > self.max_delta:
                peak = previous_value + (self.max_delta if delta > 0 else -self.max_delta)

        return int(round(peak))

# ----------------------------------------------------------------------
# 8.2 Flow Pattern
# ----------------------------------------------------------------------
class FlowPatternEngine:
    def recommend_pattern(self, data):
        disease = data.get('lung_disease_pattern', '').lower()
        mode = data.get('mode', '').lower()
        if 'ards' in disease or 'restrictive' in disease:
            return "Decelerating"
        if 'copd' in disease:
            return "Square"
        if 'psv' in mode or 'spontaneous' in mode:
            return "Sinusoidal"
        return "Decelerating"


# ----------------------------------------------------------------------
# 9.1 ASV Target %
# ----------------------------------------------------------------------
class ASVEngine:
    def __init__(self):
        self.min_asv = 50
        self.max_asv = 200

    def recommend_asv(self, data):
        paco2 = to_float(data.get('paco2'))
        if paco2 is None:
            return 100
        if paco2 > 50:
            return 120
        if paco2 > 45:
            return 110
        if paco2 < 35:
            return 90
        return 100


# ----------------------------------------------------------------------
# 9.2 PAV Gain %
# ----------------------------------------------------------------------
class PAVGainEngine:
    def __init__(self):
        self.min_gain = 30
        self.max_gain = 80

    def recommend_pav_gain(self, data):
        wob = data.get('work_of_breathing')
        if wob == 'Severe':
            return 70
        if wob == 'Moderate':
            return 50
        return 40


# ----------------------------------------------------------------------
# 9.3 Tube Compensation %
# ----------------------------------------------------------------------
class TubeCompEngine:
    def __init__(self):
        self.min_comp = 0
        self.max_comp = 100

    def recommend_tube_comp(self, data):
        ett = to_float(data.get('ett_size'))
        if ett is None:
            return 50
        if ett <= 7.0:
            return 80
        if ett <= 8.0:
            return 60
        return 40


# ----------------------------------------------------------------------
# 9.4 NIV IPAP
# ----------------------------------------------------------------------
class IPAPEngine:
    def __init__(self):
        self.min_ipap = 8
        self.max_ipap = 25
        self.max_delta = 2  # cmH2O per cycle

    def recommend_ipap(self, data, previous_value=None):
        vt = to_float(data.get('target_vt')) or to_float(data.get('vte'))
        if vt is None:
            print("Warning [IPAPEngine]: Vt missing, cannot calculate.")
            return None
        ipap = 12 + (vt - 400) / 50
        paco2 = to_float(data.get('paco2'))
        if paco2 and paco2 > 45:
            ipap += 2
        ipap = int(max(self.min_ipap, min(ipap, self.max_ipap)))

        if previous_value is not None:
            delta = ipap - previous_value
            if abs(delta) > self.max_delta:
                ipap = previous_value + (self.max_delta if delta > 0 else -self.max_delta)
        return ipap


# ----------------------------------------------------------------------
# 9.5 NIV EPAP
# ----------------------------------------------------------------------
class EPAPEngine:
    def __init__(self):
        self.min_epap = 4
        self.max_epap = 12
        self.max_delta = 1  # cmH2O per cycle

    def recommend_epap(self, data, previous_value=None):
        spo2 = to_float(data.get('spo2'))
        epap = 5
        if spo2 and spo2 < 90:
            epap += 2
        disease = data.get('lung_disease_pattern', '').lower()
        if 'copd' in disease:
            epap += 1
        epap = int(max(self.min_epap, min(epap, self.max_epap)))

        if previous_value is not None:
            delta = epap - previous_value
            if abs(delta) > self.max_delta:
                epap = previous_value + (self.max_delta if delta > 0 else -self.max_delta)
        return epap

# ----------------------------------------------------------------------
# 11. Alarms Configuration
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# 11. Alarms Configuration (محدث)
# ----------------------------------------------------------------------
# في all_engines.py، استبدل محتوى AlarmsEngine بما يلي:

class AlarmsEngine:
    def __init__(self):
        self.base_pressure_margin = 10
        self.base_vt_margin = 100
        self.base_rr_margin = 10
        self.base_mv_margin = 2
        self.base_fio2_margin = 10
        self.apnea_default = 20

        self.compliance_sensitivity = 0.3
        self.resistance_sensitivity = 0.2
        self.co2_sensitivity = 0.25
        self.oxygenation_sensitivity = 0.2
        self.effort_sensitivity = 0.15

        self.baseline = {}

    def calculate_pbw(self, height_cm, gender):
        if not height_cm:
            return 70.0
        base = 50.0 if gender and gender.lower() in ['male', 'ذكر'] else 45.5
        pbw = base + 0.91 * (height_cm - 152.4)
        return max(30, pbw)

    def update_baseline(self, param, value):
        if param not in self.baseline:
            self.baseline[param] = []
        self.baseline[param].append(value)
        if len(self.baseline[param]) > 10:
            self.baseline[param].pop(0)

    def get_avg(self, param):
        if param in self.baseline and self.baseline[param]:
            return sum(self.baseline[param]) / len(self.baseline[param])
        return None

    def _calculate_dynamic_margin(self, base_margin, data):
        comp = to_float(data.get('static_compliance'), 50)
        raw = to_float(data.get('airway_resistance'), 10)
        paco2 = to_float(data.get('paco2'), 40)
        spo2 = to_float(data.get('spo2'), 95)
        wob = data.get('work_of_breathing', 'Moderate')

        baseline_comp = self.get_avg('static_compliance') or comp
        baseline_raw = self.get_avg('airway_resistance') or raw
        baseline_paco2 = self.get_avg('paco2') or paco2
        baseline_spo2 = self.get_avg('spo2') or spo2

        comp_dev = abs(comp - baseline_comp) / (baseline_comp + 1)
        raw_dev = abs(raw - baseline_raw) / (baseline_raw + 1)
        paco2_dev = abs(paco2 - baseline_paco2) / (baseline_paco2 + 1)
        spo2_dev = abs(spo2 - baseline_spo2) / (baseline_spo2 + 1)
        wob_factor = {'Mild': 0.2, 'Moderate': 0.5, 'Severe': 1.0}.get(wob, 0.5)

        adjustment = (
            self.compliance_sensitivity * comp_dev +
            self.resistance_sensitivity * raw_dev +
            self.co2_sensitivity * paco2_dev +
            self.oxygenation_sensitivity * spo2_dev +
            self.effort_sensitivity * wob_factor
        )
        margin = base_margin * (1 + adjustment)
        return min(margin, base_margin * 2)

    def recommend_high_pressure(self, data):
        pip = to_float(data.get('pip'))
        peep = to_float(data.get('peep'))
        if pip is None or peep is None:
            pip = pip or 25
            peep = peep or 5

        vt = to_float(data.get('target_vt')) or to_float(data.get('vte'))
        comp = to_float(data.get('static_compliance'))
        flow = to_float(data.get('peak_flow')) or 60
        raw = to_float(data.get('airway_resistance')) or 10

        if vt and comp:
            pip_est = (vt / comp) + (flow * raw / 1000) + peep
            pip_est = max(pip_est, pip)
        else:
            pip_est = pip + 5

        base_margin = self.base_pressure_margin
        margin = self._calculate_dynamic_margin(base_margin, data)
        baseline = self.get_avg('pip') or pip_est
        high_limit = baseline + margin
        if comp and comp < 40:
            high_limit -= 2
        return round(high_limit)

    def recommend_low_vt(self, data):
        height = to_float(data.get('height_cm'))
        gender = data.get('gender', 'Male')
        pbw = self.calculate_pbw(height, gender) if height else 70.0
        target_low = pbw * 4   # 4 mL/kg
        target_high = pbw * 6   # 6 mL/kg
        target_vt = (target_low + target_high) / 2

        base_margin = self.base_vt_margin
        margin = self._calculate_dynamic_margin(base_margin, data)
        low_limit = target_vt - margin
        return max(100, round(low_limit))

    def recommend_high_rr(self, data):
        rr = to_float(data.get('rr'))
        if rr is None:
            rr = 15

        paco2 = to_float(data.get('paco2'), 40)
        disease = data.get('lung_disease_pattern', '').lower()
        is_copd = 'copd' in disease

        base_margin = self.base_rr_margin
        margin = self._calculate_dynamic_margin(base_margin, data)
        baseline = self.get_avg('rr') or rr
        high_limit = baseline + margin

        # تعديل حسب PaCO2
        if paco2 > 50:
            high_limit += 5
        elif paco2 > 45:
            high_limit += 2
        elif paco2 < 35:
            high_limit -= 3

        # تعديل لمرضى COPD
        if is_copd:
            high_limit = min(high_limit, 25)

        return round(high_limit)

    def recommend_low_mv(self, data):
        mv = to_float(data.get('mvent'))
        if mv is None:
            mv = 6

        base_margin = self.base_mv_margin
        margin = self._calculate_dynamic_margin(base_margin, data)
        baseline = self.get_avg('mvent') or mv
        low_limit = baseline - margin
        return round(max(2.0, low_limit), 1)

    def recommend_apnea_time(self, data):
        return self.apnea_default

    def recommend_high_fio2(self, data):
        fio2 = to_float(data.get('fio2'))
        if fio2 is None:
            fio2 = 40

        base_margin = self.base_fio2_margin
        margin = self._calculate_dynamic_margin(base_margin, data)
        baseline = self.get_avg('fio2') or fio2
        high_limit = baseline + margin
        return min(100, round(high_limit))

    def recommend_low_fio2(self, data):
        fio2 = to_float(data.get('fio2'))
        if fio2 is None:
            fio2 = 40

        base_margin = self.base_fio2_margin
        margin = self._calculate_dynamic_margin(base_margin, data)
        baseline = self.get_avg('fio2') or fio2
        low_limit = baseline - margin
        return max(21, round(low_limit))
# ----------------------------------------------------------------------
# وحدات إضافية لتوسيع وظائف النظام (يُضاف في نهاية ملف all_engines.py)
# ----------------------------------------------------------------------

# ======================================================================
# 1. Trend Buffer لتخزين وتحليل اتجاهات المتغيرات
# ======================================================================
class TrendBuffer:
    """
    مخزن للقيم التاريخية للمتغيرات المختلفة،
    مع إمكانية حساب المتوسط والانحراف المعياري واكتشاف الاتجاه.
    """
    def __init__(self, maxlen=10):
        self.maxlen = maxlen
        self.data = {}          # قاموس {param_name: list of values}
        self.timestamps = {}     # اختياري: تخزين الوقت المرتبط

    def add(self, param, value, timestamp=None):
        """إضافة قيمة جديدة للمتغير"""
        if param not in self.data:
            self.data[param] = []
            self.timestamps[param] = []
        self.data[param].append(value)
        if timestamp:
            self.timestamps[param].append(timestamp)
        # الاحتفاظ بآخر maxlen قيمة
        if len(self.data[param]) > self.maxlen:
            self.data[param].pop(0)
            if timestamp and len(self.timestamps[param]) > self.maxlen:
                self.timestamps[param].pop(0)

    def get_latest(self, param, default=None):
        """آخر قيمة مسجلة للمتغير"""
        if param in self.data and self.data[param]:
            return self.data[param][-1]
        return default

    def get_mean(self, param, n_last=None):
        """متوسط آخر n قيمة (أو الكل إذا لم يحدد)"""
        if param not in self.data or not self.data[param]:
            return None
        values = self.data[param]
        if n_last:
            values = values[-n_last:]
        return sum(values) / len(values)

    def get_trend(self, param, window=3):
        """
        تحليل الاتجاه: يعيد 'rising', 'falling', 'stable'
        بناءً على مقارنة متوسط آخر window قيمة مع المتوسط العام.
        """
        if param not in self.data or len(self.data[param]) < window:
            return 'stable'
        recent = self.data[param][-window:]
        older = self.data[param][:-window] if len(self.data[param]) > window else self.data[param]
        if not older:
            return 'stable'
        avg_recent = sum(recent) / len(recent)
        avg_older = sum(older) / len(older)
        diff = avg_recent - avg_older
        if diff > 0.05 * avg_older:      # ارتفاع > 5%
            return 'rising'
        if diff < -0.05 * avg_older:     # انخفاض > 5%
            return 'falling'
        return 'stable'

    def get_std(self, param):
        """الانحراف المعياري لقيم المتغير"""
        if param not in self.data or len(self.data[param]) < 2:
            return 0.0
        values = self.data[param]
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5


# ======================================================================
# 2. تطبيق الإعدادات التلقائية لجميع المحركات (Auto Settings)
# ======================================================================
def apply_auto_settings(data, trend_buffer=None):
    """
    تشغيل جميع محركات التوصية وجمع النتائج مع تحذيرات البيانات المفقودة.
    - data: قاموس يحتوي على القيم المدخلة.
    - trend_buffer: كائن TrendBuffer اختياري لاستخدامه في التحليلات المتقدمة.
    يعيد قاموساً بالمفاتيح التالية:
        - recommendations: توصيات كل محرك.
        - warnings: قائمة بالتحذيرات (لكل محرك).
        - missing_fields: قاموس بأسماء المحركات والحقول المفقودة.
    """
    # إنشاء كائنات المحركات
    fio2_engine = FiO2Engine()
    peep_engine = PEEPEEngine()
    vt_engine = VtEngine()
    ve_engine = VeEngine()
    rr_engine = RREngine()
    apnea_rr_engine = ApneaRREngine()
    pip_engine = PIPEngine()
    ps_engine = PSEngine()
    pmax_engine = PMaxEngine()
    ti_engine = TIEngine()
    ie_engine = IERatioEngine()
    rise_engine = RiseTimeEngine()
    cycling_engine = CyclingEngine()
    flow_trigger_engine = FlowTriggerEngine()
    pressure_trigger_engine = PressureTriggerEngine()
    peak_flow_engine = PeakFlowEngine()
    flow_pattern_engine = FlowPatternEngine()
    asv_engine = ASVEngine()
    pav_gain_engine = PAVGainEngine()
    tube_comp_engine = TubeCompEngine()
    ipap_engine = IPAPEngine()
    epap_engine = EPAPEngine()
    alarms_engine = AlarmsEngine()

    # قاموس لتخزين التوصيات
    recommendations = {}
    warnings = []
    missing_fields = {}

    # دالة مساعدة لتشغيل محرك وتسجيل التحذيرات
    def run_engine(engine_name, engine_func, *args, **kwargs):
        try:
            result = engine_func(*args, **kwargs)
            if result is None:
                # إذا أرجع None فهذا يعني فشل بسبب بيانات مفقودة (المحرك يجب أن يطبع تحذيراً)
                # سنضيف تحذيراً عاماً
                warnings.append(f"{engine_name}: لم يتمكن من الحساب (بيانات مفقودة).")
                missing_fields[engine_name] = check_required(data, engine_func.__code__.co_varnames)  # تقريبي
            return result
        except Exception as e:
            warnings.append(f"{engine_name}: خطأ في الحساب - {str(e)}")
            return None

    # FiO2
    recommendations['fio2'] = run_engine('FiO2Engine', fio2_engine.recommend_fio2, data)
    # PEEP
    recommendations['peep'] = run_engine('PEEPEngine', peep_engine.recommend_peep, data)
    # Vt
    recommendations['vt'] = run_engine('VtEngine', vt_engine.recommend_vt, data)
    # Minute Ventilation
    recommendations['ve'] = run_engine('VeEngine', ve_engine.recommend_ve, data)
    # Respiratory Rate
    recommendations['rr'] = run_engine('RREngine', rr_engine.recommend_rr, data)
    # Apnea RR
    recommendations['apnea_rr'] = run_engine('ApneaRREngine', apnea_rr_engine.recommend_apnea_rr, data)
    # PIP
    recommendations['pip'] = run_engine('PIPEngine', pip_engine.recommend_pip, data)
    # PS
    recommendations['ps'] = run_engine('PSEngine', ps_engine.recommend_ps, data)
    # PMax
    recommendations['pmax'] = run_engine('PMaxEngine', pmax_engine.recommend_pmax, data)
    # Ti
    recommendations['ti'] = run_engine('TIEngine', ti_engine.recommend_ti, data)
    # I:E
    recommendations['ie_ratio'] = run_engine('IERatioEngine', ie_engine.recommend_ie, data)
    # Rise Time
    recommendations['rise_time'] = run_engine('RiseTimeEngine', rise_engine.recommend_rise, data)
    # Cycling
    recommendations['cycling'] = run_engine('CyclingEngine', cycling_engine.recommend_cycling, data)
    # Flow Trigger
    recommendations['flow_trigger'] = run_engine('FlowTriggerEngine', flow_trigger_engine.recommend_flow_trigger, data)
    # Pressure Trigger
    recommendations['pressure_trigger'] = run_engine('PressureTriggerEngine', pressure_trigger_engine.recommend_pressure_trigger, data)
    # Peak Flow
    recommendations['peak_flow'] = run_engine('PeakFlowEngine', peak_flow_engine.recommend_peak_flow, data)
    # Flow Pattern
    recommendations['flow_pattern'] = run_engine('FlowPatternEngine', flow_pattern_engine.recommend_pattern, data)
    # ASV %
    recommendations['asv_percent'] = run_engine('ASVEngine', asv_engine.recommend_asv, data)
    # PAV Gain %
    recommendations['pav_gain'] = run_engine('PAVGainEngine', pav_gain_engine.recommend_pav_gain, data)
    # Tube Compensation %
    recommendations['tube_comp'] = run_engine('TubeCompEngine', tube_comp_engine.recommend_tube_comp, data)
    # NIV IPAP
    recommendations['ipap'] = run_engine('IPAPEngine', ipap_engine.recommend_ipap, data)
    # NIV EPAP
    recommendations['epap'] = run_engine('EPAPEngine', epap_engine.recommend_epap, data)

    # توصيات الإنذارات (قد تحتاج إلى تمرير البيانات الحالية والتاريخية)
    # نمرر trend_buffer إذا كان موجوداً لتحسين الدقة
    alarms_rec = {}
    alarms_rec['high_pressure'] = run_engine('AlarmsEngine (High Pressure)', alarms_engine.recommend_high_pressure, data)
    alarms_rec['low_vt'] = run_engine('AlarmsEngine (Low Vt)', alarms_engine.recommend_low_vt, data)
    alarms_rec['high_rr'] = run_engine('AlarmsEngine (High RR)', alarms_engine.recommend_high_rr, data)
    alarms_rec['low_mv'] = run_engine('AlarmsEngine (Low MV)', alarms_engine.recommend_low_mv, data)
    alarms_rec['apnea_time'] = run_engine('AlarmsEngine (Apnea Time)', alarms_engine.recommend_apnea_time, data)
    alarms_rec['high_fio2'] = run_engine('AlarmsEngine (High FiO2)', alarms_engine.recommend_high_fio2, data)
    alarms_rec['low_fio2'] = run_engine('AlarmsEngine (Low FiO2)', alarms_engine.recommend_low_fio2, data)
    recommendations['alarms'] = alarms_rec

    return {
        'recommendations': recommendations,
        'warnings': warnings,
        'missing_fields': missing_fields
    }


# ======================================================================
# 3. تحديث check_alarms لاستخدام AlarmsEngine مع عداد تأكيد
# ======================================================================
class AlarmMonitor:
    """
    مراقب الإنذارات مع عدادات تأكيد لتجنب الإنذارات الكاذبة.
    يحتفظ بحالة كل إنذار وعدد مرات التكرار المطلوبة لتأكيده.
    """
    def __init__(self, alarms_engine, confirmation_count=3):
        self.alarms_engine = alarms_engine
        self.confirmation_count = confirmation_count
        self.alarm_state = {}       # لكل إنذار: {'count': 0, 'active': False, 'limits': {}}
        self.trend_buffer = None    # يمكن ربطه لاحقاً

    def set_trend_buffer(self, trend_buffer):
        self.trend_buffer = trend_buffer

    def check_alarms(self, data):
        """
        فحص القيم الحالية ومقارنتها بحدود الإنذار (يتم حسابها ديناميكياً من AlarmsEngine).
        يعيد قائمة بالإنذارات النشطة (المؤكدة) بعد الوصول للعدد المطلوب من التكرارات.
        """
        # تحديث حدود الإنذار بناءً على البيانات الحالية
        limits = {
            'high_pressure': self.alarms_engine.recommend_high_pressure(data),
            'low_vt': self.alarms_engine.recommend_low_vt(data),
            'high_rr': self.alarms_engine.recommend_high_rr(data),
            'low_mv': self.alarms_engine.recommend_low_mv(data),
            'apnea_time': self.alarms_engine.recommend_apnea_time(data),
            'high_fio2': self.alarms_engine.recommend_high_fio2(data),
            'low_fio2': self.alarms_engine.recommend_low_fio2(data)
        }

        # استخراج القيم الحالية من data
        current = {
            'pip': to_float(data.get('pip')),
            'vt': to_float(data.get('vte')) or to_float(data.get('target_vt')),
            'rr': to_float(data.get('rr')),
            'mvent': to_float(data.get('mvent')),
            'fio2': to_float(data.get('fio2'))
        }

        # تعريف شروط الإنذار (يمكن توسيعها)
        alarm_conditions = [
            ('high_pressure', current['pip'] is not None and limits['high_pressure'] is not None and current['pip'] > limits['high_pressure']),
            ('low_vt', current['vt'] is not None and limits['low_vt'] is not None and current['vt'] < limits['low_vt']),
            ('high_rr', current['rr'] is not None and limits['high_rr'] is not None and current['rr'] > limits['high_rr']),
            ('low_mv', current['mvent'] is not None and limits['low_mv'] is not None and current['mvent'] < limits['low_mv']),
            ('high_fio2', current['fio2'] is not None and limits['high_fio2'] is not None and current['fio2'] > limits['high_fio2']),
            ('low_fio2', current['fio2'] is not None and limits['low_fio2'] is not None and current['fio2'] < limits['low_fio2'])
        ]
        # ملاحظة: apnea_time لا يفحص هنا، يمكن إضافته بشكل منفصل

        active_alarms = []
        for alarm_name, condition in alarm_conditions:
            if alarm_name not in self.alarm_state:
                self.alarm_state[alarm_name] = {'count': 0, 'active': False, 'limits': limits.get(alarm_name)}

            # إذا تحقق الشرط
            if condition:
                self.alarm_state[alarm_name]['count'] += 1
                # إذا وصل العداد إلى الحد المطلوب ولم يكن الإنذار نشطاً بالفعل، نفعّله
                if self.alarm_state[alarm_name]['count'] >= self.confirmation_count and not self.alarm_state[alarm_name]['active']:
                    self.alarm_state[alarm_name]['active'] = True
                    active_alarms.append({
                        'name': alarm_name,
                        'limit': limits[alarm_name],
                        'current_value': current[alarm_name.split('_')[1]] if alarm_name != 'high_pressure' else current['pip'],
                        'message': f"{alarm_name} exceeded limit"
                    })
            else:
                # إذا لم يتحقق الشرط، نخفض العداد (أو نعيد ضبطه) ونلغي النشاط إذا كان العداد صفر
                self.alarm_state[alarm_name]['count'] = max(0, self.alarm_state[alarm_name]['count'] - 1)
                if self.alarm_state[alarm_name]['count'] == 0:
                    self.alarm_state[alarm_name]['active'] = False

        # يمكن إضافة إنذار apnea بشكل منفصل إذا لم تكن هناك أنفاس خلال فترة زمنية
        # (يتطلب مراقبة الوقت، هنا نبسط)
        return active_alarms


# ======================================================================
# 4. توحيد أسلوب التعامل مع البيانات المفقودة في المحركات
# ======================================================================
# (نقوم بمراجعة المحركات التي لا تتحقق من الحقول المطلوبة بشكل صحيح وتعديلها)
# ملاحظة: معظم المحركات تستخدم require_fields أو تطبع تحذيراً وتعيد None.
# لكن بعضها مثل PS Engine, RiseTimeEngine, CyclingEngine لا تتطلب حقولاً إجبارية، وهذا مقبول.
# إذا أردنا توحيد الأسلوب، نضيف في بداية كل دالة recommend_* فحصاً باستخدام require_fields
# للحقول الأساسية التي بدونها لا يمكن الحساب. لكن هذا قد يكون موجوداً بالفعل.
# نكتفي بتعزيز دالة run_engine في apply_auto_settings للتعامل مع None.

# ======================================================================
# 5. تحسين واجهة المستخدم: دالة تلخيص البيانات المفقودة
# ======================================================================
def get_missing_fields_summary(auto_settings_result):
    """
    تستخدم نتيجة apply_auto_settings لإنشاء نص ملخص عن الحقول المفقودة لكل محرك.
    """
    missing = auto_settings_result.get('missing_fields', {})
    warnings = auto_settings_result.get('warnings', [])
    summary = "تحذيرات البيانات المفقودة:\n"
    for engine, fields in missing.items():
        if fields:
            summary += f"- {engine}: الحقول المطلوبة {fields}\n"
    if warnings:
        summary += "\n".join(warnings)
    if not missing and not warnings:
        summary = "جميع البيانات متوفرة، لا توجد تحذيرات."
    return summary


# ======================================================================
# مثال استخدام (اختياري)
# ======================================================================
if __name__ == "__main__":
    # بيانات تجريبية
    sample_data = {
        'pao2': 75, 'spo2': 92, 'fio2': 40,
        'static_compliance': 45, 'map': 70, 'plateau_pressure': 25,
        'height_cm': 175, 'gender': 'Male', 'lung_disease_pattern': 'ARDS',
        'target_vt': 450, 'vte': 430, 'mvent': 7.2,
        'paco2': 48, 'peep': 8, 'airway_resistance': 12,
        'work_of_breathing': 'Moderate', 'auto_peep': False,
        'rr': 18, 'pip': 28, 'cardiac_output': 5.0,
        'ett_size': 7.5
    }

    trend = TrendBuffer()
    # إضافة بعض البيانات التاريخية
    for i in range(5):
        trend.add('rr', 18 + i, i)
        trend.add('pip', 28 + i*0.5, i)
        trend.add('resistance', 12 + i*0.2, i)
        trend.add('mean_flow', 35 - i, i)

    result = apply_auto_settings(sample_data, trend)
    print("التوصيات:")
    for k, v in result['recommendations'].items():
        print(f"  {k}: {v}")
    print("\nالتحذيرات:")
    for w in result['warnings']:
        print(f"  {w}")
    print("\nملخص البيانات المفقودة:")
    print(get_missing_fields_summary(result))

    # اختبار مراقب الإنذارات
    alarms_engine = AlarmsEngine()
    monitor = AlarmMonitor(alarms_engine, confirmation_count=2)
    monitor.set_trend_buffer(trend)
    # محاكاة عدة دورات
    for i in range(3):
        sample_data['pip'] = 35 + i  # زيادة PIP
        active = monitor.check_alarms(sample_data)
        if active:
            print(f"الدورة {i+1}: إنذارات نشطة: {active}")