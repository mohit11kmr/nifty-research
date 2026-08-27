"""Phase I - AI Strategy Proposal Registry (filesystem-backed).

Each accepted proposal is stored as a JSON record under strategy_proposals/.
The record preserves full provenance (section 19): proposal_hash, spec_hash,
fingerprint, dataset_hash, model identity, creation timestamp, and lifecycle
status. Promotion is explicit only - the registry never auto-promotes.
"""
import hashlib
import json
import os
import uuid

import strategy_proposal_schema as PS

PROPOSALS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "strategy_proposals")


class ProposalRegistry:
    def __init__(self, base_dir=None):
        self.base_dir = base_dir or PROPOSALS_DIR
        os.makedirs(self.base_dir, exist_ok=True)

    # -- paths -----------------------------------------------------------------
    def _path(self, proposal_id):
        safe = "".join(c for c in str(proposal_id) if c.isalnum() or c in "_-")
        return os.path.join(self.base_dir, f"{safe}.json")

    # -- listing ----------------------------------------------------------------
    def list_proposals(self):
        out = []
        for f in sorted(os.listdir(self.base_dir)):
            if not f.endswith(".json"):
                continue
            path = os.path.join(self.base_dir, f)
            try:
                with open(path) as fh:
                    rec = json.load(fh)
                out.append({
                    "proposal_id": rec.get("proposal_id"),
                    "title": rec.get("title"),
                    "strategy_id": rec.get("strategy_id"),
                    "status": rec.get("status"),
                    "created_at": rec.get("created_at"),
                    "path": path,
                })
            except Exception:
                out.append({"proposal_id": os.path.splitext(f)[0],
                            "path": path, "status": "unreadable"})
        return out

    # -- writes ----------------------------------------------------------------
    def register(self, compilation, dataset_hash=None, status="DRAFT",
                 experiment_id=None, model_id=None, model_version=None):
        """Register a validated/compiled proposal (idempotent by proposal_id).
        Existing records are never silently overwritten with a different
        proposal_hash (provenance immutability).

        experiment_id / model_id / model_version record the controlled
        multi-model experiment provenance (Phase I.1, section 19).
        """
        meta = (compilation.proposal.get("proposal") or {})
        proposal_id = meta.get("proposal_id") or uuid.uuid4().hex[:12]
        path = self._path(proposal_id)
        if os.path.exists(path):
            with open(path) as fh:
                existing = json.load(fh)
            if existing.get("proposal_hash") != compilation.proposal_hash:
                raise ValueError(
                    f"proposal {proposal_id} already exists with a DIFFERENT "
                    f"content hash; refusing to overwrite provenance")
        record = {
            "proposal_id": proposal_id,
            "title": meta.get("title"),
            "author_type": meta.get("author_type"),
            "author_model": meta.get("author_model"),
            "parent_strategy_id": meta.get("parent_strategy_id"),
            "created_at": meta.get("created_at"),
            "template_version": PS.PROPOSAL_SCHEMA_VERSION,
            "experiment_id": experiment_id,
            "model_id": model_id,
            "model_version": model_version,
            "strategy_id": compilation.strategy_id,
            "proposal_hash": compilation.proposal_hash,
            "spec_hash": compilation.spec_hash,
            "fingerprint": compilation.fingerprint,
            "dataset_hash": dataset_hash,
            "result_hash": None,
            "status": status,
            "failure_code": None,
            "human_decision": None,
            "evidence": None,
            "validation_status": "PENDING",
            "backtest_status": "PENDING",
            "review_status": "PENDING_REVIEW",
        }
        with open(path, "w") as fh:
            json.dump(record, fh, indent=2, sort_keys=True, default=str)
        return record

    # -- updates ----------------------------------------------------------------
    def update(self, proposal_id, **fields):
        path = self._path(proposal_id)
        if not os.path.exists(path):
            raise KeyError(f"proposal {proposal_id} not registered")
        with open(path) as fh:
            record = json.load(fh)
        for k, v in fields.items():
            record[k] = v
        with open(path, "w") as fh:
            json.dump(record, fh, indent=2, sort_keys=True, default=str)
        return record

    # -- lookup ----------------------------------------------------------------
    def get(self, proposal_id):
        path = self._path(proposal_id)
        if not os.path.exists(path):
            raise KeyError(proposal_id)
        with open(path) as fh:
            return json.load(fh)

    def find_by_fingerprint(self, fingerprint):
        for f in os.listdir(self.base_dir):
            if not f.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.base_dir, f)) as fh:
                    rec = json.load(fh)
            except Exception:
                continue
            if rec.get("fingerprint") == fingerprint:
                return rec
        return None

    # -- duplicate detection ------------------------------------------------------
    def duplicate(self, compilation):
        """Return the existing record if the proposal is an exact/near duplicate
        (same normalized rule fingerprint), else None."""
        return self.find_by_fingerprint(compilation.fingerprint)


def default_registry():
    return ProposalRegistry()
