from src.tools.base_tool import BaseTool

if __name__ == "__main__":
    base_tool = BaseTool()
    base_tool.auto_discover()
    print("Discovered Tools Grouped by Category:")
    tools = []
    tools.append(base_tool.get_tool(name="create_file"))
    tools.append(base_tool.get_tool(name="add"))
    tools.append(base_tool.get_tool(name="divide"))
    print(tools)
    print(base_tool.get_tools_grouped_str_by_callables(tools=tools))