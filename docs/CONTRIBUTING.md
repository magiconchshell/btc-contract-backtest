# 🤝 Contributing to BTC Contract Backtest System

Thank you for your interest in contributing! This guide will help you get started.

## 🚀 Quick Start

### 1. Fork and Clone

```bash
git clone https://github.com/YOUR_USERNAME/btc-contract-backtest.git
cd btc-contract-backtest
```

### 2. Set Up Development Environment

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -e ".[dev]"

# Pre-commit hooks (optional)
pre-commit install
```

### 3. Make Your Changes

Follow these guidelines:
- Write clear commit messages
- Add tests for new functionality
- Update documentation
- Run all tests before submitting

## 📝 Code Style

We use:
- **Black** for code formatting
- **Flake8** for linting
- **Mypy** for type checking

```bash
# Format code
black src/

# Lint code
flake8 src/

# Type check
mypy src/
```

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=btc_contract_backtest --cov-report=html
```

## 📦 Submitting Changes

1. Create a feature branch
   ```bash
   git checkout -b feature/amazing-feature
   ```

2. Make your changes and commit
   ```bash
   git add .
   git commit -m "feat: add amazing feature"
   ```

3. Push to your fork
   ```bash
   git push origin feature/amazing-feature
   ```

4. Open a Pull Request on GitHub

## 🐛 Bug Reports

When filing a bug report, please include:
- Clear description of the issue
- Steps to reproduce
- Expected vs actual behavior
- Your environment (OS, Python version, etc.)
- Screenshots if applicable

## 💡 Feature Requests

For new features:
1. Check if it already exists in issues
2. Describe the use case clearly
3. Provide examples if possible
4. Be open to discussion about implementation

## 📄 License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thanks for helping make this project better! 🎉
