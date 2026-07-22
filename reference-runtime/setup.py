"""Intent OS — setup.py for backward compatibility."""
from setuptools import setup, find_packages

setup(
    name="intent-os",
    version="0.2.0",
    description="An open interoperability layer for AI capabilities, workflows, and execution",
    packages=find_packages(exclude=["tests*"]),
    py_modules=["cli"],
    python_requires=">=3.10",
    install_requires=[
        "pyyaml>=6.0",
    ],
    extras_require={
        "openai": ["openai>=1.0.0"],
        "anthropic": ["anthropic>=0.30.0"],
        "all": ["openai>=1.0.0", "anthropic>=0.30.0"],
    },
    entry_points={
        "console_scripts": [
            "intent-os=cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
)
