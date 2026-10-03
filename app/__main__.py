from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="ChatGPT workspace usage dashboard API")
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve_parser = subparsers.add_parser("serve", help="Run the API server")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run("app.web:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
