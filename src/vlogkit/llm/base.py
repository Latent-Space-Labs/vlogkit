"""LLM backend protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMBackend(Protocol):
    def complete(self, prompt: str, system: str = "") -> str:
        """Send a text prompt and return the completion."""
        ...

    def complete_with_images(
        self,
        prompt: str,
        image_paths: list[str],
        system: str = "",
    ) -> str:
        """Send a prompt with images and return the completion."""
        ...
