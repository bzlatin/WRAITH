"""Harmless tools passed through the application's real --functions loader."""

import tool_runtime as _runtime


def multiply(a: int, b: int) -> int:
    """Multiply two integers."""
    return _runtime.record("multiply", {"a": a, "b": b}, a * b)


def greet(name: str) -> str:
    """Greet a named person."""
    return _runtime.record("greet", {"name": name}, f"Hello, {name}!")
