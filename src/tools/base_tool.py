import inspect
import importlib
import pkgutil
from functools import wraps
from collections import defaultdict
from src.utils.logger import LoggerMixin


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
                annotation = (
                    "Any"
                    if p.annotation == inspect._empty
                    else str(p.annotation).replace("typing.", "")
                )
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
    def auto_discover(cls, package_name="src.tools"):
        """
        Quét package và tự động import module chứa tool.
        Điều này kích hoạt decorator và registry sẽ tự đầy.
        """
        package = importlib.import_module(package_name)

        for loader, module_name, is_pkg in pkgutil.walk_packages(
            package.__path__, package.__name__ + "."
        ):
            importlib.import_module(module_name)
