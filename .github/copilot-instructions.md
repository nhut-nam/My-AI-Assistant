# AI Agent Instructions for My-AI-Assistant

## Architecture Overview

This is a **multi-stage agentic workflow engine** built on LangChain and LangGraph. The system enforces a strict pipeline:

**User Request → PlannerAgent → PlanCriticAgent → SOPAgent → ExecutorAgent → (optional HITL pause) → Execution**

### Core Pipeline Stages

1. **Planning Phase**: `PlannerAgent` analyzes intent and generates high-level ordered steps. Tools are NOT executed here.
2. **Validation Phase**: `PlanCriticAgent` scores plans (0-100); only 100-score plans proceed. Prevents incomplete/illogical execution.
3. **SOP Generation**: `SOPAgent` converts validated plans into deterministic JSON-based SOPs with strict schema validation.
4. **Execution Phase**: `ExecutorAgent` runs SOP steps sequentially, respecting conditional logic and retries.
5. **HITL Integration**: `HITLMiddleware` intercepts sensitive tool calls (e.g., `delete_file`) and pauses for human approval.

See `LifeCycle` class in [src/lifecycle/life_cycle.py](src/lifecycle/life_cycle.py#L1) for end-to-end orchestration.

## Critical Patterns

### Tool System (Auto-Discovery & Registration)

- **Location**: [src/tools/base_tool.py](src/tools/base_tool.py)
- **Pattern**: Use `@BaseTool.register_tool(name="...", category="...")` decorator on tool functions in `src/tools/group/` subdirectories.
- **Example**: [src/tools/group/simple_math.py](src/tools/group/simple_math.py) and [src/tools/group/crud_file.py](src/tools/group/crud_file.py)
- **Discovery**: `base_tool.auto_discover("src.tools.group")` dynamically loads all decorated tools and groups them by category.
- **Accessing Tools**: Agents use `register_tool(base_tool.get_tools_by_group("category"))` to bind tools by group.

### Agent Pattern (BaseAgent Hierarchy)

- **BaseAgent** ([src/agent/base_agent.py](src/agent/base_agent.py)) is the abstract parent with:
  - `register_tool()`: Accepts callables, tool names (string lookup), or lists.
  - `invoke()`: Async method each subclass overrides.
  - Tool registry: Map of `tool_name → callable`.
- **Subclasses**: `PlannerAgent`, `PlanCriticAgent`, `SOPAgent`, `ExecutorAgent`, `CRUDAgent`, `SimpleMathAgent`
- **Constraint**: Agents do NOT hold tool metadata (grouping, descriptions); only BaseAgent registry does.

### SOP Model & Validation

- **SOP Structure** ([src/models/models.py](src/models/models.py#L40)): JSON-serializable dataclass with:
  - `steps`: List of SOPStep objects (each has `step_number`, `description`, `agent_type`, `action_type`, `params`, `conditions`, `retry`, `store_result_as`)
  - Conditions enforce acyclic DAG (no future-step references allowed)
  - `execution_mode`: "static" (pre-defined params) or "dynamic" (params resolved from prior step outputs)
- **Validation**: `validate_sop()` in [src/utils/helper.py](src/utils/helper.py) ensures:
  - Agent names exist and have required tools.
  - Conditions reference only prior steps.
  - Unsafe references (e.g., `*..*` or future-step lookups) are rejected.

### SOP Generation with Auto-Repair

- **Location**: [src/agent/sop_agent.py](src/agent/sop_agent.py)
- **Process**: Up to 5 retry attempts using `SmartSerializer.extract_json()` + `validate_sop()` + parsing.
- **Key Pattern**: If JSON extraction fails, loop retries with error message passed back to LLM for repair.
- **Critical**: SOP prompt ([src/prompt_engineering/templates.py](src/prompt_engineering/templates.py)) constrains LLM to output ONLY SOP JSON, no explanation.

### Middleware System (Priority-Based Hooks)

- **Location**: [src/middleware/](src/middleware/)
- **Manager**: [src/middleware/middleware_manager.py](src/middleware/middleware_manager.py) dispatches hooks by priority (lower priority runs first).
- **HITL Middleware** ([src/middleware/HITL_middleware.py](src/middleware/HITL_middleware.py)): Intercepts `before_tool_call` to pause unsafe tools.
- **Hook Contract**: `async def before_tool_call(self, tool_name, params)` and `async def after_tool_call(self, tool_name, result)`.
- **Usage**: Pass `middleware=[]` list to ExecutorAgent during init.

### Error Handling

- **Handler**: [src/handler/error_handler.py](src/handler/error_handler.py)
- **Pattern**: All errors classified as `Recoverable` or `Critical`. Recoverable errors trigger SOP agent retries; Critical errors halt execution.
- **Logging**: All agents inherit `LoggerMixin` ([src/utils/logger.py](src/utils/logger.py)); logs are structured with context keys.

## Developer Workflows

### Installation & Setup

```bash
pip install -e .
export GROQ_API_KEY="your_key"
export OLLAMA_MODEL="llama3.1"
```

### Running the Full Pipeline

```bash
# See example in examples/test_life_cycle.py
python examples/test_life_cycle.py
```

### Testing

- **Unit tests** in `tests/unit/`; use `mock_llm_client` fixture from [tests/conftest.py](tests/conftest.py).
- **Integration tests** in `tests/integration/`; spawn real agents with test plans.
- **Run**: `pytest tests/` or `pytest tests/unit/test_*.py`

### Debugging Workflows

1. Enable debug logs: Set `log_dir="logs"` (agents auto-create logs there).
2. Inspect SOP JSON: Check executor logs for the exact SOP executed.
3. Trace middleware hooks: HITL middleware logs `before_tool_call` / `after_tool_call` events.

## Project-Specific Conventions

- **Async-First**: All agent `invoke()` methods are `async`. Use `await`.
- **Config Files**: YAML templates in `config/` (e.g., `prompt_templates.yaml`, `safety_policy.yaml`).
- **Serialization**: `SmartSerializer` ([src/serializer/serializer.py](src/serializer/serializer.py)) handles JSON extraction, model parsing, and type coercion.
- **LLM Clients**: Abstract base `BaseClient` ([src/llm/base.py](src/llm/base.py)) with subclasses `GroqClient`, `OllamaClient`. Always instantiate via `client._create_client()` to get the LangChain-compatible object.
- **Naming**: Agent names follow `*Agent` pattern; tool names use snake_case; step descriptions are human-readable strings.

## Cross-Component Communication

- **Plan → SOP**: `SOPStepDispatcher.build_sop(plan)` passes plan + agent capabilities to SOPAgent.
- **SOP → Execution**: `ExecutorAgent` iterates SOP steps, resolving dynamic params using `StateSchema` context.
- **HITL → Pause/Resume**: Middleware sets `execution_state` to `PENDING_HITL`; user approval in UI resumes without re-executing completed steps.
- **Logging**: All components log to `logs/` with timestamps; structured logging keys aid debugging.

## Key Files to Reference

| File | Purpose |
|------|---------|
| [src/lifecycle/life_cycle.py](src/lifecycle/life_cycle.py) | End-to-end orchestration; shows how all agents integrate |
| [src/agent/base_agent.py](src/agent/base_agent.py) | Tool registration, agent base contract |
| [src/models/models.py](src/models/models.py) | All dataclasses: SOP, Plan, Response, ExecutionState |
| [src/tools/base_tool.py](src/tools/base_tool.py) | Tool registry, auto-discovery, grouping |
| [src/serializer/serializer.py](src/serializer/serializer.py) | JSON extraction, model parsing, type coercion |
| [src/handler/error_handler.py](src/handler/error_handler.py) | Error classification and recovery logic |
