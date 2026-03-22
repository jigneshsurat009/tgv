from __future__ import annotations


def human_size(value: int) -> str:
    num = float(value)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num < 1024 or unit == "TB":
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{value} B"
