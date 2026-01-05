"""
FastAPI Web Interface để xem logs.
Chạy: uvicorn src.web.log_viewer:app --reload
Truy cập: http://localhost:8000
"""
import os
import json
import glob
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict


class LogEntry(BaseModel):
    """Model cho một log entry."""
    model_config = ConfigDict(extra='allow')  # Cho phép dynamic fields
    
    timestamp: str
    level: str
    event: str
    component: str
    execution_id: Optional[str] = None


class LogViewer:
    """Service để đọc và parse logs."""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
    
    def get_log_files(self) -> List[str]:
        """Lấy danh sách tất cả log files."""
        pattern = str(self.log_dir / "*.log")
        files = glob.glob(pattern)
        return [Path(f).name for f in files]
    
    def parse_log_file(self, filename: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """Parse một log file và trả về list các log entries."""
        filepath = self.log_dir / filename
        if not filepath.exists():
            return []
        
        entries = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        entry = json.loads(line)
                        entries.append(entry)
                    except json.JSONDecodeError:
                        # Skip invalid JSON lines
                        continue
                    
                    if len(entries) >= limit:
                        break
        except Exception as e:
            print(f"Error reading {filename}: {e}")
        
        # Sort by timestamp (newest first)
        entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return entries
    
    def get_all_logs(
        self,
        component: Optional[str] = None,
        level: Optional[str] = None,
        event: Optional[str] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Lấy tất cả logs với filters."""
        all_entries = []
        
        for filename in self.get_log_files():
            entries = self.parse_log_file(filename, limit=limit)
            all_entries.extend(entries)
        
        # Apply filters
        if component:
            all_entries = [e for e in all_entries if e.get("component") == component]
        
        if level:
            all_entries = [e for e in all_entries if e.get("level") == level.upper()]
        
        if event:
            all_entries = [e for e in all_entries if event.lower() in e.get("event", "").lower()]
        
        # Sort by timestamp (newest first)
        all_entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        return all_entries[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        """Lấy statistics về logs."""
        all_entries = self.get_all_logs(limit=10000)
        
        components = {}
        levels = {}
        events = {}
        
        for entry in all_entries:
            comp = entry.get("component", "unknown")
            level = entry.get("level", "unknown")
            event_name = entry.get("event", "unknown")
            
            components[comp] = components.get(comp, 0) + 1
            levels[level] = levels.get(level, 0) + 1
            events[event_name] = events.get(event_name, 0) + 1
        
        return {
            "total_logs": len(all_entries),
            "components": components,
            "levels": levels,
            "top_events": dict(sorted(events.items(), key=lambda x: x[1], reverse=True)[:10]),
            "log_files": len(self.get_log_files())
        }


# Initialize FastAPI app
app = FastAPI(title="Log Viewer", description="Web interface để xem logs của My-AI-Assistant")
viewer = LogViewer()


@app.get("/", response_class=HTMLResponse)
async def index():
    """Main page với HTML interface."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Log Viewer - My-AI-Assistant</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: #1e1e1e;
                color: #d4d4d4;
                padding: 20px;
            }
            .header {
                background: #252526;
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            h1 { color: #4ec9b0; }
            .controls {
                background: #252526;
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 20px;
                display: flex;
                gap: 10px;
                flex-wrap: wrap;
            }
            select, input, button {
                padding: 8px 12px;
                background: #3c3c3c;
                border: 1px solid #555;
                border-radius: 4px;
                color: #d4d4d4;
                font-size: 14px;
            }
            button {
                background: #007acc;
                cursor: pointer;
                border: none;
            }
            button:hover { background: #0098ff; }
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
                margin-bottom: 20px;
            }
            .stat-card {
                background: #252526;
                padding: 15px;
                border-radius: 8px;
                border-left: 4px solid #007acc;
            }
            .stat-value { font-size: 24px; font-weight: bold; color: #4ec9b0; }
            .stat-label { color: #858585; font-size: 12px; margin-top: 5px; }
            .logs-container {
                background: #252526;
                border-radius: 8px;
                padding: 15px;
                max-height: 600px;
                overflow-y: auto;
            }
            .log-entry {
                padding: 10px;
                margin-bottom: 8px;
                border-radius: 4px;
                border-left: 4px solid #555;
                background: #1e1e1e;
                font-family: 'Consolas', monospace;
                font-size: 13px;
            }
            .log-entry.INFO { border-left-color: #4ec9b0; }
            .log-entry.WARNING { border-left-color: #dcdcaa; }
            .log-entry.ERROR { border-left-color: #f48771; }
            .log-entry.DEBUG { border-left-color: #858585; }
            .log-header {
                display: flex;
                justify-content: space-between;
                margin-bottom: 5px;
            }
            .log-timestamp { color: #858585; font-size: 11px; }
            .log-level {
                padding: 2px 8px;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
            }
            .log-level.INFO { background: #4ec9b0; color: #1e1e1e; }
            .log-level.WARNING { background: #dcdcaa; color: #1e1e1e; }
            .log-level.ERROR { background: #f48771; color: #1e1e1e; }
            .log-level.DEBUG { background: #858585; color: #1e1e1e; }
            .log-component { color: #9cdcfe; font-weight: bold; }
            .log-event { color: #dcdcaa; margin-left: 10px; }
            .log-meta {
                margin-top: 5px;
                padding-top: 5px;
                border-top: 1px solid #3c3c3c;
                color: #858585;
                font-size: 11px;
            }
            .log-meta-key { color: #9cdcfe; }
            .loading { text-align: center; padding: 20px; color: #858585; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📊 Log Viewer - My-AI-Assistant</h1>
            <button onclick="refreshLogs()">🔄 Refresh</button>
        </div>
        
        <div class="controls">
            <select id="componentFilter">
                <option value="">All Components</option>
            </select>
            <select id="levelFilter">
                <option value="">All Levels</option>
                <option value="DEBUG">DEBUG</option>
                <option value="INFO">INFO</option>
                <option value="WARNING">WARNING</option>
                <option value="ERROR">ERROR</option>
            </select>
            <input type="text" id="eventFilter" placeholder="Filter by event...">
            <input type="number" id="limitInput" value="100" min="10" max="1000" placeholder="Limit">
            <button onclick="loadLogs()">🔍 Filter</button>
            <button onclick="loadStats()">📈 Stats</button>
        </div>
        
        <div class="stats" id="stats"></div>
        
        <div class="logs-container">
            <div class="loading">Loading logs...</div>
        </div>
        
        <script>
            async function loadLogs() {
                const component = document.getElementById('componentFilter').value;
                const level = document.getElementById('levelFilter').value;
                const event = document.getElementById('eventFilter').value;
                const limit = document.getElementById('limitInput').value || 100;
                
                const params = new URLSearchParams({ limit });
                if (component) params.append('component', component);
                if (level) params.append('level', level);
                if (event) params.append('event', event);
                
                const response = await fetch(`/api/logs?${params}`);
                const logs = await response.json();
                
                renderLogs(logs);
            }
            
            async function loadStats() {
                const response = await fetch('/api/stats');
                const stats = await response.json();
                renderStats(stats);
            }
            
            async function loadComponents() {
                const response = await fetch('/api/stats');
                const stats = await response.json();
                const select = document.getElementById('componentFilter');
                select.innerHTML = '<option value="">All Components</option>';
                Object.keys(stats.components || {}).forEach(comp => {
                    const option = document.createElement('option');
                    option.value = comp;
                    option.textContent = `${comp} (${stats.components[comp]})`;
                    select.appendChild(option);
                });
            }
            
            function renderStats(stats) {
                const container = document.getElementById('stats');
                container.innerHTML = `
                    <div class="stat-card">
                        <div class="stat-value">${stats.total_logs}</div>
                        <div class="stat-label">Total Logs</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${stats.log_files}</div>
                        <div class="stat-label">Log Files</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${Object.keys(stats.components || {}).length}</div>
                        <div class="stat-label">Components</div>
                    </div>
                `;
            }
            
            function renderLogs(logs) {
                const container = document.querySelector('.logs-container');
                if (logs.length === 0) {
                    container.innerHTML = '<div class="loading">No logs found</div>';
                    return;
                }
                
                container.innerHTML = logs.map(log => {
                    const level = log.level || 'INFO';
                    const meta = Object.keys(log)
                        .filter(k => !['timestamp', 'level', 'event', 'component', 'execution_id'].includes(k))
                        .map(k => `<span class="log-meta-key">${k}:</span> ${JSON.stringify(log[k])}`)
                        .join(', ');
                    
                    return `
                        <div class="log-entry ${level}">
                            <div class="log-header">
                                <div>
                                    <span class="log-component">${log.component || 'unknown'}</span>
                                    <span class="log-event">${log.event || 'no-event'}</span>
                                    <span class="log-level ${level}">${level}</span>
                                </div>
                                <span class="log-timestamp">${log.timestamp || ''}</span>
                            </div>
                            ${meta ? `<div class="log-meta">${meta}</div>` : ''}
                        </div>
                    `;
                }).join('');
            }
            
            function refreshLogs() {
                loadLogs();
                loadStats();
            }
            
            // Auto-refresh every 5 seconds
            setInterval(refreshLogs, 5000);
            
            // Initial load
            loadComponents();
            loadStats();
            loadLogs();
        </script>
    </body>
    </html>
    """


@app.get("/api/logs")
async def get_logs(
    component: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    event: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000)
):
    """API endpoint để lấy logs với filters."""
    logs = viewer.get_all_logs(
        component=component,
        level=level,
        event=event,
        limit=limit
    )
    return JSONResponse(content=logs)


@app.get("/api/stats")
async def get_stats():
    """API endpoint để lấy statistics."""
    stats = viewer.get_stats()
    return JSONResponse(content=stats)


@app.get("/api/files")
async def get_log_files():
    """API endpoint để lấy danh sách log files."""
    files = viewer.get_log_files()
    return JSONResponse(content={"files": files})


@app.get("/api/file/{filename}")
async def get_file_logs(filename: str, limit: int = Query(100, ge=1, le=1000)):
    """API endpoint để lấy logs từ một file cụ thể."""
    logs = viewer.parse_log_file(filename, limit=limit)
    return JSONResponse(content=logs)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

