import os
import shutil
import time
from typing_extensions import Literal, Any
from src.tools.base_tool import BaseTool

class SandboxFS:
    def __init__(self, root: str):
        self.root = os.path.realpath(os.path.abspath(root))
        os.makedirs(self.root, exist_ok=True)

    def resolve(self, path: str) -> str:
        """
        Resolve user path into sandbox.
        - Reject absolute path
        - Reject ../ escape
        - Reject symlink escape
        """ 
        if os.path.isabs(path):
            raise PermissionError("Absolute path is not allowed")

        joined = os.path.join(self.root, path)
        real = os.path.realpath(joined)

        if not real.startswith(self.root):
            raise PermissionError("Sandbox escape attempt")

        return real
    
SANDBOX = SandboxFS("F:/agent_workspace")

class CRUDFile(BaseTool):
    """
    Bộ công cụ CRUD file theo Option 1:
    - Tool TRẢ dict raw
    - ExecutorAgent wrap thành ToolResponse
    """

    # ===========================================================
    # CREATE FILE
    # ===========================================================
    @BaseTool.register_tool(category="file", description=
        """
        Tạo file mới và ghi nội dung.
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
    )
    @staticmethod
    def create_file(
        filename: str,
        content: Any,
        type_file: Literal[".txt", ".py"] = ".txt",
        directory: str | None = None,
    ) -> dict:
        content = str(content)
        try:
            if not filename.endswith(type_file):
                filename += type_file

            relative_path = (
                os.path.join(directory, filename) if directory else filename
            )

            abs_path = SANDBOX.resolve(relative_path)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)

            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)

            return {
                "success": True,
                "error": None,
                "meta": {
                    "action": "create_file",
                    "filename": filename,
                    "path": abs_path,
                    "message": "File created inside sandbox",
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
    @BaseTool.register_tool(category="file", description=
        """
        Ghi đè hoặc nối thêm nội dung vào file.
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
        """)
    @staticmethod
    def edit_file(
        filename: str,
        new_content: Any,
        mode: Literal["overwrite", "append"] = "overwrite",
    ) -> dict:
        new_content = str(new_content)
        try:
            abs_path = SANDBOX.resolve(filename)

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
    @BaseTool.register_tool(category="file", description=
        """
        Xóa file nếu tồn tại.
        Returns:
            dict:
                success (bool)
                error (str|None)
                meta {action, filename, path, message}
        """)
    @staticmethod
    def delete_file(filename: str) -> dict:
        try:
            abs_path = SANDBOX.resolve(filename)

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
                    "message": "File deleted inside sandbox",
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
            
    @BaseTool.register_tool(category="file", description=
        """
        Đọc file nếu tồn tại.
        Returns:
            dict:
                success (bool)
                error (str|None)
                content: (str|None)
                meta {action, filename, path, message}
        """)
    @staticmethod
    def read_file(filename: str) -> dict:
        try:
            abs_path = SANDBOX.resolve(filename)

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
                    "message": "File read inside sandbox",
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
    @BaseTool.register_tool(category="file", description=
        """
        Đổi tên file hoặc di chuyển file.
        Returns:
            dict:
                success, error,
                meta {action, old_filename, new_filename, path, message}
        """)
    @staticmethod
    def rename_file(old_name: str, new_name: str) -> dict:
        try:
            abs_old = SANDBOX.resolve(old_name)
            abs_new = SANDBOX.resolve(new_name)

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

            os.makedirs(os.path.dirname(abs_new), exist_ok=True)
            os.rename(abs_old, abs_new)

            return {
                "success": True,
                "error": None,
                "meta": {
                    "action": "rename_file",
                    "old_filename": old_name,
                    "new_filename": new_name,
                    "path": abs_new,
                    "message": "File renamed inside sandbox",
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
    @BaseTool.register_tool(category="file", description=
        """
        Sao chép file từ src sang dest.
        Returns:
            dict:
                success, error,
                meta {action, source_filename, destination_filename, path, message}
        """)
    @staticmethod
    def copy_file(src: str, dest: str) -> dict:
        try:
            abs_src = SANDBOX.resolve(src)
            abs_dest = SANDBOX.resolve(dest)

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

            os.makedirs(os.path.dirname(abs_dest), exist_ok=True)
            shutil.copy2(abs_src, abs_dest)

            return {
                "success": True,
                "error": None,
                "meta": {
                    "action": "copy_file",
                    "source_filename": src,
                    "destination_filename": dest,
                    "path": abs_dest,
                    "message": "File copied inside sandbox",
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
    @BaseTool.register_tool(category="file", description=
        """
        Lấy thông tin file.
        Returns:
            dict:
                success, error,
                info {size, created, modified} | None
                meta {action, filename, path, message}
        """)
    @staticmethod
    def file_info(filename: str) -> dict:
        try:
            abs_path = SANDBOX.resolve(filename)

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
                    "message": "File info retrieved inside sandbox",
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
    @BaseTool.register_tool(category="file", description=
        """
        Kiểm tra file có tồn tại.
        Returns:
            dict:
                success (bool)
                error (str|None)
                exists (bool): True nếu file tồn tại.
                meta {action, filename, path, message}
        """)
    @staticmethod
    def check_file_exists(filename: str) -> dict:
        """
        Kiểm tra file có tồn tại.
        """
        try:
            abs_path = SANDBOX.resolve(filename)
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
    @BaseTool.register_tool(category="file", description=
        """
        Chuẩn hóa tên file (auto thêm .txt).
        Returns:
            dict:
                success (bool)
                error (str|None)
                info:
                    final_filename (str)
                    extension (str)
                meta {action, filename, final_filename, extension, message}
        """)
    @staticmethod
    def identify_target_file(filename: str) -> dict:
        """
        Chuẩn hóa tên file (auto thêm .txt).
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
