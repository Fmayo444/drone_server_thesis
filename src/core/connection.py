import asyncio
import os
import logging
from dataclasses import dataclass, field
from mavsdk import System

logger = logging.getLogger("droneserver")
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, log_level, logging.INFO))

# Add console handler if it doesn't already have one
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter('%(asctime)s | %(levelname)-7s | %(message)s', datefmt='%H:%M:%S')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    logger.propagate = False

class LogColors:
    """ANSI color codes for colored terminal output"""
    RESET = '\033[0m'
    ERROR = '\033[31m'

@dataclass
class MAVLinkConnector:
    drone: System
    connection_ready: asyncio.Event = field(default_factory=asyncio.Event)
    pending_destination: dict | None = field(default=None)
    landing_in_progress: bool = field(default=False)

_global_connector: MAVLinkConnector | None = None
_connection_task: asyncio.Task | None = None
_connection_lock = asyncio.Lock()

async def ensure_connection(connector: MAVLinkConnector, timeout: float = 30.0) -> bool:
    """Wait for the drone connection to be ready."""
    try:
        await asyncio.wait_for(connector.connection_ready.wait(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        logger.error(f"{LogColors.ERROR}❌ Drone connection timeout after {timeout}s{LogColors.RESET}")
        return False

async def connect_drone_background(drone: System, address: str, port: str, protocol: str, connection_ready: asyncio.Event):
    """Connect to drone in the background without blocking server startup"""
    connection_string = f"{protocol}://{address}:{port}"
    logger.info("Background: Connecting to drone...")
    logger.info("  Protocol: %s", protocol.upper())
    logger.info("  Target: %s:%s", address, port)
    
    await drone.connect(system_address=connection_string)

    logger.info("Background: Waiting for drone to respond...")
    async for state in drone.core.connection_state():
        if state.is_connected:
            logger.info("=" * 60)
            logger.info("✓ SUCCESS: Connected to drone at %s:%s!", address, port)
            logger.info("=" * 60)
            break

    logger.info("Background: Waiting for GPS lock...")
    async for health in drone.telemetry.health():
        if health.is_global_position_ok or health.is_home_position_ok:
            logger.info("=" * 60)
            logger.info("✓ GPS LOCK ACQUIRED")
            logger.info("  Global position: %s", "OK" if health.is_global_position_ok else "Not ready")
            logger.info("  Home position: %s", "OK" if health.is_home_position_ok else "Not ready")
            logger.info("=" * 60)
            logger.info("Drone is READY for commands")
            logger.info("=" * 60)
            connection_ready.set()
            break

async def get_or_create_global_connector() -> MAVLinkConnector:
    """Get or create the global drone connector (thread-safe)"""
    global _global_connector, _connection_task
    
    async with _connection_lock:
        if _global_connector is not None:
            return _global_connector
        
        logger.info("=" * 60)
        logger.info("REST Server - Initializing Global Drone Connection")
        logger.info("=" * 60)
        
        address = os.environ.get("MAVLINK_ADDRESS", "")
        port = os.environ.get("MAVLINK_PORT", "14540")
        protocol = os.environ.get("MAVLINK_PROTOCOL", "udp").lower()
        
        if protocol not in ["tcp", "udp", "serial"]:
            protocol = "udp"
        
        drone = System()
        connection_ready = asyncio.Event()
        
        _global_connector = MAVLinkConnector(drone=drone, connection_ready=connection_ready)
        
        logger.info("Starting persistent drone connection in background...")
        
        _connection_task = asyncio.create_task(
            connect_drone_background(drone, address, port, protocol, connection_ready)
        )
        
        return _global_connector
