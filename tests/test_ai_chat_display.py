"""Offline presentation tests; no AI requests or simulation updates."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QFontDatabase, QTextDocument, QTextTable
from PyQt5.QtWidgets import QApplication
from ai_chat_display import ChatDisplay, MessageText, text_direction


ARABIC = "شرح محاكاة التهوية: ضغط نهاية الزفير PEEP وحجم المد والجزر Tidal Volume. "


class ChatDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        # Windows' offscreen plugin does not discover system fonts automatically.
        # Register installed fonts for realistic layout tests without changing the app.
        if not QFontDatabase().families():
            for name in ("segoeui.ttf", "segoeuib.ttf", "arial.ttf"):
                path = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", name)
                if os.path.exists(path):
                    QFontDatabase.addApplicationFont(path)

    def settle(self):
        for _ in range(15):
            self.app.processEvents()

    def display(self, width=650):
        widget = ChatDisplay()
        widget.resize(width, 450)
        widget.show()
        self.addCleanup(widget.close)
        self.settle()
        return widget

    def test_bubbles_turns_loading_copy_and_no_duplicate_answer(self):
        display = self.display()
        question = "  Explain PEEP\nباللغة العربية  "
        display.begin_turn(question)
        self.settle()
        self.assertTrue(display.loading_timer.isActive())
        self.assertTrue(display.loading_label.isVisible())
        answer = "## التفسير\n\n" + ARABIC * 10
        display.finish_turn(answer)
        display.finish_turn(answer)
        self.settle()
        self.assertEqual(len(display.bubbles), 2)
        self.assertFalse(display.loading_timer.isActive())
        self.assertFalse(display.loading_label.isVisible())
        user, assistant = display.bubbles
        self.assertEqual(user.raw_text, question)
        self.assertEqual(user.body.toPlainText(), question)
        self.assertGreater(user.mapTo(display.content, user.rect().topLeft()).x(),
                           assistant.mapTo(display.content, assistant.rect().topLeft()).x())
        assistant.copy_button.click()
        self.assertEqual(self.app.clipboard().text(), answer)
        display.begin_turn("Second question")
        display.finish_turn("Second answer")
        self.settle()
        self.assertEqual(len(display.turns), 2)
        self.assertEqual(len(display.bubbles), 4)
        self.assertEqual(display.verticalScrollBar().value(), display.verticalScrollBar().maximum())

    def test_markdown_and_paragraph_direction(self):
        display = self.display()
        display.begin_turn("Question")
        display.finish_turn("# Heading\n\n**Bold** English paragraph\nNext line\n\n"
                            "شرح عربي PEEP 5 cmH2O\n\n1. First\n2. Second\n\n"
                            "- Bullet one\n- Bullet two\n\n"
                            "| Parameter | Value |\n| --- | --- |\n| PEEP | 5 |")
        self.settle()
        document = display.bubbles[-1].body.document()
        blocks = []
        block = document.begin()
        while block.isValid():
            blocks.append(block)
            block = block.next()
        heading = next(b for b in blocks if b.text() == "Heading")
        self.assertEqual(heading.blockFormat().headingLevel(), 1)
        arabic = next(b for b in blocks if b.text().startswith("شرح"))
        english = next(b for b in blocks if b.text().startswith("Bold"))
        self.assertEqual(arabic.blockFormat().layoutDirection(), Qt.RightToLeft)
        self.assertEqual(english.blockFormat().layoutDirection(), Qt.LeftToRight)
        self.assertTrue(any(b.textList() is not None for b in blocks))
        self.assertTrue(any(isinstance(frame, QTextTable)
                            for frame in document.rootFrame().childFrames()))
        self.assertIn("Next line", document.toPlainText())
        self.assertNotIn("**Bold**", document.toPlainText())
        self.assertEqual(text_direction("PEEP ضغط"), Qt.LeftToRight)
        self.assertEqual(text_direction("ضغط PEEP"), Qt.RightToLeft)

    def test_long_mixed_responses_wrap_and_scroll_after_resize(self):
        display = self.display(460)
        display.begin_turn("Long synthetic question")
        answer = (ARABIC * 20 + "\n\n" + "English FiO2 40% and PEEP 5 cmH2O. " * 20
                  + "\n\n" + "LongMedicalTerm" * 60 + "\n\n"
                  + "| المصطلح | Description |\n| --- | --- |\n| ضغط PEEP | "
                  + "LongMedicalTerm" * 20 + " |")
        display.finish_turn(answer)
        self.settle()
        for width in (460, 340, 820):
            display.resize(width, 450)
            self.settle()
            body = display.bubbles[-1].body
            self.assertLessEqual(body.document().size().width(), body.viewport().width() + 1)
            self.assertGreaterEqual(body.height(), body.document().size().height())
            self.assertEqual(display.horizontalScrollBar().maximum(), 0)
            self.assertGreater(display.verticalScrollBar().maximum(), 0)
            self.assertEqual(display.verticalScrollBar().value(), display.verticalScrollBar().maximum())

    def test_untrusted_html_is_literal_and_resources_never_load(self):
        raw = '<b>not HTML</b>\n<script>alert(1)</script>\n![image](https://example.test/x.png)'
        with patch.object(QTextDocument, "loadResource", side_effect=AssertionError("network resource")):
            body = MessageText(raw, True)
            self.addCleanup(body.close)
            self.assertIn("<b>not HTML</b>", body.toPlainText())
            self.assertIn("<script>alert(1)</script>", body.toPlainText())
            self.assertIsNone(body.loadResource(QTextDocument.ImageResource, QUrl("file:///private.png")))
            self.assertFalse(body.openLinks())
            self.assertFalse(body.openExternalLinks())


if __name__ == "__main__":
    unittest.main()
