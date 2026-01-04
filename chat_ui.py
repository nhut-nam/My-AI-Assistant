import sys
import uuid
import asyncio
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton
)
from PySide6.QtCore import Qt
from src.prompt_engineering.chaining import GradChaining
from src.models.models import ConversationStatus
import traceback as trackback


class ChatWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.grad = GradChaining()

        self.setWindowTitle("Agent Chat (Local)")
        self.resize(800, 600)

        self.active_segment_id = None

        self._build_ui()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    # -------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.chat_area = QTextEdit()
        self.chat_area.setReadOnly(True)
        layout.addWidget(self.chat_area)

        input_layout = QHBoxLayout()

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Type your message...")
        self.input_box.returnPressed.connect(self.send_message)

        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.send_message)

        input_layout.addWidget(self.input_box)
        input_layout.addWidget(self.send_btn)

        layout.addLayout(input_layout)

    # -------------------------------------------------
    def render_segment(self, segment):
        self.chat_area.clear()

        for msg in segment.messages:
            role = "You" if msg.role == "user" else "Agent"
            self.chat_area.append(f"<b>{role}:</b> {msg.content}")

        self.chat_area.append(
            f"<hr><i>Status: {segment.status}</i>"
        )

        self.chat_area.verticalScrollBar().setValue(
            self.chat_area.verticalScrollBar().maximum()
        )

    # -------------------------------------------------
    def send_message(self):
        text = self.input_box.text().strip()
        if not text:
            return
        self.input_box.clear()

        try:
            # -----------------------------------------
            # CHƯA CÓ SEGMENT → TẠO MỚI
            # -----------------------------------------
            if self.active_segment_id is None:
                self.active_segment_id = f"seg-{uuid.uuid4().hex[:8]}"

                segment = self.loop.run_until_complete(
                    self.grad.invoke(
                        segment_id=self.active_segment_id,
                        user_request=text
                    )
                )

            # -----------------------------------------
            # SEGMENT ĐANG WAITING HITL
            # -----------------------------------------
            else:
                segment = self.grad.segments[self.active_segment_id]

                if segment.status == ConversationStatus.WAITING_HITL:
                    if text.lower() not in ("approve", "reject"):
                        self.chat_area.append(
                            "<b>Agent:</b> Please type 'approve' or 'reject'."
                        )
                        return

                    segment = self.loop.run_until_complete(
                        self.grad.invoke(
                            segment_id=self.active_segment_id,
                            hitl_decision=text.lower()
                        )
                    )

                else:
                    # segment đã DONE / FAILED → tạo segment mới
                    self.active_segment_id = f"seg-{uuid.uuid4().hex[:8]}"
                    segment = self.loop.run_until_complete(
                        self.grad.invoke(
                            segment_id=self.active_segment_id,
                            user_request=text
                        )
                    )

            self.render_segment(segment)

        except Exception as e:
            trackback.print_exc()
            self.chat_area.append(f"<b>Agent:</b> Error: {e}")


# -------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ChatWindow()
    window.show()
    sys.exit(app.exec())
