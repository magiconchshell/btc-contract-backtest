from setuptools import setup, find_packages

setup(
    name="btc-contract-backtest",
    version="5.0.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.9",
    install_requires=[
        "ccxt>=4.0.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "matplotlib>=3.7.0",
        "seaborn>=0.12.0",
        "fastapi>=0.115.0",
        "uvicorn>=0.30.0",
    ],
    entry_points={
        "console_scripts": [
            "btc-backtest=btc_contract_backtest.cli.main:main",
        ]
    },
)
