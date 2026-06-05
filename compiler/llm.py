import ollama
import json
import re

MODEL = "qwen2.5:3b"

# qwen2.5:3b needs more room — Stage 2 IR alone can exceed 1000 tokens.
# 4096 is safe for all stages. Increase to 8192 if Stage 2 still truncates.
DEFAULT_NUM_PREDICT = 4096


def call_llm(system: str, user: str, max_retries: int = 3) -> dict:
    """
    Calls Ollama and returns parsed JSON.
    Retries up to max_retries times if JSON parsing fails.
    On each retry the user prompt is augmented with an explicit reminder
    so the model self-corrects rather than repeating the same bad output.
    """
    last_error = None
    last_raw = ""

    for attempt in range(max_retries):
        # On retries, append a strong corrective hint to the user message
        # so each attempt is meaningfully different (avoids identical failures).
        user_msg = user
        if attempt > 0:
            user_msg = (
                f"{user}\n\n"
                f"IMPORTANT: Your previous response could not be parsed as JSON. "
                f"Return ONLY a raw JSON object. No prose, no markdown, no backticks, "
                f"no explanations before or after the JSON. Start your response with {{ "
                f"and end it with }}."
            )

        try:
            response = ollama.chat(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user_msg},
                ],
                options={
                    "temperature": 0,
                    "num_predict": DEFAULT_NUM_PREDICT,
                },
            )
        except Exception as e:
            print(f"  ⚠ Attempt {attempt + 1}: Ollama call failed: {e}")
            last_error = e
            continue

        raw = response["message"]["content"].strip()
        last_raw = raw

        cleaned = _extract_json(raw)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            print(f"  ⚠ Attempt {attempt + 1}: JSON parse failed ({e}), retrying...")
            last_error = e

    raise ValueError(
        f"LLM returned invalid JSON after {max_retries} attempts.\n"
        f"Last error: {last_error}\n"
        f"Raw output (first 800 chars):\n{last_raw[:800]}"
    )


def _extract_json(text: str) -> str:
    """
    Robustly extracts a JSON object or array from LLM output that may contain:
      - markdown fences  (```json ... ```)
      - preamble prose   ("Here is the JSON: {...")
      - postamble prose  ("...} \n\nNote: I followed the rules.")
      - mixed braces in prose that surround the real JSON

    Strategy: strip fences first, then use a brace-depth counter to find the
    exact span of the outermost JSON object/array.  This is O(n) and handles
    nested structures correctly — unlike the previous first-{/last-} slice which
    breaks whenever trailing text contains any } character.
    """
    # 1. Strip markdown fences
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()

    # 2. Find the start of the first JSON object or array
    start = -1
    open_char = None
    close_char = None
    for i, ch in enumerate(text):
        if ch == "{":
            start = i
            open_char = "{"
            close_char = "}"
            break
        if ch == "[":
            start = i
            open_char = "["
            close_char = "]"
            break

    if start == -1:
        # No JSON structure found at all — return as-is and let caller raise
        return text

    # 3. Walk forward tracking brace depth to find the matching close
    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape_next:
            escape_next = False
            continue

        if ch == "\\" and in_string:
            escape_next = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                # Found the exact end of the outermost JSON structure
                return text[start : i + 1]

    # Depth never reached 0 — JSON was truncated.
    # Return whatever we have; json.loads will raise and trigger a retry.
    return text[start:]
