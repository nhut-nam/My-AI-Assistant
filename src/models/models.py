from pydantic import BaseModel, Field, field_validator
from dataclasses import dataclass, field
import uuid
from typing import Union
import operator
from typing import Annotated, List, Tuple, Dict, Literal, Optional, Any
from typing_extensions import TypedDict
from enum import Enum

class ExecutionState(str, Enum):
    DONE = "done"
    PENDING_HITL = "pending_hitl"
    FAILED = "failed"
    CANCELLED = "cancelled"
    
class ConversationStatus(str, Enum):
    RUNNING = "RUNNING"
    WAITING_HITL = "WAITING_HITL"
    DONE = "DONE"
    FAILED = "FAILED"

class Response(BaseModel):
    """Response to user."""
    status: Literal["Success", "Fail"]
    result: Any = Field(
        description="Reason why Fail"
    )

class Plan(BaseModel):
    """Plan to follow in future"""

    steps: List[str] = Field(
        description="different steps to follow, should be in sorted order"
    )

class PlanExecute(TypedDict):
    input: str
    plan: str
    past_steps: Annotated[List[Tuple], operator.add]
    response: str

class Act(BaseModel):
    """Action to perform."""

    action: Union[Response, Plan] = Field(
        description="Action to perform. If you want to respond to user, use Response. "
        "If you need to further use tools to get the answer, use Plan."
    )

class ToolResponse(BaseModel):
    """
    Chuẩn output mà mọi tool phải trả về.
    Dùng cho Executor, ConditionEngine và các step sau.
    """
    success: bool = Field(..., description="Tool chạy thành công hay không.")
    output: Any = Field(None, description="Kết quả trả về của tool.")
    error: Optional[str] = Field(None, description="Thông tin lỗi nếu có.")
    meta: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata bổ sung (vd: path, log, thời gian thực thi)."
    )

class Condition(BaseModel):
    """
    Điều kiện logic dựa trên output của 1 step trước đó.
    Cho phép so sánh:
      - ToolResponse field trực tiếp: success, output, error, meta
      - Nested field: output.xxx, output.a.b, meta.xxx,...
    """

    step: int = Field(..., description="Step number cần kiểm tra.")

    field: str = Field(
        ...,
        description=(
            "Trường trong ToolResponse để so sánh. "
            "Hỗ trợ các dạng: "
            "  - 'success'\n"
            "  - 'output'\n"
            "  - 'output.<subfield>'\n"
            "  - 'output.<nested>.<field>'\n"
            "  - 'error'\n"
            "  - 'meta'\n"
            "  - 'meta.<subfield>'"
        )
    )

    operator: Literal["==", "!=", ">", "<", ">=", "<="] = Field(
        ..., description="Toán tử so sánh."
    )

    value: Any = Field(
        ..., description="Giá trị để so sánh với field đã chọn."
    )

    jump_to_step_on_success: Optional[int] = Field(
        None, description="Step number để nhảy tới nếu điều kiện đúng."
    )

    jump_to_step_on_failure: Optional[int] = Field(
        None, description="Step number để nhảy tới nếu điều kiện sai."
    )

    @field_validator("field")
    def validate_field_format(cls, v):
        """
        field phải bắt đầu bằng 1 trong 4 trường:
            success | output | error | meta
        Và có thể chứa dot-notation: output.xxx, meta.key.value
        """
        import re

        if not re.match(r"^(success|output|error|meta)(\.[a-zA-Z0-9_]+)*$", v):
            raise ValueError(
                "field must match pattern: "
                "'success' | 'output(.xxx)*' | 'error(.xxx)*' | 'meta(.xxx)*'"
            )
        return v


class SOPStep(BaseModel):
    """
    Một bước trong SOP.
    - SIMPLE (static): step có chỉ định rõ agent + tool.
    - DYNAMIC: chỉ có agent, tool do agent/LLM quyết định lúc chạy.
    """

    step_number: int = Field(
        ..., description="Số thứ tự của bước."
    )

    description: str = Field(
        ..., description="Mục tiêu của bước (WHAT), không mô tả HOW."
    )

    agent_type: str = Field(
        ...,
        description="Tên agent phụ trách step này (vd: CRUDAgent, APIAgent)."
    )

    execution_mode: Literal["static", "dynamic"] = Field(
        "dynamic",
        description=(
            "static: step đơn giản → thực thi tool trực tiếp.\n"
            "dynamic: step phức tạp → agent dùng LLM để chọn tool."
        )
    )

    action_type: Optional[Dict[str, str]] = Field(
        default=None,
        description=(
            "Chỉ sử dụng trong static mode.\n"
            "Dạng: { 'agent': '<Agent>', 'tool': '<tool_name>' }\n"
            "Nếu dynamic mode: luôn là null."
        )
    )

    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Tham số cho tool hoặc agent reasoning."
    )

    conditions: List[Condition] = Field(
        default_factory=list,
        description="Các điều kiện step trước để step hiện tại được phép chạy. Dạng: [Condition.step == value, ...]"
    )

    # condition: List[Condition] = Field(
    #     None, description="Các điều kiện để  chạy hoặc bỏ qua step."
    # )

    retry: int = Field(
        0, description="Số lần retry nếu step thất bại."
    )

    store_result_as: Optional[str] = Field(
        None,
        description="Biến để lưu output vào execution context."
    )

    condition_to_jump_step: Optional[List[Condition]] = Field(
        None,
        description="Điều kiện để chuyển sang step khác sau khi hoàn thành step này."
    )


class SOP(BaseModel):
    """
    SOP gồm nhiều step chạy theo thứ tự.
    """
    steps: List[SOPStep] = Field(
        ..., description="Danh sách step theo thứ tự thực thi."
    )

    final_target: Optional[str] = Field(
        None, description="Mục tiêu cuối cùng của SOP."
    )

class CriticIssue(BaseModel):
    description: str = Field(..., description="Mô tả vấn đề phát hiện trong plan")
    severity: str = Field(
        ...,
        description="Mức độ nghiêm trọng: none | low | medium | high | critical"
    )
    impact: str = Field(
        ...,
        description="Hậu quả hoặc rủi ro tiềm năng nếu vấn đề không được xử lý"
    )


class CriticFeedback(BaseModel):
    score: int = Field(..., description="Điểm đánh giá tổng thể (0–100)")
    issues: list[CriticIssue] = Field(..., description="Danh sách vấn đề được phát hiện")
    summary: str = Field(..., description="Tóm tắt đánh giá + Pass/Fail")


class SynthesizedCriticReport(BaseModel):
    summary: str = Field(..., description="Tóm tắt ngắn gọn kết quả phân tích.")
    key_failures: list[str] = Field(..., description="Các lỗi quan trọng rút ra từ execution + SOP result.")
    improvement_advice: list[str] = Field(..., description="Gợi ý cải thiện SOP hoặc Planner.")
    risk_level: str = Field(..., description="Đánh giá rủi ro tổng thể: low | medium | high | critical")
    
class HITLRequired(Exception):
    def __init__(self, tool_name, params, reason=None):
        self.tool_name = tool_name
        self.params = params
        self.reason = reason
        
@dataclass
class ExecutionStatus:
    state: ExecutionState

    result: Optional[Any] = None

    tool_name: Optional[str] = None
    params: Optional[dict] = None
    reason: Optional[str] = None
    current_step_idx: Optional[int] = None

    error: Optional[str] = None
    steps: Optional[list] = None
    context: Optional[dict] = None
    
class StateSchema(BaseModel):
    user_request: str
    plan: Optional[Plan] = None
    critic: Dict[str, Any] = Field(default_factory=dict)
    sop: Optional[SOP] = None
    exec_result: ExecutionStatus = None
    retry: int = 3
    
    is_resume: bool = False
    hitl_decision: Optional[Literal["approve", "reject"]] = None


@dataclass
class Message:
    role: Literal["user", "agent", "system"]
    content: str

@dataclass
class ConversationSegment:
    segment_id: str         
    intent: str = ""
    status: ConversationStatus = ConversationStatus.RUNNING
    messages: List[Message] = field(default_factory=list)

    pending_state: Optional[StateSchema] = None
