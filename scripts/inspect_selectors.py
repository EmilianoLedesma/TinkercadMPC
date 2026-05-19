"""
Selector inspector — opens Tinkercad in headed mode and tests every SEL entry.

Usage:
    .venv\Scripts\python.exe scripts\inspect_selectors.py

Steps:
    1. Browser opens at tinkercad.com/dashboard
    2. If not logged in, log in manually — then press Enter in this terminal
    3. Script tests all selectors and prints a report
    4. For failed selectors, it dumps nearby DOM so you can find the real one
"""

import asyncio
import os
import sys

# Make sure src/ is importable when run from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

os.environ["TINKERCAD_HEADLESS"] = "false"

from playwright.async_api import async_playwright
from tinkercad_mcp.utils import SEL, SESSION_FILE, TINKERCAD_DASHBOARD, USER_AGENT

GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


async def test_selector(page, name: str, sel: str) -> bool:
    try:
        # Use first() so comma-separated selectors are handled
        el = await page.query_selector(sel)
        return el is not None
    except Exception:
        return False


async def dump_dom_hint(page, name: str) -> None:
    """Print a small DOM snippet to help identify the real selector."""
    hints = {
        "user_avatar":   "header, nav, [class*='Header'], [class*='header']",
        "user_name":     "header, nav, [class*='Header'], [class*='header']",
        "tab_3d":        "nav, [role='tablist'], [class*='Tab'], [class*='tab']",
        "tab_circuits":  "nav, [role='tablist'], [class*='Tab'], [class*='tab']",
        "design_cards":  "main, [class*='Dashboard'], [class*='card'], [class*='Card']",
        "btn_create_design":  "main, [class*='Dashboard'], button",
        "btn_create_circuit": "main, [class*='Dashboard'], button",
        "btn_start_sim": "[class*='Simulation'], [class*='toolbar'], button",
        "btn_stop_sim":  "[class*='Simulation'], [class*='toolbar'], button",
        "component_search": "aside, [class*='Panel'], [class*='panel'], input",
        "serial_monitor": "[class*='Serial'], [class*='Monitor'], [class*='console']",
    }
    scope = hints.get(name)
    if not scope:
        return
    try:
        el = await page.query_selector(scope)
        if el:
            html = await el.inner_html()
            # Trim to first 600 chars to avoid flooding terminal
            preview = html.replace("\n", " ")[:600]
            print(f"  {YELLOW}DOM hint ({scope}):{RESET}")
            print(f"  {preview}")
    except Exception:
        pass


async def main() -> None:
    async with async_playwright() as p:
        storage = str(SESSION_FILE) if SESSION_FILE.exists() else None

        browser = await p.chromium.launch(
            headless=False,
            args=["--no-sandbox"],
        )
        context = await browser.new_context(
            storage_state=storage,
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        print(f"\n{BOLD}Navigating to Tinkercad dashboard...{RESET}")
        await page.goto(TINKERCAD_DASHBOARD, wait_until="networkidle")

        # Check if login needed
        avatar = await page.query_selector(SEL["user_avatar"])
        if avatar is None:
            print(f"\n{YELLOW}Not logged in. Log in manually in the browser, then press Enter here.{RESET}")
            input()
            await page.goto(TINKERCAD_DASHBOARD, wait_until="networkidle")

        print(f"\n{BOLD}=== DASHBOARD SELECTORS ==={RESET}\n")
        dashboard_keys = [
            "user_avatar", "user_name",
            "tab_3d", "tab_circuits",
            "design_cards", "btn_create_design", "btn_create_circuit",
            "btn_delete_design",
        ]
        await _test_group(page, dashboard_keys)

        # Click 3D tab to open editor if possible
        print(f"\n{BOLD}=== 3D EDITOR SELECTORS ==={RESET}")
        print(f"{YELLOW}Open a 3D design in the browser, then press Enter.{RESET}")
        input()
        await page.wait_for_load_state("networkidle")
        editor_keys = [
            "btn_export", "btn_export_stl", "shape_toolbar",
            "design_name_input",
        ]
        await _test_group(page, editor_keys)

        # Circuit editor
        print(f"\n{BOLD}=== CIRCUIT EDITOR SELECTORS ==={RESET}")
        print(f"{YELLOW}Open a circuit in the browser, then press Enter.{RESET}")
        input()
        await page.wait_for_load_state("networkidle")
        circuit_keys = [
            "circuit_canvas", "component_search",
            "btn_start_sim", "btn_stop_sim",
            "serial_monitor", "serial_output",
            "btn_add_code", "code_editor", "btn_upload_code",
        ]
        await _test_group(page, circuit_keys)

        # Summary
        print(f"\n{BOLD}=== SUMMARY ==={RESET}")
        all_keys = list(SEL.keys())
        results: dict[str, bool] = {}
        # Re-test everything on current page for summary
        for name in all_keys:
            results[name] = await test_selector(page, name, SEL[name])

        passed = [k for k, v in results.items() if v]
        failed = [k for k, v in results.items() if not v]

        print(f"\n{GREEN}FOUND ({len(passed)}):{RESET} {', '.join(passed)}")
        print(f"{RED}NOT FOUND ({len(failed)}):{RESET} {', '.join(failed)}")

        print(f"\n{YELLOW}Browser stays open — inspect DevTools manually if needed.{RESET}")
        print("Press Enter to close.")
        input()

        await context.storage_state(path=str(SESSION_FILE))
        print("Session saved.")
        await browser.close()


async def _test_group(page, keys: list[str]) -> None:
    print()
    for name in keys:
        sel = SEL[name]
        found = await test_selector(page, name, sel)
        status = f"{GREEN}FOUND{RESET}" if found else f"{RED}MISSING{RESET}"
        print(f"  [{status}] {BOLD}{name}{RESET}")
        if not found:
            print(f"           selector: {sel}")
            await dump_dom_hint(page, name)
        print()


if __name__ == "__main__":
    asyncio.run(main())
