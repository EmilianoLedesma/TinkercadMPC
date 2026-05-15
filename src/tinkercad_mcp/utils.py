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
# All selectors in one place — update here when Tinkercad changes its DOM.

SEL: dict[str, str] = {
    # Auth
    "btn_login": "[data-testid='login-button'], a[href*='login'], button:has-text('Sign In')",
    "user_avatar": "[data-testid='user-avatar'], .user-avatar, img[alt*='avatar'], [aria-label*='account']",
    "user_name": "[data-testid='user-name'], .username, [aria-label*='username']",
    # Dashboard tabs
    "tab_3d": "[data-testid='3d-designs-tab'], button:has-text('3D Designs')",
    "tab_circuits": "[data-testid='circuits-tab'], button:has-text('Circuits')",
    # Design cards (dashboard)
    "design_cards": "[data-testid='design-card'], .design-card, [class*='DesignCard']",
    "design_card_title": "[data-testid='design-title'], .design-title, [class*='title']",
    "design_card_id": "[data-testid='design-id'], [data-id]",
    "btn_create_design": "[data-testid='create-design'], button:has-text('Create new design')",
    "btn_create_circuit": "[data-testid='create-circuit'], button:has-text('Create new circuit')",
    "btn_delete_design": "[data-testid='delete-design'], button:has-text('Delete')",
    "btn_confirm_delete": "[data-testid='confirm-delete'], button:has-text('OK'), button:has-text('Confirm')",
    "design_name_input": "[data-testid='design-name-input'], input[placeholder*='name'], input[name='name']",
    # 3D editor
    "btn_export": "[data-testid='export-btn'], button:has-text('Export')",
    "btn_export_stl": "[data-testid='export-stl'], button:has-text('STL')",
    "shape_toolbar": "[data-testid='shape-toolbar'], .shape-toolbar",
    # Circuit editor
    "circuit_canvas": "[data-testid='circuit-canvas'], #circuit-canvas, canvas",
    "btn_start_sim": "[data-testid='start-simulation'], button:has-text('Start Simulation')",
    "btn_stop_sim": "[data-testid='stop-simulation'], button:has-text('Stop Simulation')",
    "serial_monitor": "[data-testid='serial-monitor'], .serial-monitor, [class*='SerialMonitor']",
    "serial_output": "[data-testid='serial-output'], .serial-output, [class*='output']",
    "component_search": "[data-testid='component-search'], input[placeholder*='Search'], .component-search input",
    "btn_add_code": "[data-testid='code-editor-btn'], button:has-text('Code')",
    "code_editor": "[data-testid='code-editor'], .code-editor, textarea[class*='code']",
    "btn_upload_code": "[data-testid='upload-code'], button:has-text('Upload')",
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
