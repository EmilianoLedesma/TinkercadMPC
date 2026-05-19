"""Centralized selectors, constants, and shared helpers for tinkercad-mcp."""

from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

SESSION_DIR = Path.home() / ".tinkercad_mcp"
SESSION_FILE = SESSION_DIR / "session.json"

# ── URLs ─────────────────────────────────────────────────────────────────────

TINKERCAD_BASE = "https://www.tinkercad.com"
TINKERCAD_DASHBOARD = f"{TINKERCAD_BASE}/dashboard"
TINKERCAD_DASHBOARD_DESIGNS = f"{TINKERCAD_BASE}/dashboard/designs"
TINKERCAD_LOGIN = f"{TINKERCAD_BASE}/login"

# Circuit editor uses /editel, 3D editor uses /edit
# Verified 2026-05-19 against live DOM
TINKERCAD_3D_EDIT_SUFFIX = "edit"
TINKERCAD_CIRCUIT_EDIT_SUFFIX = "editel"

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
    # TODO: verify after opening a 3D design editor — selectors below are best-guess
    "design_name_input": "input[name='name'], input[placeholder*='name']",
    "btn_export":        "button[title*='Export'], button[aria-label*='Export']",
    "btn_export_stl":    "button[title='STL'], a[title='STL']",
    "shape_toolbar":     ".shape-toolbar, [class*='ShapePanel']",

    # ── Circuit editor — verified 2026-05-19 ─────────────────────────────────
    # Main drawing canvas
    "circuit_canvas":       "canvas.js-tpl-target__render-canvas",

    # Component search box (right panel)
    "component_search":      "input#q",

    # Autocomplete dropdown result items (appear after typing in search)
    "component_autocomplete_item": "ul.ui-autocomplete li.ui-menu-item",

    # Component grid items in panel after autocomplete selection
    "component_grid_item":   "div.editor__component_picker__groups__item.grid__item",

    # Start/Stop simulation — same element, text toggles between states
    "btn_start_sim":        "a#SIMULATION_ID",
    "btn_stop_sim":         "a#SIMULATION_ID",

    # Open code editor panel
    "btn_add_code":         "a#CODE_EDITOR_ID",

    # Code panel container
    "code_panel":           ".code_panel",

    # Hidden textarea backing the CodeMirror editor (use CM API to set value)
    "code_editor_textarea": "textarea.js-code_editor__textarea",

    # CodeMirror editor instance (use page.evaluate to call .CodeMirror.setValue())
    "code_editor_cm":       ".CodeMirror",

    # Serial Monitor toggle button (inside code panel)
    "btn_serial_monitor":   "a#SERIAL_MONITOR_ID",

    # Serial monitor panel
    "serial_monitor":       ".code_panel__serial",

    # Serial output text (populated during simulation)
    "serial_output":        ".code_panel__serial__output, .js-code_panel__serial__output",

    # Circuit design title (display span + editable input)
    "circuit_title_span":   "span.js-circuit-menu-title",
    "circuit_title_input":  "input.js-circuit-menu-title-input",
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
