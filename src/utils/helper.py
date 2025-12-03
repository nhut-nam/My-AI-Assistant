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

def validate_sop(sop: dict, available_agents: dict) -> tuple[bool, str]:

    if "steps" not in sop or not isinstance(sop["steps"], list):
        return False, "SOP must contain a list 'steps'."

    # Unique store_result_as
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

    # Validate steps
    for idx, step in enumerate(sop["steps"], start=1):

        required = [
            "step_number","description","agent_type",
            "execution_mode","params","conditions","retry","store_result_as"
        ]
        for f in required:
            if f not in step:
                return False, f"missing field '{f}' in step {idx}"

        em = step["execution_mode"]

        # Dynamic
        if em == "dynamic":
            if step.get("action_type") is not None:
                return False, f"action_type must be null in dynamic step {idx}"
            continue

        # Static
        agent = step["agent_type"]
        if agent not in available_agents:
            return False, f"Unknown agent '{agent}' in static step {idx}"

        at = step["action_type"]
        if not isinstance(at, dict):
            return False, f"action_type must be dict in static step {idx}"

        if at.get("agent") != agent:
            return False, f"action_type.agent must equal agent_type in step {idx}"

        tool = at.get("tool")
        if tool not in available_agents[agent]["tools"]:
            return False, f"tool '{tool}' not found under agent '{agent}'"

        # PARAMS: only check syntax
        params = step["params"]
        if not isinstance(params, dict):
            return False, f"params must be dict in step {idx}"

        for key, val in params.items():

            # Literal → ok
            if not isinstance(val, str):
                continue

            # Old forbidden syntax
            if val.startswith("step["):
                return False, f"invalid param syntax '{val}' in step {idx}"

            # New syntax:
            #   <var>
            #   <var>.field
            m = re.match(r"^<([a-zA-Z_][a-zA-Z0-9_]*)>(?:\..+)?$", val)
            if m:
                var = m.group(1)
                if var not in used_vars:
                    return False, (
                        f"Unknown store_result_as '{var}' referenced in step {idx}"
                    )
                continue

            # otherwise it's literal, OK
            continue

    # final_target
    ft = sop.get("final_target")
    if ft is not None and not isinstance(ft, str):
        return False, "final_target must be string or null"

    return True, "ok"







