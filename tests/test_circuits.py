"""Tests for circuit tools."""

import json
import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture
def mock_page():
    page = AsyncMock()
    page.is_closed.return_value = False
    page.url = "https://www.tinkercad.com/things/xyz789/edit"
    return page


@pytest.fixture
def mock_browser_manager(mock_page):
    mgr = AsyncMock()
    mgr.get_page.return_value = mock_page
    return mgr


def _make_card(circuit_id: str, title: str) -> AsyncMock:
    """Mock tk-thing-box card matching real Tinkercad DOM structure."""
    card = AsyncMock()

    h3 = AsyncMock()
    h3.inner_text = AsyncMock(return_value=title)

    # .thumbnail[id^='thumbnail-'] carries the design ID
    thumb = AsyncMock()
    thumb.get_attribute = AsyncMock(return_value=f"thumbnail-{circuit_id}")

    async def card_query(selector):
        if "h3" in selector:
            return h3
        if "thumbnail" in selector:
            return thumb
        return None

    card.query_selector = card_query
    return card


# ── list_circuits ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_circuits_empty(mock_browser_manager, mock_page):
    mock_page.query_selector.return_value = None
    mock_page.query_selector_all.return_value = []

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import list_circuits

        result = await list_circuits()

    data = json.loads(result)
    assert data["count"] == 0
    assert data["circuits"] == []


@pytest.mark.asyncio
async def test_list_circuits_with_results(mock_browser_manager, mock_page):
    cards = [_make_card("c-1", "Blink LED"), _make_card("c-2", "Temperature Monitor")]
    mock_page.query_selector.return_value = None
    mock_page.query_selector_all.return_value = cards

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import list_circuits

        result = await list_circuits()

    data = json.loads(result)
    assert data["count"] == 2
    names = [c["name"] for c in data["circuits"]]
    assert "Blink LED" in names


# ── create_circuit ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_circuit_success(mock_browser_manager, mock_page):
    create_btn = AsyncMock()
    name_input = AsyncMock()
    mock_page.url = "https://www.tinkercad.com/things/xyz789/edit"

    async def sel_side_effect(selector):
        if "circuit" in selector.lower() or "create" in selector.lower():
            return create_btn
        if "name" in selector.lower() or "input" in selector.lower():
            return name_input
        return None

    mock_page.query_selector.side_effect = sel_side_effect

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import create_circuit

        result = await create_circuit("LED Blink")

    data = json.loads(result)
    assert data["name"] == "LED Blink"
    assert "xyz789" in data["id"]


@pytest.mark.asyncio
async def test_create_circuit_no_button(mock_browser_manager, mock_page):
    mock_page.query_selector.return_value = None

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import create_circuit

        result = await create_circuit("Test")

    assert "error" in result.lower()
    assert "button not found" in result.lower()


# ── add_component ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_component_invalid_type(mock_browser_manager):
    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import add_component

        result = await add_component("flux_capacitor", 100, 100)

    assert "error" in result.lower()
    assert "flux_capacitor" in result


@pytest.mark.asyncio
async def test_add_component_no_search_panel(mock_browser_manager, mock_page):
    mock_page.query_selector.return_value = None

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import add_component

        result = await add_component("arduino_uno", 400, 300)

    assert "error" in result.lower()
    assert "search panel" in result.lower() or "not found" in result.lower()


@pytest.mark.asyncio
async def test_add_component_valid_catalog_key(mock_browser_manager):
    """Valid key must not produce 'unknown component' error."""
    from tinkercad_mcp.utils import COMPONENT_CATALOG

    for key in list(COMPONENT_CATALOG.keys())[:3]:
        with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
            from tinkercad_mcp.api import add_component

            result = await add_component(key, 100, 100)

        assert "Unknown component" not in result, f"Key '{key}' flagged as unknown"


# ── connect_pins ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_connect_pins_source_not_found(mock_browser_manager, mock_page):
    mock_page.query_selector.return_value = None

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import connect_pins

        result = await connect_pins("arduino-1", "GND", "led-1", "Cathode")

    assert "error" in result.lower()
    assert "gnd" in result.lower() or "arduino-1" in result.lower()


@pytest.mark.asyncio
async def test_connect_pins_destination_not_found(mock_browser_manager, mock_page):
    src_pin = AsyncMock()
    call_count = 0

    async def sel_side_effect(selector):
        nonlocal call_count
        call_count += 1
        return src_pin if call_count == 1 else None

    mock_page.query_selector.side_effect = sel_side_effect

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import connect_pins

        result = await connect_pins("arduino-1", "D13", "led-1", "Anode")

    assert "error" in result.lower()
    assert "anode" in result.lower() or "led-1" in result.lower()


# ── add_code_to_arduino ───────────────────────────────────────────────────────


BLINK_SKETCH = """
void setup() { pinMode(13, OUTPUT); }
void loop() { digitalWrite(13, HIGH); delay(1000); digitalWrite(13, LOW); delay(1000); }
"""


@pytest.mark.asyncio
async def test_add_code_arduino_not_found(mock_browser_manager, mock_page):
    """Code button missing = circuit not open."""
    mock_page.query_selector.return_value = None

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import add_code_to_arduino

        result = await add_code_to_arduino("arduino-99", BLINK_SKETCH)

    assert "error" in result.lower()
    # New flow: comp_id not looked up in DOM; failure = code panel button missing
    assert "code button" in result.lower() or "not found" in result.lower()


@pytest.mark.asyncio
async def test_add_code_success(mock_browser_manager, mock_page):
    """Code panel opens, CodeMirror API sets the sketch."""
    code_btn = AsyncMock()
    mock_page.query_selector.return_value = code_btn
    # CodeMirror.setValue() returns "ok" via page.evaluate
    mock_page.evaluate.return_value = "ok"

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import add_code_to_arduino

        result = await add_code_to_arduino("arduino-1", BLINK_SKETCH)

    assert "arduino-1" in result
    assert str(len(BLINK_SKETCH)) in result or "set" in result.lower()


# ── start / stop simulation ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_simulation_no_button(mock_browser_manager, mock_page):
    mock_page.query_selector.return_value = None

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import start_simulation

        result = await start_simulation()

    assert "error" in result.lower()


@pytest.mark.asyncio
async def test_start_simulation_success(mock_browser_manager, mock_page):
    btn = AsyncMock()
    btn.inner_text = AsyncMock(return_value="Start Simulation")
    mock_page.query_selector.return_value = btn

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import start_simulation

        result = await start_simulation()

    assert "started" in result.lower()


@pytest.mark.asyncio
async def test_stop_simulation_no_button(mock_browser_manager, mock_page):
    mock_page.query_selector.return_value = None

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import stop_simulation

        result = await stop_simulation()

    assert "error" in result.lower()


@pytest.mark.asyncio
async def test_stop_simulation_success(mock_browser_manager, mock_page):
    btn = AsyncMock()
    btn.inner_text = AsyncMock(return_value="Stop Simulation")
    mock_page.query_selector.return_value = btn

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import stop_simulation

        result = await stop_simulation()

    assert "stopped" in result.lower()


# ── get_simulation_output ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_simulation_output_no_monitor(mock_browser_manager, mock_page):
    """serial_output element missing → error."""
    # btn_serial_monitor found, panel found but serial_output not found
    serial_btn = AsyncMock()
    panel = AsyncMock()
    panel.get_attribute = AsyncMock(return_value="height: 200px")  # expanded, no click needed
    call_count = 0

    async def sel_side_effect(selector):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return serial_btn   # btn_serial_monitor
        if call_count == 2:
            return panel        # serial_monitor panel
        return None             # serial_output not found

    mock_page.query_selector.side_effect = sel_side_effect

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import get_simulation_output

        result = await get_simulation_output()

    assert "error" in result.lower()


@pytest.mark.asyncio
async def test_get_simulation_output_with_data(mock_browser_manager, mock_page):
    """Serial monitor expanded, output contains text."""
    serial_btn = AsyncMock()
    panel = AsyncMock()
    panel.get_attribute = AsyncMock(return_value="height: 200px")  # already expanded
    output_el = AsyncMock()
    output_el.inner_text = AsyncMock(return_value="Hello World\nHello World\n")
    call_count = 0

    async def sel_side_effect(selector):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return serial_btn   # btn_serial_monitor
        if call_count == 2:
            return panel        # serial_monitor panel
        return output_el        # serial_output

    mock_page.query_selector.side_effect = sel_side_effect

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import get_simulation_output

        result = await get_simulation_output()

    data = json.loads(result)
    assert "Hello World" in data["output"]


@pytest.mark.asyncio
async def test_get_simulation_output_empty_monitor(mock_browser_manager, mock_page):
    """Serial monitor expanded but no output yet."""
    serial_btn = AsyncMock()
    panel = AsyncMock()
    panel.get_attribute = AsyncMock(return_value="height: 200px")
    output_el = AsyncMock()
    output_el.inner_text = AsyncMock(return_value="   ")
    call_count = 0

    async def sel_side_effect(selector):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return serial_btn
        if call_count == 2:
            return panel
        return output_el

    mock_page.query_selector.side_effect = sel_side_effect

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import get_simulation_output

        result = await get_simulation_output()

    assert "empty" in result.lower() or "not" in result.lower()
