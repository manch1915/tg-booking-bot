"""Writes the OpenAPI schema to a file; the web app generates its types from it."""

import json
import sys
from pathlib import Path

from booking.api.app import create_app
from booking.config import Settings


def main() -> None:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
    schema = create_app(Settings()).openapi()
    target.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {target}")


if __name__ == "__main__":
    main()
