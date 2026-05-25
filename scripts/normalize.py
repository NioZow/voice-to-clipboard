#!/usr/bin/env python3
import subprocess
import sys


def normalize_text(text):
    # Use Ollama to normalize technical terms
    # Llama 3.2 1B is recommended for speed
    prompt = f"You are a technical text formatter. Clean up the following speech-to-text transcription from a developer. Fix technical terms (e.g., 'Jason' to 'JSON', 'bullion' to 'boolean'), add basic punctuation, and remove filler words like 'um' or 'uh'. Do not change the meaning and do not translate — preserve the original language entirely. Output only the cleaned text without any commentary or preamble.\n\nText: {text}"

    try:
        process = subprocess.Popen(
            ["ollama", "run", "llama3.2:1b", prompt],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        stdout, stderr = process.communicate()
        if process.returncode == 0 and stdout.strip():
            return stdout.strip()
    except Exception as e:
        print(f"Normalization error: {e}", file=sys.stderr)

    return text  # Fallback to raw text


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)

    input_text = sys.stdin.read() if not sys.argv[1] == "-" else sys.stdin.read()
    if not input_text:
        # If no stdin, use first argument
        input_text = " ".join(sys.argv[1:])

    print(normalize_text(input_text))
