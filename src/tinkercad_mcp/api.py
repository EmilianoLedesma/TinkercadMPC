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
    """Connect two pins/holes using canvas pixel coordinates.

    Uses jQuery two-click wire drawing: click src → move → click dst.
    Coordinates are canvas-relative (origin = canvas top-left corner).

    Args:
        src_x, src_y: Source position on canvas (pixels from canvas origin)
        dst_x, dst_y: Destination position on canvas (pixels from canvas origin)
    """
    try:
        page = await _get_page()

        result = await page.evaluate(
            """
            async ([sx, sy, dx, dy]) => {
                const canvas = document.querySelector('canvas.js-tpl-target__render-canvas');
                if (!canvas) return { error: 'no canvas' };
                const cr = canvas.getBoundingClientRect();

                const fire = (el, type, x, y) => {
                    if (!el) return;
                    jQuery(el).trigger(jQuery.Event(type, {
                        clientX: x, clientY: y, pageX: x, pageY: y, which: 1, button: 0
                    }));
                };

                // Find nearest SVG rect/circle with mousedown handler to a screen point.
                // This tolerates small view shifts after prior wires.
                const findNearestPin = (targetScreenX, targetScreenY, radiusPx = 20) => {
                    const allPins = Array.from(document.querySelectorAll('svg rect, svg circle'))
                        .filter(el => {
                            try { return Object.keys(jQuery._data(el, 'events') || {}).includes('mousedown'); }
                            catch(e) { return false; }
                        });
                    let best = null, bestDist = Infinity;
                    for (const el of allPins) {
                        const r = el.getBoundingClientRect();
                        if (r.width === 0) continue;
                        const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
                        const d = Math.hypot(cx - targetScreenX, cy - targetScreenY);
                        if (d < bestDist && d <= radiusPx) { best = el; bestDist = d; }
                    }
                    return best;
                };

                // Canvas-relative → screen coords
                const ssx = cr.x + sx, ssy = cr.y + sy;
                const dsx = cr.x + dx, dsy = cr.y + dy;

                // ESC to cancel any in-progress wire
                document.dispatchEvent(new KeyboardEvent('keydown', { keyCode: 27, bubbles: true }));
                await new Promise(r => setTimeout(r, 200));

                // Click 1 — start wire at source (prefer exact element, fall back to nearest pin)
                const srcEl = findNearestPin(ssx, ssy) || document.elementFromPoint(ssx, ssy);
                const srcR = srcEl?.getBoundingClientRect();
                const srcX = srcR ? srcR.x + srcR.width / 2 : ssx;
                const srcY = srcR ? srcR.y + srcR.height / 2 : ssy;

                fire(srcEl, 'mousedown', srcX, srcY);
                await new Promise(r => setTimeout(r, 80));
                fire(srcEl, 'mouseup', srcX, srcY);
                fire(srcEl, 'click', srcX, srcY);
                await new Promise(r => setTimeout(r, 400));

                // Move preview to destination
                fire(document, 'mousemove', dsx, dsy);
                await new Promise(r => setTimeout(r, 200));

                // Click 2 — complete wire at destination
                const dstEl = findNearestPin(dsx, dsy) || document.elementFromPoint(dsx, dsy);
                const dstR = dstEl?.getBoundingClientRect();
                const dstX = dstR ? dstR.x + dstR.width / 2 : dsx;
                const dstY = dstR ? dstR.y + dstR.height / 2 : dsy;

                fire(dstEl, 'mousedown', dstX, dstY);
                await new Promise(r => setTimeout(r, 80));
                fire(dstEl, 'mouseup', dstX, dstY);
                fire(dstEl, 'click', dstX, dstY);

                return {
                    src: { canvas: {x:sx,y:sy}, el: srcEl?.tagName, hit: {x:srcX,y:srcY} },
                    dst: { canvas: {x:dx,y:dy}, el: dstEl?.tagName, hit: {x:dstX,y:dstY} },
                };
            }
            """,
            [src_x, src_y, dst_x, dst_y],
        )

        if result and "error" in result:
            return f"Error: {result['error']}"

        await _random_delay(0.3, 0.6)
        return json.dumps({"wire": f"({src_x},{src_y}) → ({dst_x},{dst_y})"})
    except Exception as exc:
        return f"Error connecting pins by coords: {exc}"


async def get_component_pins() -> str:
    """Scan the canvas SVG for interactive component pins and group them by proximity.

    Returns canvas-relative coordinates for each detected component's pins.
    Excludes breadboard holes. Groups pins within 60px of each other as one component.

    Returns:
        JSON list of components: [{"id": "comp_0", "pins": [{"x":int,"y":int}, ...]}]
    """
    try:
        page = await _get_page()

        data = await page.evaluate("""
            () => {
                const canvas = document.querySelector('canvas.js-tpl-target__render-canvas');
                if (!canvas) return null;
                const cr = canvas.getBoundingClientRect();

                // All interactive SVG rects/circles with mousedown handler
                const els = Array.from(document.querySelectorAll('svg rect, svg circle'))
                    .filter(el => {
                        try { return Object.keys(jQuery._data(el, 'events') || {}).includes('mousedown'); }
                        catch(e) { return false; }
                    });

                // Collect canvas-relative positions
                const pts = [];
                for (const el of els) {
                    const r = el.getBoundingClientRect();
                    if (r.width === 0) continue;
                    const cx = Math.round(r.x + r.width / 2 - cr.x);
                    const cy = Math.round(r.y + r.height / 2 - cr.y);
                    // Skip breadboard area (large x range, many holes at same y)
                    if (cx > 420) continue;
                    pts.push({ x: cx, y: cy, w: Math.round(r.width) });
                }

                // Group by y-row buckets (same cy ± 5 = same row)
                const rows = {};
                for (const p of pts) {
                    const bucket = Math.round(p.y / 10) * 10;
                    if (!rows[bucket]) rows[bucket] = [];
                    rows[bucket].push(p);
                }

                // Filter out Arduino pin headers (rows with > 8 pins)
                const componentPins = [];
                for (const [bucket, rowPts] of Object.entries(rows)) {
                    if (rowPts.length <= 8) {
                        componentPins.push(...rowPts);
                    }
                }

                // Proximity clustering: group pins within 60px of each other
                const clusters = [];
                const used = new Set();
                for (let i = 0; i < componentPins.length; i++) {
                    if (used.has(i)) continue;
                    const cluster = [componentPins[i]];
                    used.add(i);
                    for (let j = i + 1; j < componentPins.length; j++) {
                        if (used.has(j)) continue;
                        const dist = Math.hypot(
                            componentPins[i].x - componentPins[j].x,
                            componentPins[i].y - componentPins[j].y
                        );
                        if (dist <= 60) { cluster.push(componentPins[j]); used.add(j); }
                    }
                    clusters.push(cluster);
                }

                // Build output: sort pins within cluster by x then y
                return clusters.map((pins, idx) => ({
                    id: `comp_${idx}`,
                    pin_count: pins.length,
                    pins: pins
                        .sort((a, b) => a.x - b.x || a.y - b.y)
                        .map(p => ({ x: p.x, y: p.y })),
                    center: {
                        x: Math.round(pins.reduce((s, p) => s + p.x, 0) / pins.length),
                        y: Math.round(pins.reduce((s, p) => s + p.y, 0) / pins.length),
                    },
                }));
            }
        """)

        if not data:
            return "Error: No component pins found. Is a circuit open?"

        return json.dumps(data, indent=2)
    except Exception as exc:
        return f"Error scanning component pins: {exc}"


async def get_breadboard_grid() -> str:
    """Scan the canvas SVG for breadboard holes and return a structured grid map.

    Tinkercad renders breadboard holes as SVG circles with class
    cgfx__breadboard-round. This function reads their live screen positions
    and returns a grid keyed by standard breadboard notation:
      - Rows: a-e (top half), f-j (bottom half)
      - Columns: 1-N (left to right)
      - Power rails: pwr_top_pos, pwr_top_neg, pwr_bot_pos, pwr_bot_neg

    Returns:
        JSON: {"grid": {"a1": {"x":int,"y":int}, "b5": {...}, ...}, "cols": N, "rows": 10}
    """
    try:
        page = await _get_page()

        grid_data = await page.evaluate("""
            () => {
                const canvas = document.querySelector('canvas.js-tpl-target__render-canvas');
                if (!canvas) return null;
                const cr = canvas.getBoundingClientRect();

                // Find breadboard holes: small dark circles inside cgfx__breadboard-round
                const circles = Array.from(document.querySelectorAll(
                    '[class*="breadboard-round"] circle, .cgfx__breadboard-round circle'
                ));

                if (circles.length === 0) return { error: 'no breadboard circles found' };

                // Collect unique (x, y) canvas-relative positions
                const pts = [];
                const seen = new Set();
                for (const c of circles) {
                    const r = c.getBoundingClientRect();
                    if (r.width === 0) continue;
                    const cx = Math.round(r.x + r.width / 2 - cr.x);
                    const cy = Math.round(r.y + r.height / 2 - cr.y);
                    const key = `${cx},${cy}`;
                    if (!seen.has(key)) { seen.add(key); pts.push({ x: cx, y: cy }); }
                }

                // Group unique x (columns) and y (rows) values
                const xs = [...new Set(pts.map(p => p.x))].sort((a, b) => a - b);
                const ys = [...new Set(pts.map(p => p.y))].sort((a, b) => a - b);

                // Identify row sections by gaps > 12px
                const rowGroups = [];
                let group = [ys[0]];
                for (let i = 1; i < ys.length; i++) {
                    if (ys[i] - ys[i - 1] > 12) {
                        rowGroups.push(group);
                        group = [];
                    }
                    group.push(ys[i]);
                }
                rowGroups.push(group);

                // Expected groups: [pwr_top], [a-e], [f-j], [pwr_bot]
                // Map row names based on group sizes
                const ROW_NAMES = ['a','b','c','d','e','f','g','h','i','j'];
                const namedRows = {};

                for (const grp of rowGroups) {
                    if (grp.length === 2) {
                        // Power rail — determine top or bottom by position
                        const isTop = grp[0] < ys[Math.floor(ys.length / 2)];
                        namedRows[isTop ? 'pwr_top_pos' : 'pwr_bot_pos'] = grp[0];
                        namedRows[isTop ? 'pwr_top_neg' : 'pwr_bot_neg'] = grp[1];
                    } else {
                        // Main rows — assign a-e or f-j
                        const startIdx = Object.keys(namedRows).filter(k => k.length === 1).length;
                        grp.forEach((y, i) => { namedRows[ROW_NAMES[startIdx + i]] = y; });
                    }
                }

                // Build grid map: notation -> {x, y}
                const grid = {};
                for (const [rowName, rowY] of Object.entries(namedRows)) {
                    xs.forEach((colX, colIdx) => {
                        const col = colIdx + 1;
                        const key = `${rowName}${col}`;
                        // Verify this point actually exists
                        if (pts.some(p => p.x === colX && p.y === rowY)) {
                            grid[key] = { x: colX, y: rowY };
                        }
                    });
                }

                return {
                    grid,
                    cols: xs.length,
                    rows: Object.keys(namedRows).filter(k => k.length === 1).length,
                    row_names: Object.keys(namedRows),
                    x_range: [xs[0], xs[xs.length - 1]],
                    y_range: [ys[0], ys[ys.length - 1]],
                };
            }
        """)

        if not grid_data:
            return "Error: No breadboard found on canvas. Add a breadboard first."
        if "error" in grid_data:
            return f"Error: {grid_data['error']}"

        return json.dumps(grid_data, indent=2)
    except Exception as exc:
        return f"Error getting breadboard grid: {exc}"


async def connect_breadboard_holes(hole_a: str, hole_b: str) -> str:
    """Connect two breadboard holes with a wire using hole notation.

    Args:
        hole_a: Source hole notation (e.g. 'a5', 'f12', 'pwr_top_pos1')
        hole_b: Destination hole notation (e.g. 'e5', 'j12', 'pwr_top_neg1')

    Returns:
        JSON confirmation or error with available hole names.
    """
    try:
        grid_json = await get_breadboard_grid()
        if grid_json.startswith("Error"):
            return grid_json

        grid_data = json.loads(grid_json)
        grid = grid_data["grid"]

        if hole_a not in grid:
            return f"Error: '{hole_a}' not found. Available rows: {grid_data['row_names']}, cols: 1-{grid_data['cols']}"
        if hole_b not in grid:
            return f"Error: '{hole_b}' not found. Available rows: {grid_data['row_names']}, cols: 1-{grid_data['cols']}"

        src = grid[hole_a]
        dst = grid[hole_b]

        return await connect_pins_by_coords(src["x"], src["y"], dst["x"], dst["y"])
    except Exception as exc:
        return f"Error connecting breadboard holes: {exc}"


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
