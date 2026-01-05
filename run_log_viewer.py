#!/usr/bin/env python
"""
Script để chạy Log Viewer.
Usage: python run_log_viewer.py [--port 8000] [--host 0.0.0.0]
"""
import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Run Log Viewer Web Interface")
    parser.add_argument("--port", type=int, default=8000, help="Port to run on (default: 8000)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload on code changes")
    
    args = parser.parse_args()
    
    print(f"🚀 Starting Log Viewer on http://{args.host}:{args.port}")
    print(f"📊 Open your browser and navigate to: http://localhost:{args.port}")
    
    uvicorn.run(
        "src.web.log_viewer:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )


if __name__ == "__main__":
    main()

