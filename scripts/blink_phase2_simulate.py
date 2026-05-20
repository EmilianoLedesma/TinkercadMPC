"""
LED Blink — Phase 2: upload code + start simulation.
Run this after completing manual wiring from Phase 1.
"""
import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ["TINKERCAD_HEADLESS"] = "false"  # stay headed so user sees simulation
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


async def main():
    print(SEP)
    print("  LED Blink — Phase 2: Code + Simulation")
    print(SEP)

    # Load circuit URL saved by Phase 1
    url_file = os.path.join(os.path.dirname(__file__), ".circuit_url")
    if not os.path.exists(url_file):
        print("ERROR: .circuit_url not found. Run Phase 1 first.")
        return
    editor_url = open(url_file).read().strip()
    print(f"\nCircuit: {editor_url[:70]}")

    # Session
    status = await api.get_session_status()
    print(f"Session: {status[:60]}")
    if "invalid" in status.lower():
        await api.login()

    # Open headed browser on the circuit
    mgr = await BrowserManager.get_instance()
    page = await mgr.get_page(headless=False)
    await page.goto(editor_url, wait_until="load", timeout=60_000)
    await asyncio.sleep(3)

    # Screenshot to verify wiring before uploading code
    print("\n[0] Verifying wiring (screenshot)...")
    ss = os.path.join(os.path.dirname(__file__), "wiring_verification.png")
    await page.screenshot(path=ss)
    print(f"     Saved: {ss}")
    print("     Check wiring_verification.png to confirm connections look correct.")

    # Upload sketch
    print("\n[1] Uploading Arduino sketch...")
    r = await api.add_code_to_arduino("", BLINK_SKETCH)
    print(f"     {r}")

    # Start simulation
    print("\n[2] Starting simulation...")
    r = await api.start_simulation()
    print(f"     {r}")
    await asyncio.sleep(3)

    # Read serial output (sketch doesn't print but check anyway)
    print("\n[3] Serial monitor output:")
    r = await api.get_simulation_output()
    print(f"     {r[:200]}")

    print(f"\n{SEP}")
    print("  Simulation running. LED should be blinking.")
    print("  Ctrl+C to exit.")
    print(SEP)
    try:
        await asyncio.sleep(9999)
    except KeyboardInterrupt:
        await api.stop_simulation()
    await mgr.close()


if __name__ == "__main__":
    asyncio.run(main())
