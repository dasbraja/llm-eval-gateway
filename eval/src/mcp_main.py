"""
src/mcp_main.py
---------------
Entry point for the MCP server.

Stdio transport (Claude Desktop / local MCP clients):
    python src/mcp_main.py

SSE transport (remote / browser-based clients):
    python src/mcp_main.py --transport sse --port 8001

Both the FastAPI server and the MCP server can run simultaneously —
they are independent processes on different ports.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

# Ensure the project root (eval/) is on sys.path so `src.*` imports resolve
# correctly whether this file is run as a script or as a module.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.eval_mcp.server import mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="GenAI Eval MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host for SSE transport (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8081,
        help="Port for SSE transport (default: 8081)",
    )
    args = parser.parse_args()


    print("mcp server starting")
    mcp.run(transport=args.transport, host=args.host, port=args.port)  # ← use args
    print("mcp server started")
    #mcp.run(transport="sse", port=8081)


if __name__ == "__main__":
    main()