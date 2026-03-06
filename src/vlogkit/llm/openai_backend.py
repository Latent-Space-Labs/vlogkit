"""OpenAI LLM backend (alternative to Claude)."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from ..config import Settings


class OpenAIBackend:
    def __init__(self, settings: Settings):
        import openai

        self.client = openai.OpenAI(api_key=settings.openai_api_key)
        self.model = "gpt-4o"

    def complete(self, prompt: str, system: str = "") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=4096,
        )
        return response.choices[0].message.content or ""

    def complete_with_images(
        self,
        prompt: str,
        image_paths: list[str],
        system: str = "",
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})

        content: list[dict] = []
        for img_path in image_paths:
            p = Path(img_path)
            media_type = mimetypes.guess_type(str(p))[0] or "image/jpeg"
            data = base64.standard_b64encode(p.read_bytes()).decode("utf-8")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{data}"},
            })
        content.append({"type": "text", "text": prompt})

        messages.append({"role": "user", "content": content})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=4096,
        )
        return response.choices[0].message.content or ""
