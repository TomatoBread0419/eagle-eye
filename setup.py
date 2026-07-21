from setuptools import setup, find_packages

setup(
    name="eagle_eye",
    version="7.2.0",
    packages=find_packages(),
    install_requires=[
        "requests",
        "python-dotenv",
        # "alpaca-py",  # optional: custom AlpacaClient used instead
        "numpy",
        "pandas",
    ],
)
