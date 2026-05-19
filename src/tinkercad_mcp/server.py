"""FastMCP server — registers all Tinkercad tools and exposes the CLI entry point."""

import logging
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

import tinkercad_mcp.api as api
from tinkercad_mcp.utils import COMPONENT_CATALOG, SHAPE_TYPES

logging.basicConfig(
    level=os.getenv("TINKERCAD_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

mcp = FastMCP("tinkercad_mcp")


# ── Input models ──────────────────────────────────────────────────────────────


class ShapeInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    shape_type: str = Field(
        ...,
        description=f"Primitive shape type. One of: {sorted(SHAPE_TYPES)}",
    )
    x: float = Field(default=0.0, description="X position in mm")
    y: float = Field(default=0.0, description="Y position in mm")
    z: float = Field(default=0.0, description="Z position in mm")
    width: float = Field(default=20.0, ge=0.1, description="Width in mm")
    height: float = Field(default=20.0, ge=0.1, description="Height in mm")
    depth: float = Field(default=20.0, ge=0.1, description="Depth in mm")


class GroupShapesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shape_ids: list[str] = Field(
        ...,
        min_length=2,
        description="List of shape IDs to group (minimum 2)",
    )


class DesignNameInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(..., min_length=1, max_length=200, description="Design name")


class DesignIdInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    design_id: str = Field(..., min_length=1, description="Tinkercad design ID")


class ComponentInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    component_type: str = Field(
        ...,
        description=f"Component key. Valid: {sorted(COMPONENT_CATALOG.keys())}",
    )
    x: float = Field(default=400.0, description="X drop position on canvas (pixels)")
    y: float = Field(default=300.0, description="Y drop position on canvas (pixels)")


class ConnectPinsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    comp_a: str = Field(..., description="Source component ID or selector")
    pin_a: str = Field(..., description="Source pin name (e.g. 'GND', 'D13', '~5V')")
    comp_b: str = Field(..., description="Destination component ID or selector")
    pin_b: str = Field(..., description="Destination pin name")


class ArduinoCodeInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    comp_id: str = Field(..., description="Arduino component ID on the canvas")
    sketch: str = Field(..., min_length=1, description="Full Arduino C++ sketch source")


# ── Session tools ─────────────────────────────────────────────────────────────


@mcp.tool(
    name="tinkercad_login",
    annotations={
        "title": "Login to Tinkercad",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def tinkercad_login() -> str:
    """Authenticate with Tinkercad via Autodesk.

    First call opens Chromium in headed mode for manual OAuth login.
    Subsequent calls reuse the saved session from ~/.tinkercad_mcp/session.json.
    Session persists across restarts until tinkercad_logout is called.

    Returns:
        str: 'Login successful' or 'Session already active' or error message.
    """
    return await api.login()


@mcp.tool(
    name="tinkercad_logout",
    annotations={
        "title": "Logout from Tinkercad",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def tinkercad_logout() -> str:
    """End the Tinkercad session and delete saved cookies.

    Returns:
        str: Confirmation message.
    """
    return await api.logout()


@mcp.tool(
    name="tinkercad_get_session_status",
    annotations={
        "title": "Check Tinkercad Session Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def tinkercad_get_session_status() -> str:
    """Check whether the current Tinkercad session is valid.

    Returns:
        str: 'Session active. User: <name>' or 'Session invalid — call tinkercad_login'.
    """
    return await api.get_session_status()


# ── 3D Design tools ───────────────────────────────────────────────────────────


@mcp.tool(
    name="tinkercad_list_designs",
    annotations={
        "title": "List 3D Designs",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def tinkercad_list_designs() -> str:
    """List all 3D designs on the Tinkercad dashboard.

    Returns:
        str: JSON with {"count": int, "designs": [{"id": str, "name": str}]}
    """
    return await api.list_designs()


@mcp.tool(
    name="tinkercad_create_3d_design",
    annotations={
        "title": "Create 3D Design",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def tinkercad_create_3d_design(params: DesignNameInput) -> str:
    """Create a new blank 3D design.

    Args:
        params.name (str): Design name (1-200 chars)

    Returns:
        str: JSON with {"id": str, "name": str, "url": str}
    """
    return await api.create_3d_design(params.name)


@mcp.tool(
    name="tinkercad_add_shape",
    annotations={
        "title": "Add Shape to 3D Design",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def tinkercad_add_shape(params: ShapeInput) -> str:
    """Add a primitive shape to the currently open 3D design.

    Requires the 3D editor to be open (call tinkercad_create_3d_design first).

    Args:
        params.shape_type (str): box | sphere | cylinder | cone | torus | wedge | pyramid
        params.x/y/z (float): Position in mm (default 0)
        params.width/height/depth (float): Dimensions in mm (default 20)

    Returns:
        str: JSON with shape_id or guidance message if JS API not yet mapped.
    """
    return await api.add_shape(
        params.shape_type,
        params.x,
        params.y,
        params.z,
        params.width,
        params.height,
        params.depth,
    )


@mcp.tool(
    name="tinkercad_group_shapes",
    annotations={
        "title": "Group Shapes",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def tinkercad_group_shapes(params: GroupShapesInput) -> str:
    """Group two or more shapes into a single object.

    Args:
        params.shape_ids (list[str]): At least 2 shape IDs to group

    Returns:
        str: JSON with group_id or guidance if JS API not yet mapped.
    """
    return await api.group_shapes(params.shape_ids)


@mcp.tool(
    name="tinkercad_export_stl",
    annotations={
        "title": "Export Design as STL",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def tinkercad_export_stl(params: DesignIdInput) -> str:
    """Export a 3D design as an STL file via the browser download dialog.

    Args:
        params.design_id (str): Tinkercad design ID

    Returns:
        str: Confirmation that the STL download was triggered.
    """
    return await api.export_stl(params.design_id)


@mcp.tool(
    name="tinkercad_delete_design",
    annotations={
        "title": "Delete 3D Design",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def tinkercad_delete_design(params: DesignIdInput) -> str:
    """Permanently delete a 3D design.

    WARNING: This action cannot be undone.

    Args:
        params.design_id (str): Tinkercad design ID

    Returns:
        str: Confirmation message or error.
    """
    return await api.delete_design(params.design_id)


# ── Circuit tools ─────────────────────────────────────────────────────────────


@mcp.tool(
    name="tinkercad_list_circuits",
    annotations={
        "title": "List Circuits",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def tinkercad_list_circuits() -> str:
    """List all circuits on the Tinkercad dashboard.

    Returns:
        str: JSON with {"count": int, "circuits": [{"id": str, "name": str}]}
    """
    return await api.list_circuits()


@mcp.tool(
    name="tinkercad_create_circuit",
    annotations={
        "title": "Create Circuit",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def tinkercad_create_circuit(params: DesignNameInput) -> str:
    """Create a new blank circuit.

    Args:
        params.name (str): Circuit name (1-200 chars)

    Returns:
        str: JSON with {"id": str, "name": str, "url": str}
    """
    return await api.create_circuit(params.name)


@mcp.tool(
    name="tinkercad_add_component",
    annotations={
        "title": "Add Component to Circuit",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def tinkercad_add_component(params: ComponentInput) -> str:
    """Add an electronic component to the open circuit by drag-and-drop.

    Args:
        params.component_type (str): Key from component catalog
            (e.g. 'arduino_uno', 'led', 'resistor', 'breadboard')
        params.x (float): Drop X position on canvas in pixels (default 400)
        params.y (float): Drop Y position on canvas in pixels (default 300)

    Returns:
        str: JSON confirmation or error with list of valid component keys.
    """
    return await api.add_component(params.component_type, params.x, params.y)


@mcp.tool(
    name="tinkercad_connect_pins",
    annotations={
        "title": "Connect Component Pins",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def tinkercad_connect_pins(params: ConnectPinsInput) -> str:
    """Connect two component pins with a wire.

    Args:
        params.comp_a (str): Source component ID
        params.pin_a (str): Source pin label (e.g. 'GND', 'D13', '~5V', 'Anode')
        params.comp_b (str): Destination component ID
        params.pin_b (str): Destination pin label

    Returns:
        str: JSON {"wire": "compA:pinA → compB:pinB"} or error.
    """
    return await api.connect_pins(params.comp_a, params.pin_a, params.comp_b, params.pin_b)


class ConnectByCoordsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    src_x: float = Field(..., description="Source pin X position on canvas (pixels from left)")
    src_y: float = Field(..., description="Source pin Y position on canvas (pixels from top)")
    dst_x: float = Field(..., description="Destination pin X position on canvas (pixels from left)")
    dst_y: float = Field(..., description="Destination pin Y position on canvas (pixels from top)")


class ConnectHolesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    hole_a: str = Field(
        ...,
        description="Source breadboard hole notation (e.g. 'a5', 'f12', 'pwr_top_pos1'). "
                    "Call tinkercad_get_breadboard_grid first to see available holes.",
    )
    hole_b: str = Field(
        ...,
        description="Destination breadboard hole notation (e.g. 'e5', 'j12').",
    )


@mcp.tool(
    name="tinkercad_connect_pins_by_coords",
    annotations={
        "title": "Connect Pins by Canvas Coordinates",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def tinkercad_connect_pins_by_coords(params: ConnectByCoordsInput) -> str:
    """Connect two pins using raw canvas pixel coordinates.

    Use when tinkercad_connect_pins cannot resolve pin DOM elements.
    Coordinates are relative to the canvas top-left corner.

    Args:
        params.src_x, params.src_y: Source pin position on canvas
        params.dst_x, params.dst_y: Destination pin position on canvas

    Returns:
        str: JSON confirmation or error.
    """
    return await api.connect_pins_by_coords(
        params.src_x, params.src_y, params.dst_x, params.dst_y
    )


@mcp.tool(
    name="tinkercad_get_breadboard_grid",
    annotations={
        "title": "Get Breadboard Grid",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def tinkercad_get_breadboard_grid() -> str:
    """Scan the canvas for breadboard holes and return a structured grid map.

    Must be called before tinkercad_connect_breadboard_holes to get valid hole names.
    Returns hole notation (e.g. 'a5', 'f12', 'pwr_top_pos1') mapped to canvas coordinates.

    Returns:
        str: JSON with {"grid": {"a1": {"x":int,"y":int}, ...}, "cols": N, "rows": 10, "row_names": [...]}
    """
    return await api.get_breadboard_grid()


@mcp.tool(
    name="tinkercad_connect_breadboard_holes",
    annotations={
        "title": "Connect Breadboard Holes",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def tinkercad_connect_breadboard_holes(params: ConnectHolesInput) -> str:
    """Connect two breadboard holes with a wire.

    Use standard breadboard notation:
      - Main holes: row letter (a-j) + column number (e.g. 'a5', 'f12')
      - Power rails: 'pwr_top_pos1', 'pwr_top_neg1', 'pwr_bot_pos1', etc.

    Call tinkercad_get_breadboard_grid first to confirm hole names and columns.

    Args:
        params.hole_a (str): Source hole (e.g. 'a5')
        params.hole_b (str): Destination hole (e.g. 'e5')

    Returns:
        str: JSON wire confirmation or error with available holes.
    """
    return await api.connect_breadboard_holes(params.hole_a, params.hole_b)


@mcp.tool(
    name="tinkercad_add_code_to_arduino",
    annotations={
        "title": "Upload Arduino Sketch",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def tinkercad_add_code_to_arduino(params: ArduinoCodeInput) -> str:
    """Upload a C++ Arduino sketch to an Arduino component in the circuit.

    Args:
        params.comp_id (str): Arduino component ID on the canvas
        params.sketch (str): Full Arduino sketch source (setup + loop)

    Returns:
        str: Confirmation with character count or error.
    """
    return await api.add_code_to_arduino(params.comp_id, params.sketch)


@mcp.tool(
    name="tinkercad_start_simulation",
    annotations={
        "title": "Start Circuit Simulation",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def tinkercad_start_simulation() -> str:
    """Start the Tinkercad circuit simulation.

    Returns:
        str: 'Simulation started.' or error.
    """
    return await api.start_simulation()


@mcp.tool(
    name="tinkercad_stop_simulation",
    annotations={
        "title": "Stop Circuit Simulation",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def tinkercad_stop_simulation() -> str:
    """Stop the running Tinkercad circuit simulation.

    Returns:
        str: 'Simulation stopped.' or error.
    """
    return await api.stop_simulation()


@mcp.tool(
    name="tinkercad_get_simulation_output",
    annotations={
        "title": "Get Arduino Serial Monitor Output",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def tinkercad_get_simulation_output() -> str:
    """Read the Arduino Serial Monitor output from the running simulation.

    Returns:
        str: JSON {"output": "<serial text>"} or error/empty message.
    """
    return await api.get_simulation_output()


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
