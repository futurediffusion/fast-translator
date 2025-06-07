# fast-translator

A small PySide6 application that floats above other windows and translates
text between languages using Google's Gemini generative language API. Choose
the source and target languages from the drop-down menus.

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

The application contains a built-in example API key, but you can modify the
`GEMINI_API_KEY` constant in `floating_translator.py` to use your own.

The translator prompts the Gemini API to respond with the target-language
translation enclosed in double asterisks (for example `**hola**`).
The application filters the response to display only the text inside the
asterisks.

Press `Ctrl+Enter` (or `Ctrl+Return`) inside the input box to send the text
for translation. The input field supports multiple lines so you can type
longer passages.
