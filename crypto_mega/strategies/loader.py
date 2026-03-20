"""Dynamic strategy loader — loads strategies from files, code strings, or modules."""

from __future__ import annotations

import importlib.util
import logging
import sys
import types
from pathlib import Path
from typing import Type

from crypto_mega.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


class StrategyLoader:
    """Loads strategy classes from various sources."""

    def __init__(self):
        self._registry: dict[str, Type[BaseStrategy]] = {}

    def register(self, name: str, cls: Type[BaseStrategy]) -> None:
        """Manually register a strategy class."""
        if not issubclass(cls, BaseStrategy):
            raise TypeError(f"{cls} must be a subclass of BaseStrategy")
        self._registry[name] = cls
        logger.info(f"Registered strategy: {name}")

    def load_from_file(self, filepath: str | Path) -> list[Type[BaseStrategy]]:
        """Load all BaseStrategy subclasses from a .py file."""
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"Strategy file not found: {filepath}")

        module_name = f"strategy_{filepath.stem}"
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        found = []
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseStrategy)
                and attr is not BaseStrategy
            ):
                self._registry[attr_name] = attr
                found.append(attr)
                logger.info(f"Loaded strategy from file: {attr_name} ({filepath})")

        return found

    def load_from_code(self, code: str, name: str = "dynamic_strategy") -> list[Type[BaseStrategy]]:
        """
        Load strategy from a code string.
        This is the key feature — Vasya or GPT writes code, we execute it.
        """
        module = types.ModuleType(f"strategy_{name}")
        # Inject base class into module namespace so strategies can import it
        module.__dict__["BaseStrategy"] = BaseStrategy

        exec(code, module.__dict__)  # noqa: S102
        sys.modules[f"strategy_{name}"] = module

        found = []
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseStrategy)
                and attr is not BaseStrategy
            ):
                self._registry[attr_name] = attr
                found.append(attr)
                logger.info(f"Loaded strategy from code: {attr_name}")

        return found

    def load_directory(self, directory: str | Path) -> list[Type[BaseStrategy]]:
        """Scan a directory and load all .py files containing strategies."""
        directory = Path(directory)
        if not directory.exists():
            logger.warning(f"Strategy directory not found: {directory}")
            return []

        found = []
        for py_file in sorted(directory.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                found.extend(self.load_from_file(py_file))
            except Exception as e:
                logger.error(f"Failed to load {py_file}: {e}")
        return found

    def get(self, name: str) -> Type[BaseStrategy] | None:
        return self._registry.get(name)

    def list_all(self) -> dict[str, Type[BaseStrategy]]:
        return dict(self._registry)


# Global singleton
strategy_loader = StrategyLoader()
