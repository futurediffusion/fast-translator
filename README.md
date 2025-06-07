# fast-translator

A small PySide6 application that floats above other windows and translates
text between languages using Google's Gemini generative language API. Choose
the source and target languages from the drop-down menus. The source list now
includes an "Detectar" option for automatic language detection and several
additional languages such as Chinese, Japanese and Russian.

When translating text the application automatically detects the input
language. If the text is in the same language as the current target, the
languages are swapped so the translation always goes to the opposite side.
You can set a default language in the settings panel that will be used as the
target whenever a new language is detected.

## Installation

Install the required dependencies using pip:

```bash
pip install -r requirements.txt
```

## Usage

Run the translator with:

```bash
python floating_translator.py
```

The application starts without an API key. Click the gear button in the bottom
right corner to open the settings popup and enter your own key. The key is
stored in `config.json` so you only need to provide it once.

The translator prompts the Gemini API to respond with the target-language
translation enclosed in double asterisks (for example `**hola**`).
The application filters the response to display only the text inside the
asterisks.

Translations are executed on a global `QThreadPool` so threads are reused
between requests. This keeps the user interface responsive while avoiding the
overhead of creating new threads for every translation.

Previous translations are stored in `translation_cache.json` so frequent
requests are reused without contacting the API. A small delay is also applied
between requests and the application automatically retries when the API
responds with HTTP 429 errors.

While the translation is in progress, the output label shows an animated
ellipsis to indicate activity.

Press `Ctrl+Enter` (or `Ctrl+Return`) inside the input box to send the text
for translation. The input field supports multiple lines so you can type
longer passages. Press `Ctrl+C` while editing to quickly copy the latest
translation to the clipboard.

Click the small down-arrow button next to the copy icon to open the history
menu. It lists previous translations ordered by how often each one has been
used, showing a counter for every entry. Selecting an item copies the text to
the clipboard and displays it again in the output label. The menu also provides
options to export the history to a text file or clear it entirely. The cache is
automatically trimmed to the 15 most frequently used entries so it stays
lightweight.

The settings popup now includes a button for toggling dark mode as well as an
option to adjust the font size. The button displays a moon when the interface
is light and a sun when it is dark, switching the theme with a single click. A
blue minimize button next to the red close button lets you minimize the window
when you want it out of the way.
