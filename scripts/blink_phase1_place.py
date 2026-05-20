"""
LED Blink — Phase 1: place components + show wiring diagram.
Runs headless, then opens headed browser for manual wiring.
Run Phase 2 after wiring is done.
"""
import asyncio, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ["TINKERCAD_HEADLESS"] = "true"
os.environ["PYTHONIOENCODING"] = "utf-8"

import tinkercad_mcp.api as api
from tinkercad_mcp.browser import BrowserManager

SEP = "=" * 60

BLINK_SKETCH = """\
void setup() {
  pinMode(13, OUTPUT);
}

void loop() {
  digitalWrite(13, HIGH);
  delay(1000);
  digitalWrite(13, LOW);
  delay(1000);
}"""

# LED Blink circuit connections
CONNECTIONS = [
    {"from_component": "Arduino Uno", "from_pin": "D13",
     "to_component": "Breadboard",   "to_pin": "e5",
     "wire_color": "green"},
    {"from_component": "Resistor",    "from_pin": "leg 1",
     "to_component": "Breadboard",   "to_pin": "a5",
     "wire_color": "green",
     "note": "same strip as e5 → connected to D13"},
    {"from_component": "Resistor",    "from_pin": "leg 2",
     "to_component": "Breadboard",   "to_pin": "a8",
     "wire_color": "green"},
    {"from_component": "LED",         "from_pin": "Anode (+, long leg)",
     "to_component": "Breadboard",   "to_pin": "b8",
     "wire_color": "green",
     "note": "same strip as a8 → connected to Resistor"},
    {"from_component": "LED",         "from_pin": "Cathode (-, short leg)",
     "to_component": "Breadboard",   "to_pin": "a11",
     "wire_color": "black"},
    {"from_component": "Breadboard",  "from_pin": "a11",
     "to_component": "Breadboard",   "to_pin": "GND rail (-)",
     "wire_color": "black"},
    {"from_component": "Arduino Uno", "from_pin": "GND",
     "to_component": "Breadboard",   "to_pin": "GND rail (-)",
     "wire_color": "black"},
    {"from_component": "Arduino Uno", "from_pin": "5V",
     "to_component": "Breadboard",   "to_pin": "PWR rail (+)",
     "wire_color": "red"},
]


async def main():
    print(SEP)
    print("  LED Blink — Phase 1: Place Components")
    print(SEP)

    # Session
    status = await api.get_session_status()
    print(f"\n[1] Session: {status[:70]}")
    if "invalid" in status.lower():
        print(await api.login())

    # Create circuit
    print("\n[2] Creating circuit...")
    r = await api.create_circuit("LED Blink - MCP")
    data = json.loads(r) if r.startswith("{") else {}
    circuit_url = data.get("url", "")
    print(f"     OK  id={data.get('id','')}  url={circuit_url[:60]}")
    if "error" in r.lower(): return
    await asyncio.sleep(4)

    # Add components — Escape after each drop prevents auto-pan
    print("\n[3] Placing components (headless)...")
    placements = [
        # (component,  canvas_x, canvas_y)  — well separated, no overlap
        ("breadboard",   420, 140),   # right side
        ("arduino_uno",   60, 200),   # left side (Arduino ~350px wide, ends at x~410)
        ("led",          390,  55),   # top-right, above breadboard
        ("resistor",     290,  55),   # top-center
    ]
    for comp, x, y in placements:
        r = await api.add_component(comp, x=x, y=y)
        ok = "error" not in r.lower()
        print(f"     [{'OK' if ok else 'FAIL'}] {comp:15s} @ ({x:3d},{y:3d})")
        await asyncio.sleep(2.5)

    # Save circuit URL for Phase 2
    mgr = await BrowserManager.get_instance()
    page = await mgr.get_page()
    editor_url = page.url
    url_file = os.path.join(os.path.dirname(__file__), ".circuit_url")
    open(url_file, "w").write(editor_url)
    print(f"\n     Circuit URL saved for Phase 2: {editor_url[:60]}")

    # Generate wiring diagram
    print("\n[4] Wiring diagram:")
    diagram = api.get_wiring_diagram("LED Blink", CONNECTIONS,
        notes="D13 -> Resistor -> LED keeps LED from burning out.\n"
              "  Breadboard strips: a5/b5/c5/d5/e5 all connected, same for a8-e8.")
    print(diagram)

    # Open headed so user can wire
    print("\n[5] Opening browser for manual wiring...")
    os.environ["TINKERCAD_HEADLESS"] = "false"
    await mgr.close()
    await asyncio.sleep(1)
    mgr2 = await BrowserManager.get_instance()
    page2 = await mgr2.get_page(headless=False)
    await page2.goto(editor_url, wait_until="load", timeout=60_000)

    print(f"\n{SEP}")
    print("  Browser open. Connect wires following the diagram above.")
    print("  When done, run: blink_phase2_simulate.py")
    print(SEP)

    # Keep browser open indefinitely — user closes when done wiring
    try:
        await asyncio.sleep(9999)
    except KeyboardInterrupt:
        pass
    await mgr2.close()


if __name__ == "__main__":
    asyncio.run(main())
