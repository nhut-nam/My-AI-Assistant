import asyncio
from src.agent.plan_critic import PlanCriticAgent
from src.models.models import Plan
from src.llm.groq_client import GroqClient


async def test_critic_only(user_request: str, plan_steps: list[str]):
    """
    Test PlanCriticAgent by providing:
    - user_request (string)
    - plan_steps (list of steps)
    """

    llm = GroqClient()
    critic = PlanCriticAgent(llm=llm)

    # Tạo object Plan
    plan = Plan(steps=plan_steps)

    print("\n==================== REQUEST ====================")
    print(user_request)

    print("\n==================== PLAN ====================")
    for i, s in enumerate(plan_steps, 1):
        print(f"{i}. {s}")

    print("\n==================== CRITIC RESULT ====================")

    critic_resp = await critic.invoke(plan=plan, query=user_request)

    if not critic_resp.get("success"):
        print("❌ Critic failed:", critic_resp["error"])
        return

    fb = critic_resp["feedback"]

    print("Score:", fb.score)
    print("Summary:", fb.summary)

    if len(fb.issues) == 0:
        print("No issues detected.")
    else:
        print("Issues:")
        for issue in fb.issues:
            print(f" - [{issue.severity}] {issue.description} | Impact: {issue.impact}")


if __name__ == "__main__":

    async def main():
        await test_critic_only(
            user_request=(
                "Đọc giá trị trong file F:/balance.txt, "
                "nếu số tiền nhỏ hơn 0 thì hãy tạo file F:/warning.txt với nội dung 'Âm tiền', "
                "nếu số tiền lớn hơn hoặc bằng 0 thì hãy nhân số tiền đó với 1.1 "
                "và lưu kết quả vào file F:/balance_updated.txt."
            ),
            plan_steps=[
                "Đọc file F:/balance.txt",
                "Lấy giá trị số trong file",
                "Nếu số tiền nhỏ hơn 0 thì tạo file F:/warning.txt với nội dung 'Âm tiền'",
                # ❌ intentionally missing positive-case logic:
                "Nếu số tiền >= 0 thì nhân số tiền đó với 1.1 và lưu vào balance_updated.txt"
            ]
        )

    asyncio.run(main())

