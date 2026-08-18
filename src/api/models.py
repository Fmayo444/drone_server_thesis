from pydantic import BaseModel, Field
from typing import Optional

class TakeoffRequest(BaseModel):
    altitude: float = Field(10.0, description="Altitude to ascend to after takeoff in meters.")
    callback_url: Optional[str] = Field(None, description="Callback URL to call when takeoff is complete.")

class LandRequest(BaseModel):
    force: bool = Field(False, description="Bypass safety checks if True.")
    callback_url: Optional[str] = Field(None, description="Callback URL to call when landing is complete.")

class GotoRequest(BaseModel):
    latitude_deg: float
    longitude_deg: float
    absolute_altitude_m: float
    yaw_deg: float = float('nan')
    callback_url: Optional[str] = Field(None, description="Callback URL to call when destination is reached.")

class WebhookResponse(BaseModel):
    status: str
    task_id: str
    message: str

class MoveRelativeRequest(BaseModel):
    north_m: float
    east_m: float
    down_m: float
    yaw_deg: float = float('nan')
    callback_url: Optional[str] = Field(None, description="Callback URL to call when destination is reached.")
