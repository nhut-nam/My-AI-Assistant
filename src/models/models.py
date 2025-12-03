from pydantic import BaseModel, Field, field_validator
from typing import Union
import operator
from typing import Annotated, List, Tuple, Dict, Literal, Optional, Any
from typing_extensions import TypedDict

class Response(BaseModel):
    """Response to user."""
    status: Literal["Success", "Fail"]
    response: str = Field(
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



