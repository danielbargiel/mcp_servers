import os
import asyncio
import json
from fastapi import FastAPI, Request
from starlette.responses import StreamingResponse, Response
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

# This is the main SSE endpoint that the client will connect to.
@app.get("/sse")
async def sse_endpoint(request: Request) -> Response:
    """The endpoint that establishes the SSE connection."""
    
    # The mcp.server.sse library is designed to work with raw ASGI.
    # We adapt the FastAPI request to what the library expects.
    
    # We need to create a compatible handler for the MCP server to run.
    # This is an internal detail of the FastMCP server.
    async def mcp_handler(streams):
        # This is the run method from the low-level MCP server, not FastMCP.
        await mcp._mcp_server.run(
            streams[0],
            streams[1],
            mcp._mcp_server.create_initialization_options(),
        )

    async with transport.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        # The MCP server runs over the connection provided by the transport.
        await mcp_handler(streams)

    # The connection is closed, return an empty response.
    return Response()

# Mount the POST handler for receiving messages from the client.
# FastAPI is built on Starlette, so we can access the underlying app.
app.mount("/messages/", app=transport.handle_post_message)

@app.get("/")
def read_root():
    return {"message": "MCP Server is running. Connect to the /sse endpoint."}
