import yaml
from typing import Any
from dotenv import load_dotenv
import os
import re

load_dotenv() 

def load_yaml(path: str) -> Any:
    """
    Đọc file YAML và trả về dữ liệu Python.
    Tự động xử lý lỗi file không tồn tại hoặc YAML không hợp lệ.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"YAML file not found: {path}")
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML format in file {path}: {e}")

def get_env(key: str, default=None):
    value = os.getenv(key, default)
    if value is None:
        raise ValueError(f"Environment variable '{key}' is missing")
    return value

import re

def validate_sop(sop: dict, available_agents: dict) -> tuple[bool, str]:

    # -------------------------------------------------------
    # 🔥 1) Normalize available_agents về dạng chuẩn:
    #     {
    #        "CRUDAgent": {...},
    #        "SimpleMathAgent": {...}
    #     }
    # -------------------------------------------------------
    if isinstance(available_agents, list):
        flat = {}
        for item in available_agents:
            if isinstance(item, dict):
                flat.update(item)
        available_agents = flat

    elif not isinstance(available_agents, dict):
        return False, "available_agents must be dict or list-of-dicts"

    # -------------------------------------------------------
    # 🔥 2) SOP must contain steps
    # -------------------------------------------------------
    if "steps" not in sop or not isinstance(sop["steps"], list):
        return False, "SOP must contain a list 'steps'."

    # -------------------------------------------------------
    # 🔥 3) Validate unique store_result_as
    # -------------------------------------------------------
    used_vars = {}
    for step in sop["steps"]:
        sra = step.get("store_result_as")
        sn = step.get("step_number")

        if isinstance(sra, str):
            if sra in used_vars:
                return False, (
                    f"Duplicate store_result_as '{sra}' in step {sn} "
                    f"(already used in step {used_vars[sra]})"
                )
            used_vars[sra] = sn

    # -------------------------------------------------------
    # 🔥 4) Validate từng step
    # -------------------------------------------------------
    for idx, step in enumerate(sop["steps"], start=1):

        required = [
            "step_number","description","agent_type",
            "execution_mode","params","conditions","retry","store_result_as"
        ]

        for f in required:
            if f not in step:
                return False, f"missing field '{f}' in step {idx}"

        em = step["execution_mode"]

        # ---------------------------------------------------
        # Dynamic step
        # ---------------------------------------------------
        if em == "dynamic":
            if step.get("action_type") is not None:
                return False, f"action_type must be null in dynamic step {idx}"
            continue

        # ---------------------------------------------------
        # Static step — validate agent & tool
        # ---------------------------------------------------
        agent = step["agent_type"]

        # 🔥 FIXED: agent check
        if agent not in available_agents:
            return False, f"Unknown agent '{agent}' in static step {idx}"

        at = step["action_type"]
        if not isinstance(at, dict):
            return False, f"action_type must be dict in static step {idx}"

        # agent trong action_type phải trùng
        if at.get("agent") != agent:
            return False, f"action_type.agent must equal agent_type in step {idx}"

        # validate tool
        tool = at.get("tool")
        agent_tools = available_agents[agent].get("tools", {})

        if tool not in agent_tools:
            return False, f"tool '{tool}' not found under agent '{agent}'"

        # ---------------------------------------------------
        # Validate params syntax (<var>.field)
        # ---------------------------------------------------
        params = step["params"]
        if not isinstance(params, dict):
            return False, f"params must be dict in step {idx}"

        for key, val in params.items():

            if not isinstance(val, str):
                continue

            if val.startswith("step["):
                return False, f"invalid param syntax '{val}' in step {idx}"

            # <var> or <var>.field
            m = re.match(r"^<([a-zA-Z_][a-zA-Z0-9_]*)>(?:\..+)?$", val)
            if m:
                var = m.group(1)
                if var not in used_vars:
                    return False, (
                        f"Unknown store_result_as '{var}' referenced in step {idx}"
                    )
                continue

    # -------------------------------------------------------
    # 🔥 5) validate final_target
    # -------------------------------------------------------
    ft = sop.get("final_target")
    if ft is not None and not isinstance(ft, str):
        return False, "final_target must be string or null"

    return True, "ok"







