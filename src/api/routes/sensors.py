from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from pydantic import BaseModel

router = APIRouter()

# Global state to store the latest sensor data from the standalone ROS2 node
SENSOR_STATE = {
    "product_detected": False,
    "product_bbox": None,
    "closest_obstacle_distance": None,
    "obstacle_front_m": None,
    "obstacle_left_m": None,
    "obstacle_right_m": None,
    "latest_image_base64": None,
    "latest_floor_image_base64": None,
    "qr_data": None,
    "aruco_data": None,
    "last_update": 0
}

class SensorUpdate(BaseModel):
    product_detected: bool
    product_bbox: dict | None = None
    closest_obstacle_distance: float
    obstacle_front_m: float | None = None
    obstacle_left_m: float | None = None
    obstacle_right_m: float | None = None
    latest_image_base64: str | None = None
    latest_floor_image_base64: str | None = None
    qr_data: dict | str | list | None = None
    aruco_data: dict | None = None

@router.post("/internal/update")
async def update_sensors(data: SensorUpdate):
    """Internal endpoint for the standalone ROS2 node to push sensor data."""
    import time
    global SENSOR_STATE
    SENSOR_STATE["product_detected"] = data.product_detected
    SENSOR_STATE["product_bbox"] = data.product_bbox
    SENSOR_STATE["closest_obstacle_distance"] = data.closest_obstacle_distance
    SENSOR_STATE["obstacle_front_m"] = data.obstacle_front_m
    SENSOR_STATE["obstacle_left_m"] = data.obstacle_left_m
    SENSOR_STATE["obstacle_right_m"] = data.obstacle_right_m
    SENSOR_STATE["latest_image_base64"] = data.latest_image_base64
    SENSOR_STATE["latest_floor_image_base64"] = data.latest_floor_image_base64
    SENSOR_STATE["qr_data"] = data.qr_data
    SENSOR_STATE["aruco_data"] = data.aruco_data
    SENSOR_STATE["last_update"] = time.time()
    return {"status": "ok"}

@router.get("/vision/product")
async def get_product_detection() -> Dict[str, Any]:
    """Returns whether the red product is currently detected by the drone's camera."""
    import time
    if time.time() - SENSOR_STATE["last_update"] > 5.0:
        raise HTTPException(status_code=503, detail="ROS2 Node data is stale or not running.")
        
    return {
        "status": "success",
        "product_detected": SENSOR_STATE["product_detected"],
        "product_bbox": SENSOR_STATE["product_bbox"]
    }

@router.get("/lidar/obstacle")
async def get_closest_obstacle() -> Dict[str, Any]:
    """Returns the distance to the closest obstacle detected by the Lidar, broken down by sector."""
    import time
    if time.time() - SENSOR_STATE["last_update"] > 5.0:
        raise HTTPException(status_code=503, detail="ROS2 Node data is stale or not running. Check the ROS2 node is running")
        
    def sanitize(dist: float | None) -> float | None:
        if dist is None or dist == -1.0:
            return None
        return dist

    closest = sanitize(SENSOR_STATE.get("closest_obstacle_distance"))
    front = sanitize(SENSOR_STATE.get("obstacle_front_m"))
    left = sanitize(SENSOR_STATE.get("obstacle_left_m"))
    right = sanitize(SENSOR_STATE.get("obstacle_right_m"))
        
    return {
        "status": "success",
        "closest_obstacle_distance_m": closest,
        "sectors": {
            "front_m": front,
            "left_m": left,
            "right_m": right
        }
    }

@router.get("/vision/image")
async def get_latest_image() -> Dict[str, Any]:
    """Returns the latest annotated image encoded in base64."""
    import time
    if time.time() - SENSOR_STATE["last_update"] > 5.0:
        raise HTTPException(status_code=503, detail="ROS2 Node data is stale or not running.")
        
    if not SENSOR_STATE["latest_image_base64"]:
        raise HTTPException(status_code=404, detail="Image not yet available")

    return {
        "status": "success",
        "image_base64": SENSOR_STATE["latest_image_base64"]
    }

@router.get("/vision/floor_image")
async def get_latest_floor_image() -> Dict[str, Any]:
    """Returns the latest annotated floor camera image encoded in base64."""
    import time
    if time.time() - SENSOR_STATE["last_update"] > 5.0:
        raise HTTPException(status_code=503, detail="ROS2 Node data is stale or not running.")
        
    if not SENSOR_STATE["latest_floor_image_base64"]:
        raise HTTPException(status_code=404, detail="Floor image not yet available")

    return {
        "status": "success",
        "image_base64": SENSOR_STATE["latest_floor_image_base64"]
    }

@router.get("/vision/qr")
async def get_latest_qr() -> Dict[str, Any]:
    """Returns the latest QR code data detected by the camera."""
    import time
    if time.time() - SENSOR_STATE["last_update"] > 5.0:
        raise HTTPException(status_code=503, detail="ROS2 Node data is stale or not running.")

    if SENSOR_STATE["qr_data"] is None:
        return {
            "status": "no qr detected",
            "qr_data": SENSOR_STATE["qr_data"]
        }

    return {
        "status": "success",
        "qr_data": SENSOR_STATE["qr_data"]
    }

@router.get("/vision/aruco")
async def get_latest_aruco() -> Dict[str, Any]:
    """Returns the latest ArUco marker data detected by the downward floor camera."""
    import time
    if time.time() - SENSOR_STATE["last_update"] > 5.0:
        raise HTTPException(status_code=503, detail="ROS2 Node data is stale or not running.")

    if SENSOR_STATE["aruco_data"] is None:
        return {
            "status": "no aruco detected",
            "marker_count": 0,
            "stages": {
                "is_shelf_start": False,
                "is_shelf_end": False,
                "is_landing_pad": False
            }
        }

    return {
        "status": "success",
        **SENSOR_STATE["aruco_data"]
    }
