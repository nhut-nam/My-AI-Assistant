from src.utils.logger import LoggerMixin

class GradChaining(LoggerMixin):
    def __init__(self, name="GradChaining"):
        super().__init__(name)
        self.steps = []
        self.agents = {}
        self.prompts = {}

    def add_step(self, step_func):
        self.steps.append(step_func)
        self.debug(f"Step added: {step_func.__name__}")

    def bind_agent(self, name, agent):
        self.agents[name] = agent
        self.info(f"Agent registered: {name}")

    def bind_prompt(self, name, prompt):
        self.prompts[name] = prompt

    def run(self, input_data):
        data = input_data
        for step in self.steps:
            self.debug(f"Running step: {step.__name__}")
            data = step(data)
        return data
