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


@pytest.mark.asyncio
async def test_add_component_invalid_type(mock_browser_manager):
    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import add_component

        result = await add_component("flux_capacitor", 100, 100)

    assert "error" in result.lower()
    assert "flux_capacitor" in result


@pytest.mark.asyncio
async def test_add_component_valid_type_no_panel(mock_browser_manager, mock_page):
    mock_page.query_selector.return_value = None  # panel not found

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import add_component

        result = await add_component("arduino_uno", 400, 300)

    assert "error" in result.lower()
    assert "search panel" in result.lower() or "not found" in result.lower()


@pytest.mark.asyncio
async def test_start_simulation_no_button(mock_browser_manager, mock_page):
    mock_page.query_selector.return_value = None

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import start_simulation

        result = await start_simulation()

    assert "error" in result.lower()


@pytest.mark.asyncio
async def test_get_simulation_output_no_monitor(mock_browser_manager, mock_page):
    mock_page.query_selector.return_value = None

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import get_simulation_output

        result = await get_simulation_output()

    assert "error" in result.lower()
