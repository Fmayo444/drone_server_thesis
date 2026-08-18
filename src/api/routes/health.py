from fastapi import APIRouter, HTTPException
from src.core.connection import get_or_create_global_connector, ensure_connection
from typing import Dict, Any

router = APIRouter()

@router.get("")
async def get_health() -> Dict[str, Any]:
    connector = await get_or_create_global_connector()
    if not await ensure_connection(connector, timeout=5.0):
        raise HTTPException(status_code=503, detail="Drone connection not ready")
        
    drone = connector.drone
    try:
        async for health in drone.telemetry.health():
            return {
                "status": "success",
                "health": {
                    "is_gyrometer_calibrated": health.is_gyrometer_calibration_ok,
                    "is_accelerometer_calibrated": health.is_accelerometer_calibration_ok,
                    "is_magnetometer_calibrated": health.is_magnetometer_calibration_ok,
                    "is_global_position_ok": health.is_global_position_ok,
                    "is_armable": health.is_armable,
                }
            }
            break
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    raise HTTPException(status_code=500, detail="Failed to get health")
