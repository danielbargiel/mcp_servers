#!/usr/bin/env python3
"""
Run the MCP server using FastMCP's built-in SSE transport
"""
import os
from app.main import mcp

if __name__ == "__main__":
    # Set database path - DB_HOST_PATH + database/properties.db (same structure as Docker)
    base_path = "/Users/daniel/Documents/Git/AI/LLM_Experiments/scp_o_l_x"
    os.environ["DB_PATH"] = f"{base_path}/database/properties.db"
    
    print("Starting MCP SQLite Server with SSE transport on port 8000...")
    print("Database path:", os.environ["DB_PATH"])
    
    # Run using FastMCP's built-in SSE support
    mcp.run(transport="sse")