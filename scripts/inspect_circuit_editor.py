"""
Inspect circuit editor DOM to verify/discover real selectors.

Usage:
    .venv/Scripts/python.exe scripts/inspect_circuit_editor.py

Opens the Semáforo circuit (or first available circuit) in headed mode,
waits for it to load, then prints all selector results and dumps
relevant DOM sections for any that are missing.
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ["TINKERCAD_HEADLESS"] = "false"

from playwright.async_api import async_playwright
from tinkercad_mcp.utils import SEL, SESSION_FILE, TINKERCAD_BASE, USER_AGENT

GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

CIRCUIT_EDIT_URL = f"{TINKERCAD_BASE}/things/er6MjDHxvna-semaforo/editel"


async def main() -> None:
    async with async_playwright() as p:
        storage = str(SESSION_FILE) if SESSION_FILE.exists() else None

        browser = await p.chromium.launch(headless=False, args=["--no-sandbox"])
        context = await browser.new_context(
            storage_state=storage,
            user_agent=USER_AGENT,
            viewport={"width": 1600, "height": 900},
        )
        page = await context.new_page()

        print(f"\n{BOLD}Opening circuit editor...{RESET}")
        await page.goto(CIRCUIT_EDIT_URL, wait_until="networkidle", timeout=60_000)

        # Give Angular time to render
        await asyncio.sleep(3)

        print(f"\n{BOLD}=== CIRCUIT EDITOR SELECTORS ==={RESET}\n")

        result = await page.evaluate("""
        () => {
            const info = el => el ? {
                tag: el.tagName,
                id: el.id || null,
                classes: Array.from(el.classList),
                text: el.innerText?.trim().slice(0, 80),
                ariaLabel: el.getAttribute('aria-label'),
                title: el.getAttribute('title'),
                placeholder: el.getAttribute('placeholder'),
                type: el.getAttribute('type'),
                html: el.outerHTML.slice(0, 300),
            } : null;

            // Canvas
            const canvases = Array.from(document.querySelectorAll('canvas')).map(info);

            // All buttons
            const buttons = Array.from(document.querySelectorAll('button')).map(b => ({
                text: b.innerText?.trim().slice(0, 60),
                title: b.getAttribute('title'),
                ariaLabel: b.getAttribute('aria-label'),
                id: b.id || null,
                classes: Array.from(b.classList),
            })).filter(b => b.text || b.title || b.ariaLabel);

            // All inputs
            const inputs = Array.from(document.querySelectorAll('input, textarea')).map(info);

            // Simulation controls area
            const simArea = info(document.querySelector(
                '[class*="simulation"], [class*="Simulation"], [id*="simulation"]'
            ));

            // Search input for components
            const searchInput = info(document.querySelector(
                'input[placeholder*="Search"], input[placeholder*="search"], input[type="search"]'
            ));

            // Serial monitor
            const serialEl = info(document.querySelector(
                '[class*="serial"], [class*="Serial"], [id*="serial"]'
            ));

            // Toolbar / top bar
            const toolbar = info(document.querySelector(
                '[class*="toolbar"], [class*="Toolbar"], [class*="top-bar"], [id*="toolbar"]'
            ));

            // Design name input
            const nameInput = info(document.querySelector(
                'input[name="name"], input[placeholder*="name"], [class*="design-name"] input, [contenteditable]'
            ));

            // All links with href containing things
            const thingLinks = Array.from(document.querySelectorAll('a[href*="/things/"]')).map(a => ({
                href: a.href, text: a.innerText?.trim().slice(0,40), classes: Array.from(a.classList)
            })).slice(0, 5);

            return {
                url: window.location.href,
                canvases, buttons, inputs,
                simArea, searchInput, serialEl, toolbar, nameInput, thingLinks,
            };
        }
        """)

        print(f"URL: {result['url']}\n")

        print(f"{BOLD}Canvas elements ({len(result['canvases'])}):{RESET}")
        for c in result['canvases']:
            print(f"  id={c['id']} classes={c['classes']} html={c['html'][:150]}")

        print(f"\n{BOLD}Buttons ({len(result['buttons'])}):{RESET}")
        for b in result['buttons']:
            print(f"  [{b.get('id','')}] title={b['title']} aria={b['ariaLabel']} text={b['text']} cls={b['classes'][:3]}")

        print(f"\n{BOLD}Inputs ({len(result['inputs'])}):{RESET}")
        for inp in result['inputs']:
            print(f"  tag={inp['tag']} id={inp['id']} placeholder={inp['placeholder']} type={inp['type']} cls={inp['classes']}")

        print(f"\n{BOLD}Simulation area:{RESET} {json.dumps(result['simArea'], indent=2)}")
        print(f"\n{BOLD}Search input:{RESET} {json.dumps(result['searchInput'], indent=2)}")
        print(f"\n{BOLD}Serial element:{RESET} {json.dumps(result['serialEl'], indent=2)}")
        print(f"\n{BOLD}Toolbar:{RESET} {json.dumps(result['toolbar'], indent=2)}")
        print(f"\n{BOLD}Name input:{RESET} {json.dumps(result['nameInput'], indent=2)}")

        print(f"\n{YELLOW}Browser open — inspect DevTools (F12) for more detail.{RESET}")
        print("Press Enter to close.")
        input()

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
