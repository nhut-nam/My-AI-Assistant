# 🤖 My-AI-Assistant
**Build agentic workflows with planning, validation, SOP generation, and deterministic execution**

---

## What this project does

- Convert natural language requests into executable workflows  
- Enforce planning → validation → SOP → execution separation  
- Prevent unsafe or incomplete LLM-generated actions  
- Execute multi-step tasks with tools in a controlled manner  

---

## System Flow

User Request
→ Generate plan
→ Critique plan
→ Generate SOP (JSON)
→ Validate SOP
→ Execute step-by-step
→ Pause for HITL if required
→ Resume or terminate


---

## Core Components

### PlannerAgent
- Analyze user intent  
- Generate ordered high-level plans  
- Retry on failure  
- Do not execute tools  

### PlanCriticAgent
- Validate plan completeness and ordering  
- Block incomplete or illogical plans  
- Allow execution only if score == 100  

### SOPAgent
- Convert plans into SOP JSON  
- Auto-repair invalid outputs  
- Enforce strict schema rules  
- Reject unsafe references and future-step access  

### ExecutorAgent
- Execute SOP deterministically  

### Tool System
- Auto-discover tools via decorators  
- Register tools with metadata  
- Group tools by category  
- Inspect tool signatures for prompt safety  

### HITL Middleware
- Intercept sensitive tool calls  
- Require human approval  
- Pause execution safely  
- Resume without re-running completed steps  

---

## Key Capabilities

- Multi-step workflow execution  
- Static and dynamic tool usage  
- Context chaining across steps  
- Conditional execution and branching  
- Deterministic retries  
- Human-in-the-loop (HITL) control  
- Async-first design (`async/await`)  

---

## Installation

### Clone repository
```bash
git clone https://github.com/nhut-nam/My-AI-Assistant.git
cd My-AI-Assistant
```
---

## Install package
```bash
pip install -e .
```

## Configure environment variables

Create a `.env` file or export variables manually:

```bash
GROQ_API_KEY=your_groq_api_key
OLLAMA_MODEL=llama3.1
```

---

## Usage Examples

### Basic Usage

```python
from src.lifecycle.life_cycle import LifeCycle
from src.models.models import StateSchema
import asyncio

async def main():
    life_cycle = LifeCycle()
    state = StateSchema(
        user_request="Calculate the area of a rectangle and save it to a file"
    )
    result = await life_cycle.run(state)
    print(result.exec_result)

asyncio.run(main())
```

### Using Chat UI

```bash
python chat_ui.py
```

Opens a GUI window for interactive conversations with the AI assistant.

---

## Logging System

### Overview

The project includes a comprehensive **structured logging system** that tracks all operations with JSON-formatted logs. All logs are automatically tagged with `segment_id` for conversation tracking.

### Features

- **Structured JSON Logs**: All logs are in JSON format for easy parsing and analysis
- **Component-based Logging**: Each component (agents, executor, lifecycle) logs to separate files
- **Rich Metadata**: Logs include step numbers, tool names, severity levels, errors, and more
- **Conversation Tracking**: All logs are tagged with `segment_id` to track conversation segments
- **Rotating Log Files**: Automatic log rotation (5MB per file, 3 backups)

### Log Format

Each log entry follows this structure:

```json
{
  "timestamp": "2024-01-01T12:00:00.000000",
  "level": "INFO",
  "event": "tool_execution_success",
  "component": "ExecutorAgent",
  "segment_id": "seg-abc12345",
  "step": 3,
  "tool": "create_file",
  "severity": "RECOVERABLE"
}
```

### Log Viewer Web Interface

A FastAPI-based web interface for viewing and filtering logs in real-time.

#### Installation

```bash
# Install web dependencies
pip install fastapi uvicorn[standard]
```

#### Running Log Viewer

```bash
# Option 1: Use the helper script
python run_log_viewer.py

# Option 2: Use uvicorn directly
uvicorn src.web.log_viewer:app --reload
```

Then open your browser at: **http://localhost:8000**

#### Features

- **Table View**: Logs displayed in a searchable table format
- **Real-time Filtering**: Filter by component, level, event, or segment_id
- **Statistics Dashboard**: View log counts, component distribution, and top events
- **Auto-refresh**: Automatically updates every 5 seconds
- **Color-coded Levels**: Visual distinction for INFO, WARNING, ERROR, DEBUG

#### API Endpoints

- `GET /api/logs` - Get logs with filters (component, level, event, segment_id)
- `GET /api/stats` - Get log statistics
- `GET /api/files` - List all log files
- `GET /api/file/{filename}` - Get logs from a specific file

#### Example: Filter logs by segment_id

```bash
curl "http://localhost:8000/api/logs?segment_id=seg-abc12345"
```

### Log Files Location

All logs are stored in the `logs/` directory:

```
logs/
├── LifeCycle.log
├── ExecutorAgent.log
├── PlannerAgent.log
├── SOPAgent.log
├── PlanCriticAgent.log
└── ...
```

---

## Design Rules

- **Let LLMs plan, not execute** - Separation of planning and execution
- **Validate before acting** - All plans and SOPs are validated before execution
- **Prefer deterministic execution** - Over probabilistic reasoning
- **Keep state explicit and traceable** - Full state management with logging
- **Isolate responsibilities** - Clear separation between agents
- **Treat safety as a first-class concern** - HITL middleware for sensitive operations

---

## Intended Use Cases

- Agentic workflow orchestration
- Tool-based automation systems
- Planner–Executor architecture research
- Safe execution of LLM-generated plans
- Educational reference for Agentic AI systems

---

## License

[Add your license here]

---





