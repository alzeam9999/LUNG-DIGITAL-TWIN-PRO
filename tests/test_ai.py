import ast
import copy
import json
import os
import sys
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout, QPushButton, QTextEdit, QMessageBox
from PyQt5.QtCore import QEventLoop, QTimer
from ai_service import AIService, AIServiceError, DEFAULT_BASE_URL, DEFAULT_MODEL
from ai_chat import AIChatMixin, AIWorker


class ServiceTests(unittest.TestCase):
    def client(self, text="Educational answer"):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(output_text=text)
        return client

    def test_success_history_context_and_configuration(self):
        client = self.client()
        service = AIService(client)
        with patch.dict(os.environ, {"OPENAI_MODEL": "test-model"}):
            self.assertEqual(service.ask("Explain PEEP", "synthetic parameters"), "Educational answer")
        args = client.responses.create.call_args.kwargs
        self.assertEqual(args["model"], "test-model")
        self.assertFalse(args["store"])
        self.assertIn("synthetic parameters", args["input"][-1]["content"])
        service.ask("Explain further")
        args = client.responses.create.call_args.kwargs
        self.assertEqual(len(args["input"]), 1)
        self.assertNotIn("synthetic parameters", str(service.history))

    def test_missing_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            with self.assertRaisesRegex(AIServiceError, "No request was sent"):
                AIService().ask("Explain PEEP")

    def test_openrouter_sdk_configuration(self):
        # A fake SDK module verifies construction without installing it or using the network.
        for base, model in [("", ""), ("https://example.test/v1", "test/model")]:
            with self.subTest(base=base):
                client = self.client()
                constructor = Mock(return_value=client)
                with patch.dict(sys.modules, {"openai": SimpleNamespace(OpenAI=constructor)}), \
                        patch.dict(os.environ, {"OPENAI_API_KEY": "offline-test-placeholder",
                            "OPENAI_BASE_URL": base, "OPENAI_MODEL": model}):
                    AIService().ask("Synthetic question")
                constructor.assert_called_once_with(api_key="offline-test-placeholder",
                    base_url=base or DEFAULT_BASE_URL, timeout=45.0, max_retries=0)
                args = client.responses.create.call_args.kwargs
                self.assertEqual(args["model"], model or DEFAULT_MODEL)
                self.assertFalse(args["store"])
                self.assertNotIn("previous_response_id", args)
                client.close.assert_called_once()

    def test_errors_do_not_commit_history_or_expose_payload(self):
        for name, status, expected in [("AuthenticationError", 401, "Authentication"),
                ("RateLimitError", 429, "quota"), ("APITimeoutError", None, "timed out"),
                ("APIConnectionError", None, "network"), ("APIStatusError", 500, "failed"),
                ("APIStatusError", 402, "credits")]:
            with self.subTest(name=name):
                exc = type(name, (Exception,), {"status_code": status})("SECRET payload")
                client = self.client()
                client.responses.create.side_effect = exc
                service = AIService(client)
                with self.assertRaisesRegex(AIServiceError, expected) as raised:
                    service.ask("question")
                self.assertNotIn("SECRET", str(raised.exception))
                self.assertEqual(service.history, [])

    def test_empty_response_and_input(self):
        service = AIService(self.client(""))
        for question in ["", "x" * 12001, "question"]:
            with self.assertRaises(AIServiceError):
                service.ask(question)
        self.assertEqual(service.history, [])


class Form(AIChatMixin, QDialog):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.ai_text = QTextEdit()
        layout.addWidget(self.ai_text)
        self.button = QPushButton()
        self.value = 5
        self.setup_chat(layout, self.button)

    def collect_ai_data(self):
        return {"peep": self.value, "ai_query": self.ai_text.toPlainText()}


class QtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_worker(self, worker):
        loop = QEventLoop()
        worker.finished.connect(loop.quit)
        QTimer.singleShot(3000, loop.quit)
        loop.exec_()
        self.assertTrue(worker.wait(1000))
        self.app.processEvents()

    def test_worker_success_and_failure(self):
        for result, error in [("answer", None), (None, AIServiceError("safe error")),
                              (None, RuntimeError("private"))]:
            service = Mock()
            service.ask.return_value = result
            service.ask.side_effect = error
            worker = AIWorker(service, "question")
            success, failure = [], []
            worker.succeeded.connect(success.append)
            worker.failed.connect(failure.append)
            worker.start()
            self.wait_worker(worker)
            self.assertEqual(success, [result] if error is None else [])
            self.assertEqual(len(failure), int(error is not None))
            self.assertNotIn("private", str(failure))

    def test_consent_duplicate_submission_and_dialog_stays_open(self):
        form = Form()
        form.ai_text.setPlainText("Synthetic question")
        form.service = Mock(history=[], prepare_request=Mock(return_value={}))
        form.service.ask.return_value = "answer"
        with patch.object(QMessageBox, "exec_", return_value=QMessageBox.No):
            form.on_send()
        form.service.ask.assert_not_called()
        with patch.object(QMessageBox, "exec_", return_value=QMessageBox.Yes):
            form.on_send()
            worker = form.worker
            self.assertFalse(form.button.isEnabled())
            form.on_send()
            form.reject()
            self.assertIs(form.worker, worker)
            self.wait_worker(worker)
        form.service.ask.assert_called_once_with("Synthetic question", None, request={})
        self.assertIsNone(form.worker)
        self.assertTrue(form.button.isEnabled())
        self.assertIn("answer", form.transcript.toPlainText())

    def test_existing_dialog_import_and_form_provenance(self):
        from simulation_dash import AIChatDialog
        dialog = AIChatDialog()
        self.assertIn("peep", dialog.defaults)
        dialog.share_form.setChecked(True)
        dialog.ai_text.setPlainText("Synthetic only")
        dialog.ai_peep_min.setValue(dialog.ai_peep_min.value() + 1)
        dialog.service = Mock(history=[], prepare_request=Mock(return_value={}))
        dialog.service.ask.return_value = "answer"
        with patch.object(QMessageBox, "exec_", return_value=QMessageBox.Yes):
            dialog.on_send()
            self.wait_worker(dialog.worker)
        context = dialog.service.ask.call_args.args[1]
        self.assertIn("manual entry", context)
        self.assertIn("form default", context)
        self.assertNotIn("ai_query", context)

    def test_checkbox_privacy_freshness_and_exact_preview(self):
        from simulation_dash import AIChatDialog, SimulationDashboard
        dashboard = SimulationDashboard()
        self.addCleanup(dashboard.close)
        dashboard.patient_full_data.update(patient_name="PRIVATE_NAME", patient_id="PRIVATE_ID",
                                            notes="PRIVATE_NOTES", hemodynamics="Stable")
        dialog = AIChatDialog(dashboard)
        self.addCleanup(dialog.close)
        client = Mock()
        dialog.service = AIService(client)
        self.assertEqual(dialog.include_simulation_data.text(), "Include Simulation Data")
        self.assertFalse(dialog.include_simulation_data.isChecked())
        previews = []

        def confirm(box):
            previews.append((box.text(), json.loads(box.detailedText())))
            return QMessageBox.Yes

        def send(question, answer):
            dialog.ai_text.setPlainText(question)
            client.responses.create.return_value = SimpleNamespace(output_text=answer)
            with patch.object(QMessageBox, "exec_", new=confirm):
                dialog.send_button.click()
                self.wait_worker(dialog.worker)
            payload = client.responses.create.call_args.kwargs
            self.assertEqual(previews[-1][1], payload)
            self.assertEqual(payload["input"][-2 if dialog.share_form.isChecked() else -1]["content"], question)
            return payload

        with patch("ai_chat.collect_simulation_data", side_effect=AssertionError("OFF must not collect")):
            payload = send("  Exact question\n", "clean answer")
        self.assertIn("NOT INCLUDED", previews[-1][0])
        self.assertEqual(payload["input"], [{"role": "user", "content": "  Exact question\n"}])
        dialog.share_form.setChecked(True)
        dashboard.current_params["peep"] = (17, 18)
        dashboard.value_labels["fio2"].setText("57.3")
        dashboard.alarm_flags["pip_high"] = True
        before = copy.deepcopy(dashboard.current_params)
        payload = send("Explain these", "SENSITIVE_SIMULATION_ANSWER")
        self.assertIn("INCLUDED", previews[-1][0])
        data = json.loads(payload["input"][-1]["content"].split("\n", 1)[1])
        self.assertEqual(data["dashboard"]["configured_parameters"]["values"]["peep"], [17, 18])
        self.assertEqual(data["dashboard"]["displayed_parameters"]["fio2"]["value"], 57.3)
        self.assertTrue(data["dashboard"]["alarm_flags"]["pip_high"])
        self.assertEqual(data["dashboard"]["clinical_status"]["hemodynamics"]["value"], "Stable")
        for secret in ("PRIVATE_NAME", "PRIVATE_ID", "PRIVATE_NOTES"):
            self.assertNotIn(secret, json.dumps(payload))
        self.assertEqual(dashboard.current_params, before)
        dashboard.current_params["peep"] = (19, 20)
        dashboard.value_labels["fio2"].setText("63.1")
        payload = send("Fresh snapshot", "SECOND_SENSITIVE_ANSWER")
        data = json.loads(payload["input"][-1]["content"].split("\n", 1)[1])
        self.assertEqual(data["dashboard"]["configured_parameters"]["values"]["peep"], [19, 20])
        self.assertEqual(data["dashboard"]["displayed_parameters"]["fio2"]["value"], 63.1)
        dialog.share_form.setChecked(False)
        with patch("ai_chat.collect_simulation_data", side_effect=AssertionError("OFF must not collect")):
            payload = send("Text only again", "clean follow-up")
        outgoing = json.dumps(payload)
        for secret in ("SENSITIVE_SIMULATION_ANSWER", "SECOND_SENSITIVE_ANSWER", "Fresh snapshot",
                       "configured_parameters", "clinical_status", "63.1"):
            self.assertNotIn(secret, outgoing)
        self.assertEqual(len(payload["input"]), 3)
        self.assertEqual(payload["input"][1]["content"], "clean answer")

    def test_cancelled_preview_never_calls_api(self):
        form = Form()
        client = Mock()
        form.service = AIService(client)
        form.share_form.setChecked(True)
        form.ai_text.setPlainText("Synthetic question")
        with patch.object(QMessageBox, "exec_", return_value=QMessageBox.No):
            form.on_send()
        client.responses.create.assert_not_called()
        self.assertEqual(form.service.history, [])
        self.assertEqual(form.service.simulation_history, [])
        self.assertIsNone(form.worker)

    def test_dashboard_has_no_settings_connection(self):
        tree = ast.parse(Path("simulation_dash.py").read_text(encoding="utf-8"))
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                      and n.name == "open_ai_chat")
        self.assertNotIn("apply_ai_settings", ast.unparse(method))

    def test_dashboard_button_send_preserves_settings(self):
        from simulation_dash import AIChatDialog, SimulationDashboard
        dashboard = SimulationDashboard()
        self.addCleanup(dashboard.close)
        dashboard.show()
        self.app.processEvents()
        self.assertTrue(dashboard.isVisible())
        before = copy.deepcopy(dashboard.current_params)
        mode_before = dashboard.mode_box.currentText()
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text="Educational example: consider changing PEEP. Do not apply automatically.")
        opened = []
        callback_errors = []

        def exercise_dialog(dialog):
            opened.append(dialog)
            dialog.show()
            self.app.processEvents()
            self.assertTrue(dialog.isVisible())
            dialog.service = AIService(client)
            dialog.share_form.setChecked(True)
            dialog.ai_peep_min.setValue(dialog.ai_peep_min.maximum())
            dialog.ai_text.setPlainText("Explain synthetic ventilation parameters")
            with patch.object(QMessageBox, "exec_", return_value=QMessageBox.Yes):
                dialog.send_button.click()
                self.wait_worker(dialog.worker)
            self.assertTrue(dialog.isVisible())
            self.assertIn("Educational example", dialog.transcript.toPlainText())
            self.assertEqual(dashboard.current_params, before)
            self.assertEqual(dashboard.mode_box.currentText(), mode_before)
            # Also exercise the actual UI error path without credentials.
            dialog.service = AIService()
            dialog.ai_text.setPlainText("Another synthetic question")
            with patch.dict(os.environ, {"OPENAI_API_KEY": ""}), \
                    patch.object(QMessageBox, "exec_", return_value=QMessageBox.Yes):
                dialog.send_button.click()
                self.wait_worker(dialog.worker)
            self.assertIn("No request was sent", dialog.transcript.toPlainText())
            self.assertEqual(dashboard.current_params, before)
            self.assertEqual(dashboard.mode_box.currentText(), mode_before)
            dialog.reject()
            return QDialog.Rejected

        def checked_dialog(dialog):
            # Qt slots otherwise print exceptions without failing unittest.
            try:
                return exercise_dialog(dialog)
            except Exception as exc:
                callback_errors.append(exc)
                return QDialog.Rejected

        with patch.object(dashboard, "apply_ai_settings") as apply, \
                patch.object(AIChatDialog, "exec_", new=checked_dialog):
            dashboard.btn_ai.click()
            if callback_errors:
                raise callback_errors[0]
            self.assertEqual(len(opened), 1)
            apply.assert_not_called()
        client.responses.create.assert_called_once()


if __name__ == "__main__":
    unittest.main()
