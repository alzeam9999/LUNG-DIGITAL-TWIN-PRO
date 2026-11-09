"""Read-only snapshots of structured simulation data; never export patient records/logs."""
import math
from datetime import datetime, timezone
from PyQt5.QtWidgets import QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox


def numeric(value):
    if isinstance(value, (int, float)) and math.isfinite(value):
        return value
    if isinstance(value, (tuple, list)):
        converted = [numeric(v) for v in value]
        if all(v is not None for v in converted):
            return converted
    return None


def form_controls(dialog):
    values = {}
    for name, widget in vars(dialog).items():
        if not name.startswith("ai_"):
            continue
        if isinstance(widget, QComboBox):
            value = widget.currentText()
        elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            value = widget.value()
        elif isinstance(widget, QCheckBox):
            value = widget.isChecked()
        else:
            continue
        values[name] = value
    return values


def collect_simulation_data(dialog):
    """Called on the GUI thread on each Send; no simulation updates are triggered."""
    form = dialog.collect_ai_data()
    form.pop("ai_query", None)
    form_values = {k: {"value": v, "source": "form default" if v == dialog.defaults.get(k)
                       else "manual entry"} for k, v in form.items()}
    # Include every bounded form control, including controls omitted by the legacy collector.
    for name, value in form_controls(dialog).items():
        form_values[name] = {"value": value, "source": "form default"
                            if value == dialog.control_defaults.get(name) else "manual entry"}
    result = {"snapshot_utc": datetime.now(timezone.utc).isoformat(), "form": form_values,
              "timing_note": "Snapshot taken on Send. Display values are the latest available; "
                             "their original measurement timestamps are not available."}
    dashboard = dialog.parent()
    if dashboard is None or not hasattr(dashboard, "current_params"):
        result["dashboard"] = {"available": False}
        return result
    params = {k: numeric(v) for k, v in dashboard.current_params.items() if numeric(v) is not None}
    displayed = {}
    for key, label in dashboard.value_labels.items():
        try:
            value = float(label.text())
        except ValueError:
            value = None
        displayed[key] = {"value": numeric(value), "source": "current dashboard display",
                          "unit": dashboard.RULES.get(key, {}).get("unit", "not specified")}
    # Only bounded clinical selections and known numeric parameter names may be
    # read from patient_full_data. Names, IDs, notes, paths and logs stay local.
    clinical = {}
    for key, widget_name in {"consciousness": "ai_consciousness", "synchrony": "ai_synchrony",
            "rr_wob": "ai_rr_wob", "sedation": "ai_sedation", "hemodynamics": "ai_hemodynamics",
            "alarms_response": "ai_alarms", "weaning": "ai_weaning", "mask_seal": "ai_mask"}.items():
        value = dashboard.patient_full_data.get(key)
        widget = getattr(dialog, widget_name, None)
        if isinstance(value, str) and widget is not None and widget.findText(value) >= 0:
            clinical[key] = {"value": value, "source": "dashboard clinical selection"}
    patient_parameters = {k: numeric(v) for k, v in dashboard.patient_full_data.items()
                          if k in set(params) | set(displayed) and numeric(v) is not None}
    result["dashboard"] = {
        "available": True, "data_source": dashboard.data_source,
        "ventilation_mode": dashboard.mode_box.currentText(),
        "simulation_running": dashboard.sim_timer.isActive(),
        "configured_parameters": {"source": "configured ranges/settings, not measurements", "values": params},
        "displayed_parameters": displayed, "clinical_status": clinical,
        "entered_numeric_parameters": patient_parameters,
        "alarm_flags": {k: v for k, v in dashboard.alarm_flags.items() if isinstance(v, bool)},
        "waveform_alerts": {k: v for k, v in dashboard.waveform_alerts.items() if isinstance(v, bool)},
        "alarm_thresholds": dashboard.RULES,
        "waveforms": {name: numeric(getattr(dashboard, name, []))
                      for name in ("pressure_data", "flow_data", "volume_data")}}
    return result
