"""Tests for session management tools."""

import pytest
from unittest.mock import AsyncMock, patch


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


# ── login ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_already_active(mock_browser_manager, mock_page):
    """When avatar exists on dashboard, login returns early without headed mode."""
    avatar_mock = AsyncMock()
    mock_page.query_selector.return_value = avatar_mock

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import login

        result = await login()

    mock_browser_manager.relaunch_headed.assert_not_called()
    assert "already" in result.lower() or "active" in result.lower()


@pytest.mark.asyncio
async def test_login_saves_session_on_success(mock_browser_manager, mock_page):
    """First login: no avatar → headed mode → wait for dashboard URL → save session."""
    mock_page.query_selector.return_value = None  # not logged in
    mock_page.url = "https://www.tinkercad.com/dashboard"

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import login

        result = await login()

    mock_browser_manager.relaunch_headed.assert_called_once()
    mock_browser_manager.save_session.assert_called_once()
    assert "successful" in result.lower() or "saved" in result.lower()


# ── get_session_status ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_session_status_active(mock_browser_manager, mock_page):
    avatar_el = AsyncMock()
    name_el = AsyncMock()
    name_el.inner_text = AsyncMock(return_value="Ada Lovelace")

    # SEL["user_avatar"] = ".header-avatar-trigger"  (contains "avatar")
    # SEL["user_name"]   = ".dashboard-avatar-username"  (contains BOTH "avatar" AND "username")
    # Must check username specifically to avoid collision
    async def sel_side_effect(selector):
        if "username" in selector:
            return name_el
        if "avatar" in selector:
            return avatar_el
        return None

    mock_page.query_selector.side_effect = sel_side_effect

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import get_session_status

        result = await get_session_status()

    assert "active" in result.lower()
    assert "ada lovelace" in result.lower()


@pytest.mark.asyncio
async def test_get_session_status_not_logged_in(mock_browser_manager, mock_page):
    mock_page.query_selector.return_value = None

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import get_session_status

        result = await get_session_status()

    assert "invalid" in result.lower() or "login" in result.lower()


@pytest.mark.asyncio
async def test_get_session_status_network_error(mock_browser_manager, mock_page):
    mock_page.goto.side_effect = Exception("net::ERR_NAME_NOT_RESOLVED")

    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import get_session_status

        result = await get_session_status()

    assert "error" in result.lower()


# ── logout ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_logout_clears_session(mock_browser_manager):
    with patch("tinkercad_mcp.api.BrowserManager.get_instance", return_value=mock_browser_manager):
        from tinkercad_mcp.api import logout

        result = await logout()

    mock_browser_manager.clear_session.assert_called_once()
    mock_browser_manager.close.assert_called_once()
    assert "logged out" in result.lower()
