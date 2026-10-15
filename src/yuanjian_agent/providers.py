from __future__ import annotations

import hashlib
import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .secrets import SecretScanner


@dataclass(slots=True)
class OpenAICompatibleProvider:
    """Optional, default-off comparison provider; target source code is never sent."""

    base_url: str
    model: str
    api_key: str
    cache_dir: Path
    secret_scanner: SecretScanner
    enabled: bool = False
    timeout_seconds: int = 30

    def explain(self, task_text: str, tool_name: str, tool_description: str) -> dict:
        if not self.enabled:
            raise RuntimeError("External provider is disabled")
        safe_input = {
            "task": self.secret_scanner.redact_text(task_text)[:2000],
            "tool_name": self.secret_scanner.redact_text(tool_name)[:200],
            "tool_description": self.secret_scanner.redact_text(tool_description)[:2000],
        }
        prompt = (
            "Decide whether the tool is over-exposed for the declared agent task. "
            "Return JSON with probability, rationale, and uncertainty. Do not infer missing runtime controls.\n"
            + json.dumps(safe_input, ensure_ascii=False)
        )
        request_payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }
        cache_key = hashlib.sha256(json.dumps(request_payload, sort_keys=True).encode()).hexdigest()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self.cache_dir / f"{cache_key}.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))["result"]
        request = urllib.request.Request(
            self.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(request_payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            raw = json.loads(response.read().decode("utf-8"))
        content = raw["choices"][0]["message"]["content"]
        result = json.loads(content)
        record = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "provider_base_url": self.base_url,
            "request": request_payload,
            "result": result,
        }
        cache_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
