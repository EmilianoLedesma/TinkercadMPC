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


async def _navigate(page: Page, url: str, *, wait: str = "networkidle") -> None:
    await page.goto(url, wait_until=wait)
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
            await name_input.triple_click()
            await name_input.type(name)
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
        await _navigate(page, f"{TINKERCAD_BASE}/things/{design_id}/edit")
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

        name_input = await page.query_selector(SEL["design_name_input"])
        if name_input:
            await name_input.triple_click()
            await name_input.type(name)
            await page.keyboard.press("Enter")
            await _random_delay()

        url = page.url
        m = re.search(r"/things/([^/]+)", url)
        circuit_id = m.group(1) if m else "unknown"

        return json.dumps({"id": circuit_id, "name": name, "url": url})
    except Exception as exc:
        return f"Error creating circuit: {exc}"


async def add_component(component_type: str, x: float, y: float) -> str:
    """Add a component to the open circuit by searching the parts panel.

    Args:
        component_type: Key from COMPONENT_CATALOG (e.g. 'arduino_uno', 'led')
        x, y: Drop position on the circuit canvas (pixels)
    """
    search_term = COMPONENT_CATALOG.get(component_type)
    if search_term is None:
        valid = ", ".join(sorted(COMPONENT_CATALOG.keys()))
        return f"Error: Unknown component '{component_type}'. Valid keys: {valid}"

    try:
        page = await _get_page()

        search = await page.query_selector(SEL["component_search"])
        if not search:
            return "Error: Component search panel not found. Is a circuit open?"
        await search.click()
        await search.fill(search_term)
        await _random_delay()

        # Click first result in the component list
        first_result = await page.query_selector("[class*='component-item']:first-child, [data-testid='component-item']")
        if not first_result:
            return f"Error: No results found for '{search_term}'."

        # Drag component onto canvas
        canvas = await page.query_selector(SEL["circuit_canvas"])
        if not canvas:
            return "Error: Circuit canvas not found."

        canvas_box = await canvas.bounding_box()
        if not canvas_box:
            return "Error: Could not get canvas bounds."

        target_x = canvas_box["x"] + x
        target_y = canvas_box["y"] + y

        result_box = await first_result.bounding_box()
        if not result_box:
            return "Error: Could not get component bounds."

        await page.mouse.move(result_box["x"] + result_box["width"] / 2, result_box["y"] + result_box["height"] / 2)
        await page.mouse.down()
        await _random_delay(0.2, 0.4)
        await page.mouse.move(target_x, target_y)
        await page.mouse.up()
        await _random_delay()

        return json.dumps({"component": component_type, "search_term": search_term, "x": x, "y": y})
    except Exception as exc:
        return f"Error adding component: {exc}"


async def connect_pins(comp_a: str, pin_a: str, comp_b: str, pin_b: str) -> str:
    """Connect two component pins with a wire.

    Args:
        comp_a: Component A selector or identifier
        pin_a: Pin name/label on component A (e.g. '~5V', 'GND', 'D13')
        comp_b: Component B selector or identifier
        pin_b: Pin name/label on component B
    """
    try:
        page = await _get_page()

        # Locate source pin
        src_pin = await page.query_selector(
            f"[data-component='{comp_a}'] [data-pin='{pin_a}'], "
            f"[data-id='{comp_a}'] [title='{pin_a}']"
        )
        if not src_pin:
            return f"Error: Pin '{pin_a}' not found on component '{comp_a}'."

        dst_pin = await page.query_selector(
            f"[data-component='{comp_b}'] [data-pin='{pin_b}'], "
            f"[data-id='{comp_b}'] [title='{pin_b}']"
        )
        if not dst_pin:
            return f"Error: Pin '{pin_b}' not found on component '{comp_b}'."

        src_box = await src_pin.bounding_box()
        dst_box = await dst_pin.bounding_box()
        if not src_box or not dst_box:
            return "Error: Could not get pin positions."

        sx = src_box["x"] + src_box["width"] / 2
        sy = src_box["y"] + src_box["height"] / 2
        dx = dst_box["x"] + dst_box["width"] / 2
        dy = dst_box["y"] + dst_box["height"] / 2

        await page.mouse.move(sx, sy)
        await page.mouse.down()
        await _random_delay(0.1, 0.3)
        await page.mouse.move(dx, dy)
        await page.mouse.up()
        await _random_delay()

        return json.dumps({"wire": f"{comp_a}:{pin_a} → {comp_b}:{pin_b}"})
    except Exception as exc:
        return f"Error connecting pins: {exc}"


async def add_code_to_arduino(comp_id: str, sketch: str) -> str:
    """Upload an Arduino sketch (C++) to a simulated Arduino component.

    Args:
        comp_id: The Arduino component's identifier on the canvas
        sketch: Full Arduino C++ sketch source code
    """
    try:
        page = await _get_page()

        # Click on the Arduino component
        arduino = await page.query_selector(
            f"[data-id='{comp_id}'], [data-component='{comp_id}']"
        )
        if not arduino:
            return f"Error: Arduino component '{comp_id}' not found."
        await arduino.double_click()
        await _random_delay()

        btn_code = await page.query_selector(SEL["btn_add_code"])
        if not btn_code:
            return "Error: Code editor button not found."
        await btn_code.click()
        await _random_delay(0.5, 1.0)

        editor = await page.query_selector(SEL["code_editor"])
        if not editor:
            return "Error: Code editor text area not found."

        # Select all existing code and replace
        await editor.click()
        await page.keyboard.press("Control+A")
        await editor.type(sketch)
        await _random_delay()

        upload = await page.query_selector(SEL["btn_upload_code"])
        if upload:
            await upload.click()
            await _random_delay(0.5, 1.0)

        return f"Sketch uploaded to Arduino '{comp_id}' ({len(sketch)} chars)."
    except Exception as exc:
        return f"Error uploading sketch: {exc}"


async def start_simulation() -> str:
    """Start the circuit simulation."""
    try:
        page = await _get_page()
        btn = await page.query_selector(SEL["btn_start_sim"])
        if not btn:
            return "Error: Start Simulation button not found. Is a circuit open?"
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
            return "Error: Stop Simulation button not found. Is simulation running?"
        await btn.click()
        await _random_delay()
        return "Simulation stopped."
    except Exception as exc:
        return f"Error stopping simulation: {exc}"


async def get_simulation_output() -> str:
    """Read the Arduino Serial Monitor output from the running simulation."""
    try:
        page = await _get_page()
        monitor = await page.query_selector(SEL["serial_monitor"])
        if not monitor:
            return "Error: Serial monitor not found. Start simulation first."

        output_el = await monitor.query_selector(SEL["serial_output"])
        if not output_el:
            return "Error: Serial output area not found inside monitor."

        text = (await output_el.inner_text()).strip()
        if not text:
            return "Serial monitor is empty (simulation may not be running or Arduino is not printing)."

        return json.dumps({"output": text})
    except Exception as exc:
        return f"Error reading simulation output: {exc}"
