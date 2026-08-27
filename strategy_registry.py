"""Phase H1 v2 - Strategy Registry (filesystem-backed, MVP).

No database: strategies are YAML files under strategies/. Registry exposes
list / load / validate / compile / spec_hash and enforces id+version identity.
"""
import os

import strategy_schema as S
import strategy_validator
import strategy_compiler

STRATEGIES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategies")


class StrategyRegistry:
    def __init__(self, base_dir=None):
        self.base_dir = base_dir or STRATEGIES_DIR

    # -- discovery ----------------------------------------------------------
    def _files(self):
        if not os.path.isdir(self.base_dir):
            return []
        return sorted(
            os.path.join(self.base_dir, f)
            for f in os.listdir(self.base_dir)
            if f.endswith(".yaml")
        )

    def list_strategies(self):
        out = []
        for path in self._files():
            try:
                spec = self._read(path)
                st = spec["strategy"]
                state = spec.get("state", {})
                out.append({
                    "id": st["id"], "name": st.get("name"), "version": st.get("version"),
                    "classification": st.get("classification"),
                    "lifecycle": state.get("lifecycle"),
                    "path": path,
                })
            except Exception:
                out.append({"id": os.path.splitext(os.path.basename(path))[0],
                            "path": path, "error": "unreadable"})
        return out

    # -- loading --------------------------------------------------------------
    @staticmethod
    def _read(path):
        import yaml
        with open(path) as fh:
            return yaml.safe_load(fh)

    def find_path(self, strategy_id):
        for path in self._files():
            try:
                spec = self._read(path)
            except Exception:
                continue
            if spec.get("strategy", {}).get("id") == strategy_id:
                return path
        return None

    def load(self, strategy_id, version=None):
        """Load a spec dict by id, optionally pinning the version."""
        path = self.find_path(strategy_id)
        if path is None:
            raise KeyError(f"strategy {strategy_id!r} not found in {self.base_dir}")
        spec = self._read(path)
        st = spec.get("strategy", {})
        if st.get("id") != strategy_id:
            raise ValueError(f"file {path} declares id {st.get('id')!r}, not {strategy_id!r}")
        if version is not None and st.get("version") != version:
            raise ValueError(f"strategy {strategy_id} version mismatch: "
                             f"requested {version}, file has {st.get('version')}")
        return spec

    # -- lifecycle ------------------------------------------------------------------
    def validate(self, strategy_id):
        path = self.find_path(strategy_id)
        if path is None:
            raise KeyError(strategy_id)
        return strategy_validator.validate_file(path)

    def compile(self, strategy_id):
        path = self.find_path(strategy_id)
        if path is None:
            raise KeyError(strategy_id)
        return strategy_compiler.compile_file(path)

    def spec_hash(self, strategy_id):
        return S.spec_hash(self.load(strategy_id))


def default_registry():
    return StrategyRegistry()
