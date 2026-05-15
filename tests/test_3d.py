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


def _make_card(design_id: str, title: str) -> AsyncMock:
    """Build a mock design card element."""
    card = AsyncMock()
    card.get_attribute = AsyncMock(return_value=design_id)
    title_el = AsyncMock()
    title_el.inner_text = AsyncMock(return_value=title)
    card.query_selector = AsyncMock(return_value=title_el)
    return card


# ── list_designs ──────────────────────────────────────────────────────────────


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
async def test_list_designs_with_results(mock_browser_manager, mock_page):
    cards = [_make_card("id-1", "My Box"), _make_card("id-2", "My Sphere")]
    mock_page.query_selector.return_value = None
    mock_page.query_selector_all.return_value = cards

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import list_designs

        result = await list_designs()

    data = json.loads(result)
    assert data["count"] == 2
    names = [d["name"] for d in data["designs"]]
    assert "My Box" in names
    assert "My Sphere" in names


# ── create_3d_design ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_3d_design_success(mock_browser_manager, mock_page):
    create_btn = AsyncMock()
    name_input = AsyncMock()

    async def sel_side_effect(selector):
        if "create" in selector.lower():
            return create_btn
        if "name" in selector.lower() or "input" in selector.lower():
            return name_input
        return None

    mock_page.query_selector.side_effect = sel_side_effect
    mock_page.url = "https://www.tinkercad.com/things/abc123/edit"

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import create_3d_design

        result = await create_3d_design("My Design")

    data = json.loads(result)
    assert data["name"] == "My Design"
    assert "abc123" in data["id"]


@pytest.mark.asyncio
async def test_create_3d_design_no_button(mock_browser_manager, mock_page):
    mock_page.query_selector.return_value = None

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import create_3d_design

        result = await create_3d_design("Test")

    assert "error" in result.lower()
    assert "button not found" in result.lower()


# ── add_shape ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_shape_invalid_type(mock_browser_manager):
    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import add_shape

        result = await add_shape("invalid_shape", 0, 0, 0, 10, 10, 10)

    assert "error" in result.lower()
    assert "invalid_shape" in result


@pytest.mark.asyncio
async def test_add_shape_valid_type_api_not_mapped(mock_browser_manager, mock_page):
    mock_page.evaluate.return_value = None

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import add_shape

        result = await add_shape("box", 0, 0, 0, 20, 20, 20)

    assert "Unknown shape" not in result


@pytest.mark.asyncio
async def test_add_shape_valid_type_api_mapped(mock_browser_manager, mock_page):
    mock_page.evaluate.return_value = "shape-xyz"

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import add_shape

        result = await add_shape("cylinder", 10, 0, 0, 15, 30, 15)

    data = json.loads(result)
    assert data["shape_id"] == "shape-xyz"
    assert data["type"] == "cylinder"


# ── group_shapes ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_group_shapes_empty_list(mock_browser_manager):
    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import group_shapes

        result = await group_shapes([])

    assert "error" in result.lower()


@pytest.mark.asyncio
async def test_group_shapes_api_mapped(mock_browser_manager, mock_page):
    mock_page.evaluate.return_value = "group-abc"

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import group_shapes

        result = await group_shapes(["s1", "s2", "s3"])

    data = json.loads(result)
    assert data["group_id"] == "group-abc"
    assert data["shapes"] == ["s1", "s2", "s3"]


# ── export_stl ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_stl_success(mock_browser_manager, mock_page):
    export_btn = AsyncMock()
    stl_btn = AsyncMock()
    call_count = 0

    async def sel_side_effect(selector):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return export_btn
        return stl_btn

    mock_page.query_selector.side_effect = sel_side_effect

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import export_stl

        result = await export_stl("abc123")

    assert "abc123" in result
    assert "stl" in result.lower()


@pytest.mark.asyncio
async def test_export_stl_no_export_button(mock_browser_manager, mock_page):
    mock_page.query_selector.return_value = None

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import export_stl

        result = await export_stl("abc123")

    assert "error" in result.lower()
    assert "export button" in result.lower()


# ── delete_design ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_design_not_found(mock_browser_manager, mock_page):
    mock_page.query_selector.return_value = None

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import delete_design

        result = await delete_design("nonexistent-id")

    assert "error" in result.lower()
    assert "not found" in result.lower()


@pytest.mark.asyncio
async def test_delete_design_success(mock_browser_manager, mock_page):
    card = AsyncMock()
    delete_btn = AsyncMock()
    card.query_selector = AsyncMock(return_value=delete_btn)
    confirm_btn = AsyncMock()

    async def page_sel(selector):
        if "nonexistent" in selector:
            return None
        if "confirm" in selector.lower() or "ok" in selector.lower():
            return confirm_btn
        return card

    mock_page.query_selector.side_effect = page_sel

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import delete_design

        result = await delete_design("abc123")

    assert "abc123" in result
    assert "deleted" in result.lower()
