# Floating Translator PySide6 GUI

from PySide6 import QtCore, QtGui, QtWidgets
import json
import os
import re
import time
import threading
import keyboard
from urllib import request, error

try:
    from langdetect import detect, LangDetectException
except Exception:  # pragma: no cover - optional dependency
    detect = None
    LangDetectException = Exception

# Optional fallback translator if Gemini filtering fails
try:
    from googletrans import Translator as GoogleTranslator
except Exception:  # pragma: no cover - optional dependency
    GoogleTranslator = None

# API key for Google's Gemini generative language API
GEMINI_API_KEY = ""
THEME = "light"
FONT_SIZE = 16
# Default language used when auto switching
DEFAULT_LANG = "es"

# Optional config file storing the API key
CONFIG_FILE = "config.json"

if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            GEMINI_API_KEY = data.get("api_key", "")
            THEME = data.get("theme", THEME)
            FONT_SIZE = int(data.get("font_size", FONT_SIZE))
            DEFAULT_LANG = data.get("default_lang", DEFAULT_LANG)
    except Exception as exc:  # pragma: no cover - best effort
        print("Could not load config:", exc)

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
                        "time": float(value.get("time", time.time())),
                    }
                else:
                    _translation_cache[(parts[0], parts[1], parts[2])] = {
                        "translation": value,
                        "count": 0,
                        "time": time.time(),
                    }
    except Exception as exc:  # pragma: no cover - best effort
        print("Could not load cache:", exc)


def _trim_cache(max_size: int = 15) -> None:
    """Remove old/unused entries keeping the most popular ones."""
    if len(_translation_cache) <= max_size:
        return
    items = sorted(
        _translation_cache.items(),
        key=lambda kv: (
            -int(kv[1].get("count", 0)),
            -float(kv[1].get("time", 0.0)),
        ),
    )
    for key, _ in items[max_size:]:
        _translation_cache.pop(key, None)


def _save_cache() -> None:
    """Persist the translation cache to disk."""
    _trim_cache()
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            data = {
                "||".join(k): {
                    "translation": v.get("translation", ""),
                    "count": int(v.get("count", 0)),
                    "time": float(v.get("time", time.time())),
                }
                for k, v in _translation_cache.items()
            }
            json.dump(data, f)
    except Exception as exc:  # pragma: no cover - best effort
        print("Could not save cache:", exc)


def save_config() -> None:
    """Persist the configuration options to disk."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "api_key": GEMINI_API_KEY,
                    "theme": THEME,
                    "font_size": FONT_SIZE,
                    "default_lang": DEFAULT_LANG,
                },
                f,
            )
    except Exception as exc:  # pragma: no cover - best effort
        print("Could not save config:", exc)


def set_api_key(key: str) -> None:
    """Update the API key and save it."""
    global GEMINI_API_KEY
    GEMINI_API_KEY = key.strip()
    save_config()


def set_theme(value: str) -> None:
    """Update the theme and save it."""
    global THEME
    THEME = value
    save_config()


def set_font_size(value: int) -> None:
    """Update the font size and save it."""
    global FONT_SIZE
    FONT_SIZE = int(value)
    save_config()


def set_default_lang(value: str) -> None:
    """Update the default language and save it."""
    global DEFAULT_LANG
    DEFAULT_LANG = value
    save_config()


def get_translation_history() -> list[tuple[str, int]]:
    """Return cached translations ordered by most frequently used."""
    items: list[tuple[str, int, float]] = []
    for entry in _translation_cache.values():
        items.append(
            (
                entry.get("translation", ""),
                int(entry.get("count", 0)),
                float(entry.get("time", 0.0)),
            )
        )
    items.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return [(t, c) for t, c, _ in items]


def clear_translation_history() -> None:
    """Remove all cached translations from memory and disk."""
    _translation_cache.clear()
    if os.path.exists(CACHE_FILE):
        try:
            os.remove(CACHE_FILE)
        except Exception as exc:  # pragma: no cover - best effort
            print("Could not delete cache:", exc)


def export_translation_history(path: str) -> None:
    """Write the history to ``path`` as tab-separated values."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            for translation, count in get_translation_history():
                f.write(f"{translation}\t{count}\n")
    except Exception as exc:  # pragma: no cover - best effort
        print("Could not export history:", exc)


def remove_translation_item(translation: str) -> None:
    """Delete a single translation from the cache."""
    keys = [
        key
        for key, val in list(_translation_cache.items())
        if val.get("translation") == translation
    ]
    for key in keys:
        _translation_cache.pop(key, None)
    if keys:
        _save_cache()


def detect_language(text: str) -> str:
    """Best-effort language detection using ``langdetect``."""
    if detect is None:
        return "en"
    try:
        code = detect(text)
    except LangDetectException:
        return "en"
    if code.startswith("zh"):
        code = "zh"
    return code if code in LANG_PROMPT_NAMES else "en"

# Language options for the UI and prompt names used by the API
# List of supported languages for the UI
LANG_OPTIONS = [
    ("Español", "es"),
    ("Inglés", "en"),
    ("Francés", "fr"),
    ("Alemán", "de"),
    ("Italiano", "it"),
    ("Portugués", "pt"),
    ("Catal\u00e1n", "ca"),
    ("Chino", "zh"),
    ("Japon\u00e9s", "ja"),
    ("Coreano", "ko"),
    ("Ruso", "ru"),
    ("\u00c1rabe", "ar"),
]

# English names used when prompting the API
LANG_PROMPT_NAMES = {
    "es": "Spanish",
    "en": "English",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ca": "Catalan",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ru": "Russian",
    "ar": "Arabic",
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
    if source_lang == "auto":
        source_lang = detect_language(text)
    key = (text, source_lang, target_lang)
    if key in _translation_cache:
        entry = _translation_cache[key]
        entry["count"] = entry.get("count", 0) + 1
        entry["time"] = time.time()
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
                    _translation_cache[key] = {
                        "translation": translated,
                        "count": 1,
                        "time": time.time(),
                    }
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
            _translation_cache[key] = {
                "translation": translated,
                "count": 1,
                "time": time.time(),
            }
            _save_cache()
            return translated
        except Exception as fallback_exc:  # pragma: no cover - best effort
            print("Fallback translation failed:", fallback_exc)

    return text


class TranslationTask(QtCore.QObject, QtCore.QRunnable):
    """Runnable task that performs a translation on a thread pool."""

    translation_ready = QtCore.Signal(str)

    def __init__(self, text: str, source_lang: str, target_lang: str) -> None:
        QtCore.QObject.__init__(self)
        QtCore.QRunnable.__init__(self)
        self.text = text
        self.source_lang = source_lang
        self.target_lang = target_lang

    @QtCore.Slot()
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
        self.default_lang = DEFAULT_LANG
        self.dark_mode = THEME == "dark"
        self.font_size = FONT_SIZE
        self.init_ui()
        self.loading_timer = QtCore.QTimer(self)
        self.loading_timer.setInterval(500)
        self.loading_timer.timeout.connect(self._update_loading_dots)
        self._loading_step = 0
        self.thread_pool = QtCore.QThreadPool.globalInstance()
        self.tasks: list[TranslationTask] = []

    @QtCore.Slot(str)
    def set_clipboard_text(self, text: str) -> None:
        """Set clipboard text on the GUI thread."""
        QtWidgets.QApplication.clipboard().setText(text)

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

        # Minimize and close buttons
        self.minimize_btn = QtWidgets.QPushButton("\u2013", self.container)
        self.minimize_btn.setObjectName("minimize")
        self.minimize_btn.setFixedSize(24, 24)
        self.minimize_btn.clicked.connect(self.showMinimized)
        self.minimize_btn.setStyleSheet(
            "QPushButton#minimize {"
            "border: none;"
            "background: transparent;"
            "color: #2196F3;"
            "font-weight: bold;"
            "font-size: 18px;"
            "}"
            "QPushButton#minimize:hover { color: #64b5f6; }"
        )

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
        self.minimize_btn.move(self.width() - 64, 8)
        self.close_btn.move(self.width() - 32, 8)

        main_layout = QtWidgets.QVBoxLayout(self.container)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)

        # Language row
        lang_row = QtWidgets.QHBoxLayout()
        lang_row.setAlignment(QtCore.Qt.AlignCenter)

        self.src_combo = QtWidgets.QComboBox()
        self.dest_combo = QtWidgets.QComboBox()
        # Allow automatic detection for the source language
        self.src_combo.addItem("Detectar", "auto")
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
        self.src_combo.setCurrentIndex(1)
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
            "font-weight: bold;"
            "color: #2196F3;"
            "}"
            "QPushButton#swap:hover { color: #42a5f5; }"
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
        self.card = QtWidgets.QFrame()
        self.card.setObjectName("card")
        self.card.setStyleSheet(
            "#card {"
            "background-color: rgba(255, 255, 255, 0.85);"
            "border-radius: 24px;"
            "}"
        )
        card_layout = QtWidgets.QVBoxLayout(self.card)
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
        shortcut_copy = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+C"), self.input_edit)
        shortcut_copy.activated.connect(self.copy_translation)
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

        main_layout.addWidget(self.card)

        grip_row = QtWidgets.QHBoxLayout()
        grip_row.addStretch()

        self.settings_btn = QtWidgets.QPushButton("\u2699")
        self.settings_btn.setObjectName("settings")
        self.settings_btn.setFixedSize(24, 24)
        self.settings_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.settings_btn.clicked.connect(self.show_settings)
        self.settings_btn.setStyleSheet(
            "QPushButton#settings {"
            "background: transparent;"
            "border: none;"
            "color: #2196F3;"
            "font-size: 16px;"
            "}"
            "QPushButton#settings:hover { color: #42a5f5; }"
        )
        grip_row.addWidget(self.settings_btn)

        self.size_grip = QtWidgets.QSizeGrip(self.container)
        grip_row.addWidget(self.size_grip)
        main_layout.addLayout(grip_row)

        self._init_settings_popup()
        self.apply_theme()

    def _init_settings_popup(self) -> None:
        self.settings_popup = QtWidgets.QFrame(self, QtCore.Qt.Popup)
        self.settings_popup.setObjectName("settings_popup")
        self.settings_popup.setStyleSheet(
            "#settings_popup {"
            "background-color: rgba(255, 255, 255, 0.95);"
            "border-radius: 16px;"
            "}"
        )
        layout = QtWidgets.QVBoxLayout(self.settings_popup)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        top_row = QtWidgets.QHBoxLayout()
        top_row.addStretch()
        close_btn = QtWidgets.QPushButton("\u2715", self.settings_popup)
        close_btn.setObjectName("close")
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self.settings_popup.hide)
        close_btn.setStyleSheet(
            "QPushButton#close {"
            "border: none;"
            "background: transparent;"
            "color: red;"
            "font-weight: bold;"
            "font-size: 18px;"
            "}"
            "QPushButton#close:hover { color: #ff6666; }"
        )
        top_row.addWidget(close_btn)
        layout.addLayout(top_row)

        self.api_key_edit = QtWidgets.QLineEdit()
        self.api_key_edit.setPlaceholderText("API key")
        self.api_key_edit.editingFinished.connect(
            lambda: set_api_key(self.api_key_edit.text())
        )
        layout.addWidget(self.api_key_edit)

        self.api_link = QtWidgets.QLabel(
            '<a href="https://aistudio.google.com/app/apikey">consigue tu api key aqui</a>'
        )
        self.api_link.setOpenExternalLinks(True)
        font = self.api_link.font()
        font.setPointSize(8)
        self.api_link.setFont(font)
        self.api_link.setStyleSheet("color: #2196F3;")
        layout.addWidget(self.api_link)

        self.theme_btn = QtWidgets.QPushButton()
        self.theme_btn.setCheckable(True)
        self.theme_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.theme_btn.setChecked(THEME == "dark")
        self.theme_btn.clicked.connect(lambda _=None: self._on_theme_changed())
        layout.addWidget(self.theme_btn)
        self._update_theme_button()

        font_row = QtWidgets.QHBoxLayout()
        font_row.addWidget(QtWidgets.QLabel("Tama\u00f1o fuente"))
        self.font_spin = QtWidgets.QSpinBox()
        self.font_spin.setRange(10, 24)
        self.font_spin.setValue(FONT_SIZE)
        self.font_spin.valueChanged.connect(self._on_font_changed)
        font_row.addWidget(self.font_spin)
        layout.addLayout(font_row)

        default_row = QtWidgets.QHBoxLayout()
        default_row.addWidget(QtWidgets.QLabel("Idioma por defecto"))
        self.default_combo = QtWidgets.QComboBox()
        for label, code in LANG_OPTIONS:
            self.default_combo.addItem(label, code)
        idx = self.default_combo.findData(self.default_lang)
        if idx != -1:
            self.default_combo.setCurrentIndex(idx)
        self.default_combo.currentIndexChanged.connect(
            lambda i: (
                setattr(self, "default_lang", self.default_combo.itemData(i)),
                set_default_lang(self.default_combo.itemData(i)),
            )
        )
        default_row.addWidget(self.default_combo)
        layout.addLayout(default_row)

    def _on_theme_changed(self) -> None:
        self.dark_mode = self.theme_btn.isChecked()
        set_theme("dark" if self.dark_mode else "light")
        self.apply_theme()
        self._update_theme_button()

    def _on_font_changed(self) -> None:
        self.font_size = self.font_spin.value()
        set_font_size(self.font_size)
        self.apply_theme()

    def apply_theme(self) -> None:
        if self.dark_mode:
            container_bg = "rgba(40,40,40,0.85)"
            card_bg = "rgba(55,55,55,0.85)"
            text_color = "white"
            combo_bg = "#333333"
            link_color = "white"
        else:
            container_bg = "rgba(255,255,255,0.85)"
            card_bg = "rgba(255,255,255,0.85)"
            text_color = "black"
            combo_bg = "white"
            link_color = "#2196F3"

        self.container.setStyleSheet(
            f"#container {{background-color: {container_bg}; border-radius: 24px;}}"
        )
        self.card.setStyleSheet(
            f"#card {{background-color: {card_bg}; border-radius: 24px;}}"
        )
        for combo in (self.src_combo, self.dest_combo):
            combo.setStyleSheet(
                f"QComboBox {{font-size: 14px; color: {text_color}; background-color: {combo_bg};}}"
                f"QComboBox QAbstractItemView {{color: {text_color}; background-color: {combo_bg};}}"
            )
        self.input_edit.setStyleSheet(
            f"QPlainTextEdit {{color: {text_color}; font-weight: bold; border: none; background: transparent; font-size: {self.font_size}px;}}"
        )
        self.translated_label.setStyleSheet(
            f"color: #2196F3; font-size: {self.font_size}px; font-weight: bold;"
        )
        self.api_link.setStyleSheet(f"color: {link_color};")

    def _update_theme_button(self) -> None:
        if self.theme_btn.isChecked():
            self.theme_btn.setText("\u2600 Light mode")
            self.theme_btn.setStyleSheet(
                "QPushButton { background-color: white; color: black; border-radius: 16px; padding: 4px 8px; }"
            )
        else:
            self.theme_btn.setText("\U0001F319 Dark mode")
            self.theme_btn.setStyleSheet(
                "QPushButton { background-color: #2196F3; color: white; border-radius: 16px; padding: 4px 8px; }"
            )

    def show_settings(self):
        self.api_key_edit.setText(GEMINI_API_KEY)
        self.theme_btn.setChecked(self.dark_mode)
        self._update_theme_button()
        self.font_spin.setValue(self.font_size)
        idx = self.default_combo.findData(self.default_lang)
        if idx != -1:
            self.default_combo.setCurrentIndex(idx)
        self.settings_popup.adjustSize()
        pos = self.settings_btn.mapToGlobal(
            QtCore.QPoint(0, -self.settings_popup.height())
        )
        self.settings_popup.move(pos)
        self.settings_popup.show()

    def _update_loading_dots(self) -> None:
        """Update the loading indicator with an animated ellipsis."""
        self._loading_step = (self._loading_step + 1) % 4
        dots = "." * self._loading_step
        self.translated_label.setText(dots)

    def on_text_changed(self, text: str) -> None:
        """Translate the provided text asynchronously."""
        self._loading_step = 0
        self._update_loading_dots()
        self.loading_timer.start()
        task = TranslationTask(text, self.source_lang, self.target_lang)
        task.setAutoDelete(True)
        task.translation_ready.connect(self._display_translation)
        task.translation_ready.connect(lambda _=None, t=task: self._cleanup_task(t))
        self.tasks.append(task)
        self.thread_pool.start(task)

    def _cleanup_task(self, task: TranslationTask) -> None:
        """Remove finished task from the list."""
        if task in self.tasks:
            self.tasks.remove(task)

    def _display_translation(self, text: str) -> None:
        """Stop the loading animation and show the translated text."""
        self.loading_timer.stop()
        self.translated_label.setText(text)

    def _auto_set_langs(self, text: str) -> None:
        """Automatically adjust source and target languages based on ``text``."""
        if not text.strip():
            return
        detected = detect_language(text)
        if detected == self.dest_combo.currentData():
            # swap first so we keep the previous source on the right
            self.swap_languages()
        elif detected != self.default_lang:
            dest_idx = self.dest_combo.findData(self.default_lang)
            if dest_idx != -1:
                self.dest_combo.setCurrentIndex(dest_idx)

        src_idx = self.src_combo.findData(detected)
        if src_idx != -1:
            self.src_combo.setCurrentIndex(src_idx)

    def swap_languages(self):
        """Swap source and target languages."""
        src_code = self.src_combo.currentData()
        dest_code = self.dest_combo.currentData()
        src_idx = self.src_combo.findData(dest_code)
        dest_idx = self.dest_combo.findData(src_code)
        if src_idx != -1:
            self.src_combo.setCurrentIndex(src_idx)
        if dest_idx != -1:
            self.dest_combo.setCurrentIndex(dest_idx)

    def translate_current_text(self):
        """Handle the Enter key press from the input box."""
        text = self.input_edit.toPlainText()
        self._auto_set_langs(text)
        self.on_text_changed(text)

    @QtCore.Slot(str)
    def handle_hotkey_text(self, text: str) -> None:
        """Display text grabbed by the global hotkey."""
        if not text:
            return
        self.input_edit.setPlainText(text)
        self.show()
        self.raise_()
        self.activateWindow()

    @QtCore.Slot(str)
    def handle_hotkey_translation(self, text: str) -> None:
        """Show a translation triggered by the global hotkey."""
        if not text:
            return
        self.translated_label.setText(text)
        self.show()
        self.raise_()
        self.activateWindow()

    def language_changed(self, *args):
        if not hasattr(self, "input_edit"):
            return
        text = self.input_edit.toPlainText().strip()
        if text:
            self.on_text_changed(text)



    def copy_translation(self):
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(self.translated_label.text())

    def _delete_history_item(self, translation: str, menu: QtWidgets.QMenu) -> None:
        """Remove a translation entry and refresh the menu."""
        remove_translation_item(translation)
        menu.close()
        self.show_history_menu()

    def _select_history_item(self, translation: str, menu: QtWidgets.QMenu) -> None:
        """Copy the chosen translation and close the menu."""
        self.translated_label.setText(translation)
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(translation)
        menu.close()

    def _clear_history(self, menu: QtWidgets.QMenu) -> None:
        """Clear all history entries and close the menu."""
        clear_translation_history()
        self.translated_label.setText("")
        menu.close()

    def _export_history(self, menu: QtWidgets.QMenu) -> None:
        """Export translation history and close the menu."""
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export History",
            "translation_history.txt",
            "Text Files (*.txt);;All Files (*)",
        )
        if path:
            export_translation_history(path)
        menu.close()

    def show_history_menu(self):
        menu = QtWidgets.QMenu(self)
        history = get_translation_history()
        for translation, count in history:
            widget = QtWidgets.QWidget()
            layout = QtWidgets.QHBoxLayout(widget)
            layout.setContentsMargins(4, 2, 4, 2)
            select_btn = QtWidgets.QToolButton(widget)
            select_btn.setText(f"{translation} ({count})")
            select_btn.setStyleSheet(
                "QToolButton { border: none; text-align: left; padding: 0px; }"
            )
            select_btn.clicked.connect(
                lambda _=None, t=translation, m=menu: self._select_history_item(t, m)
            )
            del_btn = QtWidgets.QToolButton(widget)
            del_btn.setText("\u2715")
            del_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
            del_btn.setStyleSheet(
                "QToolButton { border: none; color: red; font-weight: bold; }"
                "QToolButton:hover { color: #ff6666; }"
            )
            del_btn.clicked.connect(
                lambda _=None, t=translation, m=menu: self._delete_history_item(t, m)
            )
            layout.addWidget(select_btn)
            layout.addStretch()
            layout.addWidget(del_btn)
            action = QtWidgets.QWidgetAction(menu)
            action.setDefaultWidget(widget)
            menu.addAction(action)
        if not history:
            menu.addAction("(no history)")
        else:
            menu.addSeparator()
        export_action = menu.addAction("Export history...")
        clear_action = menu.addAction("Clear history")

        export_action.triggered.connect(lambda: self._export_history(menu))
        clear_action.triggered.connect(lambda: self._clear_history(menu))

        menu.exec(
            self.history_btn.mapToGlobal(QtCore.QPoint(0, self.history_btn.height()))
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.container.setGeometry(0, 0, self.width(), self.height())
        self.minimize_btn.move(self.width() - 64, 8)
        self.close_btn.move(self.width() - 32, 8)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.offset = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self.offset is not None and event.buttons() & QtCore.Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.offset)

    def mouseReleaseEvent(self, event):
        self.offset = None

    def closeEvent(self, event):
        """Wait for running translation tasks before closing."""
        self.thread_pool.waitForDone()
        super().closeEvent(event)


def start_global_hotkey(window: "FloatingTranslatorWindow", hotkey: str = "ctrl+shift+t") -> None:
    """Listen for ``hotkey`` globally and translate the selected text."""

    def handle_hotkey() -> None:
        keyboard.press_and_release("ctrl+c")
        time.sleep(0.05)
        text = QtWidgets.QApplication.clipboard().text()
        QtCore.QMetaObject.invokeMethod(
            window,
            "handle_hotkey_text",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(str, text),
        )
        if not text:
            return
        translated = translate_text(text, "auto", "en")
        QtCore.QMetaObject.invokeMethod(
            window,
            "handle_hotkey_translation",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(str, translated),
        )
        QtCore.QMetaObject.invokeMethod(
            window,
            "set_clipboard_text",
            QtCore.Qt.BlockingQueuedConnection,
            QtCore.Q_ARG(str, translated),
        )
        keyboard.press_and_release("ctrl+v")

    thread = threading.Thread(
        target=lambda: (keyboard.add_hotkey(hotkey, handle_hotkey), keyboard.wait()),
        daemon=True,
    )
    thread.start()


if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    window = FloatingTranslatorWindow()
    window.show()
    start_global_hotkey(window)
    app.exec()
