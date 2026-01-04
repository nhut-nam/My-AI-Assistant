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

I can help you fix the README.md. I notice several markdown formatting issues:

1. **Missing closing backtick** after "Clone repository" section
2. **Inconsistent heading levels** (### vs ##)
3. **Missing code fence** before "Configure environment variables"
4. **Mixed languages** (English + Vietnamese at the end)
5. **Incomplete License section**

For the `$SELECTION_PLACEHOLDER$`, based on context, it should be:
```
modes (static/dynamic execution paths)
```

Would you like me to provide:
- A corrected full README with proper markdown syntax?
- English-only version (removing Vietnamese section)?
- Fixed placeholder text only?

- Resolve parameters from context  
- Apply retry, conditions, and step jumps  
- Maintain execution state and results  

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

# Create a .env file or export variables manually:

```bash
GROQ_API_KEY=your_groq_api_key
OLLAMA_MODEL=llama3.1
```

### Usage Example
```bash
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


### Design Rules

Let LLMs plan, not execute

Validate before acting

Prefer deterministic execution over probabilistic reasoning

Keep state explicit and traceable

Isolate responsibilities between agents

Treat safety as a first-class concern

Intended Use Cases

Agentic workflow orchestration

Tool-based automation systems

Planner–Executor architecture research

Safe execution of LLM-generated plans

Educational reference for Agentic AI systems

License

---





