import math
from pydantic import BaseModel, Field
from typing import Optional

CALLBACK_DESCRIPTION = (
    "URL to PUT the result to when the action finishes. If set (or if the CPEE-CALLBACK "
    "header is sent), the request returns 202 immediately and runs in the background; "
    "otherwise it blocks and returns 200 with the result."
)

class CallbackRequest(BaseModel):
    """Body for actions that take no parameters besides the optional callback."""
    callback_url: Optional[str] = Field(None, description=CALLBACK_DESCRIPTION)

class TakeoffRequest(BaseModel):
    altitude: float = Field(3.0, description="Altitude to ascend to after takeoff in meters.")
    callback_url: Optional[str] = Field(None, description=CALLBACK_DESCRIPTION)

class LandRequest(BaseModel):
    force: bool = Field(False, description="Bypass safety checks if True.")
    callback_url: Optional[str] = Field(None, description=CALLBACK_DESCRIPTION)

class GotoRequest(BaseModel):
    latitude_deg: float = Field(..., description="Target latitude in degrees. Aliases: lat, latitude.")
    longitude_deg: float = Field(..., description="Target longitude in degrees. Aliases: lon, longitude.")
    absolute_altitude_m: float = Field(..., description="Target altitude above mean sea level in meters. Aliases: altitude, alt.")
    yaw_deg: float = Field(float('nan'), description="Target heading in degrees. Omit to keep the current heading.")
    callback_url: Optional[str] = Field(None, description=CALLBACK_DESCRIPTION)

class WebhookResponse(BaseModel):
    status: str
    task_id: str
    message: str

class MoveRelativeRequest(BaseModel):
    north_m: float = Field(..., description="Meters to move north (negative = south). Alias: north.")
    east_m: float = Field(..., description="Meters to move east (negative = west). Alias: east.")
    down_m: float = Field(..., description="Meters to move down (negative = up). Alias: down.")
    yaw_deg: float = Field(float('nan'), description="Target heading in degrees. Omit to keep the current heading.")
    callback_url: Optional[str] = Field(None, description=CALLBACK_DESCRIPTION)

class AlignToArucoRequest(BaseModel):
    marker_id: Optional[int] = Field(None, description="ID of the ArUco marker to align over. Omit to use the closest detected marker.")
    callback_url: Optional[str] = Field(None, description=CALLBACK_DESCRIPTION)

class SetFlightModeRequest(BaseModel):
    flight_mode: str = Field(..., description="One of HOLD, LOITER, RTL, RETURN_TO_LAUNCH, LAND, GUIDED. Alias: mode.")
    callback_url: Optional[str] = Field(None, description=CALLBACK_DESCRIPTION)


def request_docs(model: type[BaseModel]) -> dict:
    """
    OpenAPI documentation for an action route's parameters.

    The action routes parse their input manually (JSON, form data, query string, or the
    CPEE-CALLBACK header), so FastAPI cannot infer the body. This describes it for /docs
    without changing how requests are parsed.
    """
    schema = model.model_json_schema()
    for prop in schema.get("properties", {}).values():
        default = prop.get("default")
        if isinstance(default, float) and math.isnan(default):
            del prop["default"]  # NaN is not valid JSON and would break /openapi.json
    return {
        "parameters": [
            {
                "name": "CPEE-CALLBACK",
                "in": "header",
                "required": False,
                "schema": {"type": "string"},
                "description": "Callback URL sent by the CPEE engine. Equivalent to callback_url.",
            }
        ],
        "requestBody": {
            "required": bool(schema.get("required")),
            "content": {
                "application/json": {"schema": schema},
                "application/x-www-form-urlencoded": {"schema": schema},
            },
        },
    }


ACTION_RESPONSES: dict = {
    200: {
        "model": WebhookResponse,
        "description": "Synchronous call (no callback): the action has finished. task_id is \"sync\".",
    },
    202: {
        "description": "Asynchronous call (callback_url or CPEE-CALLBACK header given): the action was "
        "started in the background and the result will be PUT to the callback URL.",
    },
}
