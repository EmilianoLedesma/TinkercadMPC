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
    card = AsyncMock()
    card.get_attribute = AsyncMock(return_value=circuit_id)
    title_el = AsyncMock()
    title_el.inner_text = AsyncMock(return_value=title)
    card.query_selector = AsyncMock(return_value=title_el)
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
    mock_page.query_selector.return_value = None

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import add_code_to_arduino

        result = await add_code_to_arduino("arduino-99", BLINK_SKETCH)

    assert "error" in result.lower()
    assert "arduino-99" in result


@pytest.mark.asyncio
async def test_add_code_success(mock_browser_manager, mock_page):
    arduino_el = AsyncMock()
    code_btn = AsyncMock()
    editor_el = AsyncMock()
    upload_btn = AsyncMock()
    call_seq = [arduino_el, code_btn, editor_el, upload_btn]
    call_count = 0

    async def sel_side_effect(selector):
        nonlocal call_count
        val = call_seq[call_count] if call_count < len(call_seq) else AsyncMock()
        call_count += 1
        return val

    mock_page.query_selector.side_effect = sel_side_effect

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import add_code_to_arduino

        result = await add_code_to_arduino("arduino-1", BLINK_SKETCH)

    assert "arduino-1" in result
    assert str(len(BLINK_SKETCH)) in result or "uploaded" in result.lower()


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
    mock_page.query_selector.return_value = AsyncMock()

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
    mock_page.query_selector.return_value = AsyncMock()

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import stop_simulation

        result = await stop_simulation()

    assert "stopped" in result.lower()


# ── get_simulation_output ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_simulation_output_no_monitor(mock_browser_manager, mock_page):
    mock_page.query_selector.return_value = None

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import get_simulation_output

        result = await get_simulation_output()

    assert "error" in result.lower()


@pytest.mark.asyncio
async def test_get_simulation_output_with_data(mock_browser_manager, mock_page):
    monitor_el = AsyncMock()
    output_el = AsyncMock()
    output_el.inner_text = AsyncMock(return_value="Hello World\nHello World\n")
    monitor_el.query_selector = AsyncMock(return_value=output_el)
    mock_page.query_selector.return_value = monitor_el

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import get_simulation_output

        result = await get_simulation_output()

    data = json.loads(result)
    assert "Hello World" in data["output"]


@pytest.mark.asyncio
async def test_get_simulation_output_empty_monitor(mock_browser_manager, mock_page):
    monitor_el = AsyncMock()
    output_el = AsyncMock()
    output_el.inner_text = AsyncMock(return_value="   ")
    monitor_el.query_selector = AsyncMock(return_value=output_el)
    mock_page.query_selector.return_value = monitor_el

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import get_simulation_output

        result = await get_simulation_output()

    assert "empty" in result.lower() or "not" in result.lower()
