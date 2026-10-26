import re

# Pictographic emoji and the invisible characters that join or style them. Plain typographic
# symbols (stars used for ratings, check marks) are deliberately not matched.
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF✅❌✨⚠⭐➕ℹ❓❗⌛⏳️‍]+"
)


def strip_emoji(text):
    """Remove emoji from user-facing text and tidy the spacing they leave behind."""
    if not isinstance(text, str):
        return text
    return re.sub(r"\s{2,}", " ", _EMOJI.sub("", text)).strip()
