from __future__ import annotations

import argparse
import json

import uvicorn

from app.client import AnalyticsClient, AnalyticsAPIError
from app.collector import collect
from app.config import Settings
from app.storage import create_storage


def main() -> None:
    parser = argparse.ArgumentParser(description="ChatGPT workspace usage dashboard")
    subparsers = parser.add_subparsers(dest="command", required=True)
    collect_parser = subparsers.add_parser("collect", help="Collect workspace usage manually")
    collect_parser.add_argument("--days", type=int, default=7)
    serve_parser = subparsers.add_parser("serve", help="Run the local dashboard")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.command == "serve":
        uvicorn.run("app.web:app", host=args.host, port=args.port)
        return
    try:
        settings = Settings.from_env(require_key=True)
        storage = create_storage(settings)
        client = AnalyticsClient(settings.analytics_url, settings.admin_key, settings.timeout_seconds, settings.max_retries)
        result = collect(client, storage, days=args.days)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, AnalyticsAPIError) as exc:
        parser.exit(1, f"collection failed: {exc}\n")


if __name__ == "__main__":
    main()
