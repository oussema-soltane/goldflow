"""Research readiness and descriptive event statistics for GoldFlow."""

from src.research.data_readiness import (
    audit_all_datasets, audit_dataset, classify_gaps, evaluate_research_readiness,
)
from src.research.event_statistics import (
    PeriodSplit, measure_forward_excursion, classify_session,
    build_structure_break_report, build_fvg_report, compute_rolling_atr,
)
from src.research.smc_research import (
    ResearchProtocolConfig,
    load_and_verify_inputs,
    extract_events_dataframe,
    compute_event_distribution,
    evaluate_setups_and_excursions,
    compute_common_window_study,
    run_full_phase3c_research,
)

__all__ = [
    "audit_all_datasets", "audit_dataset", "classify_gaps", "evaluate_research_readiness",
    "PeriodSplit", "measure_forward_excursion", "classify_session",
    "build_structure_break_report", "build_fvg_report", "compute_rolling_atr",
    "ResearchProtocolConfig",
    "load_and_verify_inputs",
    "extract_events_dataframe",
    "compute_event_distribution",
    "evaluate_setups_and_excursions",
    "compute_common_window_study",
    "run_full_phase3c_research",
]

