import asyncio
from src.lifecycle.life_cycle import LifeCycle

async def main():
    life_cycle = LifeCycle()
    result = await life_cycle.run(
        user_request="Lấy kết quả từ file F:/result.txt so sánh có bằng số 67 nếu bằng thì hãy tạo ra file mới F:/troll_2.txt với nội dung 'sybau'."
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
