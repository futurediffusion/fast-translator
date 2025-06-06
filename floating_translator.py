# Floating Translator PySide6 GUI

from PySide6 import QtCore, QtGui, QtWidgets
import json
import re
from urllib import request

# Optional fallback translator if Gemini filtering fails
try:
    from googletrans import Translator as GoogleTranslator
except Exception:  # pragma: no cover - optional dependency
    GoogleTranslator = None

# API key for Google's Gemini generative language API
GEMINI_API_KEY = "AIzaSyDnO8MO4qFgkOcSO2eHVZkfQ7cZ2KhrA5I"


class FloatingTranslatorWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__(
            None,
            QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.FramelessWindowHint,
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setFixedSize(380, 160)
        self.offset = None
        self.init_ui()

    def init_ui(self):
        # Main container with rounded corners and translucent background
        self.container = QtWidgets.QFrame(self)
        self.container.setObjectName("container")
        self.container.setStyleSheet(
            "#container {"
            "background-color: rgba(255, 255, 255, 0.85);"
            "border-radius: 32px;"
            "}"
        )
        self.container.setGeometry(0, 0, 380, 160)
        effect = QtWidgets.QGraphicsDropShadowEffect(
            blurRadius=20, xOffset=0, yOffset=2
        )
        effect.setColor(QtGui.QColor(0, 0, 0, 80))
        self.container.setGraphicsEffect(effect)

        # Close button
        close_btn = QtWidgets.QPushButton("\u2715", self.container)
        close_btn.setObjectName("close")
        close_btn.setFixedSize(16, 16)
        close_btn.clicked.connect(self.close)
        close_btn.setStyleSheet(
            "QPushButton#close {"
            "border: none;"
            "color: white;"
            "background-color: red;"
            "border-radius: 8px;"
            "font-weight: bold;"
            "}"
            "QPushButton#close:hover { background-color: #ff6666; }"
        )
        close_btn.move(self.width() - 24, 8)

        main_layout = QtWidgets.QVBoxLayout(self.container)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)

        # Language row
        lang_row = QtWidgets.QHBoxLayout()
        esp_label = QtWidgets.QLabel("Espa\u00f1ol")
        arrow_label = QtWidgets.QLabel("\u2192")
        eng_label = QtWidgets.QLabel("Ingl\u00e9s")
        for lbl in (esp_label, arrow_label, eng_label):
            lbl.setStyleSheet("font-size: 14px;")
        arrow_label.setAlignment(QtCore.Qt.AlignCenter)
        lang_row.addWidget(esp_label)
        lang_row.addStretch()
        lang_row.addWidget(arrow_label)
        lang_row.addStretch()
        lang_row.addWidget(eng_label)
        main_layout.addLayout(lang_row)

        # Translation card
        card = QtWidgets.QFrame()
        card.setObjectName("card")
        card.setStyleSheet(
            "#card {"
            "background-color: rgba(255, 255, 255, 0.85);"
            "border-radius: 24px;"
            "}"
        )
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(8)

        self.input_edit = QtWidgets.QLineEdit()
        self.input_edit.setText("Hola, ¿cómo estás?")
        # Only translate after the user presses Enter
        self.input_edit.returnPressed.connect(self.translate_current_text)
        self.input_edit.setStyleSheet(
            "QLineEdit {"
            "color: black;"
            "font-weight: bold;"
            "border: none;"
            "background: transparent;"
            "font-size: 16px;"
            "}"
        )
        self.translated_label = QtWidgets.QLabel("Hello, how are you?")
        # Show translations in blue for better visibility
        self.translated_label.setStyleSheet(
            "color: blue; font-size: 16px; font-weight: bold;"
        )
        bottom_row = QtWidgets.QHBoxLayout()
        bottom_row.addWidget(self.translated_label)
        bottom_row.addStretch()

        self.copy_btn = QtWidgets.QPushButton()
        self.copy_btn.setObjectName("copy")
        self.copy_btn.setFixedSize(32, 32)
        self.copy_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.copy_btn.clicked.connect(self.copy_translation)
        self.copy_btn.setStyleSheet(
            "QPushButton#copy {"
            "background-color: #D9EEFF;"
            "border-radius: 16px;"
            "border: none;"
            "}"
            "QPushButton#copy:hover { background-color: #cce4ff; }"
        )
        copy_icon = self.style().standardIcon(
            QtWidgets.QStyle.SP_DialogOpenButton
        )
        self.copy_btn.setIcon(copy_icon)
        bottom_row.addWidget(self.copy_btn)

        card_layout.addWidget(self.input_edit)
        card_layout.addLayout(bottom_row)

        main_layout.addWidget(card)

    def on_text_changed(self, text):
        translated = self.translate_text(text)
        self.translated_label.setText(translated)

    def translate_current_text(self):
        """Handle the Enter key press from the input box."""
        self.on_text_changed(self.input_edit.text())

    def translate_text(self, text):
        """Translate Spanish text to English using Gemini."""
        prompt = (
            "Translate the following Spanish text to English as a single"
            " concise phrase. Respond only with the English translation"
            " wrapped in double asterisks.\n\nSpanish: "
            f"{text}"
        )
        payload = json.dumps(
            {"contents": [{"parts": [{"text": prompt}]}]}
        ).encode()
        try:
            req = request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if raw_text:
                    return self.clean_translation(raw_text)
        except Exception as exc:
            print("Translation failed:", exc)

        # If Gemini failed or returned empty, try googletrans if available
        if GoogleTranslator is not None:
            try:
                translator = GoogleTranslator()
                translated = translator.translate(text, src="es", dest="en").text
                return translated
            except Exception as fallback_exc:  # pragma: no cover - best effort
                print("Fallback translation failed:", fallback_exc)

        # As a last resort, return the original text
        return text

    def clean_translation(self, text: str) -> str:
        """Return a simplified single-line translation."""
        if not text:
            return text
        # Take only the first line if the model returned multiple suggestions
        line = text.strip().splitlines()[0]
        # Remove common bullet or formatting characters
        line = line.lstrip("*-• ").strip()

        # Extract content wrapped in double asterisks if present
        match = re.search(r"\*\*(.+?)\*\*", line)
        if match:
            return match.group(1).strip()

        if line.startswith("**") and line.endswith("**"):
            line = line[2:-2]
        line = line.strip("*")
        return line

    def copy_translation(self):
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(self.translated_label.text())

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.offset = event.pos()

    def mouseMoveEvent(self, event):
        if self.offset is not None and event.buttons() & QtCore.Qt.LeftButton:
            self.move(event.globalPos() - self.offset)

    def mouseReleaseEvent(self, event):
        self.offset = None


if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    window = FloatingTranslatorWindow()
    window.show()
    app.exec()
