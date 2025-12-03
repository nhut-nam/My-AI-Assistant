import setuptools
from pathlib import Path

# Read README safely
readme_path = Path(__file__).parent / "README.md"
if readme_path.exists():
    long_description = readme_path.read_text(encoding="utf-8")
else:
    long_description = "My-AI-Assistant Package"

__version__ = "0.0.1"

REPO_NAME = "My-AI-Assistant"
AUTHOR_USER_NAME = "nhut-nam"
SRC_REPO = "src"
AUTHOR_EMAIL = "namnhut1426@gmail.com"

setuptools.setup(
    name=SRC_REPO,
    version=__version__,
    author=AUTHOR_USER_NAME,
    author_email=AUTHOR_EMAIL,
    description="A package for My-AI-Assistant",
    long_description=long_description,
    long_description_content_type="text/markdown",

    url=f"https://github.com/{AUTHOR_USER_NAME}/{REPO_NAME}",
    project_urls={
        "Bug Tracker": f"https://github.com/{AUTHOR_USER_NAME}/{REPO_NAME}/issues",
    },

    package_dir={"": "src"},
    packages=setuptools.find_packages(where="src"),

    include_package_data=True,  # <-- include YAML/JSON/prompts/templates

    python_requires=">=3.10",

    # If needed, add your dependencies here
    install_requires=[
        "python-dotenv",
        "langchain",
        "langchain-groq",
        "langchain-ollama",
    ],

    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],

    keywords="agent multi-agent sop plan executor langchain langgraph",
)
