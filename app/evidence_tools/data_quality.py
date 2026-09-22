import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class UnknownDataQualityRunError(Exception):
    pass

@dataclass
class DataQualityMetrics:
    row_count: int
    revenue: float
    expected_partition_count: int
    observed_partition_count: int
    missing_partitions: List[str]
    null_key_ratio: float
    duplicate_ratio: float

@dataclass
class DataQualityRun:
    run_id: str
    dataset: str
    table: str
    metrics: DataQualityMetrics

class DataQualityEvidenceProvider(ABC):
    @abstractmethod
    def get_run(self, run_id: str) -> DataQualityRun:
        pass
    
    @abstractmethod
    def get_baseline(self, dataset: str, table: str) -> DataQualityRun:
        pass

class DataQualityFixtureEvidenceProvider(DataQualityEvidenceProvider):
    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            self.data_dir = Path(__file__).resolve().parent.parent.parent / "scenarios" / "data_quality"
        else:
            self.data_dir = Path(data_dir)
            
    def _load_run(self, path: Path) -> DataQualityRun:
        if not path.exists():
            raise UnknownDataQualityRunError(f"Fixture not found: {path}")
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return DataQualityRun(
                run_id=data["run_id"],
                dataset=data["dataset"],
                table=data["table"],
                metrics=DataQualityMetrics(**data["metrics"])
            )
        except Exception as e:
            logger.error(f"Error loading fixture {path}: {e}")
            raise

    def get_run(self, run_id: str) -> DataQualityRun:
        if run_id != "dq-run-2026-09-20":
            raise UnknownDataQualityRunError(f"Unknown run ID: {run_id}")
        # In this mock, we just load the incident run
        # In a real system, we'd query by run_id
        path = self.data_dir / "incident" / "run.json"
        return self._load_run(path)

    def get_baseline(self, dataset: str, table: str) -> DataQualityRun:
        path = self.data_dir / "baseline" / "run.json"
        return self._load_run(path)
