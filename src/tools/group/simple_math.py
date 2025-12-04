import math
from src.tools.base_tool import BaseTool


class SimpleMathTool(BaseTool):
    """
    Bộ công cụ toán đơn giản (cộng, trừ, nhân, chia,
    bình phương, căn bậc hai, diện tích/chu vi cơ bản).
    Mọi hàm đều trả về dict chuẩn:
        {
            "success": True/False,
            "error": None hoặc thông báo lỗi,
            "result": giá trị kết quả,
            "meta": { thông tin bổ sung }
        }
    """

    # ===========================================================
    # ADD
    # ===========================================================
    @BaseTool.register_tool(
        category="math",
        description="Cộng hai số a và b."
    )
    @staticmethod
    def add(a: float, b: float) -> dict:
        """
        Cộng hai số.

        Params:
            a (float): Số thứ nhất.
            b (float): Số thứ hai.

        Returns:
            dict:
                success (bool): True nếu phép tính thành công.
                error (str|None): Lỗi xảy ra (nếu có).
                result (float): Kết quả a + b.
                meta (dict): Thông tin bổ sung.
        """
        try:
            result = a + b
            return {
                "success": True,
                "error": None,
                "result": result,
                "meta": {
                    "action": "add",
                    "a": a,
                    "b": b,
                    "message": f"{a} + {b} = {result}"
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e), "result": None}

    # ===========================================================
    # SUBTRACT
    # ===========================================================
    @BaseTool.register_tool(
        category="math",
        description="Trừ hai số a và b."
    )
    @staticmethod
    def subtract(a: float, b: float) -> dict:
        """
        Trừ hai số.

        Params:
            a (float): Số thứ nhất.
            b (float): Số thứ hai.

        Returns:
            dict: Giống mô tả ở hàm add().
        """
        try:
            result = a - b
            return {
                "success": True,
                "error": None,
                "result": result,
                "meta": {
                    "action": "subtract",
                    "a": a,
                    "b": b,
                    "message": f"{a} - {b} = {result}"
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e), "result": None}

    # ===========================================================
    # MULTIPLY
    # ===========================================================
    @BaseTool.register_tool(
        category="math",
        description="Nhân hai số a và b."
    )
    @staticmethod
    def multiply(a: float, b: float) -> dict:
        """
        Nhân hai số.

        Params:
            a (float): Số thứ nhất.
            b (float): Số thứ hai.

        Returns:
            dict: Kết quả phép nhân.
        """
        try:
            result = a * b
            return {
                "success": True,
                "error": None,
                "result": result,
                "meta": {
                    "action": "multiply",
                    "a": a,
                    "b": b,
                    "message": f"{a} * {b} = {result}"
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e), "result": None}

    # ===========================================================
    # DIVIDE
    # ===========================================================
    @BaseTool.register_tool(
        category="math",
        description="Chia hai số a và b (không chia cho 0)."
    )
    @staticmethod
    def divide(a: float, b: float) -> dict:
        """
        Chia hai số (không chia cho 0).

        Params:
            a (float): Số chia.
            b (float): Số bị chia.

        Returns:
            dict:
                result = a / b nếu b != 0.
        """
        try:
            if b == 0:
                return {
                    "success": False,
                    "error": "Không thể chia cho 0",
                    "result": None,
                    "meta": {"action": "divide", "a": a, "b": b}
                }
            result = a / b
            return {
                "success": True,
                "error": None,
                "result": result,
                "meta": {
                    "action": "divide",
                    "a": a,
                    "b": b,
                    "message": f"{a} / {b} = {result}"
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e), "result": None}

    # ===========================================================
    # SQUARE
    # ===========================================================
    @BaseTool.register_tool(
        category="math",
        description="Tính bình phương của một số."
    )
    @staticmethod
    def square(n: float) -> dict:
        """
        Tính bình phương.

        Params:
            n (float): Số cần bình phương.

        Returns:
            dict: Kết quả n * n.
        """
        try:
            result = n * n
            return {
                "success": True,
                "error": None,
                "result": result,
                "meta": {
                    "action": "square",
                    "n": n,
                    "message": f"{n}^2 = {result}"
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e), "result": None}

    # ===========================================================
    # SQUARE ROOT
    # ===========================================================
    @BaseTool.register_tool(
        category="math",
        description="Tính căn bậc hai (không áp dụng cho số âm)."
    )
    @staticmethod
    def square_root(n: float) -> dict:
        """
        Tính căn bậc hai.

        Params:
            n (float): Số đầu vào, phải >= 0.

        Returns:
            dict: Kết quả sqrt(n).
        """
        try:
            if n < 0:
                return {
                    "success": False,
                    "error": "Không thể lấy căn bậc hai của số âm",
                    "result": None,
                    "meta": {"action": "square_root", "n": n}
                }
            result = math.sqrt(n)
            return {
                "success": True,
                "error": None,
                "result": result,
                "meta": {
                    "action": "square_root",
                    "n": n,
                    "message": f"√{n} = {result}"
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e), "result": None}

    # ===========================================================
    # RECTANGLE AREA
    # ===========================================================
    @BaseTool.register_tool(
        category="math",
        description="Tính diện tích hình chữ nhật (dài * rộng)."
    )
    @staticmethod
    def rectangle_area(width: float, height: float) -> dict:
        """
        Tính diện tích hình chữ nhật.

        Params:
            width (float): Chiều rộng.
            height (float): Chiều dài.

        Returns:
            dict: width * height.
        """
        try:
            result = width * height
            return {
                "success": True,
                "error": None,
                "result": result,
                "meta": {
                    "action": "rectangle_area",
                    "width": width,
                    "height": height,
                    "message": f"Area = {result}"
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e), "result": None}

    # ===========================================================
    # CIRCLE AREA
    # ===========================================================
    @BaseTool.register_tool(
        category="math",
        description="Tính diện tích hình tròn: π * r^2."
    )
    @staticmethod
    def circle_area(radius: float) -> dict:
        """
        Tính diện tích hình tròn.

        Params:
            radius (float): Bán kính hình tròn.

        Returns:
            dict: π * r^2.
        """
        try:
            result = math.pi * radius * radius
            return {
                "success": True,
                "error": None,
                "result": result,
                "meta": {
                    "action": "circle_area",
                    "radius": radius,
                    "message": f"Circle Area = {result}"
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e), "result": None}
