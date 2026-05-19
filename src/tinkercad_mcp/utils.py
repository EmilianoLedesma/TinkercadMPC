"""Centralized selectors, constants, and shared helpers for tinkercad-mcp."""

from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

SESSION_DIR = Path.home() / ".tinkercad_mcp"
SESSION_FILE = SESSION_DIR / "session.json"

# ── URLs ─────────────────────────────────────────────────────────────────────

TINKERCAD_BASE = "https://www.tinkercad.com"
TINKERCAD_DASHBOARD = f"{TINKERCAD_BASE}/dashboard"
TINKERCAD_LOGIN = f"{TINKERCAD_BASE}/login"

# ── DOM Selectors ─────────────────────────────────────────────────────────────
# All selectors verified against live Tinkercad DOM (2026-05-19).
# Update here when Tinkercad changes its DOM — nowhere else.

SEL: dict[str, str] = {
    # ── Auth ──────────────────────────────────────────────────────────────────
    # Login page has a standard Autodesk OAuth redirect; no special button needed.
    # After manual login the page redirects to /dashboard automatically.
    "btn_login": "a[href*='login'], a[href*='autodesk']",

    # Header avatar (top-right) — triggers user menu dropdown
    "user_avatar": ".header-avatar-trigger",

    # Sidebar username text (below avatar photo in left sidebar)
    "user_name": ".dashboard-avatar-username",

    # ── Dashboard — navigation ────────────────────────────────────────────────
    # Filter pills on /dashboard/designs page (icon + text tabs)
    "tab_3d":       "a.filter-3d",
    "tab_circuits": "a.filter-circuits",

    # ── Dashboard — design cards ──────────────────────────────────────────────
    # Angular custom element; one per design/circuit
    "design_cards":      "tk-thing-box",
    # H3 inside each card (no class — use descendant selector in code)
    "design_card_title": "tk-thing-box h3",
    # Thumbnail div carries the design ID: id="thumbnail-{designId}"
    "design_card_thumb": ".thumbnail[id^='thumbnail-']",

    # ── Dashboard — create ────────────────────────────────────────────────────
    # Step 1: open the Create dropdown (visible at ≥1280 px wide)
    "btn_create_dropdown": "#create-design",
    # Step 2a: 3D Design option inside the dropdown
    "btn_create_design":   "#dashboard-create-3d-design",
    # Step 2b: Circuit option inside the dropdown
    "btn_create_circuit":  "#dashboard-create-circuits",

    # ── Dashboard — delete ────────────────────────────────────────────────────
    # Per-card gear/dots button (opens Properties/Duplicate/Delete menu)
    "btn_card_menu":    "button.dropdown-toggle.compact[title='Design actions']",
    # Delete item inside the per-card dropdown
    "btn_delete_design": "[id$='delete'] a.dropdown-item",
    # Confirm-delete modal button (TODO: verify selector when modal opens)
    "btn_confirm_delete": ".modal .btn-danger, .modal button.button-md:not(.button-cancel)",

    # ── 3D editor ─────────────────────────────────────────────────────────────
    # TODO: verify after opening a 3D design editor
    "design_name_input": "input[name='name'], input[placeholder*='name']",
    "btn_export":        "button[title*='Export'], button[aria-label*='Export']",
    "btn_export_stl":    "button[title='STL'], a[title='STL']",
    "shape_toolbar":     ".shape-toolbar, [class*='ShapePanel']",

    # ── Circuit editor ────────────────────────────────────────────────────────
    # TODO: verify after opening a circuit editor
    "circuit_canvas":    "canvas#my-canvas, canvas[class*='circuit'], canvas",
    "btn_start_sim":     "button[title*='Start'], button[aria-label*='Start Simulation']",
    "btn_stop_sim":      "button[title*='Stop'], button[aria-label*='Stop Simulation']",
    "serial_monitor":    "[class*='serial-monitor'], [class*='SerialMonitor']",
    "serial_output":     "[class*='serial-output'], [class*='console-output']",
    "component_search":  "input[placeholder*='Search'], input[placeholder*='search']",
    "btn_add_code":      "button[title*='Code'], button[aria-label*='Code Editor']",
    "code_editor":       "textarea.code-input, [class*='CodeMirror'] textarea, .ace_editor",
    "btn_upload_code":   "button[title*='Upload'], button[aria-label*='Upload']",
}

# ── Component catalog ─────────────────────────────────────────────────────────
# Maps user-friendly names to Tinkercad internal component identifiers.
# Update search terms if Tinkercad renames components.

COMPONENT_CATALOG: dict[str, str] = {
    # Microcontrollers
    "arduino_uno": "Arduino Uno R3",
    "arduino_nano": "Arduino Nano",
    "arduino_mega": "Arduino Mega",
    # Passive components
    "resistor": "Resistor",
    "capacitor": "Capacitor",
    "inductor": "Inductor",
    # Output
    "led": "LED",
    "rgb_led": "RGB LED",
    "buzzer": "Buzzer",
    "dc_motor": "DC Motor",
    "servo": "Servo Motor",
    # Input
    "button": "Pushbutton",
    "potentiometer": "Potentiometer",
    "photoresistor": "Photoresistor",
    "temperature_sensor": "TMP36 Temperature Sensor",
    "ultrasonic": "Ultrasonic Distance Sensor",
    # Power
    "battery_9v": "9V Battery",
    "power_supply": "Power Supply",
    # Other
    "breadboard": "Breadboard",
    "breadboard_small": "Small Breadboard",
    "lcd": "LCD 16x2",
    "seven_segment": "7-Segment Display",
}

# ── 3D primitive shapes ───────────────────────────────────────────────────────

SHAPE_TYPES = frozenset({"box", "sphere", "cylinder", "cone", "torus", "wedge", "pyramid"})

# ── User-Agent ────────────────────────────────────────────────────────────────

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
