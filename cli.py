#!/usr/bin/env python3
"""
NURU V10 — CLI interactif.

Usage:
  nuru ask <question>         — Question one‑shot, réponse complète
  nuru chat                    — Mode interactif (multi‑tour)
  nuru list                    — Lister les sessions
  nuru show <session_id>       — Afficher une session
  nuru delete <session_id>     — Supprimer une session

Exemples :
  nuru ask "Quels sont mes documents PDF ?"
  nuru chat
  nuru list
  nuru show default
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Couleurs ANSI
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
CLS = "\033[2J\033[H"


def banner():
    print(f"{CLS}{CYAN}{BOLD}")
    print("╔══════════════════════════════════════╗")
    print("║     NURU V10 — Assistant IA          ║")
    print("║     Mode CLI interactif               ║")
    print("╚══════════════════════════════════════╝")
    print(f"{RESET}")


def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def print_msg(role: str, content: str):
    """Affiche un message formaté."""
    prefix = f"{GREEN}[{now()}]{RESET} "
    if role == "user":
        prefix += f"{BOLD}Vous{RESET}"
    elif role == "assistant":
        prefix += f"{CYAN}NURU{RESET}"
    else:
        prefix += f"{YELLOW}{role}{RESET}"
    print(f"\n{prefix}  ")
    print(f"  {content}\n")


async def cmd_ask(query: str, session_id: str = "default"):
    """Question one‑shot."""
    sys.path.insert(0, str(Path(__file__).parent))

    from src.nuru_core import NURU

    core = NURU()
    print(f"{DIM}🧠 Initialisation de NURU...{RESET}", end="", flush=True)
    await core._async_init()
    print(f" {GREEN}✓{RESET}")

    print(f"\n{CYAN}╭─ Question ─────────────────────────╮{RESET}")
    print(f"  {BOLD}{query}{RESET}")
    print(f"{CYAN}╰─────────────────────────────────────╯{RESET}\n")

    t0 = time.monotonic()
    tokens = []
    try:
        async for token in core.process_query_v45(query):
            tokens.append(token)
            print(token, end="", flush=True)
    except KeyboardInterrupt:
        print(f"\n{DIM}Interrompu.{RESET}")
    except Exception as e:
        print(f"\n{RED}Erreur : {e}{RESET}")

    elapsed = time.monotonic() - t0
    full = "".join(tokens)
    print(f"\n\n{DIM}━━ réponse en {elapsed:.1f}s, {len(full)} chars{RESET}")

    await core.cleanup()


async def cmd_chat():
    """Mode interactif multi‑tour."""
    import readline  # améliore l'édition de ligne

    sys.path.insert(0, str(Path(__file__).parent))

    from src.nuru_core import NURU

    core = NURU()
    print(f"\n{DIM}🧠 Initialisation de NURU...{RESET}", end="", flush=True)
    await core._async_init()
    print(f" {GREEN}✓{RESET}\n")

    print(f"{DIM}Commandes spéciales : /exit, /clear, /help{RESET}\n")

    session_id = "default"
    while True:
        try:
            query = input(f"{GREEN}[{now()}]{RESET} {BOLD}Vous >{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not query:
            continue
        if query.lower() in ("/exit", "/quit", "/q"):
            break
        if query.lower() == "/clear":
            print(CLS)
            banner()
            core.orchestrator.session_store.clear_session(session_id)
            print(f"  {DIM}Session nettoyée.{RESET}\n")
            continue
        if query.lower() == "/help":
            print(f"\n  {BOLD}Commandes disponibles :{RESET}")
            print(f"  {DIM}/exit, /q{RESET}    — Quitter")
            print(f"  {DIM}/clear{RESET}      — Nettoyer la session courante")
            print(f"  {DIM}/new{RESET}        — Nouvelle session")
            print(f"  {DIM}/help{RESET}       — Cette aide\n")
            continue
        if query.lower() == "/new":
            session_id = f"cli_{int(time.time())}"
            print(f"  {DIM}Nouvelle session : {session_id}{RESET}\n")
            continue

        print(f"\n{CYAN}╭─ NURU ─────────────────────────────╮{RESET}")
        t0 = time.monotonic()
        tokens = []
        try:
            async for token in core.orchestrator.process_query(
                query=query, session_id=session_id
            ):
                tokens.append(token)
                print(token, end="", flush=True)
        except KeyboardInterrupt:
            print(f"\n{DIM}Interrompu.{RESET}")
        except Exception as e:
            print(f"\n{RED}Erreur : {e}{RESET}")

        elapsed = time.monotonic() - t0
        full = "".join(tokens)
        print(f"\n{CYAN}╰{'─'*30}╯{RESET}")
        print(f"{DIM}  {elapsed:.1f}s · {len(full)} chars{RESET}\n")

    await core.cleanup()
    print(f"\n{GREEN}Au revoir ! 👋{RESET}\n")


async def cmd_list(limit: int = 10):
    """Lister les sessions."""
    sys.path.insert(0, str(Path(__file__).parent))
    from src.session.store import SessionStore

    store = SessionStore()
    sessions = store.list_sessions(limit=limit)
    if not sessions:
        print(f"{YELLOW}Aucune session trouvée.{RESET}")
        return
    print(f"\n{BOLD}Sessions ({len(sessions)}) :{RESET}\n")
    for s in sessions:
        raw_ts = s.get("updated_at") or s.get("created_at") or 0
        if isinstance(raw_ts, (int, float)) and raw_ts:
            try:
                dt_str = datetime.fromtimestamp(raw_ts).strftime("%H:%M %d/%m")
            except (OSError, ValueError, OverflowError):
                dt_str = str(raw_ts)[:16]
        else:
            dt_str = str(raw_ts)[:16] if raw_ts else "?"
        print(
            f"  {CYAN}{s['id'][:24]:<24}{RESET}"
            f"{s['title'][:45]:<48} "
            f"{DIM}{s['message_count']} msg · {dt_str}{RESET}"
        )
    print()


async def cmd_show(session_id: str):
    """Afficher une session."""
    sys.path.insert(0, str(Path(__file__).parent))
    from src.session.store import SessionStore

    store = SessionStore()
    session = store.get_or_create(session_id)
    print(f"\n{BOLD}Session : {session.title}{RESET}")
    print(f"{DIM}ID : {session.id} | "
          f"{len(session.messages)} messages{RESET}\n")
    for m in session.messages:
        role_icon = f"{GREEN}▶{RESET}" if m.role == "user" else f"{CYAN}◆{RESET}"
        ts_str = ""
        if m.timestamp:
            try:
                ts_str = datetime.fromtimestamp(m.timestamp).strftime("%Y-%m-%d %H:%M")
            except (OSError, ValueError, OverflowError):
                ts_str = str(m.timestamp)[:19]
        print(f"  {role_icon} {BOLD}{m.role.capitalize()}{RESET} "
              f"({ts_str})")
        content = m.content[:500] + ("..." if len(m.content) > 500 else "")
        for line in content.split("\n"):
            print(f"    {line}")
        print()


async def cmd_delete(session_id: str):
    """Supprimer une session."""
    sys.path.insert(0, str(Path(__file__).parent))
    from src.session.store import SessionStore

    store = SessionStore()
    store.delete_session(session_id)
    print(f"{GREEN}✓{RESET} Session « {session_id} » supprimée.\n")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "ask" and len(sys.argv) >= 3:
        query = " ".join(sys.argv[2:])
        asyncio.run(cmd_ask(query))
    elif command == "chat":
        asyncio.run(cmd_chat())
    elif command == "list":
        asyncio.run(cmd_list())
    elif command == "show" and len(sys.argv) >= 3:
        asyncio.run(cmd_show(sys.argv[2]))
    elif command == "delete" and len(sys.argv) >= 3:
        asyncio.run(cmd_delete(sys.argv[2]))
    else:
        print(f"{RED}Commande inconnue ou arguments manquants.{RESET}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
