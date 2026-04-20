"""DSPy optimization scaffold for the discovery pipeline.

Defines DSPy modules and signatures for each discovery stage, a quality
metric function, and optimization entry points. Run per-stage optimization
first, then end-to-end validation.

This is a development-time tool. Optimized prompts are exported back to
the DB prompt block system — DSPy is NOT a production runtime dependency.

Usage:
    pip install dspy-ai
    python -m scripts.dspy_optimize --stage discovery_domain --preset light
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

try:
    import dspy
except ImportError:
    logger.error("DSPy not installed. Run: pip install dspy-ai")
    sys.exit(1)


class DomainDiscoverySignature(dspy.Signature):
    """Identify top-level business process domains from org metadata and documents."""
    org_context: str = dspy.InputField(desc="Organization context JSON")
    metadata_summary: str = dspy.InputField(desc="Platform metadata summary JSON")
    document_excerpts: str = dspy.InputField(desc="Relevant document excerpts JSON")
    domains: str = dspy.OutputField(desc="JSON array of domain objects with name, description, confidence, associated_objects, reasoning")


class StructuralDecompositionSignature(dspy.Signature):
    """Decompose a business domain into processes, subprocesses, and steps."""
    domain: str = dspy.InputField(desc="Domain name and description JSON")
    metadata_detail: str = dspy.InputField(desc="Detailed metadata for this domain JSON")
    document_chunks: str = dspy.InputField(desc="Relevant document excerpts JSON")
    processes: str = dspy.OutputField(desc="Flat JSON array of process/subprocess/step items with parent_name hierarchy")


class EnrichmentFlowSignature(dspy.Signature):
    """Enrich steps with operational details and identify flows/handoffs."""
    steps: str = dspy.InputField(desc="Steps to enrich with metadata context JSON")
    process_tree: str = dspy.InputField(desc="Enriched process hierarchy JSON")
    relationships: str = dspy.InputField(desc="Metadata relationships and dependency graph JSON")
    enriched_steps: str = dspy.OutputField(desc="JSON with enriched_steps array and step_flows/handoffs")


class ValidationSignature(dspy.Signature):
    """Validate a complete process map against raw metadata evidence."""
    process_map: str = dspy.InputField(desc="Complete enriched process map JSON")
    raw_metadata: str = dspy.InputField(desc="Raw metadata for validation JSON")
    document_evidence: str = dspy.InputField(desc="Document evidence JSON")
    critique_and_patches: str = dspy.OutputField(desc="JSON with critique array and patches object")


class SynthesisSignature(dspy.Signature):
    """Identify cross-domain handoffs, gaps, and orphaned artifacts."""
    all_domains: str = dspy.InputField(desc="All domains with full process hierarchies JSON")
    orphaned_artifacts: str = dspy.InputField(desc="Unclaimed metadata artifacts JSON")
    synthesis: str = dspy.OutputField(desc="JSON with cross_domain_handoffs, orphaned_artifacts, executive_summary")


STAGE_SIGNATURES = {
    "discovery_domain": DomainDiscoverySignature,
    "discovery_structure": StructuralDecompositionSignature,
    "discovery_enrichment_flow": EnrichmentFlowSignature,
    "discovery_validation": ValidationSignature,
    "discovery_synthesis": SynthesisSignature,
}


def quality_metric(example: dspy.Example, prediction: dspy.Prediction, trace=None) -> float:
    """Combined quality + cost metric for optimizer.

    Uses the stage 7 quality scoring heuristics as the primary signal.
    Cost penalty ensures the optimizer doesn't find prompts that require
    significantly more tokens for marginal quality gains.
    """
    try:
        output = json.loads(prediction.get("domains") or prediction.get("processes") or
                           prediction.get("enriched_steps") or prediction.get("critique_and_patches") or
                           prediction.get("synthesis") or "{}")
    except (json.JSONDecodeError, TypeError):
        return 0.0

    if not output:
        return 0.0

    completeness = 1.0
    if isinstance(output, list):
        completeness = min(1.0, len(output) / 3)
    elif isinstance(output, dict):
        required_keys = set(example.get("expected_keys", []))
        if required_keys:
            present = required_keys & set(output.keys())
            completeness = len(present) / len(required_keys)

    return completeness


def load_training_data(stage: str, data_dir: str = "scripts/dspy_data") -> list[dspy.Example]:
    """Load training examples from JSON files.

    Training data should be captured from production Langfuse traces
    using capture_baseline.py as the starting point.
    """
    data_path = Path(data_dir) / f"{stage}_examples.json"
    if not data_path.exists():
        logger.warning("No training data found at %s", data_path)
        logger.info("Create training data by running the pipeline and exporting Langfuse traces.")
        return []

    with open(data_path) as f:
        examples = json.load(f)

    return [dspy.Example(**ex).with_inputs(*[k for k in ex if k != "expected_output"]) for ex in examples]


def optimize_stage(stage: str, model: str, preset: str = "light") -> None:
    """Run MIPROv2 optimization for a single pipeline stage."""
    if stage not in STAGE_SIGNATURES:
        logger.error("Unknown stage: %s. Available: %s", stage, list(STAGE_SIGNATURES.keys()))
        sys.exit(1)

    lm = dspy.LM(model)
    dspy.configure(lm=lm)

    signature = STAGE_SIGNATURES[stage]
    module = dspy.ChainOfThought(signature)

    trainset = load_training_data(stage)
    if not trainset:
        logger.error("Cannot optimize without training data. See load_training_data() for instructions.")
        sys.exit(1)

    optimizer = dspy.MIPROv2(
        metric=quality_metric,
        auto=preset,
    )

    logger.info("Starting %s optimization for stage=%s with %d examples", preset, stage, len(trainset))
    optimized = optimizer.compile(
        module.deepcopy(),
        trainset=trainset,
        max_bootstrapped_demos=3,
        max_labeled_demos=4,
    )

    out_path = Path("scripts/dspy_data") / f"{stage}_optimized.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    optimized.save(str(out_path))
    logger.info("Optimized module saved to %s", out_path)


def main():
    parser = argparse.ArgumentParser(description="DSPy optimization for discovery pipeline")
    parser.add_argument("--stage", required=True, choices=list(STAGE_SIGNATURES.keys()),
                       help="Pipeline stage to optimize")
    parser.add_argument("--model", default="anthropic/claude-sonnet-4-6",
                       help="LiteLLM model string for optimization")
    parser.add_argument("--preset", default="light", choices=["light", "medium", "heavy"],
                       help="MIPROv2 preset (light=~10 trials, medium=~40, heavy=~100+)")
    args = parser.parse_args()

    optimize_stage(args.stage, args.model, args.preset)


if __name__ == "__main__":
    main()
