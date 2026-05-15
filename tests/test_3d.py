"""Tests for 3D design tools."""

import json
import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture
def mock_page():
    page = AsyncMock()
    page.is_closed.return_value = False
    page.url = "https://www.tinkercad.com/things/abc123/edit"
    return page


@pytest.fixture
def mock_browser_manager(mock_page):
    mgr = AsyncMock()
    mgr.get_page.return_value = mock_page
    return mgr


@pytest.mark.asyncio
async def test_list_designs_empty(mock_browser_manager, mock_page):
    mock_page.query_selector.return_value = None
    mock_page.query_selector_all.return_value = []

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import list_designs

        result = await list_designs()

    data = json.loads(result)
    assert data["count"] == 0
    assert data["designs"] == []


@pytest.mark.asyncio
async def test_add_shape_invalid_type(mock_browser_manager):
    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import add_shape

        result = await add_shape("invalid_shape", 0, 0, 0, 10, 10, 10)

    assert "error" in result.lower()
    assert "invalid_shape" in result


@pytest.mark.asyncio
async def test_add_shape_valid_type(mock_browser_manager, mock_page):
    mock_page.evaluate.return_value = None  # API not yet mapped

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import add_shape

        result = await add_shape("box", 0, 0, 0, 20, 20, 20)

    # Should not be an "unknown shape" error
    assert "Unknown shape" not in result


@pytest.mark.asyncio
async def test_group_shapes_too_few(mock_browser_manager):
    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import group_shapes

        result = await group_shapes([])

    assert "error" in result.lower()
