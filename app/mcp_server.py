import json
from mcp.server.mcpserver import MCPServer
from app.evidence_tools.spark import SparkFixtureEvidenceProvider, SparkEvidenceProviderError
from app.evidence_tools.pipeline import PipelineFixtureEvidenceProvider, PipelineEvidenceProviderError
from app.evidence_tools.data_quality import DataQualityFixtureEvidenceProvider, UnknownDataQualityRunError
from app.evidence_tools.sql_regression import SQLFixtureEvidenceProvider, UnknownSQLQueryError

mcp = MCPServer("Spark Evidence Server")
provider = SparkFixtureEvidenceProvider()
pipeline_provider = PipelineFixtureEvidenceProvider()
dq_provider = DataQualityFixtureEvidenceProvider()
sql_provider = SQLFixtureEvidenceProvider()

@mcp.tool()
def spark_get_job(run_id: str) -> str:
    """Get high level Spark job telemetry for a specific run."""
    try:
        res = provider.get_job(run_id)
        return res.model_dump_json()
    except SparkEvidenceProviderError as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def spark_get_run(run_id: str) -> str:
    """Get the complete raw telemetry fixture for a specific run."""
    try:
        res = provider.get_run(run_id)
        return res.model_dump_json()
    except SparkEvidenceProviderError as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def spark_get_stages(run_id: str) -> str:
    """Get detailed stage-level telemetry for a Spark run."""
    try:
        res = provider.get_stages(run_id)
        return res.model_dump_json()
    except SparkEvidenceProviderError as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def spark_get_partition_statistics(run_id: str) -> str:
    """Get global partition size statistics for a Spark run."""
    try:
        res = provider.get_partition_statistics(run_id)
        return res.model_dump_json()
    except SparkEvidenceProviderError as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def spark_get_configuration(run_id: str) -> str:
    """Get the Spark configuration for a specific run."""
    try:
        res = provider.get_configuration(run_id)
        return json.dumps(res)
    except SparkEvidenceProviderError as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def spark_get_baseline(job_id: str, run_id: str) -> str:
    """Get comparable baseline telemetry for a Spark job."""
    try:
        res = provider.get_baseline(job_id, run_id)
        return res.model_dump_json()
    except SparkEvidenceProviderError as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def pipeline_get_run(run_id: str) -> str:
    """Get metadata for a specific pipeline run."""
    try:
        res = pipeline_provider.get_run(run_id)
        return res.model_dump_json()
    except PipelineEvidenceProviderError as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def pipeline_get_logs(run_id: str, task_id: str) -> str:
    """Get logs for a specific task in a pipeline run."""
    try:
        res = pipeline_provider.get_logs(run_id, task_id)
        return res.model_dump_json()
    except PipelineEvidenceProviderError as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def pipeline_get_current_schema(dataset_id: str, table_id: str) -> str:
    """Get the current schema for a given table."""
    try:
        res = pipeline_provider.get_current_schema(dataset_id, table_id)
        return res.model_dump_json()
    except PipelineEvidenceProviderError as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def pipeline_get_baseline_schema(dataset_id: str, table_id: str) -> str:
    """Get the historical/expected schema for a given table."""
    try:
        res = pipeline_provider.get_baseline_schema(dataset_id, table_id)
        return res.model_dump_json()
    except PipelineEvidenceProviderError as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def data_quality_get_run(run_id: str) -> str:
    """Get metadata for a specific data quality run."""
    try:
        from dataclasses import asdict
        res = dq_provider.get_run(run_id)
        return json.dumps(asdict(res))
    except UnknownDataQualityRunError as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def data_quality_get_baseline(dataset: str, table: str) -> str:
    """Get the baseline data quality metrics for a given table."""
    try:
        from dataclasses import asdict
        res = dq_provider.get_baseline(dataset, table)
        return json.dumps(asdict(res))
    except UnknownDataQualityRunError as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def sql_get_query(query_id: str) -> str:
    """Get metadata for a specific SQL query run."""
    try:
        from dataclasses import asdict
        res = sql_provider.get_query(query_id)
        return json.dumps(asdict(res))
    except UnknownSQLQueryError as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def sql_get_baseline_query() -> str:
    """Get the baseline query for SQL regression investigation."""
    try:
        from dataclasses import asdict
        res = sql_provider.get_baseline_query()
        return json.dumps(asdict(res))
    except UnknownSQLQueryError as e:
        return json.dumps({"error": str(e)})

if __name__ == "__main__":
    mcp.run()
