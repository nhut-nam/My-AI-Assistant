# 🤖 My-AI-Assistant

My-AI-Assistant là hệ thống Agent hỗ trợ lập kế hoạch, sinh SOP và chạy tác vụ tự động thông qua mạng lưới Agent + Tool.  
Hệ thống gồm ba thành phần chính:

- **PlannerAgent** – phân tích yêu cầu và tạo kế hoạch
- **SOPAgent** – chuyển kế hoạch thành SOP JSON chuẩn
- **ExecutorAgent** – thực thi SOP theo từng bước với tool

Hệ thống hỗ trợ:
- Multi-step workflow
- Static + dynamic tool execution
- Auto-discovery tool
- Retry, conditions, context chaining
- Async execution (async/await)

---

## 🚀 Cài đặt

### 1. Clone repository
```bash
git clone https://github.com/nhut-nam/My-AI-Assistant.git
cd My-AI-Assistant

``` bash
pip install -e .

GROQ_API_KEY=your_key
OLLAMA_MODEL=llama3.1


