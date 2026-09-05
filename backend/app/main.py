"""
Main FastAPI Application Entrypoint.
Wires database initialization, routes, WebSocket, and static frontend hosting.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.database import init_db
from backend.app.api.routes import router as api_router
from backend.app.api.websocket import ws_manager

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database tables
    await init_db()
    yield
    # Shutdown logic if needed


app = FastAPI(
    title="AI-Powered Autonomous Performance Testing Platform",
    description="Transforms plain-English test descriptions into autonomous, validated k6 load tests with real-time analytics and AI diagnostics.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(api_router)


# WebSocket live metrics endpoint
@app.websocket("/ws/runs/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str):
    await ws_manager.connect(run_id, websocket)
    try:
        while True:
            # Keep-alive receive loop
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(run_id, websocket)
    except Exception:
        ws_manager.disconnect(run_id, websocket)


from fastapi.responses import FileResponse

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "performance-testing-backend"}


@app.get("/landing")
async def landing_route():
    return FileResponse(FRONTEND_DIR / "landing.html")


@app.get("/app")
async def app_route():
    return FileResponse(FRONTEND_DIR / "app.html")


# Mount frontend static directory if index.html exists
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=False)
