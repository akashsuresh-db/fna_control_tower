"""Configuration for the Finance Operations App."""
import os

IS_DATABRICKS_APP = bool(os.environ.get("DATABRICKS_APP_NAME"))

WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID", "148ccb90800933a1")
GENIE_SPACE_ID = os.environ.get("GENIE_SPACE_ID", "01f122c95c741815919b6457017f0899")
CATALOG = os.environ.get("DATABRICKS_CATALOG", "akash_s_demo")
SCHEMA = os.environ.get("DATABRICKS_SCHEMA", "finance_and_accounting")

FMAPI_MODEL = "databricks-claude-sonnet-4-5"


def get_workspace_host() -> str:
    """Get workspace host URL with https:// prefix."""
    host = os.environ.get("DATABRICKS_HOST", "")
    if host and not host.startswith("http"):
        host = f"https://{host}"
    if not host:
        # Fallback for local dev
        host = "https://adb-984752964297111.11.azuredatabricks.net"
    return host.rstrip("/")


def get_token() -> str:
    """Get auth token - works in Databricks Apps and locally."""
    # First try explicit token (Databricks Apps injects this)
    token = os.environ.get("DATABRICKS_TOKEN", "")
    if token:
        return token

    # Try Databricks SDK (works for service principal and local dev)
    try:
        from databricks.sdk import WorkspaceClient

        if IS_DATABRICKS_APP:
            w = WorkspaceClient()
        else:
            profile = os.environ.get("DATABRICKS_CONFIG_PROFILE", "field-east")
            w = WorkspaceClient(profile=profile)

        if w.config.token:
            return w.config.token

        headers = w.config.authenticate()
        if headers and "Authorization" in headers:
            return headers["Authorization"].replace("Bearer ", "")
    except Exception as e:
        print(f"SDK auth failed: {e}")

    return ""


def full_table(table: str) -> str:
    """Return fully qualified table name."""
    return f"`{CATALOG}`.`{SCHEMA}`.`{table}`"
