"""Phase I - AI Strategy Proposal Compiler.

Proposal -> existing Strategy Specification -> existing CompiledStrategy.

The proposal's ``strategy`` block IS a full existing strategy specification
(schema_version, strategy, market, regime, entry, direction, instrument,
strike_selection, risk, exit, execution, data_requirements, state,
references). Compiling a proposal therefore does NOT create a parallel engine:
it validates the block with the EXISTING strategy_validator and compiles it
with the EXISTING strategy_compiler, attaching proposal provenance alongside.

Never executes anything from the proposal.
"""
import json
import os

import strategy_proposal_schema as PS
import strategy_proposal_validator as PV
import strategy_validator as SV
import strategy_compiler as SC


class ProposalCompilation:
    def __init__(self, proposal, validation, compiled):
        self.proposal = proposal
        self.validation = validation
        self.compiled = compiled  # strategy_compiler.CompiledStrategy
        self.spec = compiled.spec if compiled else None
        self.spec_hash = compiled.spec_hash if compiled else None
        self.proposal_hash = PS.proposal_hash(proposal)
        self.fingerprint = PS.normalized_rule_fingerprint(compiled.spec) \
            if compiled else None

    @property
    def strategy_id(self):
        return self.compiled.strategy_id if self.compiled else None

    def to_record(self):
        return {
            "proposal_id": (self.proposal.get("proposal") or {}).get("proposal_id"),
            "title": (self.proposal.get("proposal") or {}).get("title"),
            "author_type": (self.proposal.get("proposal") or {}).get("author_type"),
            "author_model": (self.proposal.get("proposal") or {}).get("author_model"),
            "parent_strategy_id": (self.proposal.get("proposal") or {}).get(
                "parent_strategy_id"),
            "strategy_id": self.strategy_id,
            "proposal_hash": self.proposal_hash,
            "spec_hash": self.spec_hash,
            "fingerprint": self.fingerprint,
            "research": self.proposal.get("research") or {},
        }


def compile_proposal(proposal):
    """Validate then compile a proposal document.

    Returns ProposalCompilation. Raises ValueError with a structured failure
    code if the proposal is invalid.
    """
    validation = PV.validate_proposal(proposal)
    if not validation.valid:
        raise ValueError(
            f"{validation.failure_code}: proposal failed validation "
            f"({len(validation.errors)} errors)\n" + "\n".join(validation.errors[:8]))

    strategy_block = proposal["strategy"]
    compiled = SC.compile_strategy(strategy_block)
    return ProposalCompilation(proposal, validation, compiled)


def compile_file(path):
    """Compile a YAML proposal file."""
    import yaml
    with open(path) as fh:
        proposal = yaml.safe_load(fh)
    return compile_proposal(proposal)
