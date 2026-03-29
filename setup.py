#!/usr/bin/env python3
"""Setup script for Bitcoin Contract Trading Backtest System."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="btc-contract-backtest",
    version="4.0.0",
    author="Magic Conch Shell Team",
    author_email="contact@magicconchshell.com",
    description="Professional cryptocurrency trading backtest platform",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/magiconch/btc-contract-backtest",
    project_urls={
        "Bug Tracker": "https://github.com/magiconch/btc-contract-backtest/issues",
        "Documentation": "https://github.com/magiconch/btc-contract-backtest#readme",
        "Source Code": "https://github.com/magiconch/btc-contract-backtest",
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Financial and Insurance Industry",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Office/Business :: Financial :: Investment",
        "Topic :: Scientific/Engineering :: Information Analysis",
    ],
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.9",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "black>=23.0.0",
            "flake8>=6.1.0",
            "mypy>=1.5.0",
        ],
        "optional": [
            "plotly>=5.18.0",
            "jupyter>=1.0.0",
            "scikit-learn>=1.3.0",
            "statsmodels>=0.14.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "btc-backtest=btc_contract_backtest.main:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
