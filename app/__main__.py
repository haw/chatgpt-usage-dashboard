from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="ChatGPT workspace usage dashboard API")
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve_parser = subparsers.add_parser("serve", help="Run the API server")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    subparsers.add_parser(
        "evaluate", help="Check the detection rules against the stored data, assuming it contains no abuse")
    args = parser.parse_args()
    if args.command == "evaluate":
        from app.analytics import default_detectors
        from app.config import Settings
        from app.evaluation import render
        from app.storage import create_storage

        rows = sorted(create_storage(Settings.from_env()).load_workspace_usage(), key=lambda row: row["date"])
        print(render(rows, default_detectors()))
        return
    uvicorn.run("app.web:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
