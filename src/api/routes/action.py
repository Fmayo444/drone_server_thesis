from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from typing import Dict, Any
from src.api.models import (
    TakeoffRequest, LandRequest, GotoRequest, MoveRelativeRequest, WebhookResponse,
    CallbackRequest, AlignToArucoRequest, SetFlightModeRequest, request_docs, ACTION_RESPONSES,
)
from src.core.task_manager import task_manager
from src.core.connection import get_or_create_global_connector, ensure_connection
import math
import asyncio
from fastapi import Request, Response

router = APIRouter()

async def parse_request_data(request: Request) -> dict:
    data = {}
    
    cpee_callback = request.headers.get("cpee-callback")
    if cpee_callback:
        data["callback_url"] = cpee_callback

    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        try:
            form = await request.form()
            for k, v in form.items():
                data[k.lower()] = v
        except Exception as e:
            print(f"Error parsing form data: {e}")
    elif "application/json" in content_type:
        try:
            json_data = await request.json()
            for k, v in json_data.items():
                data[k.lower()] = v
        except:
            pass
            
    for k, v in request.query_params.items():
        if k.lower() not in data:
            data[k.lower()] = v
            
    return data

async def execute_takeoff(altitude: float) -> Dict[str, Any]:
    connector = await get_or_create_global_connector()
    if not await ensure_connection(connector):
        raise HTTPException(status_code=408, detail="Drone connection timeout")
    
    drone = connector.drone
    
    # The drone MUST be armed before it can actually take off
    try:
        await drone.action.arm()
    except Exception as e:
        # If the error is not about it already being armed, abort takeoff
        if "already armed" not in str(e).lower() and "command denied" not in str(e).lower():
            pass # ignore unknown edge cases
        
        # Check if it actually is armed
        async for armed in drone.telemetry.armed():
            if not armed:
                raise Exception(f"Takeoff aborted: Could not arm the drone. Health status might not be ready. Error: {e}")
            break
        
    await drone.action.set_takeoff_altitude(altitude)
    await drone.action.takeoff()

    print(f"         Taking off, waiting for altitude {altitude}m...")

    # Wait until altitude is reached
    altitude_threshold = 0.5
    max_wait_time = 60
    check_interval = 1.0
    elapsed_time = 0
    
    while elapsed_time < max_wait_time:
        async for position in drone.telemetry.position():
            current_alt = position.relative_altitude_m
            if current_alt >= (altitude - altitude_threshold):
                return {
                    "status": "success",
                    "altitude_reached_m": round(current_alt, 1),
                    "target_altitude_m": altitude
                }
            break
        await asyncio.sleep(check_interval)
        elapsed_time += check_interval
        
    raise Exception(f"Takeoff timeout after {max_wait_time}s")

@router.post("/arm", response_model=WebhookResponse, status_code=202, responses=ACTION_RESPONSES, openapi_extra=request_docs(CallbackRequest))
async def arm(request: Request, response: Response):
    """Arms the drone. Supports JSON, Form-data, and CPEE Engine headers."""
    data = await parse_request_data(request)
    callback_url = data.get("callback_url")

    if callback_url:
        task_id = task_manager.start_task(execute_arm(), callback_url)
        response.headers["CPEE-CALLBACK"] = "true"
        return WebhookResponse(status="accepted", task_id=task_id, message="Arming initiated. Callback will be sent upon completion.")
    
    try:
        result = await execute_arm()
        response.status_code = 200
        return WebhookResponse(status="success", task_id="sync", message=str(result))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/takeoff", response_model=WebhookResponse, status_code=202, responses=ACTION_RESPONSES, openapi_extra=request_docs(TakeoffRequest))
async def takeoff(request: Request, response: Response):
    """Initiates takeoff. Supports JSON, Form-data, and CPEE Engine headers."""
    data = await parse_request_data(request)
    altitude = float(data.get("altitude", 3.0))
    callback_url = data.get("callback_url")

    if callback_url:
        task_id = task_manager.start_task(execute_takeoff(altitude), callback_url)
        response.headers["CPEE-CALLBACK"] = "true"
        return WebhookResponse(status="accepted", task_id=task_id, message="Takeoff initiated. Callback will be sent upon completion.")
    
    # Synchronous path if no callback
    try:
        result = await execute_takeoff(altitude)
        response.status_code = 200
        return WebhookResponse(status="success", task_id="sync", message=str(result))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def execute_land(force: bool) -> Dict[str, Any]:
    connector = await get_or_create_global_connector()
    if not await ensure_connection(connector):
        raise HTTPException(status_code=408, detail="Drone connection timeout")
    
    drone = connector.drone
    connector.pending_destination = None
    connector.landing_in_progress = True
    
    await drone.action.land()
    
    # Wait until landed
    max_wait_time = 120
    check_interval = 2.0
    elapsed_time = 0
    while elapsed_time < max_wait_time:
        async for in_air in drone.telemetry.in_air():
            if not in_air:
                return {"status": "success", "message": "Drone landed safely"}
            break
        await asyncio.sleep(check_interval)
        elapsed_time += check_interval
        
    raise Exception("Landing timeout or not detected")

@router.post("/land", response_model=WebhookResponse, status_code=202, responses=ACTION_RESPONSES, openapi_extra=request_docs(LandRequest))
async def land(request: Request, response: Response):
    data = await parse_request_data(request)
    force = str(data.get("force", "")).lower() in ("true", "1", "yes")
    callback_url = data.get("callback_url")

    if callback_url:
        task_id = task_manager.start_task(execute_land(force), callback_url)
        response.headers["CPEE-CALLBACK"] = "true"
        return WebhookResponse(status="accepted", task_id=task_id, message="Landing initiated. Callback will be sent upon completion.")
    
    try:
        result = await execute_land(force)
        response.status_code = 200
        return WebhookResponse(status="success", task_id="sync", message=str(result))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def distance_3d(lat1, lon1, alt1, lat2, lon2, alt2):
    horizontal_dist = haversine_distance(lat1, lon1, lat2, lon2)
    vertical_dist = alt2 - alt1
    return math.sqrt(horizontal_dist**2 + vertical_dist**2)

async def execute_go_home() -> Dict[str, Any]:
    connector = await get_or_create_global_connector()
    if not await ensure_connection(connector):
        raise HTTPException(status_code=408, detail="Drone connection timeout")
    
    drone = connector.drone
    await drone.action.set_return_to_launch_altitude(3.5) 
    
    try:
        print(" Going home...")
        await drone.action.return_to_launch()
    except Exception as e:
        raise Exception(f"Failed to go home: {str(e)}")
        
    return {"status": "success", "message": "Drone going home..."}

@router.post("/go_home", response_model=WebhookResponse, status_code=202, responses=ACTION_RESPONSES, openapi_extra=request_docs(CallbackRequest))
async def go_home(request: Request, response: Response):
    data = await parse_request_data(request)
    callback_url = data.get("callback_url")

    if callback_url:
        task_id = task_manager.start_task(execute_go_home(), callback_url)
        response.headers["CPEE-CALLBACK"] = "true"
        return WebhookResponse(status="accepted", task_id=task_id, message="Drone going home. Callback will be sent upon completion.")
    
    try:
        result = await execute_go_home()
        response.status_code = 200
        return WebhookResponse(status="success", task_id="sync", message=str(result))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def execute_goto(req: GotoRequest) -> Dict[str, Any]:
    connector = await get_or_create_global_connector()
    if not await ensure_connection(connector):
        raise HTTPException(status_code=408, detail="Drone connection timeout")
    
    drone = connector.drone
    await drone.action.goto_location(req.latitude_deg, req.longitude_deg, req.absolute_altitude_m, req.yaw_deg)
    
    # Wait until destination is reached
    threshold = 0.15
    max_wait_time = 300
    check_interval = 1.0
    elapsed_time = 0
    
    while elapsed_time < max_wait_time:
        async for pos in drone.telemetry.position():
            dist = distance_3d(pos.latitude_deg, pos.longitude_deg, pos.absolute_altitude_m, req.latitude_deg, req.longitude_deg, req.absolute_altitude_m)
            if dist <= threshold:
                return {"status": "success", "message": "Destination reached"}
            break
        await asyncio.sleep(check_interval)
        elapsed_time += check_interval
        
    raise Exception("Goto timeout")

@router.post("/goto", response_model=WebhookResponse, status_code=202, responses=ACTION_RESPONSES, openapi_extra=request_docs(GotoRequest))
async def goto(request: Request, response: Response):
    data = await parse_request_data(request)
    
    lat = data.get("latitude_deg") or data.get("lat") or data.get("latitude")
    lon = data.get("longitude_deg") or data.get("lon") or data.get("longitude")
    alt = data.get("absolute_altitude_m") or data.get("altitude") or data.get("alt")
    
    if lat is None or lon is None or alt is None:
        print(f"GOTO ERROR: Missing parameters. Parsed data: {data}")
        raise HTTPException(status_code=422, detail=f"Missing required parameters. Received: {list(data.keys())}")
        
    goto_req = GotoRequest(
        latitude_deg=float(lat),
        longitude_deg=float(lon),
        absolute_altitude_m=float(alt),
        yaw_deg=float(data.get("yaw_deg", float('nan'))),
        callback_url=data.get("callback_url")
    )

    if goto_req.callback_url:
        task_id = task_manager.start_task(execute_goto(goto_req), goto_req.callback_url)
        response.headers["CPEE-CALLBACK"] = "true"
        return WebhookResponse(status="accepted", task_id=task_id, message="Navigation started. Callback will be sent upon arrival.")
    
    try:
        result = await execute_goto(goto_req)
        response.status_code = 200
        return WebhookResponse(status="success", task_id="sync", message=str(result))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def execute_move_relative(req: MoveRelativeRequest) -> Dict[str, Any]:
    connector = await get_or_create_global_connector()
    if not await ensure_connection(connector):
        raise HTTPException(status_code=408, detail="Drone connection timeout")
    
    drone = connector.drone

    # Get current position and heading
    position = await drone.telemetry.position().__anext__()
    current_lat = position.latitude_deg
    current_lon = position.longitude_deg
    current_alt = position.absolute_altitude_m
    
    try:
        heading = await drone.telemetry.heading().__anext__()
        current_heading_deg = heading.heading_deg
    except Exception as e:
        print(f"Warning: Could not get drone heading, defaulting to 0.0: {e}")
        current_heading_deg = 0.0

    # Calculate target altitude (down is positive in NED, so negate)
    target_alt = current_alt - req.down_m
    
    # Rotate body-frame relative offsets (north_m = forward, east_m = right)
    # by current drone heading to get earth-frame offsets (North, East)
    heading_rad = math.radians(current_heading_deg)
    north_earth_m = req.north_m * math.cos(heading_rad) - req.east_m * math.sin(heading_rad)
    east_earth_m = req.north_m * math.sin(heading_rad) + req.east_m * math.cos(heading_rad)

    # Convert NED earth offsets (meters) to lat/lon offsets (degrees)
    lat_offset_deg = north_earth_m / 111320.0
    lon_offset_deg = east_earth_m / (111320.0 * math.cos(math.radians(current_lat)))
    
    # Calculate target position
    target_lat = current_lat + lat_offset_deg
    target_lon = current_lon + lon_offset_deg
    
    # Determine target yaw. If not explicitly provided, lock to current heading
    # so the drone doesn't automatically rotate to face the direction of travel.
    target_yaw = req.yaw_deg
    if math.isnan(target_yaw):
        target_yaw = current_heading_deg
        
    # await drone.set_current_speed(0.8) # speed tuning
    await drone.action.goto_location(target_lat, target_lon, target_alt, target_yaw)
    
    # Wait until destination is reached
    threshold = 0.65
    max_wait_time = 300
    check_interval = 1.5
    elapsed_time = 0
    
    while elapsed_time < max_wait_time:
        async for pos in drone.telemetry.position():
            dist = distance_3d(pos.latitude_deg, pos.longitude_deg, pos.absolute_altitude_m, target_lat, target_lon, target_alt)
            if dist <= threshold:
                return {"status": "success", "message": "Relative destination reached"}
            break
        await asyncio.sleep(check_interval)
        elapsed_time += check_interval
        
    raise Exception("Move relative timeout")

@router.post("/move_relative", response_model=WebhookResponse, status_code=202, responses=ACTION_RESPONSES, openapi_extra=request_docs(MoveRelativeRequest))
async def move_relative(request: Request, response: Response):
    # north:positive for north and negative for south
    # east:positive for east and negative for west
    # down:positive for down and negative for up 
    # yaw:positive for right and negative for left


    data = await parse_request_data(request)

    north_m = data.get("north_m") if data.get("north_m") is not None else data.get("north")
    east_m = data.get("east_m") if data.get("east_m") is not None else data.get("east")
    down_m = data.get("down_m") if data.get("down_m") is not None else data.get("down")
    
    if north_m is None or east_m is None or down_m is None:
        print(f"ERROR: Missing parameters. Parsed data: {data}")
        raise HTTPException(status_code=422, detail=f"Missing required parameters. Received: {list(data.keys())}")
        
    move_req = MoveRelativeRequest(
        north_m=float(north_m),
        east_m=float(east_m),
        down_m=float(down_m),
        yaw_deg=float(data.get("yaw_deg", float('nan'))),
        callback_url=data.get("callback_url")
    )

    if move_req.callback_url:
        task_id = task_manager.start_task(execute_move_relative(move_req), move_req.callback_url)
        response.headers["CPEE-CALLBACK"] = "true"
        return WebhookResponse(status="accepted", task_id=task_id, message="Relative navigation started. Callback will be sent upon arrival.")
    
    try:
        result = await execute_move_relative(move_req)
        response.status_code = 200
        return WebhookResponse(status="success", task_id="sync", message=str(result))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def execute_align_to_aruco(marker_id: int | None = None) -> Dict[str, Any]:
    connector = await get_or_create_global_connector()
    if not await ensure_connection(connector):
        raise HTTPException(status_code=408, detail="Drone connection timeout")
    
    drone = connector.drone
    
    from src.api.routes.sensors import SENSOR_STATE
    import time
    
    print(f"         Aligning to ArUco marker {marker_id if marker_id is not None else 'closest'}...")
    
    max_wait = 60 # Max execution time
    start_time = time.time()
    threshold_px = 30 # Pixel error threshold
    
    while time.time() - start_time < max_wait:
        aruco_data = SENSOR_STATE.get("aruco_data")
        
        if not aruco_data or not aruco_data.get("markers"):
            # No markers visible right now, just wait
            await asyncio.sleep(0.5)
            continue
            
        markers = aruco_data["markers"]
        res = aruco_data.get("resolution", {"width": 640, "height": 480})
        center_x = res["width"] / 2.0
        center_y = res["height"] / 2.0
        
        target = None
        if marker_id is not None:
            for m in markers:
                if m["id"] == marker_id:
                    target = m
                    break
        else:
            # Find closest to center
            def dist_to_center(m):
                return (m["center"]["x"] - center_x)**2 + (m["center"]["y"] - center_y)**2
            target = min(markers, key=dist_to_center)
            
        if not target:
            # Specific marker not found in frame
            await asyncio.sleep(0.5)
            continue
            
        err_x = target["center"]["x"] - center_x
        err_y = target["center"]["y"] - center_y
        
        print(f"         Alignment_error: X={err_x:.1f}px, Y={err_y:.1f}px")
        
        if abs(err_x) < threshold_px and abs(err_y) < threshold_px:
            print("        Alignment successful!")
            return {"status": "success", "message": f"Successfully aligned to marker {target['id']}"}
            
        # Alignment
        try:
            position = await drone.telemetry.position().__anext__()
            current_alt = max(0.5, position.relative_altitude_m)
            current_lat = position.latitude_deg
            current_lon = position.longitude_deg
            abs_alt = position.absolute_altitude_m
        except Exception:
            # Fallback if telemetry fails
            current_alt = 3.0
            continue 
            
        # Dynamic Kp scaling based on altitude.
        kp = 0.002 * current_alt

        # err_x > 0 means marker is on the right. Move right (positive East) to center it.
        move_east = err_x * kp
        # err_y > 0 means marker is on the bottom. Move BACKWARDS (negative North) to center it.
        move_north = -err_y * kp
        
        move_east = max(-0.2, min(0.2, move_east))
        move_north = max(-0.2, min(0.2, move_north))
        
        # Calculate target position using current heading
        try:
            heading = await drone.telemetry.heading().__anext__()
            current_heading_deg = heading.heading_deg
        except Exception:
            current_heading_deg = 0.0
            
        heading_rad = math.radians(current_heading_deg)
        north_earth_m = move_north * math.cos(heading_rad) - move_east * math.sin(heading_rad)
        east_earth_m = move_north * math.sin(heading_rad) + move_east * math.cos(heading_rad)
        
        lat_offset_deg = north_earth_m / 111320.0
        lon_offset_deg = east_earth_m / (111320.0 * math.cos(math.radians(current_lat)))
        
        target_lat = current_lat + lat_offset_deg
        target_lon = current_lon + lon_offset_deg
        
        # Move to calculated location
        await drone.action.goto_location(
            target_lat, 
            target_lon, 
            abs_alt, 
            current_heading_deg
        )
        
        # wait for stabilization
        await asyncio.sleep(1.2)
        
    raise Exception("ArUco alignment timeout (marker lost or could not stabilize)")

@router.post("/align_to_aruco", response_model=WebhookResponse, status_code=202, responses=ACTION_RESPONSES, openapi_extra=request_docs(AlignToArucoRequest))
async def align_to_aruco(request: Request, response: Response):
    """Aligns the drone directly over an ArUco marker using the floor camera."""
    data = await parse_request_data(request)
    
    marker_id = data.get("marker_id")
    if marker_id is not None:
        marker_id = int(marker_id)
        
    callback_url = data.get("callback_url")
    
    if callback_url:
        task_id = task_manager.start_task(execute_align_to_aruco(marker_id), callback_url)
        response.headers["CPEE-CALLBACK"] = "true"
        return WebhookResponse(status="accepted", task_id=task_id, message="Alignment started. Callback will be sent upon completion.")
    
    try:
        result = await execute_align_to_aruco(marker_id)
        response.status_code = 200
        return WebhookResponse(status="success", task_id="sync", message=str(result))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def execute_set_flight_mode(flight_mode: str) -> Dict[str, Any]:
    connector = await get_or_create_global_connector()
    if not await ensure_connection(connector):
        raise HTTPException(status_code=408, detail="Drone connection timeout")
    
    drone = connector.drone
    mode_upper = flight_mode.upper().strip()

    supported_modes = {
        "HOLD": "hold",
        "LOITER": "hold",  # LOITER maps to hold action
        "RTL": "return_to_launch",
        "RETURN_TO_LAUNCH": "return_to_launch",
        "LAND": "land",
        "GUIDED": "guided",
    }   
    
    if mode_upper not in supported_modes:
        raise HTTPException(status_code=422, detail=f"Unsupported mode: {flight_mode}. Supported modes: {', '.join(supported_modes.keys())}")
        
    try:
        action_name = supported_modes[mode_upper]
    
        if action_name == "hold":
            print("         Setting flight mode to HOLD")
            await drone.action.hold()
            result_mode = "HOLD"
        
        elif action_name == "return_to_launch":
            print("         Setting flight mode to RTL")
            await drone.action.return_to_launch()
            result_mode = "RTL"
        
        elif action_name == "land":
            print("         Setting flight mode to LAND")
            await drone.action.land()
            result_mode = "LAND"
        
        elif action_name == "guided":
            print("         Setting flight mode to GUIDED")
            # For GUIDED, we need to send a position command to enter GUIDED mode
            # Get current position and command drone to hold there
            async for position in drone.telemetry.position():
                await drone.action.goto_location(
                    position.latitude_deg,
                    position.longitude_deg,
                    position.absolute_altitude_m,
                    float('nan')  # Maintain current yaw
                )
                break
            result_mode = "GUIDED"
    
        # Wait a moment for mode to change
        await asyncio.sleep(0.5)
        
        actual_mode = "UNKNOWN"
        try:
            async for new_mode in drone.telemetry.flight_mode():
                actual_mode = str(new_mode)
                break
        except:
            pass

        return {
            "status": "success",
            "message": f"Flight mode changed to {result_mode}",
            "actual_mode": actual_mode
        }
    except Exception as e:
        raise Exception(f"Failed to set flight mode: {str(e)}")


# NEED TEST
@router.post("/set_flight_mode", response_model=WebhookResponse, status_code=202, responses=ACTION_RESPONSES, openapi_extra=request_docs(SetFlightModeRequest))
async def set_flight_mode(request: Request, response: Response):
    data = await parse_request_data(request)
    
    flight_mode = data.get("flight_mode") or data.get("mode")
    callback_url = data.get("callback_url")

    if not flight_mode:
        raise HTTPException(status_code=422, detail="Missing parameter: 'flight_mode' or 'mode'")

    if callback_url:
        task_id = task_manager.start_task(execute_set_flight_mode(flight_mode), callback_url)
        response.headers["CPEE-CALLBACK"] = "true"
        return WebhookResponse(status="accepted", task_id=task_id, message=f"Setting flight mode to {flight_mode}. Callback will be sent upon completion.")
    
    try:
        result = await execute_set_flight_mode(flight_mode)
        response.status_code = 200
        return WebhookResponse(status="success", task_id="sync", message=str(result))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def execute_disarm() -> Dict[str, Any]:
    connector = await get_or_create_global_connector()
    if not await ensure_connection(connector):
        raise HTTPException(status_code=408, detail="Drone connection timeout")
    
    drone = connector.drone
    
    # Check if drone is in air
    in_air = False
    try:
        async for state in drone.telemetry.in_air():
            in_air = state
            break
    except Exception as e:
        print(f"Warning: could not get in_air telemetry: {e}")
        raise Exception(f"Could not verify if drone is landed: {e}")
        
    if in_air:
        raise HTTPException(status_code=400, detail="Cannot disarm: Drone is currently in the air")
        
    # Proceed to disarm
    try:
        print("         Disarming drone...")
        await drone.action.disarm()
    except Exception as e:
        raise Exception(f"Failed to disarm drone: {str(e)}")
        
    return {"status": "success", "message": "Drone disarmed successfully"}

@router.post("/disarm", response_model=WebhookResponse, status_code=202, responses=ACTION_RESPONSES, openapi_extra=request_docs(CallbackRequest))
async def disarm(request: Request, response: Response):
    """Disarms the drone, but only if it is on the ground."""
    data = await parse_request_data(request)
    callback_url = data.get("callback_url")

    if callback_url:
        task_id = task_manager.start_task(execute_disarm(), callback_url)
        response.headers["CPEE-CALLBACK"] = "true"
        return WebhookResponse(status="accepted", task_id=task_id, message="Disarming initiated. Callback will be sent upon completion.")
    
    try:
        result = await execute_disarm()
        response.status_code = 200
        return WebhookResponse(status="success", task_id="sync", message=str(result))
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def execute_return_to_launch() -> Dict[str, Any]:
    connector = await get_or_create_global_connector()
    if not await ensure_connection(connector):
        raise HTTPException(status_code=408, detail="Drone connection timeout")
    
    drone = connector.drone
    connector.pending_destination = None
    
    try:
        print("         Returning to launch...")
        await drone.action.return_to_launch()
    except Exception as e:
        raise Exception(f"Failed to return to launch: {str(e)}")
        
    # Wait until landed (RTL could take longer depending on distance, setting to 10 mins)
    max_wait_time = 600
    check_interval = 2.0
    elapsed_time = 0
    while elapsed_time < max_wait_time:
        async for in_air in drone.telemetry.in_air():
            if not in_air:
                return {"status": "success", "message": "Drone returned to launch and landed safely"}
            break
        await asyncio.sleep(check_interval)
        elapsed_time += check_interval
        
    raise Exception("Return to launch timeout or landing not detected")
    
@router.post("/return_to_launch", response_model=WebhookResponse, status_code=202, responses=ACTION_RESPONSES, openapi_extra=request_docs(CallbackRequest))
async def return_to_launch(request: Request, response: Response):
    """Commands the drone to return to its launch position and land."""
    data = await parse_request_data(request)
    callback_url = data.get("callback_url")
    if callback_url:
        task_id = task_manager.start_task(execute_return_to_launch(), callback_url)
        response.headers["CPEE-CALLBACK"] = "true"
        return WebhookResponse(status="accepted", task_id=task_id, message="Return to launch initiated. Callback will be sent upon completion.")
    
    try:
        result = await execute_return_to_launch()
        response.status_code = 200
        return WebhookResponse(status="success", task_id="sync", message=str(result))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))