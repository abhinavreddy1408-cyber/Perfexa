"""
Step 7: WebSocket and Polling Live-Metrics Pipe.
Maintains live connections per run_id and broadcasts real-time snapshots
(active VUs, requests/sec, error rate, latency percentiles).
"""

import json
import logging
from typing import Dict, List, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("websocket_hub")


class ConnectionManager:
    def __init__(self):
        # run_id -> List[WebSocket]
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # run_id -> latest snapshot dict (for polling fallback)
        self.latest_snapshots: Dict[str, Dict[str, Any]] = {}

    async def connect(self, run_id: str, websocket: WebSocket):
        await websocket.accept()
        if run_id not in self.active_connections:
            self.active_connections[run_id] = []
        self.active_connections[run_id].append(websocket)
        logger.info(f"WebSocket client connected for run {run_id}. Total: {len(self.active_connections[run_id])}")

        # Send latest snapshot immediately if available
        if run_id in self.latest_snapshots:
            try:
                await websocket.send_json({
                    "type": "metric_snapshot",
                    "data": self.latest_snapshots[run_id]
                })
            except Exception:
                pass

    def disconnect(self, run_id: str, websocket: WebSocket):
        if run_id in self.active_connections:
            if websocket in self.active_connections[run_id]:
                self.active_connections[run_id].remove(websocket)
            if not self.active_connections[run_id]:
                del self.active_connections[run_id]
        logger.info(f"WebSocket client disconnected for run {run_id}")

    async def broadcast_metric(self, run_id: str, snapshot: Dict[str, Any]):
        """Broadcasts snapshot to all connected WebSocket clients for this run."""
        self.latest_snapshots[run_id] = snapshot
        
        if run_id not in self.active_connections:
            return

        dead_connections = []
        payload = {
            "type": "metric_snapshot",
            "run_id": run_id,
            "data": snapshot
        }

        for connection in self.active_connections[run_id]:
            try:
                await connection.send_json(payload)
            except Exception:
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(run_id, dead)

    async def broadcast_status(self, run_id: str, status: str, extra: Optional[Dict[str, Any]] = None):
        """Broadcasts test lifecycle status (e.g. STARTING, RUNNING, COMPLETED, FAILED)."""
        payload = {
            "type": "status_update",
            "run_id": run_id,
            "status": status,
            "data": extra or {}
        }
        if run_id in self.active_connections:
            for connection in list(self.active_connections[run_id]):
                try:
                    await connection.send_json(payload)
                except Exception:
                    pass

    def get_latest_metrics(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Polling fallback helper."""
        return self.latest_snapshots.get(run_id)


# Global WebSocket Hub Singleton
ws_manager = ConnectionManager()
