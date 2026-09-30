"""Write the OpenAPI schema to frontend/src/lib/openapi.json (then run `pnpm gen:types` in frontend/).

Usage (from backend/):  python -m scripts.export_openapi [--check]
`--check` exits non-zero if the committed file is out of date (used by CI and a backend test).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

TARGET = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "openapi.json"


def current_schema() -> dict[str, Any]:
    os.environ.setdefault("WARMUP_MODELS", "false")
    from app.main import create_app

    schema: dict[str, Any] = create_app().openapi()
    return schema


def render(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = render(current_schema())
    if args.check:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != text:
            sys.exit(f"{TARGET} is out of date — run: python -m scripts.export_openapi")
        print("OpenAPI schema is up to date")
        return
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {TARGET}")


if __name__ == "__main__":
    main()
