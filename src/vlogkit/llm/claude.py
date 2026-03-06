"""Claude LLM backend via Anthropic API."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

import anthropic

from ..config import Settings


class ClaudeBackend:
    def __init__(self, settings: Settings):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.claude_model
        self.vision_model = settings.claude_vision_model

    def complete(self, prompt: str, system: str = "") -> str:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        response = self.client.messages.create(**kwargs)
        return response.content[0].text

    def complete_with_images(
        self,
        prompt: str,
        image_paths: list[str],
        system: str = "",
    ) -> str:
        content: list[dict] = []
        for img_path in image_paths:
            p = Path(img_path)
            media_type = mimetypes.guess_type(str(p))[0] or "image/jpeg"
            data = base64.standard_b64encode(p.read_bytes()).decode("utf-8")
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": data,
                },
            })
        content.append({"type": "text", "text": prompt})

        kwargs: dict = {
            "model": self.vision_model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": content}],
        }
        if system:
            kwargs["system"] = system
        response = self.client.messages.create(**kwargs)
        return response.content[0].text
