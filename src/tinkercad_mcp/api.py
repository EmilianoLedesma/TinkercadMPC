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
    Returns True if dropdown opened successfully."""
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

        # Playwright native mouse drag — more reliable than JS dispatchEvent
        await page.mouse.move(src_x, src_y)
        await page.mouse.down()
        await _random_delay(0.2, 0.3)
        # Move gradually so Tinkercad's drag handler tracks correctly
        await page.mouse.move(dst_x, dst_y, steps=15)
        await _random_delay(0.1, 0.2)
        await page.mouse.up()
        await _random_delay(0.5, 1.0)

        return json.dumps({
            "component": component_type,
            "search_term": search_term,
            "data_did": grid_bbox.get("dataDid"),
            "x": x, "y": y,
        })
    except Exception as exc:
        return f"Error adding component: {exc}"


async def connect_pins(comp_a: str, pin_a: str, comp_b: str, pin_b: str) -> str:
    """Connect two component pins with a wire.

    Tinkercad renders the circuit on an HTML5 canvas — pins are not standard DOM
    elements. Connection is done by clicking on the source pin position and
    dragging to the destination pin position (canvas pixel coordinates).

    To find pin coordinates:
    1. Call get_component_pin_positions(comp_id) to get a map of pin names → coords.
    2. Pass those coords here.

    Args:
        comp_a: Source component identifier (data-did, e.g. '58422' for LED)
        pin_a: Source pin name (e.g. 'Anode', 'Cathode', 'GND', 'D13')
        comp_b: Destination component identifier
        pin_b: Destination pin name
    """
    try:
        page = await _get_page()

        # Try to resolve pin positions via circuit_editor internal model
        pin_coords = await page.evaluate("""
            ([compA, pinA, compB, pinB]) => {
                try {
                    const root = window.circuit_editor?.root;
                    if (!root) return null;
                    // objectMap maps local IDs to circuit objects
                    // Components store pin positions in their data
                    // This requires deeper mapping — placeholder for now
                    return null;
                } catch(e) { return null; }
            }
        """, [comp_a, pin_a, comp_b, pin_b])

        if pin_coords:
            sx, sy = pin_coords["src"]["x"], pin_coords["src"]["y"]
            dx, dy = pin_coords["dst"]["x"], pin_coords["dst"]["y"]
        else:
            # Fallback: try SVG overlay elements (present in some Tinkercad versions)
            src_el = await page.query_selector(
                f"[data-did='{comp_a}'] [data-pin='{pin_a}'], "
                f"[data-component='{comp_a}'] [title='{pin_a}']"
            )
            dst_el = await page.query_selector(
                f"[data-did='{comp_b}'] [data-pin='{pin_b}'], "
                f"[data-component='{comp_b}'] [title='{pin_b}']"
            )

            if not src_el or not dst_el:
                return (
                    f"Error: Cannot resolve pin positions for "
                    f"'{comp_a}:{pin_a}' → '{comp_b}:{pin_b}'. "
                    "Use tinkercad_get_pin_positions to get canvas coordinates, "
                    "then call tinkercad_connect_pins_by_coords."
                )

            src_box = await src_el.bounding_box()
            dst_box = await dst_el.bounding_box()
            if not src_box or not dst_box:
                return "Error: Pin elements found but bounding boxes are zero."

            sx = src_box["x"] + src_box["width"] / 2
            sy = src_box["y"] + src_box["height"] / 2
            dx = dst_box["x"] + dst_box["width"] / 2
            dy = dst_box["y"] + dst_box["height"] / 2

        canvas = await page.query_selector(SEL["circuit_canvas"])
        if not canvas:
            return "Error: Circuit canvas not found."
        canvas_box = await canvas.bounding_box()
        if not canvas_box:
            return "Error: Could not get canvas bounding box."

        # Click source pin, drag to destination pin
        await page.mouse.move(canvas_box["x"] + sx, canvas_box["y"] + sy)
        await page.mouse.down()
        await _random_delay(0.1, 0.2)
        await page.mouse.move(
            canvas_box["x"] + dx,
            canvas_box["y"] + dy,
            steps=15,
        )
        await page.mouse.up()
        await _random_delay()

        return json.dumps({"wire": f"{comp_a}:{pin_a} → {comp_b}:{pin_b}"})
    except Exception as exc:
        return f"Error connecting pins: {exc}"


async def connect_pins_by_coords(
    src_x: float, src_y: float, dst_x: float, dst_y: float
) -> str:
    """Connect two pins using raw canvas pixel coordinates.

    Use this when you know the exact pixel positions of the pins on the canvas.
    Coordinates are relative to the canvas origin (top-left corner).

    Args:
        src_x, src_y: Source pin position on canvas
        dst_x, dst_y: Destination pin position on canvas
    """
    try:
        page = await _get_page()
        canvas = await page.query_selector(SEL["circuit_canvas"])
        if not canvas:
            return "Error: Circuit canvas not found. Is a circuit open?"

        canvas_box = await canvas.bounding_box()
        if not canvas_box:
            return "Error: Could not get canvas bounding box."

        ox, oy = canvas_box["x"], canvas_box["y"]

        await page.mouse.move(ox + src_x, oy + src_y)
        await page.mouse.down()
        await _random_delay(0.1, 0.2)
        await page.mouse.move(ox + dst_x, oy + dst_y, steps=15)
        await page.mouse.up()
        await _random_delay()

        return json.dumps({
            "wire": f"({src_x},{src_y}) → ({dst_x},{dst_y})",
        })
    except Exception as exc:
        return f"Error connecting pins by coords: {exc}"


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

        # Open code panel
        code_btn = await page.query_selector(SEL["btn_add_code"])
        if not code_btn:
            return "Error: Code button not found. Is a circuit open?"
        await code_btn.click()
        await _random_delay(0.5, 1.0)

        # Set code via CodeMirror JS API — faster and more reliable than typing
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
            return "Error: CodeMirror editor not found in code panel."

        await _random_delay(0.3, 0.6)
        return f"Sketch set for Arduino '{comp_id or 'selected'}' ({len(sketch)} chars)."
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
