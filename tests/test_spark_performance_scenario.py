import json
from pathlib import Path
from typing import Any


SCENARIO_DIR = Path(__file__).resolve().parents[1] / "scenarios" / "spark_performance"
BASELINE_PATH = SCENARIO_DIR / "baseline" / "customer_aggregation_run.json"
INCIDENT_PATH = SCENARIO_DIR / "incident" / "customer_aggregation_run.json"
EVALUATION_PATH = SCENARIO_DIR / "evaluation" / "expected_diagnosis.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def expected_range(contract: dict[str, Any], metric: str) -> tuple[float, float]:
    for item in contract["supporting_evidence"]:
        if item["metric"] == metric:
            metric_range = item["expected_range"]
            return metric_range["min"], metric_range["max"]
    raise AssertionError(f"Evaluation contract is missing {metric}.")


def test_spark_performance_fixture_loads_successfully() -> None:
    baseline = load_json(BASELINE_PATH)
    incident = load_json(INCIDENT_PATH)

    assert baseline["run_id"] != incident["run_id"]
    assert baseline["job_id"] == incident["job_id"] == "customer_aggregation"


def test_baseline_and_incident_include_required_telemetry() -> None:
    required_fields = {
        "run_id",
        "job_id",
        "job_name",
        "timestamp",
        "duration_seconds",
        "input_size_bytes",
        "output_size_bytes",
        "partition_count",
        "partition_size_stats_bytes",
        "shuffle_bytes",
        "executor_metrics",
        "stage_metrics",
        "spark_configuration",
    }

    for run in (load_json(BASELINE_PATH), load_json(INCIDENT_PATH)):
        assert required_fields <= run.keys()
        assert {"median", "largest"} <= run["partition_size_stats_bytes"].keys()
        assert {"read", "write"} <= run["shuffle_bytes"].keys()
        assert run["stage_metrics"]
        assert run["spark_configuration"]


def test_incident_represents_meaningful_runtime_regression() -> None:
    baseline = load_json(BASELINE_PATH)
    incident = load_json(INCIDENT_PATH)
    contract = load_json(EVALUATION_PATH)

    runtime_regression_ratio = incident["duration_seconds"] / baseline["duration_seconds"]
    minimum, maximum = expected_range(contract, "runtime_regression_ratio")

    assert minimum <= runtime_regression_ratio <= maximum


def test_input_growth_is_smaller_than_runtime_growth() -> None:
    baseline = load_json(BASELINE_PATH)
    incident = load_json(INCIDENT_PATH)
    contract = load_json(EVALUATION_PATH)

    input_growth_ratio = incident["input_size_bytes"] / baseline["input_size_bytes"]
    runtime_regression_ratio = incident["duration_seconds"] / baseline["duration_seconds"]
    minimum, maximum = expected_range(contract, "input_growth_ratio")

    assert minimum <= input_growth_ratio <= maximum
    assert input_growth_ratio < runtime_regression_ratio
    assert baseline["spark_configuration"] == incident["spark_configuration"]


def test_partition_skew_is_derivable_from_the_incident_fixture() -> None:
    incident = load_json(INCIDENT_PATH)
    contract = load_json(EVALUATION_PATH)
    stats = incident["partition_size_stats_bytes"]

    skew_ratio = stats["largest"] / stats["median"]
    minimum, maximum = expected_range(contract, "incident_skew_ratio")

    assert minimum <= skew_ratio <= maximum


def test_shuffle_increased_materially() -> None:
    baseline = load_json(BASELINE_PATH)
    incident = load_json(INCIDENT_PATH)
    contract = load_json(EVALUATION_PATH)

    shuffle_write_growth_ratio = (
        incident["shuffle_bytes"]["write"] / baseline["shuffle_bytes"]["write"]
    )
    minimum, maximum = expected_range(contract, "shuffle_write_growth_ratio")

    assert minimum <= shuffle_write_growth_ratio <= maximum
    assert incident["shuffle_bytes"]["read"] > baseline["shuffle_bytes"]["read"]


def test_evaluation_contract_is_valid_and_separate_from_telemetry() -> None:
    contract = load_json(EVALUATION_PATH)
    telemetry = [load_json(BASELINE_PATH), load_json(INCIDENT_PATH)]

    assert contract["expected_root_cause_category"] == "DATA_SKEW"
    assert {item["expected_status"] for item in contract["alternative_hypotheses"]} == {
        "REJECTED",
        "INCONCLUSIVE",
    }
    assert all("DATA_SKEW" not in json.dumps(run) for run in telemetry)
    assert EVALUATION_PATH not in {BASELINE_PATH, INCIDENT_PATH}
