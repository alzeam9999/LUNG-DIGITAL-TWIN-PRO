"""Qt chat behavior shared by the existing dashboard form."""
import json
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QLabel, QTextEdit, QCheckBox, QMessageBox, QDialog
from ai_service import AIService, AIServiceError
from ai_simulation_data import collect_simulation_data, form_controls
from ai_chat_display import ChatDisplay


class AIWorker(QThread):
    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, service, question, context=None, parent=None, request=None):
        super().__init__(parent)
        self.service, self.question, self.context = service, question, context
        self.request = request

    def run(self):
        try:
            if self.request is None:
                answer = self.service.ask(self.question, self.context)
            else:
                answer = self.service.ask(self.question, self.context, request=self.request)
            self.succeeded.emit(answer)
        except AIServiceError as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("Unexpected AI error. No settings were changed.")


class AIChatMixin:
    def setup_chat(self, layout, send_button):
        self.service = AIService()
        self.worker = None
        self.send_button = send_button
        self.defaults = self.collect_ai_data()
        self.defaults.pop("ai_query", None)
        self.control_defaults = form_controls(self)
        self.notice = QLabel("Educational / research simulation only. Not validated clinical decision support.\n"
                             "Use synthetic, non-identifiable questions only. No recommendations are applied.\n"
                             "Form values and current dashboard values are labeled separately.\n"
                             "Text-only and simulation-assisted requests use separate histories.")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.include_simulation_data = QCheckBox("Include Simulation Data")
        self.include_simulation_data.setChecked(False)
        self.include_simulation_data.setToolTip(
            "Include a fresh snapshot of dashboard values, settings, alarms and clinical selections. "
            "Review the preview before sending. Off sends only text and text-only history.")
        self.share_form = self.include_simulation_data  # Existing callers remain compatible.
        layout.insertWidget(0, self.include_simulation_data)
        self.transcript = ChatDisplay()
        layout.addWidget(self.transcript)
        self.status = QLabel("Ready. Each request requires a data preview and confirmation.")
        layout.addWidget(self.status)

    def on_send(self):
        if self.worker is not None:
            return
        question = self.ai_text.toPlainText()
        if not question.strip() or len(question) > 12000:
            self.status.setText("Enter a question of 1–12,000 characters.")
            return
        context = None
        if self.share_form.isChecked():
            context = json.dumps(collect_simulation_data(self), indent=2,
                                 ensure_ascii=False, allow_nan=False)
        request = self.service.prepare_request(question, context)
        preview = QMessageBox(self)
        preview.setWindowTitle("Confirm external AI request")
        preview.setText("Send this synthetic educational question and conversation history to the configured AI service?\n"
                        "The default service is OpenRouter, which routes requests to a model provider.\n"
                        + ("Simulation data: INCLUDED.\n" if context is not None
                           else "Simulation data: NOT INCLUDED.\n") +
                        "Confirm that the preview contains no identifiable patient information.\n"
                        "Details show the exact messages and optional parameters. API charges may apply.")
        preview.setDetailedText(json.dumps(request, indent=2, ensure_ascii=False))
        preview.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        preview.setDefaultButton(QMessageBox.No)
        if preview.exec_() != QMessageBox.Yes:
            return
        self.send_button.setEnabled(False)
        self.ai_text.setReadOnly(True)
        self.status.setText("Waiting for AI…")
        self.transcript.begin_turn(question)
        self.worker = AIWorker(self.service, question, context, self, request=request)
        self.worker.succeeded.connect(self.ai_succeeded)
        self.worker.failed.connect(self.ai_failed)
        self.worker.finished.connect(self.ai_finished)
        self.worker.start()

    def ai_succeeded(self, answer):
        self.transcript.finish_turn(answer)
        self.ai_text.clear()
        self.status.setText("Response received. No settings were changed.")

    def ai_failed(self, message):
        self.transcript.finish_turn(message, error=True)
        self.status.setText(message)

    def ai_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.send_button.setEnabled(True)
        self.ai_text.setReadOnly(False)

    def done(self, result):
        if self.worker is not None:
            self.status.setText("Wait for the current request to finish before closing.")
            return
        super().done(result)

    def closeEvent(self, event):
        if self.worker is not None:
            event.ignore()
            self.status.setText("Wait for the current request to finish before closing.")
        else:
            super().closeEvent(event)
