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

import asyncio

async def main():
    base_tool = BaseTool()
    base_tool.auto_discover(package_name="src.tools.group")

    llm = GroqClient()
    llm_ollama = OllamaClient()
    agent = PlannerAgent(llm=llm_ollama)
    response = await agent.invoke("Tạo giúp tôi file txt tại đường dẫn F:/new_test.txt với nội dung là 'Nam đẹp trai quá'")

    agent = CRUDAgent(llm=llm_ollama)
    agent.register_tool(tool=base_tool.get_tools_by_group(group_name="file"))

    sop = SOPAgent(llm=llm)
    sop_dispatcher = SOPStepDispatcher(sop_agent=sop, agents=[agent])
    sop_result = await sop_dispatcher.build_sop(plan=response)
    print("SOP RESULT: ", sop_result)
    # print(agent.list_tools())
    # agent.safe_call_tool(name="create_file", filename="F:/namdeptraiqua", content="Nam đẹp trai quá", type_file=".txt")
    if sop_result is None:
        print("SOP generation failed.")
        return
    # data = {"steps":[{"step_number":1,"description":"Identify the target file as F:/test.txt","agent_type":"CRUDAgent","execution_mode":"static","action_type":{"agent":"CRUDAgent","tool":"identify_target_file"},"params":{"filename":"F:/test.txt"},"conditions":[],"retry":0,"store_result_as":"target_file_info"},
    #                  {"step_number":2,"description":"Retrieve the content of the file if it exists","agent_type":"CRUDAgent","execution_mode":"static","action_type":{"agent":"CRUDAgent","tool":"read_file"},"params":{"filename":"step[1].output.final_filename"},"conditions":[],"retry":0,"store_result_as":None}],"final_target":None}
    # sop_result = SmartSerializer.parse_model(model=SOP, 
    #                                          data=data)
    exec_agent = ExecutorAgent()
    exec_agent.register_agent(agent=agent)
    print(await exec_agent.run_sop(sop_result))


if __name__ == "__main__":
    asyncio.run(main())
