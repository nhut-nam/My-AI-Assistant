# 🤖 My-AI-Assistant  
A modular, extensible Agentic AI system with Planning, SOP generation, and Tool-based Execution.

My-AI-Assistant is a fully modular Agent framework designed to execute complex tasks through:
- **Planning (PlanAgent)**
- **Standard Operating Procedure generation (SOPAgent)**
- **Multi-step execution (ExecutorAgent)**
- **Tool-based interactions (BaseTool System)**

This project supports:
- Multi-agent orchestration  
- Automatic tool discovery  
- SOP-based deterministic execution  
- Retry logic  
- Condition-based workflows  
- Dynamic & static tool invocation  

---

## 🚀 Features

### 🔹 1. Planner Agent  
Generates a multi-step high-level plan from natural language input.

### 🔹 2. SOP Agent  
Converts a plan into a **strict JSON SOP** that the executor can safely run.

### 🔹 3. Executor Agent  
Executes each SOP step in order, handling:
- static tool calls  
- dynamic agent reasoning  
- dependency resolution (`<store_result_as>`)  
- conditional branching  
- retry logic  

### 🔹 4. Base Tool System  
Automatic tool registration with metadata:
- category  
- descriptions  
- argument signatures  
- grouping  

### 🔹 5. Full async support  
The system supports async I/O and multi-step workflows.

---

## 🏗 System Architecture

