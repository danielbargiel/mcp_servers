#!/usr/bin/env python3
"""
Test the MCP server tools using stdio transport (simpler than SSE)
"""
import os
import asyncio
import json
from app.main import mcp

async def test_tools():
    """Test the MCP tools directly"""
    print("Testing MCP tools...")
    
    # Set database path - DB_HOST_PATH + database/properties.db (same structure as Docker)
    base_path = "/Users/daniel/Documents/Git/AI/LLM_Experiments/scp_o_l_x"
    db_path = f"{base_path}/database/properties.db"
    os.environ["DB_PATH"] = db_path
    
    print(f"Using database path: {db_path}")
    print(f"Database exists: {os.path.exists(db_path)}")
    print(f"Database readable: {os.access(db_path, os.R_OK)}")
    
    # Test list_tables
    try:
        tables_result = await mcp.call_tool("list_tables", {})
        print(f"✅ list_tables result: {tables_result}")
        
        # Extract text from MCP response
        if hasattr(tables_result, 'content') and tables_result.content:
            tables_text = tables_result.content[0].text
        else:
            tables_text = str(tables_result)
        
        tables = json.loads(tables_text)
        print(f"✅ Found tables: {tables}")
        
        if tables:
            # Test execute_query
            query_result = await mcp.call_tool("execute_query", {
                "query": f"SELECT * FROM {tables[0]} LIMIT 1"
            })
            print(f"✅ query result: {query_result}")
            
            # Extract text from MCP response
            if hasattr(query_result, 'content') and query_result.content:
                query_text = query_result.content[0].text
            else:
                query_text = str(query_result)
            
            data = json.loads(query_text)
            print(f"✅ Retrieved {len(data)} row(s) from database")
            print(f"✅ Sample data: {data[0] if data else 'No data'}")
            return True
        else:
            print("⚠️  No tables found")
            return True
    except Exception as e:
        import traceback
        print(f"❌ Tool test failed: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_tools())
    if success:
        print("\n✅ MCP tools are working correctly!")
    else:
        print("\n❌ MCP tools test failed.")