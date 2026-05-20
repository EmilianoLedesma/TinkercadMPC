"""Domain logic for all Tinkercad MCP tools.

Organized in three sections:
  1. Session management
  2. 3D designs
  3. Circuits + simulation
"""

import asyncio
import json
import logging
import random
import re
from typing import Any

import httpx
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from tinkercad_mcp.browser import BrowserManager
from tinkercad_mcp.utils import (
    COMPONENT_CATALOG,
    SEL,
    SHAPE_TYPES,
    TINKERCAD_BASE,
    TINKERCAD_CIRCUIT_EDIT_SUFFIX,
    TINKERCAD_DASHBOARD,
    TINKERCAD_LOGIN,
)

logger = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_page() -> Page:
    mgr = await BrowserManager.get_instance()
    return await mgr.get_page()


async def _random_delay(lo: float = 0.3, hi: float = 0.9) -> None:
    """Small random pause to reduce bot-detection risk."""
    await asyncio.sleep(random.uniform(lo, hi))


async def _is_logged_in(page: Page) -> bool:
    try:
        el = await page.query_selector(SEL["user_avatar"])
        return el is not None
    except Exception:
        return False


async def _navigate(page: Page, url: str, *, wait: str = "load", timeout: int = 60_000) -> None:
    await page.goto(url, wait_until=wait, timeout=timeout)
    await _random_delay()


# ── 1. Session ────────────────────────────────────────────────────────────────


async def login() -> str:
    """Authenticate with Tinkercad.

    - If a valid session exists: returns status without opening browser.
    - First run or expired session: opens Chromium in headed mode so the user
      can complete Autodesk OAuth manually, then saves the cookies.
    """
    mgr = await BrowserManager.get_instance()

    # Try silent login first (existing session)
    page = await mgr.get_page()
    await _navigate(page, TINKERCAD_DASHBOARD)

    if await _is_logged_in(page):
        return "Session already active — no login needed."

    # Need manual auth: reopen headed
    page = await mgr.relaunch_headed()
    await _navigate(page, TINKERCAD_LOGIN, wait="domcontentloaded")

    try:
        # Wait up to 3 min for the user to complete Autodesk OAuth
        await page.wait_for_url(f"{TINKERCAD_BASE}/dashboard**", timeout=180_000)
    except PlaywrightTimeout:
        return "Login timed out (3 min). Please try again."

    await mgr.save_session()
    return "Login successful. Session saved to ~/.tinkercad_mcp/session.json"


async def logout() -> str:
    """End the current session and clear saved cookies."""
    mgr = await BrowserManager.get_instance()
    await mgr.clear_session()
    await mgr.close()
    return "Logged out. Session cleared."


async def get_session_status() -> str:
    """Check whether the current session is valid."""
    try:
        page = await _get_page()
        await _navigate(page, TINKERCAD_DASHBOARD)
        if await _is_logged_in(page):
            name_el = await page.query_selector(SEL["user_name"])
            name = (await name_el.inner_text()).strip() if name_el else "unknown"
            return f"Session active. User: {name}"
        return "Session invalid or expired. Call tinkercad_login first."
    except Exception as exc:
        return f"Error checking session: {exc}"


# ── 2. 3D Designs ─────────────────────────────────────────────────────────────


async def _list_items_from_dashboard(url: str, item_key: str) -> list[dict]:
    """Shared logic for list_designs and list_circuits."""
    page = await _get_page()
    await _navigate(page, url)
    await _random_delay(0.5, 1.0)

    cards = await page.query_selector_all(SEL["design_cards"])
    items = []
    for card in cards:
        # Title: <h3> inside tk-thing-box (no class)
        title_el = await card.query_selector("h3")
        title = (await title_el.inner_text()).strip() if title_el else "Untitled"

        # ID: from thumbnail div id="thumbnail-{id}" or from href
        thumb = await card.query_selector(SEL["design_card_thumb"])
        design_id = ""
        if thumb:
            thumb_id = await thumb.get_attribute("id") or ""
            design_id = thumb_id.replace("thumbnail-", "")
        if not design_id:
            link = await card.query_selector("a[href*='/things/']")
            if link:
                href = await link.get_attribute("href") or ""
                m = re.search(r"/things/([^/-]+)", href)
                design_id = m.group(1) if m else ""

        items.append({"id": design_id, "name": title})
    return items


async def list_designs() -> str:
    """Return all 3D designs on the user's dashboard as JSON."""
    try:
        items = await _list_items_from_dashboard(
            f"{TINKERCAD_BASE}/dashboard/designs/3d", "designs"
        )
        return json.dumps({"count": len(items), "designs": items}, indent=2)
    except Exception as exc:
        return f"Error listing designs: {exc}"


async def _open_create_dropdown(page) -> bool:
    """Click the '+Create' button to open the type-selection dropdown.
    Waits up to 15s for Angular to render the button. Returns True on success."""
    try:
        await page.wait_for_selector(SEL["btn_create_dropdown"], timeout=15_000)
    except Exception:
        return False
    btn = await page.query_selector(SEL["btn_create_dropdown"])
    if not btn:
        return False
    await btn.click()
    await _random_delay(0.3, 0.6)
    return True


async def create_3d_design(name: str) -> str:
    """Create a new blank 3D design with the given name."""
    try:
        page = await _get_page()
        await _navigate(page, f"{TINKERCAD_BASE}/dashboard/designs")

        if not await _open_create_dropdown(page):
            return "Error: '+Create' button not found. Make sure you're logged in."

        btn = await page.query_selector(SEL["btn_create_design"])
        if not btn:
            return "Error: '3D Design' option not found in Create dropdown."
        await btn.click()

        # Wait for 3D editor to load
        await page.wait_for_url(f"{TINKERCAD_BASE}/things/**", timeout=30_000)
        await _random_delay(1.5, 2.5)

        # Rename via editor title input
        name_input = await page.query_selector(SEL["design_name_input"])
        if name_input:
            await name_input.click(click_count=3)
            await name_input.fill(name)
            await page.keyboard.press("Enter")
            await _random_delay()

        url = page.url
        m = re.search(r"/things/([^/-]+)", url)
        design_id = m.group(1) if m else "unknown"

        return json.dumps({"id": design_id, "name": name, "url": url})
    except Exception as exc:
        return f"Error creating design: {exc}"


async def add_shape(
    shape_type: str,
    x: float,
    y: float,
    z: float,
    width: float,
    height: float,
    depth: float,
) -> str:
    """Add a primitive shape to the currently open 3D design.

    Uses page.evaluate() to call Tinkercad's internal JS API.
    The exact function names must be verified by inspecting the editor's
    JavaScript bundle (window.TC or similar namespace).

    Args:
        shape_type: One of box, sphere, cylinder, cone, torus, wedge, pyramid
        x, y, z: Position in mm
        width, height, depth: Dimensions in mm
    """
    if shape_type not in SHAPE_TYPES:
        return f"Error: Unknown shape '{shape_type}'. Valid: {sorted(SHAPE_TYPES)}"
    try:
        page = await _get_page()

        # Attempt via Tinkercad JS API (requires reverse-engineering the bundle)
        result = await page.evaluate(
            """
            ([type, x, y, z, w, h, d]) => {
                // TODO: Replace with actual Tinkercad internal API calls.
                // Inspect window object in the editor to find the correct namespace.
                // Common patterns: window.TC, window.Editor, window.app
                if (typeof window.__tinkercadAddShape === 'function') {
                    return window.__tinkercadAddShape(type, x, y, z, w, h, d);
                }
                return null;
            }
            """,
            [shape_type, x, y, z, width, height, depth],
        )

        if result:
            return json.dumps({"shape_id": result, "type": shape_type, "x": x, "y": y, "z": z})

        # Fallback: XHR replay (requires intercepting editor XHR first)
        # See docs/xhr_interception.md for capture instructions
        return (
            "Shape API not yet mapped for this Tinkercad version. "
            "Open the editor in headed mode, add a shape manually while "
            "recording network requests, then update api.py with the XHR endpoint."
        )
    except Exception as exc:
        return f"Error adding shape: {exc}"


async def group_shapes(shape_ids: list[str]) -> str:
    """Group multiple shapes into one object.

    Requires XHR interception or JS API — see add_shape notes.
    """
    if not shape_ids:
        return "Error: shape_ids list is empty."
    try:
        page = await _get_page()
        result = await page.evaluate(
            """
            (ids) => {
                if (typeof window.__tinkercadGroupShapes === 'function') {
                    return window.__tinkercadGroupShapes(ids);
                }
                return null;
            }
            """,
            shape_ids,
        )
        if result:
            return json.dumps({"group_id": result, "shapes": shape_ids})
        return "group_shapes: JS API not yet mapped. Needs XHR capture — see add_shape."
    except Exception as exc:
        return f"Error grouping shapes: {exc}"


async def export_stl(design_id: str) -> str:
    """Export a design as STL by navigating to its page and clicking Export."""
    try:
        page = await _get_page()
        # Circuits use /editel, 3D designs use /edit — try editel first, fall back
        await _navigate(page, f"{TINKERCAD_BASE}/things/{design_id}/{TINKERCAD_CIRCUIT_EDIT_SUFFIX}")
        await _random_delay(1.5, 2.5)

        btn_export = await page.query_selector(SEL["btn_export"])
        if not btn_export:
            return f"Error: Export button not found on design {design_id}."
        await btn_export.click()
        await _random_delay()

        btn_stl = await page.query_selector(SEL["btn_export_stl"])
        if not btn_stl:
            return "Error: STL option not found in export dialog."
        await btn_stl.click()
        await _random_delay(1.0, 2.0)

        return f"STL export triggered for design {design_id}. Check your browser downloads."
    except Exception as exc:
        return f"Error exporting STL: {exc}"


async def delete_design(design_id: str) -> str:
    """Delete a 3D design by ID."""
    try:
        page = await _get_page()
        await _navigate(page, f"{TINKERCAD_BASE}/dashboard/designs")

        # Find card by thumbnail id="thumbnail-{design_id}"
        card = await page.query_selector(f"#thumbnail-{design_id}")
        if not card:
            return f"Error: Design {design_id} not found on dashboard."

        # Hover to reveal the card menu button
        await card.hover()
        await _random_delay()

        # Per-card "Design actions" gear button → click to open dropdown
        card_box = await card.evaluate_handle("el => el.closest('tk-thing-box')")
        menu_btn = await card_box.query_selector(SEL["btn_card_menu"])
        if not menu_btn:
            return f"Error: Design actions button not found for design {design_id}."
        await menu_btn.click()
        await _random_delay(0.3, 0.6)

        # Click Delete item in dropdown
        delete_item = await page.query_selector(SEL["btn_delete_design"])
        if not delete_item:
            return f"Error: Delete option not found in dropdown for design {design_id}."
        await delete_item.click()
        await _random_delay()

        # Confirm delete modal
        confirm = await page.query_selector(SEL["btn_confirm_delete"])
        if confirm:
            await confirm.click()

        await _random_delay()
        return f"Design {design_id} deleted."
    except Exception as exc:
        return f"Error deleting design: {exc}"


# ── 3. Circuits ───────────────────────────────────────────────────────────────


async def list_circuits() -> str:
    """Return all circuits on the user's dashboard as JSON."""
    try:
        items = await _list_items_from_dashboard(
            f"{TINKERCAD_BASE}/dashboard/designs/circuits", "circuits"
        )
        return json.dumps({"count": len(items), "circuits": items}, indent=2)
    except Exception as exc:
        return f"Error listing circuits: {exc}"


async def create_circuit(name: str) -> str:
    """Create a new blank circuit."""
    try:
        page = await _get_page()
        await _navigate(page, f"{TINKERCAD_BASE}/dashboard/designs")

        if not await _open_create_dropdown(page):
            return "Error: '+Create' button not found. Make sure you're logged in."

        btn = await page.query_selector(SEL["btn_create_circuit"])
        if not btn:
            return "Error: 'Circuits' option not found in Create dropdown."
        await btn.click()
        await page.wait_for_url(f"{TINKERCAD_BASE}/things/**", timeout=30_000)
        await _random_delay(1.0, 2.0)

        # Rename via circuit title — click span to activate input
        title_span = await page.query_selector(SEL["circuit_title_span"])
        if title_span:
            await title_span.click()
            await _random_delay(0.3, 0.5)
            name_input = await page.query_selector(SEL["circuit_title_input"])
            if name_input:
                await name_input.click(click_count=3)
                await name_input.fill(name)
                await page.keyboard.press("Enter")
                await _random_delay()

        url = page.url
        m = re.search(r"/things/([^/-]+)", url)
        circuit_id = m.group(1) if m else "unknown"

        return json.dumps({"id": circuit_id, "name": name, "url": url})
    except Exception as exc:
        return f"Error creating circuit: {exc}"


async def add_component(component_type: str, x: float, y: float) -> str:
    """Add a component to the open circuit by searching the parts panel and dragging.

    Args:
        component_type: Key from COMPONENT_CATALOG (e.g. 'arduino_uno', 'led')
        x, y: Drop position relative to canvas origin (pixels)
    """
    search_term = COMPONENT_CATALOG.get(component_type)
    if search_term is None:
        valid = ", ".join(sorted(COMPONENT_CATALOG.keys()))
        return f"Error: Unknown component '{component_type}'. Valid keys: {valid}"

    try:
        page = await _get_page()

        # Type in component search box (id="q")
        search = await page.query_selector(SEL["component_search"])
        if not search:
            return "Error: Component search panel not found. Is a circuit open?"
        await search.click()
        # Use page.fill (Locator-based) to reliably type + trigger autocomplete events
        await page.fill(SEL["component_search"], search_term)
        await _random_delay(0.5, 1.0)

        # Click the autocomplete item that exactly matches search_term (case-insensitive)
        # First item is not always the right one (e.g. "photoresistor" before "resistor")
        exact_item = await page.evaluate(
            """
            (term) => {
                const items = document.querySelectorAll('ul.ui-autocomplete li.ui-menu-item');
                const t = term.toLowerCase();
                for (const li of items) {
                    if (li.innerText.trim().toLowerCase() === t) {
                        li.click();
                        return true;
                    }
                }
                // Fallback: click first item if no exact match
                if (items.length > 0) { items[0].click(); return 'fallback'; }
                return false;
            }
            """,
            search_term.lower(),
        )
        if not exact_item:
            return f"Error: No autocomplete results for '{search_term}'. Check spelling."
        await _random_delay(0.4, 0.7)

        # Get first VISIBLE grid item bounding box via JS (hidden items have bbox 0,0)
        grid_bbox = await page.evaluate("""
            () => {
                const items = document.querySelectorAll(
                    'div.editor__component_picker__groups__item.grid__item'
                );
                for (const el of items) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) {
                        return { x: r.x, y: r.y, width: r.width, height: r.height,
                                 dataDid: el.getAttribute('data-did') };
                    }
                }
                return null;
            }
        """)
        if not grid_bbox:
            return f"Error: No visible component grid item for '{search_term}'."

        canvas = await page.query_selector(SEL["circuit_canvas"])
        if not canvas:
            return "Error: Circuit canvas not found. Is a circuit open?"

        canvas_box = await canvas.bounding_box()
        if not canvas_box:
            return "Error: Could not get canvas bounding box."

        src_x = grid_bbox["x"] + grid_bbox["width"] / 2
        src_y = grid_bbox["y"] + grid_bbox["height"] / 2
        dst_x = canvas_box["x"] + x
        dst_y = canvas_box["y"] + y

        # Playwright native mouse drag
        await page.mouse.move(src_x, src_y)
        await page.mouse.down()
        await _random_delay(0.2, 0.3)
        await page.mouse.move(dst_x, dst_y, steps=15)
        await _random_delay(0.1, 0.2)
        await page.mouse.up()
        await _random_delay(0.5, 1.0)

        # Press Escape immediately after drop to deselect the component.
        # This prevents Tinkercad from auto-panning to follow the new component,
        # keeping subsequent drop coordinates stable.
        await page.keyboard.press("Escape")
        await _random_delay(0.2, 0.3)

        return json.dumps({
            "component": component_type,
            "search_term": search_term,
            "data_did": grid_bbox.get("dataDid"),
            "x": x, "y": y,
        })
    except Exception as exc:
        return f"Error adding component: {exc}"


def get_wiring_diagram(
    circuit_name: str,
    connections: list[dict],
    notes: str = "",
) -> str:
    """Generate a human-readable wiring diagram + step-by-step instructions.

    This is a pure-Python helper — no browser required.
    The LLM calls this with the planned circuit topology to produce clear
    instructions the user can follow to connect wires manually in Tinkercad.

    Args:
        circuit_name: Name of the circuit (e.g. 'LED Blink')
        connections: List of connection dicts, each with keys:
            - from_component: str  (e.g. 'Arduino Uno')
            - from_pin: str        (e.g. 'D13', 'GND', '5V')
            - to_component: str    (e.g. 'Breadboard', 'LED')
            - to_pin: str          (e.g. 'e5', 'Anode', 'pwr_top_pos1')
            - wire_color: str      (optional, e.g. 'green', 'black', 'red')
            - note: str            (optional, e.g. 'same strip as e5')
        notes: Optional extra notes appended at the end.

    Returns:
        str: Formatted wiring guide with ASCII legend and numbered steps.
    """
    lines = []
    lines.append("=" * 56)
    lines.append(f"  WIRING GUIDE: {circuit_name}")
    lines.append("=" * 56)

    # Breadboard notation legend
    lines.append("""
BREADBOARD NOTATION:
  Rows a-e  : top half  (all holes in same column = connected)
  Rows f-j  : bottom half (same rule)
  pwr_top_+/- : top power rails  (+5V / GND)
  pwr_bot_+/- : bottom power rails (+5V / GND)
  e.g. 'e5' = row e, column 5

TIP: holes in the SAME COLUMN and SAME HALF are electrically
     connected WITHOUT a wire (that's how breadboards work).
""")

    lines.append("CONNECTIONS (wire each step in order):")
    lines.append("-" * 56)

    for i, conn in enumerate(connections, 1):
        frm  = conn.get("from_component", "?")
        fpin = conn.get("from_pin", "?")
        to   = conn.get("to_component", "?")
        tpin = conn.get("to_pin", "?")
        color = conn.get("wire_color", "")
        note  = conn.get("note", "")

        color_tag = f"[{color} wire]" if color else ""
        note_tag  = f"  ← {note}"    if note  else ""

        lines.append(
            f"  {i:2d}. {frm} {fpin:10s} →  {to} {tpin:15s} {color_tag}{note_tag}"
        )

    if notes:
        lines.append("")
        lines.append("NOTES:")
        lines.append(f"  {notes}")

    lines.append("=" * 56)
    return "\n".join(lines)


async def add_code_to_arduino(comp_id: str, sketch: str) -> str:
    """Set Arduino sketch code via the Code panel's CodeMirror editor.

    The circuit editor uses CodeMirror for code editing.
    We open the code panel (a#CODE_EDITOR_ID) and set the value via
    the CodeMirror JS API rather than typing, which is faster and reliable.

    Args:
        comp_id: Arduino component label shown in the Code panel dropdown
                 (e.g. '1' for '1 (Arduino Uno R3)'). Pass '' to use
                 whichever Arduino is currently selected.
        sketch: Full Arduino C++ sketch source code
    """
    try:
        page = await _get_page()

        # Step 1: open code panel
        code_btn = await page.query_selector(SEL["btn_add_code"])
        if not code_btn:
            return "Error: Code button not found. Is a circuit open?"
        await code_btn.click()
        await _random_delay(0.8, 1.2)

        # Step 2: switch from Blocks to Text mode if needed.
        # The mode dropdown shows current mode (e.g. "Blocks"). Click it, select "Text".
        mode_switched = await page.evaluate("""
            async () => {
                // Check current mode
                const modeBtn = document.querySelector(
                    '.code_panel__toolbar__mode .editor__dropdown__button, '
                    + '.code_panel__toolbar__dropdown .editor__dropdown__button'
                );
                if (!modeBtn) return 'no_mode_btn';
                const currentMode = modeBtn.innerText?.trim().toLowerCase();
                if (currentMode === 'text') return 'already_text';

                // Open the dropdown
                modeBtn.click();
                await new Promise(r => setTimeout(r, 400));

                // Click the "Text" option
                const opts = Array.from(document.querySelectorAll(
                    '.editor__dropdown__list__option__value'
                ));
                const textOpt = opts.find(o => o.innerText?.trim().toLowerCase() === 'text');
                if (!textOpt) return 'no_text_option';
                textOpt.click();
                await new Promise(r => setTimeout(r, 600));

                // Confirm the "Are you sure?" dialog if it appears
                const continueBtn = Array.from(document.querySelectorAll('button'))
                    .find(b => b.innerText?.trim().toLowerCase() === 'continue');
                if (continueBtn) {
                    continueBtn.click();
                    await new Promise(r => setTimeout(r, 500));
                    return 'switched_with_confirm';
                }
                return 'switched';
            }
        """)
        logger.info("Code mode switch: %s", mode_switched)
        await _random_delay(0.5, 1.0)

        # Step 3: set code via CodeMirror JS API
        escaped = sketch.replace("\\", "\\\\").replace("`", "\\`")
        result = await page.evaluate(f"""
            () => {{
                const cm = document.querySelector('.CodeMirror')?.CodeMirror;
                if (!cm) return 'no_cm';
                cm.setValue(`{escaped}`);
                cm.save();
                return 'ok';
            }}
        """)

        if result == "no_cm":
            return (
                "Error: CodeMirror editor not found after mode switch "
                f"(mode_switch={mode_switched}). Try again."
            )

        await _random_delay(0.3, 0.6)
        return (
            f"Sketch set for Arduino '{comp_id or 'selected'}' "
            f"({len(sketch)} chars). Mode: {mode_switched}."
        )
    except Exception as exc:
        return f"Error setting sketch: {exc}"


async def start_simulation() -> str:
    """Start the circuit simulation."""
    try:
        page = await _get_page()
        btn = await page.query_selector(SEL["btn_start_sim"])
        if not btn:
            return "Error: Start Simulation button not found. Is a circuit open?"
        # Verify it's not already running
        btn_text = await btn.inner_text()
        if "Stop" in btn_text:
            return "Simulation already running."
        await btn.click()
        await _random_delay()
        return "Simulation started."
    except Exception as exc:
        return f"Error starting simulation: {exc}"


async def stop_simulation() -> str:
    """Stop the circuit simulation."""
    try:
        page = await _get_page()
        btn = await page.query_selector(SEL["btn_stop_sim"])
        if not btn:
            return "Error: Stop Simulation button not found. Is a circuit open?"
        btn_text = await btn.inner_text()
        if "Start" in btn_text:
            return "Simulation not running."
        await btn.click()
        await _random_delay()
        return "Simulation stopped."
    except Exception as exc:
        return f"Error stopping simulation: {exc}"


async def get_simulation_output() -> str:
    """Read the Arduino Serial Monitor output from the running simulation."""
    try:
        page = await _get_page()

        # Ensure serial monitor is open (click toggle if panel collapsed)
        serial_btn = await page.query_selector(SEL["btn_serial_monitor"])
        if serial_btn:
            panel = await page.query_selector(SEL["serial_monitor"])
            if panel:
                style = await panel.get_attribute("style") or ""
                # Open if panel height is collapsed (Tinkercad uses inline height)
                if "31px" in style:
                    await serial_btn.click()
                    await _random_delay(0.3, 0.6)

        output_el = await page.query_selector(SEL["serial_output"])
        if not output_el:
            return "Error: Serial output area not found. Start simulation first."

        text = (await output_el.inner_text()).strip()
        if not text:
            return "Serial monitor is empty (simulation may not be running or Arduino is not printing)."

        return json.dumps({"output": text})
    except Exception as exc:
        return f"Error reading simulation output: {exc}"
