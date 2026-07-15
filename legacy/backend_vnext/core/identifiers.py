from __future__ import annotations


def canonical_identifier(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"`", '"', "'"}:
        text = text[1:-1]
    return text.lower()
