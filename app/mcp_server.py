import json
from mcp.server.mcpserver import MCPServer
from app.evidence_tools.spark import SparkFixtureEvidenceProvider, SparkEvidenceProviderError

mcp = MCPServer("Spark Evidence Server")
provider = SparkFixtureEvidenceProvider()

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

if __name__ == "__main__":
    mcp.run()
