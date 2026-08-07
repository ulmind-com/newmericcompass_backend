"""Production entrypoint.

Binds to 0.0.0.0 and the platform-provided $PORT so hosts like Render/Railway
can detect the open port. Use as the start command:

    uv run python main.py
"""

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
