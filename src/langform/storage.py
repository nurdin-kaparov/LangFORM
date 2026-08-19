from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JSONStore:
    def __init__(self, path: str | Path, default: Any):
        self.path = Path(path)
        self.default = default
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Any:
        if not self.path.exists():
            return self.default.copy() if hasattr(self.default, "copy") else self.default
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return self.default.copy() if hasattr(self.default, "copy") else self.default

    def save(self, value: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(self.path)
