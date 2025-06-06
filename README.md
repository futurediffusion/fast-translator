# fast-translator

A small PySide6 application that floats above other windows and translates
Spanish text into English using Google's Gemini generative language API.

## Usage

Run the translator with:

```bash
python floating_translator.py
```

The application contains a built-in example API key, but you can modify the
`GEMINI_API_KEY` constant in `floating_translator.py` to use your own.

The translator prompts the Gemini API to respond with the English
translation enclosed in double asterisks (for example `**hello**`).
The application filters the response to display only the text inside the
asterisks.
