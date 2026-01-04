import asyncio
from src.lifecycle.life_cycle import LifeCycle

async def main():
    life_cycle = LifeCycle()
    result = await life_cycle.run(
        user_request="tạo giúp tôi file test_67 tại ổ F với đuôi file txt"
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
