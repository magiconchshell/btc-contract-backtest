"""Configuration file loading for EngineConfig.

Supports loading engine configuration from YAML or JSON files,
enabling reproducible, version-controlled deployment configs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from btc_contract_backtest.config.models import (
    AccountConfig,
    ContractSpec,
    EngineConfig,
    ExecutionConfig,
    LeverageBracket,
    LiveRiskConfig,
    RiskConfig,
)


def _merge_dataclass(cls, data: dict[str, Any], defaults: Optional[Any] = None):
    """Create a dataclass instance from a dict, using defaults for missing keys."""
    if defaults is not None:
        base = {k: v for k, v in vars(defaults).items()}
        base.update(data)
        data = base

    # Filter out keys not in the dataclass fields
    import dataclasses
    field_names = {f.name for f in dataclasses.fields(cls)}
    filtered = {k: v for k, v in data.items() if k in field_names}
    return cls(**filtered)


def load_config_from_dict(data: dict[str, Any]) -> EngineConfig:
    """Build EngineConfig from a nested dict (parsed from YAML/JSON)."""
    contract_data = data.get("contract", {})
    # Handle leverage_brackets specially
    brackets_raw = contract_data.pop("leverage_brackets", [])
    brackets = [
        LeverageBracket(**b) if isinstance(b, dict) else b
        for b in brackets_raw
    ]
    contract = _merge_dataclass(ContractSpec, contract_data)
    contract.leverage_brackets = brackets

    account = _merge_dataclass(AccountConfig, data.get("account", {}))
    risk = _merge_dataclass(RiskConfig, data.get("risk", {}))
    execution = _merge_dataclass(ExecutionConfig, data.get("execution", {}))
    live_risk = _merge_dataclass(LiveRiskConfig, data.get("live_risk", {}))

    return EngineConfig(
        contract=contract,
        account=account,
        risk=risk,
        execution=execution,
        live_risk=live_risk,
    )


def load_config_from_json(path: str | Path) -> EngineConfig:
    """Load EngineConfig from a JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return load_config_from_dict(data)


def load_config_from_yaml(path: str | Path) -> EngineConfig:
    """Load EngineConfig from a YAML file."""
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "PyYAML is required for YAML config loading. "
            "Install it with: pip install pyyaml"
        )
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return load_config_from_dict(data)


def load_config(path: str | Path) -> EngineConfig:
    """Load EngineConfig from a file, autodetecting format."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        return load_config_from_yaml(path)
    elif suffix == ".json":
        return load_config_from_json(path)
    else:
        # Try JSON first, then YAML
        try:
            return load_config_from_json(path)
        except (json.JSONDecodeError, Exception):
            return load_config_from_yaml(path)
