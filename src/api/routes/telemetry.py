from fastapi import APIRouter, HTTPException
from src.core.connection import get_or_create_global_connector, ensure_connection
from typing import Dict, Any

router = APIRouter()

@router.get("/position")
async def get_position() -> Dict[str, Any]:
    connector = await get_or_create_global_connector()
    if not await ensure_connection(connector, timeout=5.0):
        raise HTTPException(status_code=503, detail="Drone connection not ready")
        
    drone = connector.drone
    try:
        position = await drone.telemetry.position().__anext__()
        try:
            heading = await drone.telemetry.heading().__anext__()
            yaw_deg = heading.heading_deg
        except Exception:
            yaw_deg = 0.0
            
        return {
            "status": "success",
            "position": {
                "latitude_deg": position.latitude_deg,
                "longitude_deg": position.longitude_deg,
                "absolute_altitude_m": position.absolute_altitude_m,
                "relative_altitude_m": position.relative_altitude_m,
                "yaw_deg": yaw_deg
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    raise HTTPException(status_code=500, detail="Failed to get position")

@router.get("/battery")
async def get_battery() -> Dict[str, Any]:
    connector = await get_or_create_global_connector()
    if not await ensure_connection(connector, timeout=5.0):
        raise HTTPException(status_code=503, detail="Drone connection not ready")
        
    drone = connector.drone
    try:
        async for battery in drone.telemetry.battery():
            return {
                "status": "success",
                "battery": {
                    "voltage_v": round(battery.voltage_v, 2),
                    "remaining_percent": round(battery.remaining_percent * 100, 1),
                }
            }
            break
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    raise HTTPException(status_code=500, detail="Failed to get battery")

@router.get("/flight-mode")
async def get_flight_mode() -> Dict[str, Any]:
    connector = await get_or_create_global_connector()
    if not await ensure_connection(connector, timeout=5.0):
        raise HTTPException(status_code=503, detail="Drone connection not ready")
        
    drone = connector.drone
    try:
        async for flight_mode in drone.telemetry.flight_mode():
            return {
                "status": "success",
                "flight_mode": str(flight_mode),
            }
            break
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    raise HTTPException(status_code=500, detail="Failed to get flight mode")

    