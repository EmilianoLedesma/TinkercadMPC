"""Tests for session management tools."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_page():
    page = AsyncMock()
    page.is_closed.return_value = False
    page.url = "https://www.tinkercad.com/dashboard"
    return page


@pytest.fixture
def mock_browser_manager(mock_page):
    mgr = AsyncMock()
    mgr.get_page.return_value = mock_page
    mgr.relaunch_headed.return_value = mock_page
    return mgr


@pytest.mark.asyncio
async def test_get_session_status_active(mock_browser_manager, mock_page):
    mock_page.query_selector.side_effect = lambda sel: AsyncMock() if "avatar" in sel else None

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import get_session_status

        result = await get_session_status()

    assert "active" in result.lower() or "invalid" in result.lower()


@pytest.mark.asyncio
async def test_get_session_status_not_logged_in(mock_browser_manager, mock_page):
    mock_page.query_selector.return_value = None  # no avatar = not logged in

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import get_session_status

        result = await get_session_status()

    assert "invalid" in result.lower() or "login" in result.lower()


@pytest.mark.asyncio
async def test_logout_clears_session(mock_browser_manager):
    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import logout

        result = await logout()

    mock_browser_manager.clear_session.assert_called_once()
    mock_browser_manager.close.assert_called_once()
    assert "logged out" in result.lower()
