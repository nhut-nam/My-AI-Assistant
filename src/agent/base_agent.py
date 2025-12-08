from __future__ import annotations
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, Callable, Iterable, List, Optional, Union
from src.utils.logger import LoggerMixin
from src.tools.base_tool import BaseTool
from src.llm.base import BaseClient
from src.models.models import Response
from langchain.agents import create_agent
from src.handler.error_handler import ErrorHandler
import json

class BaseAgent(LoggerMixin, ABC):
    """
    BaseAgent chuẩn:
    - Nhận tool từ bên ngoài (list[func] hoặc str)
    - Không giữ metadata
    - Không grouping
    - Chỉ lưu: tool_name → tool_func
    """

    def __init__(
        self,
        llm: BaseClient,
        tools: Optional[List[Callable]] = None,
        name: Optional[str] = None,
        description="",
        log_dir: str = "logs"
    ):
        super().__init__(name or self.__class__.__name__, log_dir)
        self.llm = llm._create_client()
        self._tools: List[Callable] = []
        self.agent = self._create_agent()
        self.description = description
        self.error_handler = ErrorHandler()

        if tools:
            for t in tools:
                self.register_tool(t)
                
            self.logger.info(
                f"{self.__class__.__name__} initialized with tools: {list(self._tools.keys())}"
            )

    def register_tool(self, tool):
        """
        Accepts:
        - callable
        - string (ref in BaseTool.registry)
        - iterable (list/tuple/set) of callables or strings
        """
        if isinstance(tool, List):
            for item in tool:
                func = BaseTool.get_tool(item)
                if func is None:
                    self.error(f"Tool named '{tool}' not found in BaseTool.registry")
                    raise ValueError(f"Tool named '{tool}' not found in BaseTool.registry")
                self._tools.append(func)
            self.info(f"List tools: '{tool}' is registered")
            return

        # case: tool name string
        if isinstance(tool, str):
            func = BaseTool.get_tool(tool)
            if func is None:
                self.error(f"Tool named '{tool}' not found in BaseTool.registry")
                raise ValueError(f"Tool named '{tool}' not found in BaseTool.registry")
            self._tools.append(func)
            self.info(f"Tool named '{tool}' found in BaseTool.registry is registered")
            return

        # case: callable tool
        if callable(tool):
            self._tools.append(tool)
            return

        raise TypeError("Tool must be callable, string, or list of them")
    
    def register_tools_by_group(self, category: str):
        """
        Docstring for register_tools_by_group
        
        category: Tên group tool được cũng cấp sẵn trong class BaseTool
        """
        tools = BaseTool.get_tools_by_group(group_name=category)
        [self._tools.append(tool) for tool in tools]
        self.info(f"Registered tool successfully: {tools}")


    def list_tools(self) -> List[str]:
        """
        Trả về danh sách tên tool trong _tools.
        _tools: List[Callable]
        """
        return [tool.__name__ for tool in self._tools if callable(tool)]
    
    def get_tool_descriptions(self) -> Dict[str, str]:
        return {
            tool.__name__: (tool.__doc__ or "No description available.")
            for tool in self._tools
            if callable(tool)
        }


    def get_tool(self, name: str) -> Optional[Callable]:
        """
        Lấy tool theo tên từ _tools.
        _tools: List[Callable]
        """
        for tool in self._tools:
            if callable(tool) and tool.__name__ == name:
                return tool
        return None

    def _create_agent(self):
        return create_agent(
            model=self.llm,
            tools=self._tools,
        )
    
    @abstractmethod
    def build_prompt(self, **kwargs):
        raise NotImplementedError
    
    @abstractmethod
    async def invoke(self, **kwargs):
        raise NotImplementedError
    
    def __str__(self):
        tools = self.get_tool_descriptions()
        return json.dumps({self.__class__.__name__: {
            "agent_name": self.__class__.__name__,
            "description": self.description,
            "tools": tools
        }}, ensure_ascii=False, indent=2)
    
    def __repr__(self):
        return self.__str__()

    def to_string(self):
        return str(self)