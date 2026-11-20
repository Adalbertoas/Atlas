"""Agente de ATLAS para la PC (ver app/agent/client.py).

Con el backend de ATLAS en un servidor, este programa corre en la PC y ejecuta
las acciones que necesitan Windows. Lee de backend/.env:

    AGENT_SERVER_URL=https://atlas.sirinetrd.com
    AGENT_TOKEN=<la misma clave que AGENT_TOKEN en el .env del servidor>

    python agent.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

# La consola de Windows (cp1252) revienta con acentos.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [agente] %(message)s", datefmt="%H:%M:%S")
    server = os.environ.get("AGENT_SERVER_URL", "").strip()
    token = os.environ.get("AGENT_TOKEN", "").strip()
    if not server or not token:
        print("Falta AGENT_SERVER_URL o AGENT_TOKEN en backend/.env.")
        return 1

    from app.agent.client import serve
    from app.tools.pc_tools import build_pc_tools

    try:
        asyncio.run(serve(server, token, build_pc_tools()))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
