"""Presentation-only chat widgets. Markdown never loads HTML or external resources."""
import html
import math
import unicodedata
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QTextCursor, QTextDocument, QTextOption, QTextLength, QFont
from PyQt5.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QPushButton,
                            QScrollArea, QSizePolicy, QTextBrowser, QVBoxLayout, QWidget)


def text_direction(text):
    for character in text:
        direction = unicodedata.bidirectional(character)
        if direction in ("R", "AL"):
            return Qt.RightToLeft
        if direction == "L":
            return Qt.LeftToRight
    return Qt.LeftToRight


def safe_markdown(text):
    # Escape HTML before Markdown parsing; keep ordinary single line breaks visible.
    lines = html.escape(text, quote=False).split("\n")
    fenced = False
    result = []
    for line in lines:
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        if line.strip() and not fenced and not line.lstrip().startswith(("#", "|", "```", "~~~")):
            line += "  "
        result.append(line)
    return "\n".join(result)


class MessageText(QTextBrowser):
    def loadResource(self, resource_type, url):
        # Markdown images, local files and remote URLs must never load resources.
        return None

    def __init__(self, text, markdown, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFont(QFont("Segoe UI", 11))
        self.setStyleSheet("QTextBrowser { background: transparent; color: #e8edf4; border: none; }")
        document = self.document()
        option = document.defaultTextOption()
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        document.setDefaultTextOption(option)
        document.setDefaultStyleSheet(
            "p { margin-top: 5px; margin-bottom: 10px; } "
            "h1,h2,h3,h4 { color: #b9e3ed; margin-top: 12px; margin-bottom: 8px; } "
            "td,th { padding: 6px; border: 1px solid #526275; } "
            "a { color: #81cfe2; } pre,code { color: #cce4de; }")
        if markdown:
            document.setMarkdown(safe_markdown(text), QTextDocument.MarkdownDialectGitHub)
        else:
            self.setPlainText(text)
        block = document.begin()
        while block.isValid():
            cursor = QTextCursor(block)
            fmt = block.blockFormat()
            rtl = text_direction(block.text()) == Qt.RightToLeft
            fmt.setLayoutDirection(Qt.RightToLeft if rtl else Qt.LeftToRight)
            fmt.setAlignment(Qt.AlignRight if rtl else Qt.AlignLeft)
            fmt.setTopMargin(4)
            fmt.setBottomMargin(9)
            cursor.setBlockFormat(fmt)
            table = cursor.currentTable()
            if table is not None:
                table_format = table.format()
                table_format.setWidth(QTextLength(QTextLength.PercentageLength, 100))
                table_format.setColumnWidthConstraints([
                    QTextLength(QTextLength.PercentageLength, 100 / table.columns())
                    for _ in range(table.columns())])
                table.setFormat(table_format)
            block = block.next()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.document().setTextWidth(max(1, self.viewport().width()))
        height = math.ceil(self.document().size().height()) + 8
        if self.height() != height:
            self.setFixedHeight(height)


class MessageBubble(QFrame):
    def __init__(self, text, role, parent=None):
        super().__init__(parent)
        self.raw_text = text
        self.role = role
        self.setObjectName("chatBubble")
        color = "#193d55" if role == "user" else "#222e3b"
        self.setStyleSheet(f"QFrame#chatBubble {{ background: {color}; border: 1px solid #405468; border-radius: 12px; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(6)
        label = QLabel("You" if role == "user" else "AI Assistant" if role == "assistant" else "Request status")
        label.setStyleSheet("color: #8ed1df; font: 600 10pt 'Segoe UI'; background: transparent;")
        layout.addWidget(label)
        self.body = MessageText(text, role == "assistant", self)
        layout.addWidget(self.body)
        self.copy_button = None
        if role == "assistant":
            row = QHBoxLayout()
            row.addStretch()
            self.copy_button = QPushButton("Copy Response")
            self.copy_button.setStyleSheet(
                "QPushButton { color: #d5e8ef; background: #314759; border: 1px solid #526b80; "
                "border-radius: 5px; padding: 5px 10px; font: 9pt 'Segoe UI'; } "
                "QPushButton:hover { background: #405e74; }")
            self.copy_button.clicked.connect(lambda: QApplication.clipboard().setText(self.raw_text))
            row.addWidget(self.copy_button)
            layout.addLayout(row)


class ChatDisplay(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setMinimumHeight(200)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { background: #101820; border: 1px solid #3e5061; border-radius: 8px; }")
        self.content = QWidget()
        self.content.setStyleSheet("background: #101820;")
        self.rows = QVBoxLayout(self.content)
        self.rows.setContentsMargins(12, 12, 12, 12)
        self.rows.setSpacing(18)
        self.rows.addStretch()
        self.setWidget(self.content)
        self.turns = []
        self.bubbles = []
        self.loading_timer = QTimer(self)
        self.loading_timer.setInterval(350)
        self.loading_timer.timeout.connect(self.animate_loading)
        self.loading_step = 0
        self.verticalScrollBar().rangeChanged.connect(lambda *_: self.scroll_latest())

    def scroll_latest(self):
        QTimer.singleShot(0, self._scroll_bottom)

    def _scroll_bottom(self):
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def begin_turn(self, text):
        turn = QFrame()
        turn.setStyleSheet("QFrame { border: none; }")
        layout = QVBoxLayout(turn)
        layout.setContentsMargins(0, 0, 0, 16)
        layout.setSpacing(12)
        self.rows.insertWidget(self.rows.count() - 1, turn)
        self.turns.append({"layout": layout, "finished": False})
        self.add_bubble(text, "user")
        self.loading_label = QLabel("AI Assistant · Preparing response…")
        self.loading_label.setStyleSheet("color: #8caebd; font: 10pt 'Segoe UI'; padding: 6px;")
        layout.addWidget(self.loading_label)
        self.loading_timer.start()
        self.scroll_latest()

    def animate_loading(self):
        self.loading_step = (self.loading_step + 1) % 4
        self.loading_label.setText("AI Assistant · Preparing response" + "." * self.loading_step)

    def add_bubble(self, text, role):
        row = QHBoxLayout()
        bubble = MessageBubble(text, role)
        bubble.setFixedWidth(max(120, int(self.viewport().width() * .86)))
        if role == "user":
            row.addStretch()
        row.addWidget(bubble)
        if role != "user":
            row.addStretch()
        self.turns[-1]["layout"].addLayout(row)
        self.bubbles.append(bubble)

    def finish_turn(self, text, error=False):
        if not self.turns or self.turns[-1]["finished"]:
            return
        self.loading_timer.stop()
        self.loading_label.hide()
        self.turns[-1]["finished"] = True
        self.add_bubble(text, "error" if error else "assistant")
        self.scroll_latest()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for bubble in self.bubbles:
            bubble.setFixedWidth(max(120, int(self.viewport().width() * .86)))
        self.scroll_latest()

    def toPlainText(self):
        """Plain-text view for accessibility and existing integration checks."""
        return "\n\n".join(bubble.raw_text for bubble in self.bubbles)
