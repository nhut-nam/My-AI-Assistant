import inspect
import importlib
import pkgutil
from functools import wraps
from collections import defaultdict
from src.utils.logger import LoggerMixin
import inspect
from typing import Any, Union, get_origin, get_args, Callable

def _format_annotation(ann) -> str:
    if ann is inspect._empty:
        return "Any"

    # Built-in types: str, int, float, bool
    if isinstance(ann, type):
        return ann.__name__

    origin = get_origin(ann)
    args = get_args(ann)

    # List[T]
    if origin is list:
        return f"list[{_format_annotation(args[0])}]"

    # Dict[K, V]
    if origin is dict:
        return f"dict[{_format_annotation(args[0])}, {_format_annotation(args[1])}]"

    # Tuple[T1, T2, ...]
    if origin is tuple:
        return f"tuple[{', '.join(_format_annotation(a) for a in args)}]"

    # Union / Optional
    if origin is Union:
        return "|".join(_format_annotation(a) for a in args)

    # Literal["a", "b"]
    if origin is not None and origin.__name__ == "Literal":
        return "|".join(str(a) for a in args)

    # typing.Any
    if ann is Any:
        return "Any"

    # fallback
    return str(ann).replace("typing.", "").replace("<class '", "").replace("'>", "")


class BaseTool(LoggerMixin):
    """
    Core Tool System:
    - Registry: tool_name -> function
    - Metadata: tool_name -> info (category, description, module,...)
    - Grouping: category -> list[tool_name]
    - Auto-discovery: load toàn bộ package để lấy tool
    """

    registry = {}        # {"create_file": func}
    metadata = {}        # {"create_file": {...}}
    groups = defaultdict(list)  # {"file": ["create_file", "delete_file"]}

    def __init__(self, name=None, log_dir="logs"):
        super().__init__(name or self.__class__.__name__, log_dir)

    @classmethod
    def register_tool(cls, name=None, description="", category="general"):
        """
        Decorator đăng ký tool.
        - name: tên tool (mặc định là func.__name__)
        - description: mô tả tool
        - category: nhóm tool (ví dụ: "file", "search", "math", ...)
        """
        def decorator(func):
            tool_name = name or func.__name__

            # check overwrite
            if tool_name in cls.registry:
                LoggerMixin("BaseTool").warning(
                    f"[WARNING] Tool '{tool_name}' is overwritten!"
                )

            # wrapper with logging
            @wraps(func)
            def wrapper(*args, **kwargs):
                log = LoggerMixin(tool_name)
                log.info(f"[TOOL CALL] {tool_name} args={args} kwargs={kwargs}")

                try:
                    result = func(*args, **kwargs)
                    log.info(f"[TOOL RESULT] {result}")
                    return result
                except Exception as e:
                    log.error(f"[TOOL ERROR] {e}")
                    raise e

            # register
            cls.registry[tool_name] = wrapper

            # store metadata
            cls.metadata[tool_name] = {
                "name": tool_name,
                "description": description or func.__doc__ or "",
                "category": category,
                "module": func.__module__,
                "qualname": func.__qualname__,
            }

            # add to grouping
            cls.groups[category].append(tool_name)

            return wrapper

        return decorator

    @classmethod
    def get_tool(cls, name: str):
        return cls.registry.get(name)

    @classmethod
    def list_tools(cls):
        """Trả về list tool_name."""
        return list(cls.registry.keys())

    @classmethod
    def get_metadata(cls):
        return cls.metadata

    @classmethod
    def get_groups(cls):
        """Trả về danh sách category -> tool list."""
        return dict(cls.groups)

    @classmethod
    def get_tools_by_group(cls, group_name: str):
        """Trả về tool thuộc group."""
        return cls.groups.get(group_name, [])

    @classmethod
    def get_all_tools_grouped(cls):
        """
        Trả về cấu trúc chuẩn cho SOP:
        {
            "file": [
                {"name": "...", "description": "...", "args": [...], "returns": "..."}
            ],
            "math": [...]
        }
        """
        all_grouped = {}

        for category, tool_names in cls.groups.items():
            tools = []

            for name in tool_names:
                func = cls.registry[name]
                sig = inspect.signature(func)

                # extract args
                params = [
                    {
                        "name": p.name,
                        "annotation": None if p.annotation == inspect._empty else str(p.annotation),
                        "default": None if p.default == inspect._empty else p.default,
                        "kind": p.kind.name
                    }
                    for p in sig.parameters.values()
                ]

                tools.append({
                    "name": name,
                    "description": cls.metadata[name]["description"],
                    "category": cls.metadata[name]["category"],
                    "module": cls.metadata[name]["module"],
                    "args": params,
                    "returns": None
                    if sig.return_annotation == inspect._empty
                    else str(sig.return_annotation),
                })

            all_grouped[category] = tools

        return all_grouped
    
    @classmethod
    def get_tools_grouped_str_by_callables(
        cls,
        tools: list[Callable],
        agent_name: str,
        *,
        strict: bool = False
    ) -> str:
        """
        Trả về danh sách tool theo group (category)
        nhưng CHỈ lấy các tool trong list Callable.

        Params:
            tools (list[Callable]): danh sách function tool
            strict (bool):
                - True  -> raise error nếu tool không tồn tại trong registry
                - False -> silently skip tool không hợp lệ

        Format output giống get_all_tools_grouped_str()
        """

        groups: dict[str, list[str]] = {}

        for func in tools:
            if not callable(func):
                if strict:
                    raise TypeError(f"Invalid tool (not callable): {func}")
                continue

            tool_name = func.__name__

            # ---- validate registry ----
            if tool_name not in cls.registry or tool_name not in cls.metadata:
                if strict:
                    raise ValueError(f"Tool '{tool_name}' not found in BaseTool registry")
                continue

            meta = cls.metadata[tool_name]
            category = meta.get("category", "general")

            # ---- lấy signature ----
            sig = inspect.signature(func)

            params = []
            for p in sig.parameters.values():
                annotation = (
                    "Any"
                    if p.annotation == inspect._empty
                    else str(p.annotation).replace("typing.", "")
                )
                params.append(f"{p.name}: {annotation}")

            param_str = ", ".join(params)

            desc = meta.get("description", "").strip()
            tool_line = f"- {tool_name}({param_str}) -> {desc}"

            groups.setdefault(category, []).append(tool_line)

        # ---- format output ----
        output_lines: list[str] = []
        for group, tools in groups.items():
            output_lines.append(f"[{agent_name}]")
            output_lines.extend(tools)
            output_lines.append("")

        return "\n".join(output_lines).strip()


    
    @classmethod
    def get_all_tools_grouped_str(cls) -> str:
        """
        Trả về danh sách tool theo group (category)
        dạng string dễ đưa vào prompt LLM.
        Format:

        [group_name]
        - tool_name(param1: type, param2: type) -> description
        """
        groups = {}   # category → list tool info

        for tool_name, meta in cls.metadata.items():
            category = meta.get("category", "general")

            # Lấy signature
            func = cls.registry[tool_name]
            sig = inspect.signature(func)

            params = []
            for p in sig.parameters.values():
                annotation = _format_annotation(p.annotation)
                params.append(f"{p.name}: {annotation}")

            param_str = ", ".join(params)

            # Chuẩn dòng mô tả tool
            desc = meta.get("description", "").strip()
            tool_line = f"- {tool_name}({param_str}) -> {desc}"

            # Gom theo group
            groups.setdefault(category, []).append(tool_line)

        # ---- Format thành 1 string cực sạch cho prompt ----
        output_lines = []
        for group, tools in groups.items():
            output_lines.append(f"[{group}]")
            output_lines.extend(tools)
            output_lines.append("")  # newline giữa group

        return "\n".join(output_lines).strip()


    @classmethod
    def auto_discover(cls, package_name="src.tools.group"):
        """
        Quét package và tự động import module chứa tool.
        Điều này kích hoạt decorator và registry sẽ tự đầy.
        """
        package = importlib.import_module(package_name)

        for loader, module_name, is_pkg in pkgutil.walk_packages(
            package.__path__, package.__name__ + "."
        ):
            importlib.import_module(module_name)
