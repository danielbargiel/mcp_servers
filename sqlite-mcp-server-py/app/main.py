import os
import asyncio
import json
from fastapi import FastAPI, Request
from starlette.responses import StreamingResponse
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
import aiosqlite

# --- MCP Server Setup ---
# Initialize the FastMCP server. This is the heart of our MCP application.
mcp = FastMCP("python-sqlite-server")

# Get database path from environment variable, with a fallback for local testing
DB_PATH = os.environ.get("DB_PATH", "/database/properties.db")

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
    if not query.lstrip().upper().startswith("SELECT"):
        return "Error: Only SELECT queries are allowed for security reasons."
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(query)
            rows = await cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            result = [dict(zip(columns, row)) for row in rows]
            return json.dumps(result)
    except Exception as e:
        return f"Error executing query: {e}"

@mcp.tool()
async def list_tables() -> str:
    """
    Lists all tables in the SQLite database.
    Returns:
        A JSON string of the table names.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in await cursor.fetchall()]
            return json.dumps(tables)
    except Exception as e:
        return f"Error listing tables: {e}"


# --- FastAPI Application Setup ---

# Create the main FastAPI application instance
app = FastAPI(title="Python MCP SQLite Server")

# --- SSE Transport and Connection Handling ---

# ######################################################################
# # THE FIX IS HERE                                                    #
# # We now pass the path for the POST endpoint to the constructor.     #
# ######################################################################
transport = SseServerTransport(endpoint="/messages/")

# This is the main SSE endpoint that n8n will connect to.
@app.get("/sse")
async def sse_endpoint(request: Request) -> StreamingResponse:
    """The endpoint that establishes the SSE connection."""
    stream = await transport.connect_sse(request)
    # The MCP server runs over the connection provided by the transport.
    asyncio.create_task(mcp.run(stream))
    return stream

# This endpoint is where the client sends messages back to the server.
@app.post("/messages/")
async def post_message(request: Request):
    """The endpoint where the client posts messages to the server."""
    await transport.receive_post(request)
    return {"status": "message received"}

@app.get("/")
def read_root():
    return {"message": "MCP Server is running. Connect to the /sse endpoint."}
