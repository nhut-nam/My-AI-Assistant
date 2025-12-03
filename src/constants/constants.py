from src.utils.helper import load_yaml
from src.constants.config_path import MODEL_CONFIG_PATH, PROMPT_TEMPLATES_PATH

MODEL_CONFIG = load_yaml(MODEL_CONFIG_PATH)
PROMPT_TEMPLATES = load_yaml(PROMPT_TEMPLATES_PATH)