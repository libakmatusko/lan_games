"""Small synchronous terminal menu helpers used before networking starts."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")


def choose(title: str, options: Sequence[T], label: Callable[[T], str] = str) -> T:
    """Display numbered choices and return one selected option."""
    if not options:
        raise ValueError("menu requires at least one option")
    print(title)
    for index, option in enumerate(options, start=1):
        print(f"  {index}. {label(option)}")
    while True:
        answer = input("Choose a number: ").strip()
        try:
            selection = int(answer)
        except ValueError:
            selection = 0
        if 1 <= selection <= len(options):
            return options[selection - 1]
        print(f"Enter a number from 1 to {len(options)}.")
