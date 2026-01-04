from src.utils.logger import LoggerMixin

class MiddlewareManager(LoggerMixin):
    def __init__(self, middlewares):
        self.middlewares = sorted(
            middlewares,
            key=lambda m: getattr(m, "priority", 100)
        )

    async def dispatch(self, hook_name, *args):
        for m in self.middlewares:
            fn = getattr(m, hook_name, None)
            if fn:
                LoggerMixin("Middleware").debug(
                    f"[HOOK] {m.__class__.__name__}.{hook_name}"
                )
                await fn(*args)
