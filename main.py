from src.models.models import SOP
from src.tools.base_tool import BaseTool
from src.agent.planner_agent import PlannerAgent
from src.agent.crud_agent import CRUDAgent
from src.llm.groq_client import GroqClient
from src.agent.sop_agent import SOPAgent
from src.multiagent.executor_agent import ExecutorAgent
from src.llm.ollama_client import OllamaClient
from src.dispatcher.SOPStepDispatcher import SOPStepDispatcher
from src.serializer.serializer import SmartSerializer
from src.agent.simple_math_agent import SimpleMathAgent

import asyncio

async def main():
    base_tool = BaseTool()
    base_tool.auto_discover(package_name="src.tools.group")

    llm = GroqClient()
    llm_ollama = OllamaClient()
    agent = PlannerAgent(llm=llm)
    response = await agent.invoke("Lấy kết quả từ file F:/result.txt so sánh có bằng số 67 nếu bằng thì hãy tạo ra file mới F:/troll_2.txt với nội dung 'sybau'.")

    crud_agent = CRUDAgent(llm=llm_ollama)
    simple_math_agent = SimpleMathAgent(llm=llm_ollama)
    crud_agent.register_tool(tool=base_tool.get_tools_by_group(group_name="file"))
    simple_math_agent.register_tool(tool=base_tool.get_tools_by_group(group_name="math"))

    sop = SOPAgent(llm=llm)
    sop_dispatcher = SOPStepDispatcher(sop_agent=sop, agents=[crud_agent, simple_math_agent])
    sop_result = await sop_dispatcher.build_sop(plan=response)
    # print("SOP RESULT: ", sop_result)
    # print(agent.list_tools())
    # agent.safe_call_tool(name="create_file", filename="F:/namdeptraiqua", content="Nam đẹp trai quá", type_file=".txt")
    if sop_result is None:
        print("SOP generation failed.")
        return
#     data = {
#   "steps": [
#     {
#       "step_number": 1,
#       "description": "Read the content of the file at F:/numbers.txt",
#       "agent_type": "CRUDAgent",
#       "execution_mode": "static",
#       "action_type": {
#         "agent": "CRUDAgent",
#         "tool": "read_file"
#       },
#       "params": {
#         "filename": "F:/numbers.txt"
#       },
#       "conditions": [],
#       "retry": 3,
#       "store_result_as": "file_content"
#     },
#     {
#       "step_number": 2,
#       "description": "Extract the first number from the file content",
#       "agent_type": "CRUDAgent",
#       "execution_mode": "dynamic",
#       "action_type": None,
#       "params": {
#         "content": "<file_content>.content"
#       },
#       "conditions": [
#         {
#           "step": 1,
#           "field": "success",
#           "operator": "==",
#           "value": True
#         }
#       ],
#       "retry": 3,
#       "store_result_as": "first_number"
#     },
#     {
#       "step_number": 3,
#       "description": "Calculate the square of the extracted number",
#       "agent_type": "SimpleMathAgent",
#       "execution_mode": "static",
#       "action_type": {
#         "agent": "SimpleMathAgent",
#         "tool": "square"
#       },
#       "params": {
#         "n": "<first_number>"
#       },
#       "conditions": [
#         {
#           "step": 2,
#           "field": "success",
#           "operator": "==",
#           "value": True
#         }
#       ],
#       "retry": 3,
#       "store_result_as": "squared_result"
#     },
#     {
#       "step_number": 4,
#       "description": "Create a new file at F:/result.txt and write the squared result",
#       "agent_type": "CRUDAgent",
#       "execution_mode": "static",
#       "action_type": {
#         "agent": "CRUDAgent",
#         "tool": "create_file"
#       },
#       "params": {
#         "filename": "result.txt",
#         "content": "<squared_result>.result",
#         "directory": "F:/"
#       },
#       "conditions": [
#         {
#           "step": 3,
#           "field": "success",
#           "operator": "==",
#           "value": True
#         }
#       ],
#       "retry": 3,
#       "store_result_as": None
#     }
#   ]
# }
    
#     sop_result = SmartSerializer.parse_model(model=SOP, 
#                                              data=data)
    exec_agent = ExecutorAgent()
    exec_agent.register_agent(agent=crud_agent)
    exec_agent.register_agent(agent=simple_math_agent)
    print(await exec_agent.run_sop(sop_result))


if __name__ == "__main__":
    asyncio.run(main())
