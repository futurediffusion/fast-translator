# Floating Translator PySide6 GUI

from PySide6 import QtCore, QtGui, QtWidgets
import json
import os
import re
import time
from urllib import request, error

# Optional fallback translator if Gemini filtering fails
try:
    from googletrans import Translator as GoogleTranslator
except Exception:  # pragma: no cover - optional dependency
    GoogleTranslator = None

# API key for Google's Gemini generative language API
GEMINI_API_KEY = "AIzaSyDnO8MO4qFgkOcSO2eHVZkfQ7cZ2KhrA5I"

# Cache file to store previous translations
CACHE_FILE = "translation_cache.json"
# Minimum seconds between API calls
MIN_REQUEST_INTERVAL = 1.0
# Track time of last request
LAST_REQUEST_TIME = 0.0

# In-memory cache loaded from disk if available
_translation_cache: dict[tuple[str, str, str], dict[str, object]] = {}
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key, value in data.items():
            parts = key.split("||")
            if len(parts) == 3:
                if isinstance(value, dict):
                    _translation_cache[(parts[0], parts[1], parts[2])] = {
                        "translation": value.get("translation", ""),
                        "count": int(value.get("count", 0)),
                    }
                else:
                    _translation_cache[(parts[0], parts[1], parts[2])] = {
                        "translation": value,
                        "count": 0,
                    }
    except Exception as exc:  # pragma: no cover - best effort
        print("Could not load cache:", exc)


def _save_cache() -> None:
    """Persist the translation cache to disk."""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            data = {
                "||".join(k): {
                    "translation": v.get("translation", ""),
                    "count": int(v.get("count", 0)),
                }
                for k, v in _translation_cache.items()
            }
            json.dump(data, f)
    except Exception as exc:  # pragma: no cover - best effort
        print("Could not save cache:", exc)


def get_translation_history() -> list[tuple[str, int]]:
    """Return cached translations ordered by most frequently used."""
    items: list[tuple[str, int]] = []
    for entry in _translation_cache.values():
        items.append((entry.get("translation", ""), int(entry.get("count", 0))))
    items.sort(key=lambda x: x[1], reverse=True)
    return items

# Language options for the UI and prompt names used by the API
LANG_OPTIONS = [
    ("Español", "es"),
    ("Inglés", "en"),
    ("Francés", "fr"),
    ("Alemán", "de"),
    ("Italiano", "it"),
    ("Portugués", "pt"),
]

LANG_PROMPT_NAMES = {
    "es": "Spanish",
    "en": "English",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
}


def clean_translation(text: str) -> str:
    """Return a simplified single-line translation."""
    if not text:
        return text
    line = text.strip().splitlines()[0]
    line = line.lstrip("*-• ").strip()
    match = re.search(r"\*\*(.+?)\*\*", line)
    if match:
        return match.group(1).strip()
    if line.startswith("**") and line.endswith("**"):
        line = line[2:-2]
    line = line.strip("*")
    return line


def _wait_rate_limit() -> None:
    """Sleep if requests are happening too quickly."""
    global LAST_REQUEST_TIME
    elapsed = time.time() - LAST_REQUEST_TIME
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    LAST_REQUEST_TIME = time.time()


def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """Translate text using Gemini API with caching and rate limiting."""
    key = (text, source_lang, target_lang)
    if key in _translation_cache:
        entry = _translation_cache[key]
        entry["count"] = entry.get("count", 0) + 1
        _save_cache()
        return entry["translation"]

    src_name = LANG_PROMPT_NAMES.get(source_lang, source_lang)
    tgt_name = LANG_PROMPT_NAMES.get(target_lang, target_lang)
    prompt = (
        f"Translate the following {src_name} text to {tgt_name} as a single"
        f" concise phrase. Respond only with the {tgt_name} translation"
        f" wrapped in double asterisks.\n\n{src_name}: {text}"
    )
    payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    for attempt in range(3):
        try:
            _wait_rate_limit()
            req = request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
                raw_text = (
                    data["candidates"][0]["content"]["parts"][0]["text"].strip()
                )
                if raw_text:
                    translated = clean_translation(raw_text)
                    _translation_cache[key] = {"translation": translated, "count": 1}
                    _save_cache()
                    return translated
        except error.HTTPError as http_err:  # pragma: no cover - network
            if http_err.code == 429 and attempt < 2:
                time.sleep(2 ** attempt + 1)
                continue
            print("Translation failed:", http_err)
            break
        except Exception as exc:  # pragma: no cover - network
            print("Translation failed:", exc)
            break

    if GoogleTranslator is not None:
        try:
            translator = GoogleTranslator()
            translated = translator.translate(
                text, src=source_lang, dest=target_lang
            ).text
            _translation_cache[key] = {"translation": translated, "count": 1}
            _save_cache()
            return translated
        except Exception as fallback_exc:  # pragma: no cover - best effort
            print("Fallback translation failed:", fallback_exc)

    return text


class TranslationWorker(QtCore.QThread):
    """Thread to run translations without blocking the UI."""

    translation_ready = QtCore.Signal(str)

    def __init__(self, text: str, source_lang: str, target_lang: str) -> None:
        super().__init__()
        self.text = text
        self.source_lang = source_lang
        self.target_lang = target_lang

    def run(self) -> None:  # pragma: no cover - involves network
        translated = translate_text(self.text, self.source_lang, self.target_lang)
        self.translation_ready.emit(translated)


class FloatingTranslatorWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__(
            None,
            QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.FramelessWindowHint,
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        # Start with a slightly larger window so multiple lines fit easily
        self.resize(420, 200)
        self.setMinimumSize(320, 160)
        self.offset = None
        self.source_lang = "es"
        self.target_lang = "en"
        self.init_ui()

    def init_ui(self):
        # Main container with rounded corners and translucent background
        self.container = QtWidgets.QFrame(self)
        self.container.setObjectName("container")
        self.container.setStyleSheet(
            "#container {"
            "background-color: rgba(255, 255, 255, 0.85);"
            "border-radius: 24px;"
            "}"
        )
        self.container.setGeometry(0, 0, self.width(), self.height())
        effect = QtWidgets.QGraphicsDropShadowEffect(
            blurRadius=20, xOffset=0, yOffset=2
        )
        effect.setColor(QtGui.QColor(0, 0, 0, 80))
        self.container.setGraphicsEffect(effect)

        # Close button
        self.close_btn = QtWidgets.QPushButton("\u2715", self.container)
        self.close_btn.setObjectName("close")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setStyleSheet(
            "QPushButton#close {"
            "border: none;"
            "background: transparent;"
            "color: red;"
            "font-weight: bold;"
            "font-size: 18px;"
            "}"
            "QPushButton#close:hover { color: #ff6666; }"
        )
        self.close_btn.move(self.width() - 32, 8)

        main_layout = QtWidgets.QVBoxLayout(self.container)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)

        # Language row
        lang_row = QtWidgets.QHBoxLayout()
        lang_row.setAlignment(QtCore.Qt.AlignCenter)

        self.src_combo = QtWidgets.QComboBox()
        self.dest_combo = QtWidgets.QComboBox()
        for label, code in LANG_OPTIONS:
            self.src_combo.addItem(label, code)
            self.dest_combo.addItem(label, code)
        self.src_combo.currentIndexChanged.connect(
            lambda idx: setattr(self, "source_lang", self.src_combo.itemData(idx))
        )
        self.dest_combo.currentIndexChanged.connect(
            lambda idx: setattr(self, "target_lang", self.dest_combo.itemData(idx))
        )
        self.src_combo.currentIndexChanged.connect(self.language_changed)
        self.dest_combo.currentIndexChanged.connect(self.language_changed)
        self.src_combo.setCurrentIndex(0)
        self.dest_combo.setCurrentIndex(1)

        self.swap_btn = QtWidgets.QPushButton("\u2192")
        self.swap_btn.setObjectName("swap")
        self.swap_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.swap_btn.clicked.connect(self.swap_languages)
        self.swap_btn.setStyleSheet(
            "QPushButton#swap {"
            "border: none;"
            "background: transparent;"
            "font-size: 14px;"
            "color: black;"
            "}"
            "QPushButton#swap:hover { color: blue; }"
        )
        combo_style = (
            "QComboBox {"
            "font-size: 14px;"
            "color: black;"
            "background-color: white;"
            "}"
            "QComboBox QAbstractItemView {"
            "color: black;"
            "background-color: white;"
            "}"
        )
        for combo in (self.src_combo, self.dest_combo):
            combo.setStyleSheet(combo_style)
            combo.setSizePolicy(
                QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed
            )
        lang_row.addWidget(self.src_combo)
        lang_row.addSpacing(6)
        lang_row.addWidget(self.swap_btn)
        lang_row.addSpacing(6)
        lang_row.addWidget(self.dest_combo)
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

        self.input_edit = QtWidgets.QPlainTextEdit()
        self.input_edit.setPlaceholderText("Escribe tu texto")
        self.input_edit.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        shortcut = QtGui.QShortcut(
            QtGui.QKeySequence("Ctrl+Return"), self.input_edit
        )
        shortcut.activated.connect(self.translate_current_text)
        shortcut2 = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Enter"), self.input_edit)
        shortcut2.activated.connect(self.translate_current_text)
        self.input_edit.setStyleSheet(
            "QPlainTextEdit {"
            "color: black;"
            "font-weight: bold;"
            "border: none;"
            "background: transparent;"
            "font-size: 16px;"
            "}"
        )

        self.translate_btn = QtWidgets.QPushButton("\u2192")
        self.translate_btn.setObjectName("translate")
        self.translate_btn.setFixedSize(32, 32)
        self.translate_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.translate_btn.clicked.connect(self.translate_current_text)
        self.translate_btn.setStyleSheet(
            "QPushButton#translate {"
            "background-color: #2196F3;"
            "color: white;"
            "border-radius: 16px;"
            "border: none;"
            "font-size: 16px;"
            "}"
            "QPushButton#translate:hover { background-color: #42a5f5; }"
        )

        input_row = QtWidgets.QHBoxLayout()
        input_row.addWidget(self.input_edit)
        input_row.addWidget(self.translate_btn)
        self.translated_label = QtWidgets.QLabel("")
        self.translated_label.setStyleSheet(
            "color: #2196F3; font-size: 16px; font-weight: bold;"
        )
        self.translated_label.setWordWrap(True)
        bottom_row = QtWidgets.QHBoxLayout()
        bottom_row.addWidget(self.translated_label)
        bottom_row.addStretch()

        self.copy_btn = QtWidgets.QPushButton("\U0001F4CB")
        self.copy_btn.setObjectName("copy")
        self.copy_btn.setFixedSize(32, 32)
        self.copy_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.copy_btn.clicked.connect(self.copy_translation)
        self.copy_btn.setStyleSheet(
            "QPushButton#copy {"
            "background-color: #2196F3;"
            "color: white;"
            "border-radius: 16px;"
            "border: none;"
            "font-size: 18px;"
            "}"
            "QPushButton#copy:hover { background-color: #42a5f5; }"
        )
        bottom_row.addWidget(self.copy_btn)

        self.history_btn = QtWidgets.QPushButton("\u25BC")
        self.history_btn.setObjectName("history")
        self.history_btn.setFixedSize(32, 32)
        self.history_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.history_btn.clicked.connect(self.show_history_menu)
        self.history_btn.setStyleSheet(
            "QPushButton#history {"
            "background-color: #2196F3;"
            "color: white;"
            "border-radius: 16px;"
            "border: none;"
            "}"
            "QPushButton#history:hover { background-color: #42a5f5; }"
        )
        bottom_row.addWidget(self.history_btn)

        card_layout.addLayout(input_row)
        card_layout.addLayout(bottom_row)

        main_layout.addWidget(card)

        grip_row = QtWidgets.QHBoxLayout()
        grip_row.addStretch()
        self.size_grip = QtWidgets.QSizeGrip(self.container)
        grip_row.addWidget(self.size_grip)
        main_layout.addLayout(grip_row)

    def on_text_changed(self, text: str) -> None:
        """Translate the provided text asynchronously."""
        self.translated_label.setText("...")
        self.worker = TranslationWorker(text, self.source_lang, self.target_lang)
        self.worker.translation_ready.connect(self.translated_label.setText)
        self.worker.start()

    def swap_languages(self):
        """Swap source and target languages."""
        src_index = self.src_combo.currentIndex()
        dest_index = self.dest_combo.currentIndex()
        self.src_combo.setCurrentIndex(dest_index)
        self.dest_combo.setCurrentIndex(src_index)

    def translate_current_text(self):
        """Handle the Enter key press from the input box."""
        self.on_text_changed(self.input_edit.toPlainText())

    def language_changed(self, *args):
        text = self.input_edit.toPlainText().strip()
        if text:
            self.on_text_changed(text)



    def copy_translation(self):
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(self.translated_label.text())

    def show_history_menu(self):
        menu = QtWidgets.QMenu(self)
        for translation, count in get_translation_history():
            action = menu.addAction(f"{translation} ({count})")
            action.setData(translation)
        if not menu.actions():
            menu.addAction("(no history)")
        action = menu.exec_(self.history_btn.mapToGlobal(QtCore.QPoint(0, self.history_btn.height())))
        if action and action.data():
            selected = action.data()
            self.translated_label.setText(selected)
            clipboard = QtWidgets.QApplication.clipboard()
            clipboard.setText(selected)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.container.setGeometry(0, 0, self.width(), self.height())
        self.close_btn.move(self.width() - 32, 8)

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
