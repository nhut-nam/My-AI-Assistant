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
    import re

    # -------------------------------------------------------
    # Normalize available_agents → {AgentName: {tools{}}}
    # -------------------------------------------------------
    if isinstance(available_agents, list):
        flat = {}
        for item in available_agents:
            if isinstance(item, dict):
                flat.update(item)
        available_agents = flat

    if not isinstance(available_agents, dict):
        return False, "available_agents must be dict or list-of-dicts"

    # -------------------------------------------------------
    # Must have steps
    # -------------------------------------------------------
    if "steps" not in sop or not isinstance(sop["steps"], list):
        return False, "SOP must contain a list 'steps'."

    steps = sop["steps"]
    step_numbers = {step.get("step_number") for step in steps}
    step_numbers.add(-1)

    # -------------------------------------------------------
    # Validate unique store_result_as
    # -------------------------------------------------------
    used_vars = {}
    for step in steps:
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
    # VALIDATION FOR EACH STEP
    # -------------------------------------------------------
    for idx, step in enumerate(steps, start=1):

        # Required fields MUST exist exactly as in your SOPStep model
        required_fields = [
            "step_number", "description", "agent_type",
            "execution_mode", "action_type", "params",
            "conditions", "retry", "store_result_as",
            "condition_to_jump_step"
        ]

        for field in required_fields:
            if field not in step:
                return False, f"Missing required field '{field}' in step {idx}"

        # Validate execution_mode
        em = step["execution_mode"]
        if em not in ("static", "dynamic"):
            return False, f"Invalid execution_mode '{em}' in step {idx}"

        agent = step["agent_type"]
        if agent not in available_agents:
            return False, f"Unknown agent '{agent}' in step {idx}"

        # ---------------------------------------------------
        # STATIC STEP: validate action_type & tool existence
        # ---------------------------------------------------
        if em == "static":
            at = step["action_type"]
            if not isinstance(at, dict):
                return False, f"action_type must be dict in static step {idx}"

            if at.get("agent") != agent:
                return False, f"action_type.agent must equal agent_type in step {idx}"

            tool = at.get("tool")
            agent_tools = available_agents[agent].get("tools", {})
            if tool not in agent_tools:
                return False, f"Unknown tool '{tool}' under agent '{agent}' in step {idx}"

        # ---------------------------------------------------
        # DYNAMIC STEP: action_type must be None
        # ---------------------------------------------------
        if em == "dynamic":
            if step["action_type"] is not None:
                return False, f"action_type must be null in dynamic step {idx}"

        # ---------------------------------------------------
        # PARAMS VALIDATION (<var> or <var>.field)
        # ---------------------------------------------------
        params = step["params"]
        if not isinstance(params, dict):
            return False, f"params must be dict in step {idx}"

        for key, val in params.items():

            if not isinstance(val, str):
                continue

            # cấm syntax cũ step[x]
            if val.startswith("step["):
                return False, f"invalid param syntax '{val}' in step {idx}"

            # match <var> or <var>.field
            m = re.match(
                r"^<([a-zA-Z_][a-zA-Z0-9_]*)(?:\.([a-zA-Z_][a-zA-Z0-9_]*))?>$",
                val
            )
            if m:
                var = m.group(1)
                field = m.group(2)

                if var not in used_vars:
                    return False, (
                        f"Unknown store_result_as '{var}' referenced in step {idx}"
                    )

                # 🚨 CHẶN TRUY CẬP SÂU HƠN 1 CẤP
                if "." in val.strip("<>"):
                    parts = val.strip("<>").split(".")
                    if len(parts) > 2:
                        return False, (
                            f"Invalid nested reference '{val}' in step {idx}. "
                            f"Only '<var>' or '<var>.field' is allowed."
                        )

                # ---------------------------------------------------
                # CONDITIONS VALIDATION
                # ---------------------------------------------------
                for cond in step["conditions"]:
                    cond_step = cond.get("step")
                    if cond_step not in step_numbers:
                        return False, f"Condition refers to non-existent step '{cond_step}' in step {idx}"

                    # Cannot reference future steps
                    if cond_step >= step["step_number"]:
                        return False, f"Condition cannot reference future step {cond_step} in step {idx}"

                    # Validate jump targets
                    js = cond.get("jump_to_step_on_success")
                    jf = cond.get("jump_to_step_on_failure")

                    for target, label in [(js, "jump_to_step_on_success"), (jf, "jump_to_step_on_failure")]:
                        if target is not None and target not in step_numbers:
                            return False, f"{label}={target} in step {idx} is not a valid step"

        # ---------------------------------------------------
        # condition_to_jump_step VALIDATION
        # ---------------------------------------------------
        cjs_list = step.get("condition_to_jump_step") or []
        for cond in cjs_list:

            cond_step = cond.get("step")
            if cond_step not in step_numbers:
                return False, f"condition_to_jump_step refers to unknown step '{cond_step}' in step {idx}"

            if cond_step >= step["step_number"]:
                return False, f"condition_to_jump_step cannot reference future step {cond_step} in step {idx}"

            js = cond.get("jump_to_step_on_success")
            jf = cond.get("jump_to_step_on_failure")

            for target, label in [(js, "jump_to_step_on_success"), (jf, "jump_to_step_on_failure")]:
                if target is not None and target not in step_numbers and target != -1:
                    return False, f"{label}={target} in step {idx} is not a valid step"

    # -------------------------------------------------------
    # Validate final target
    # -------------------------------------------------------
    ft = sop.get("final_target")
    if ft is not None and not isinstance(ft, str):
        return False, "final_target must be string or null"

    return True, "ok"









