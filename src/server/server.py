import os
import logging
from fastapi import FastAPI, Depends, HTTPException, Security, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security.api_key import APIKeyHeader
from contextlib import asynccontextmanager
from typing import AsyncIterator
from dotenv import load_dotenv

from src.core.task_manager import task_manager
from src.core.connection import get_or_create_global_connector
from src.api.routes import health, telemetry, action, sensors

# Load env variables
load_dotenv()

class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/sensors/internal/update" not in record.getMessage()

logging.getLogger("uvicorn.access").addFilter(EndpointFilter()) # filter the sensor updates 

API_KEY_NAME = "Auth-Key"
API_KEY = os.environ.get("CLOUD_API_KEY", "default-dev-key")
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header == API_KEY:
        return api_key_header
    raise HTTPException(status_code=401, detail="Could not validate credentials")

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Initialize drone connection on startup with implementation from Burkes et. al. project.
    await get_or_create_global_connector()
    yield
    await task_manager.close()

app = FastAPI(
    title="DroneServer",
    description="API for cloud-based drone control via MAVSDK.",
    version="1.0.0",
    lifespan=lifespan
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Catch 422 errors and print the exact request body and headers
    try:
        body = await request.body()
        body_text = body.decode('utf-8')
    except Exception:
        body_text = "Could not decode body"
        
    print("\n" + "="*50)
    print("422 VALIDATION ERROR")
    print(f"URL: {request.url}")
    print("Headers:", dict(request.headers))
    print("Raw Body:", body_text)
    print("Errors:", exc.errors())
    print("="*50 + "\n")
    
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": body_text},
    )

app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(telemetry.router, prefix="/telemetry", tags=["Telemetry"])
app.include_router(action.router, prefix="/action", tags=["Action"])
app.include_router(sensors.router, prefix="/sensors", tags=["Sensors"])

@app.get("/")
async def root():
    return {"message": "MAVLink bridge for cloud-based execution engine is running. See /docs for API documentation."}
