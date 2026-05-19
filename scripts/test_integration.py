"""
End-to-end integration test — creates a circuit and adds LED, Resistor, Arduino.

Usage:
    .venv/Scripts/python.exe scripts/test_integration.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ["TINKERCAD_HEADLESS"] = "false"  # headed so user can watch

import tinkercad_mcp.api as api

SEP = "-" * 55

def log(label: str, result: str) -> None:
    ok = "OK" if "error" not in result.lower() else "FAIL"
    print(f"\n[{ok}] [{label}]\n  {result[:200]}")


async def main() -> None:
    print(SEP)
    print("  Tinkercad MCP — integration test")
    print(SEP)

    # ── 1. Session ──────────────────────────────────────────────────────────
    print("\n[1] Checking session...")
    status = await api.get_session_status()
    log("session_status", status)

    if "invalid" in status.lower() or "expired" in status.lower():
        print("\n[1b] Session invalid — opening headed browser for login...")
        result = await api.login()
        log("login", result)

    # ── 2. Create circuit ───────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("[2] Creating new circuit 'MCP Test Circuit'...")
    result = await api.create_circuit("MCP Test Circuit")
    log("create_circuit", result)

    if "error" in result.lower():
        print("\nCannot continue — circuit creation failed.")
        return

    # Wait for editor to stabilize
    await asyncio.sleep(3)

    # ── 3. Add components ───────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("[3] Adding LED...")
    result = await api.add_component("led", x=150, y=120)
    log("add_component led", result)
    await asyncio.sleep(2)

    print("\n[4] Adding Resistor...")
    result = await api.add_component("resistor", x=300, y=120)
    log("add_component resistor", result)
    await asyncio.sleep(2)

    print("\n[5] Adding Arduino Uno...")
    result = await api.add_component("arduino_uno", x=220, y=280)
    log("add_component arduino_uno", result)
    await asyncio.sleep(2)

    # ── Done ────────────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("Integration test complete. Browser stays open — press Ctrl+C to close.")
    print(SEP)

    try:
        await asyncio.sleep(9999)
    except KeyboardInterrupt:
        pass

    from tinkercad_mcp.browser import BrowserManager
    mgr = await BrowserManager.get_instance()
    await mgr.close()


if __name__ == "__main__":
    asyncio.run(main())
