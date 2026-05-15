# tinkercad-mcp

MCP server that lets LLMs interact with [Tinkercad](https://www.tinkercad.com) to create 3D designs and electronic circuits. Because Tinkercad has no public API, all interaction goes through browser automation with [Playwright](https://playwright.dev/).

## How it works

```
Claude / Claude Desktop
        │  MCP Protocol (stdio)
        ▼
  tinkercad-mcp  (Python + FastMCP)
        │  Playwright
        ▼
   Chromium → tinkercad.com
```

- **3D shapes**: driven via the editor's internal JavaScript API / XHR interception
- **Circuits**: DOM automation (components, wires, code upload)
- **Session**: Playwright `storage_state` persisted in `~/.tinkercad_mcp/session.json`

---

## Requirements

- Python 3.11+
- A free [Tinkercad account](https://www.tinkercad.com)

---

## Installation

```bash
# From source (development)
git clone https://github.com/<your-user>/tinkercad-mcp.git
cd tinkercad-mpc
pip install -e ".[dev]"

# Install Playwright browser
playwright install chromium
```

---

## First-time setup

The first login opens a headed browser window so you can complete Autodesk OAuth manually. After that, the session is saved and reused automatically.

```bash
# Verify the server starts
tinkercad-mcp
```

Then, inside a Claude session, call `tinkercad_login`. A Chromium window will open. Log in with your Autodesk/Tinkercad account and wait for the dashboard to load. The server saves your session to `~/.tinkercad_mcp/session.json` and closes the headed window. From this point on, the browser runs headless.

---

## Claude Desktop configuration

Add this block to your Claude Desktop `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tinkercad": {
      "command": "tinkercad-mcp",
      "env": {
        "TINKERCAD_HEADLESS": "true"
      }
    }
  }
}
```

Config file location:
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `TINKERCAD_HEADLESS` | `true` | Run Chromium headless. Set to `false` to see the browser. |
| `TINKERCAD_LOG_LEVEL` | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `TINKERCAD_TIMEOUT_MS` | `30000` | Default Playwright action timeout in milliseconds. |

---

## Available tools

### Session

| Tool | Description |
|---|---|
| `tinkercad_login` | Authenticate. Opens headed browser on first run, reuses saved session after. |
| `tinkercad_logout` | End session and delete saved cookies. |
| `tinkercad_get_session_status` | Check if current session is valid. |

### 3D Designs

| Tool | Description |
|---|---|
| `tinkercad_list_designs` | List all 3D designs on the dashboard. |
| `tinkercad_create_3d_design` | Create a new blank design. |
| `tinkercad_add_shape` | Add a primitive shape (box, sphere, cylinder, cone, torus, wedge, pyramid). |
| `tinkercad_group_shapes` | Group two or more shapes into one object. |
| `tinkercad_export_stl` | Trigger STL download for a design. |
| `tinkercad_delete_design` | Permanently delete a design. |

### Circuits

| Tool | Description |
|---|---|
| `tinkercad_list_circuits` | List all circuits on the dashboard. |
| `tinkercad_create_circuit` | Create a new blank circuit. |
| `tinkercad_add_component` | Add a component to the open circuit by drag-and-drop. |
| `tinkercad_connect_pins` | Connect two component pins with a wire. |
| `tinkercad_add_code_to_arduino` | Upload a C++ sketch to an Arduino component. |
| `tinkercad_start_simulation` | Start the circuit simulation. |
| `tinkercad_stop_simulation` | Stop the circuit simulation. |
| `tinkercad_get_simulation_output` | Read the Arduino Serial Monitor output. |

---

## Example usage (Claude prompts)

```
Login to Tinkercad and show me my designs.

Create a 3D design called "Bracket" and add a 40x20x5 mm box.

Create a circuit called "LED Blink", add an Arduino Uno and an LED,
connect pin D13 to the LED anode and GND to the cathode,
then upload a blink sketch and start the simulation.
```

---

## Project structure

```
tinkercad-mcp/
├── src/tinkercad_mcp/
│   ├── server.py       # FastMCP app and tool registration
│   ├── browser.py      # BrowserManager singleton (Playwright)
│   ├── api.py          # Domain logic for all tools
│   └── utils.py        # SEL selectors, COMPONENT_CATALOG, constants
├── tests/
│   ├── test_session.py
│   ├── test_3d.py
│   └── test_circuits.py
├── pyproject.toml
└── README.md
```

---

## Development

```bash
# Install with dev extras
pip install -e ".[dev]"

# Run tests (BrowserManager is mocked — no real browser needed)
pytest

# Verify syntax compiles
python -m py_compile src/tinkercad_mcp/server.py
```

---

## Known limitations and next steps

**3D shape placement** (`tinkercad_add_shape`, `tinkercad_group_shapes`) depends on reverse-engineering Tinkercad's internal JavaScript API or recording its XHR traffic. The current implementation calls `window.__tinkercadAddShape` as a probe — if that returns `null`, you need to:

1. Open the 3D editor in headed mode (`TINKERCAD_HEADLESS=false`).
2. Open DevTools → Network tab.
3. Add a shape manually and record the XHR request.
4. Map the endpoint and payload in `api.py`.

**Selector drift** — Tinkercad may update its DOM at any time. All selectors are centralized in `utils.py` under the `SEL` dict for easy maintenance.

**Circuit pin wiring** — Pin selectors in `connect_pins` are guesses based on common Tinkercad patterns. Run the circuit editor in headed mode to inspect actual attribute names.

---

## License

MIT
