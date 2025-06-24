import os
import json
from mcp.server.fastmcp import FastMCP
import aiosqlite
from dotenv import load_dotenv
import logging
import sys

# --- Logging Setup ---
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# --- Database Path and Validation ---
def check_db_path(path: str):
    """
    Validates the database path. Exits if validation fails.
    - Checks if the path exists and is a file.
    - Checks if the file is a valid SQLite3 database by reading its header.
    """
    if not os.path.isfile(path):
        logger.critical(f"Database path does not point to a file: {path}")
        sys.exit(1)

    # Check for SQLite magic number
    try:
        with open(path, 'rb') as f:
            header = f.read(16)
        if header != b'SQLite format 3\x00':
            logger.critical(f"File is not a valid SQLite3 database: {path}")
            sys.exit(1)
    except IOError as e:
        logger.critical(f"Cannot read database file at {path}: {e}")
        sys.exit(1)
    logger.info("Database file validation successful.")

# loading variable from .env file
# Rhis file contains DB_HOST_PATH variable that is having DB_PATH for a file
load_dotenv()
# Use DB_PATH from environment if available (for Docker),
# otherwise, fall back to DB_HOST_PATH (for local development).
DB_PATH = os.environ.get("DB_PATH") or os.environ.get("DB_HOST_PATH", ".")
logger.info(f"DB_PATH: {DB_PATH}")

check_db_path(DB_PATH)

# --- MCP Server Setup ---
# Initialize the FastMCP server. This is the heart of our MCP application.
mcp = FastMCP("python-sqlite-server")

# Get database path from environment variable, with a fallback for local testing

# --- MCP Tools for Database Interaction ---

@mcp.tool()
async def execute_query(query: str) -> str:
    """
    Executes a read-only SQL query on the database.
    Only SELECT statements are allowed.
    Args:
        query: The SQL SELECT statement to execute.
    Returns:
        A JSON string of the query result.
    """
    logger.debug("Received query: %s", query)
    if not query.lstrip().upper().startswith("SELECT"):
        logger.warning("Blocked non-SELECT query: %s", query)
        return "Error: Only SELECT queries are allowed for security reasons."
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(query)
            rows = await cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            result = [dict(zip(columns, row)) for row in rows]
            return json.dumps(result)
    except Exception as e:
        logger.error("Error executing query: %s", e, exc_info=True)
        return f"Error executing query: {e}"

@mcp.tool()
async def list_tables() -> str:
    """
    Lists all tables in the SQLite database.
    Returns:
        A JSON string of the table names.
    """
    logger.debug("Request to list tables")
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in await cursor.fetchall()]
            return json.dumps(tables)
    except Exception as e:
        logger.error("Error listing tables: %s", e, exc_info=True)
        return f"Error listing tables: {e}"

# Use FastMCP's built-in SSE app directly
app = mcp.sse_app()
