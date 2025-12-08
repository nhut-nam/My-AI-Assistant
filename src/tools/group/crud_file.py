import os
import shutil
import time
from typing_extensions import Literal, Any
from src.tools.base_tool import BaseTool


class CRUDFile(BaseTool):
    """
    Bộ công cụ CRUD file theo Option 1:
    - Tool TRẢ dict raw
    - ExecutorAgent wrap thành ToolResponse
    """

    # ===========================================================
    # CREATE FILE
    # ===========================================================
    @BaseTool.register_tool(category="file")
    @staticmethod
    def create_file(
        filename: str,
        content: Any,
        type_file: Literal[".txt", ".py"] = ".txt",
        directory: str | None = None,
    ) -> dict:
        """
        Tạo file mới và ghi nội dung.

        Params:
            filename (str): Tên file (có thể thiếu extension).
            content (str): Nội dung cần ghi vào file.
            type_file (".txt" | ".py"): Extension mặc định nếu filename thiếu đuôi.
            directory (str|None): Thư mục đích (None = thư mục hiện tại).

        Returns:
            dict:
                success (bool): True nếu tạo thành công.
                error (str|None): Lỗi xảy ra (nếu có).
                meta (dict):
                    action (str): "create_file".
                    filename (str): Tên file sau khi xử lý extension.
                    path (str|None): Đường dẫn tuyệt đối của file.
                    message (str): Mô tả kết quả.
        """
        content = str(content)
        try:
            if not filename.endswith(type_file):
                filename += type_file

            abs_path = (
                os.path.join(os.path.abspath(directory), filename)
                if directory
                else os.path.abspath(filename)
            )

            if directory:
                os.makedirs(os.path.abspath(directory), exist_ok=True)

            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)

            return {
                "success": True,
                "error": None,
                "meta": {
                    "action": "create_file",
                    "filename": filename,
                    "path": abs_path,
                    "message": "File created successfully",
                },
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "meta": {
                    "action": "create_file",
                    "filename": filename,
                    "path": None,
                    "message": "Failed to create file",
                },
            }

    # ===========================================================
    # EDIT FILE
    # ===========================================================
    @BaseTool.register_tool(category="file")
    @staticmethod
    def edit_file(
        filename: str,
        new_content: Any,
        mode: Literal["overwrite", "append"] = "overwrite",
    ) -> dict:
        """
        Ghi đè hoặc nối thêm nội dung vào file.

        Params:
            filename (str): Đường dẫn file.
            new_content (str): Nội dung mới.
            mode ("overwrite" | "append"): Kiểu ghi.

        Returns:
            dict:
                success (bool): True nếu chỉnh sửa thành công.
                error (str|None): Lỗi nếu có.
                meta:
                    action (str): "edit_file".
                    filename (str)
                    path (str|None)
                    mode (str)
                    message (str)
        """
        new_content = str(new_content)
        try:
            abs_path = os.path.abspath(filename)
            if not os.path.exists(abs_path):
                return {
                    "success": False,
                    "error": "File does not exist",
                    "meta": {
                        "action": "edit_file",
                        "filename": filename,
                        "path": None,
                        "mode": mode,
                        "message": "File does not exist",
                    },
                }

            write_mode = "w" if mode == "overwrite" else "a"
            with open(abs_path, write_mode, encoding="utf-8") as f:
                f.write(new_content)

            return {
                "success": True,
                "error": None,
                "meta": {
                    "action": "edit_file",
                    "filename": filename,
                    "path": abs_path,
                    "mode": mode,
                    "message": f"File updated successfully ({mode})",
                },
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "meta": {
                    "action": "edit_file",
                    "filename": filename,
                    "path": None,
                    "mode": mode,
                    "message": "Failed to edit file",
                },
            }

    # ===========================================================
    # DELETE FILE
    # ===========================================================
    @BaseTool.register_tool(category="file")
    @staticmethod
    def delete_file(filename: str) -> dict:
        """
        Xóa file nếu tồn tại.

        Params:
            filename (str): Đường dẫn file.

        Returns:
            dict:
                success (bool)
                error (str|None)
                meta {action, filename, path, message}
        """
        try:
            abs_path = os.path.abspath(filename)
            if not os.path.exists(abs_path):
                return {
                    "success": False,
                    "error": "File does not exist",
                    "meta": {
                        "action": "delete_file",
                        "filename": filename,
                        "path": None,
                        "message": "File does not exist",
                    },
                }

            os.remove(abs_path)

            return {
                "success": True,
                "error": None,
                "meta": {
                    "action": "delete_file",
                    "filename": filename,
                    "path": abs_path,
                    "message": "File deleted successfully",
                },
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "meta": {
                    "action": "delete_file",
                    "filename": filename,
                    "path": None,
                    "message": "Failed to delete file",
                },
            }

    # ===========================================================
    # READ FILE
    # ===========================================================
    @BaseTool.register_tool(category="file")
    @staticmethod
    def read_file(filename: str) -> dict:
        """
        Đọc nội dung file dạng text.

        Params:
            filename (str): Đường dẫn file.

        Returns:
            dict:
                success (bool)
                error (str|None)
                content (str|None): Nội dung file.
                meta {action, filename, path, message}
        """
        try:
            abs_path = os.path.abspath(filename)
            if not os.path.exists(abs_path):
                return {
                    "success": False,
                    "error": "File does not exist",
                    "content": None,
                    "meta": {
                        "action": "read_file",
                        "filename": filename,
                        "path": None,
                        "message": "File does not exist",
                    },
                }

            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()

            return {
                "success": True,
                "error": None,
                "content": content,
                "meta": {
                    "action": "read_file",
                    "filename": filename,
                    "path": abs_path,
                    "message": "File read successfully",
                },
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "content": None,
                "meta": {
                    "action": "read_file",
                    "filename": filename,
                    "path": None,
                    "message": "Failed to read file",
                },
            }

    # ===========================================================
    # RENAME FILE
    # ===========================================================
    @BaseTool.register_tool(category="file")
    @staticmethod
    def rename_file(old_name: str, new_name: str) -> dict:
        """
        Đổi tên file hoặc di chuyển file.

        Params:
            old_name (str): File gốc.
            new_name (str): Tên mới hoặc đường dẫn mới.

        Returns:
            dict:
                success, error,
                meta {action, old_filename, new_filename, path, message}
        """
        try:
            abs_old = os.path.abspath(old_name)
            abs_new = os.path.abspath(new_name)

            if not os.path.exists(abs_old):
                return {
                    "success": False,
                    "error": "File does not exist",
                    "meta": {
                        "action": "rename_file",
                        "old_filename": old_name,
                        "new_filename": new_name,
                        "path": None,
                        "message": "File does not exist",
                    },
                }

            os.rename(abs_old, abs_new)

            return {
                "success": True,
                "error": None,
                "meta": {
                    "action": "rename_file",
                    "old_filename": old_name,
                    "new_filename": new_name,
                    "path": abs_new,
                    "message": "File renamed successfully",
                },
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "meta": {
                    "action": "rename_file",
                    "old_filename": old_name,
                    "new_filename": new_name,
                    "path": None,
                    "message": "Failed to rename file",
                },
            }

    # ===========================================================
    # COPY FILE
    # ===========================================================
    @BaseTool.register_tool(category="file")
    @staticmethod
    def copy_file(src: str, dest: str) -> dict:
        """
        Sao chép file từ src sang dest.

        Params:
            src (str): File nguồn.
            dest (str): File đích.

        Returns:
            dict:
                success, error,
                meta {action, source_filename, destination_filename, path, message}
        """
        try:
            abs_src = os.path.abspath(src)
            abs_dest = os.path.abspath(dest)

            if not os.path.exists(abs_src):
                return {
                    "success": False,
                    "error": "Source file does not exist",
                    "meta": {
                        "action": "copy_file",
                        "source_filename": src,
                        "destination_filename": dest,
                        "path": None,
                        "message": "Source file does not exist",
                    },
                }

            shutil.copy2(abs_src, abs_dest)

            return {
                "success": True,
                "error": None,
                "meta": {
                    "action": "copy_file",
                    "source_filename": src,
                    "destination_filename": dest,
                    "path": abs_dest,
                    "message": "File copied successfully",
                },
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "meta": {
                    "action": "copy_file",
                    "source_filename": src,
                    "destination_filename": dest,
                    "path": None,
                    "message": "Failed to copy file",
                },
            }

    # ===========================================================
    # FILE INFO
    # ===========================================================
    @BaseTool.register_tool(category="file")
    @staticmethod
    def file_info(filename: str) -> dict:
        """
        Lấy thông tin file.

        Params:
            filename (str): Đường dẫn file.

        Returns:
            dict:
                success, error,
                info {size, created, modified} | None
                meta {action, filename, path, message}
        """
        try:
            abs_path = os.path.abspath(filename)
            if not os.path.exists(abs_path):
                return {
                    "success": False,
                    "error": "File does not exist",
                    "info": None,
                    "meta": {
                        "action": "file_info",
                        "filename": filename,
                        "path": None,
                        "message": "File does not exist",
                    },
                }

            stat = os.stat(abs_path)

            return {
                "success": True,
                "error": None,
                "info": {
                    "size": stat.st_size,
                    "created": time.ctime(stat.st_ctime),
                    "modified": time.ctime(stat.st_mtime),
                },
                "meta": {
                    "action": "file_info",
                    "filename": filename,
                    "path": abs_path,
                    "message": "File info retrieved successfully",
                },
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "info": None,
                "meta": {
                    "action": "file_info",
                    "filename": filename,
                    "path": None,
                    "message": "Failed to get file info",
                },
            }

    # ===========================================================
    # CHECK EXISTS
    # ===========================================================
    @BaseTool.register_tool(category="file")
    @staticmethod
    def check_file_exists(filename: str) -> dict:
        """
        Kiểm tra file có tồn tại.

        Params:
            filename (str): Đường dẫn file.

        Returns:
            dict:
                success (bool)
                error (str|None)
                exists (bool): True nếu file tồn tại.
                meta {action, filename, path, message}
        """
        try:
            abs_path = os.path.abspath(filename)
            exists = os.path.exists(abs_path)

            return {
                "success": True,
                "error": None,
                "exists": exists,
                "meta": {
                    "action": "check_file_exists",
                    "filename": filename,
                    "path": abs_path if exists else None,
                    "message": "File exists" if exists else "File does not exist",
                },
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "exists": False,
                "meta": {
                    "action": "check_file_exists",
                    "filename": filename,
                    "path": None,
                    "message": "Failed to check file",
                },
            }

    # ===========================================================
    # IDENTIFY FILE NAME
    # ===========================================================
    @BaseTool.register_tool(category="file")
    @staticmethod
    def identify_target_file(filename: str) -> dict:
        """
        Chuẩn hóa tên file (auto thêm .txt).

        Params:
            filename (str): Tên file gốc.

        Returns:
            dict:
                success (bool)
                error (str|None)
                info:
                    final_filename (str)
                    extension (str)
                meta {action, filename, final_filename, extension, message}
        """
        try:
            base, ext = os.path.splitext(filename)
            if ext == "":
                final_filename = filename + ".txt"
                ext = ".txt"
            else:
                final_filename = filename

            return {
                "success": True,
                "error": None,
                "info": {
                    "final_filename": final_filename,
                    "extension": ext,
                },
                "meta": {
                    "action": "identify_target_file",
                    "filename": filename,
                    "final_filename": final_filename,
                    "extension": ext,
                    "message": "File name processed successfully",
                },
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "info": None,
                "meta": {
                    "action": "identify_target_file",
                    "filename": filename,
                    "final_filename": None,
                    "extension": None,
                    "message": "Failed to process filename",
                },
            }
