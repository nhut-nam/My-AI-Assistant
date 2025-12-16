import asyncio
from src.agent.critic_synthesizer_agent import CriticSynthesizerAgent
from src.llm.groq_client import GroqClient

async def main():
    llm = GroqClient()
    agent = CriticSynthesizerAgent(llm=llm)

    input_text = (
        "Lấy kết quả từ file F:/result.txt so sánh có bằng số 67 "
        "nếu bằng thì hãy tạo ra file mới F:/troll_2.txt với nội dung 'sybau'."
    )

    sop_result = {
    "steps": [
        {
            "step_number": 1,
            "description": "Read the content of F:/result.txt",
            "agent_type": "CRUDAgent",
            "execution_mode": "static",
            "action_type": {
                "agent": "CRUDAgent",
                "tool": "read_file"
            },
            "params": {
                "filename": "F:/result.txt"
            },
            "conditions": [],
            "retry": 0,
            "store_result_as": "read_result",
            "condition_to_jump_step": None
        },
        {
            "step_number": 2,
            "description": "If content equals 67, create file F:/troll_2.txt with text 'sybau'",
            "agent_type": "CRUDAgent",
            "execution_mode": "static",
            "action_type": {
                "agent": "CRUDAgent",
                "tool": "create_file"
            },
            "params": {
                "filename": "F:/troll_2.txt",
                "content": "sybau",
                "type_file": ".txt",
                "directory": None
            },
            "conditions": [
                {
                    "step": 1,
                    "field": "output.content",
                    "operator": "==",
                    "value": "67",
                    "jump_to_step_on_success": None,
                    "jump_to_step_on_failure": None
                }
            ],
            "retry": 0,
            "store_result_as": "create_result",
            "condition_to_jump_step": None
        },
        {
            "step_number": 3,
            "description": "Return confirmation of the operation",
            "agent_type": "SimpleMathAgent",
            "execution_mode": "dynamic",
            "action_type": None,
            "params": {},
            "conditions": [],
            "retry": 0,
            "store_result_as": "final_confirmation",
            "condition_to_jump_step": None
        }
    ],
    "final_target": "Operation completed"
}

    execution_result = {'success': True, 'final_target': 'Operation completed', 'steps': [
        {'success': True, 'output': {'success': True, 'error': None, 'content': '67', 'meta': {'action': 'read_file', 'filename': 'F:/result.txt', 'path': 'F:\\result.txt', 'message': 'File read successfully'
                }
            }, 'error': None, 'meta': {}
        },
        {'success': True, 'output': {'success': True, 'error': None, 'meta': {'action': 'create_file', 'filename': 'F:/troll_2.txt', 'path': 'F:\\troll_2.txt', 'message': 'File created successfully'
                }
            }, 'error': None, 'meta': {}
        },
        {'success': True, 'output': None, 'error': None, 'meta': {}
        }
    ], 'context': {'read_result': {'success': True, 'error': None, 'content': '67', 'meta': {'action': 'read_file', 'filename': 'F:/result.txt', 'path': 'F:\\result.txt', 'message': 'File read successfully'
            }
        }, 'create_result': {'success': True, 'error': None, 'meta': {'action': 'create_file', 'filename': 'F:/troll_2.txt', 'path': 'F:\\troll_2.txt', 'message': 'File created successfully'
            }
        }, 'final_confirmation': None
    }
}

    # ---------------------------
    # FIX: gọi run bằng await
    # ---------------------------
    result = await agent.invoke(
        input_text=input_text,
        sop_result=sop_result,
        execution_result=execution_result
    )

    print("\n===== CRITIC SYNTHESIZER REPORT =====")
    print(result)

    print("\n===== SUMMARY =====")
    print("Summary:", result.summary)
    print("Key Failures:", result.key_failures)
    print("Improvement Advice:", result.improvement_advice)
    print("Risk Level:", result.risk_level)

# chạy async
asyncio.run(main())
