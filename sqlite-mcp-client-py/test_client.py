import requests
import sseclient
import json
import time
import threading
import uuid
from urllib.parse import urlparse, parse_qs

# --- Configuration ---
BASE_URL = "http://localhost:8000"
SSE_ENDPOINT = f"{BASE_URL}/sse"
MESSAGES_ENDPOINT = f"{BASE_URL}/messages/"

# --- Helper Class for MCP Testing ---

class MCPTestClient:
    def __init__(self):
        self.sse_client = None
        self.listener_thread = None
        self.incoming_messages = []
        self.session_id = None
        self.is_listening = threading.Event()

    def _listen(self):
        """Listen for SSE events."""
        try:
            for event in self.sse_client.events():
                if not self.is_listening.is_set():
                    break
                
                if not event.data:
                    # Skip empty events
                    continue

                if event.event == 'endpoint':
                    # The first event gives us the session ID in its data field
                    path = event.data
                    try:
                        parsed_url = urlparse(path)
                        session_id = parse_qs(parsed_url.query)['session_id'][0]
                        self.session_id = session_id
                        print(f"Received session ID: {self.session_id}")
                    except (KeyError, IndexError):
                        print(f"ERROR: Could not parse session ID from endpoint event: {path}")

                elif event.event == 'message':
                    # Other messages from the server arrive as 'message' events.
                    # We can also add them to our incoming message queue.
                    self.incoming_messages.append(event)
                    print(f"Received event: {event}")
        except Exception as e:
            if self.is_listening.is_set():
                print(f"Error in SSE listener: {e}")

    def initialize_session(self, timeout=5):
        """Sends the initialize request to the server and waits for the response."""
        message_id = str(uuid.uuid4())
        message = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "0.1.0",
                "capabilities": {},
                "clientInfo": {
                    "name": "mcp-test-client",
                    "version": "0.1.0"
                }
            },
            "id": message_id
        }
        post_url = f"{MESSAGES_ENDPOINT}?session_id={self.session_id}"
        headers = {'Content-Type': 'application/json'}
        response = requests.post(post_url, json=message, headers=headers)
        response.raise_for_status()
        print("Sent initialize request.")

        # Wait for the response to initialize
        start_time = time.time()
        while time.time() - start_time < timeout:
            for msg in self.incoming_messages:
                try:
                    data = json.loads(msg.data)
                    if data.get('id') == message_id:
                        self.incoming_messages.remove(msg)
                        print(f"Initialization successful: {data.get('result')}")
                        return
                except json.JSONDecodeError:
                    continue
            time.sleep(0.1)
        raise TimeoutError(f"No response received for initialize message {message_id}")

    def send_initialized_notification(self):
        """Sends the initialized notification to the server."""
        message = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        }
        post_url = f"{MESSAGES_ENDPOINT}?session_id={self.session_id}"
        headers = {'Content-Type': 'application/json'}
        response = requests.post(post_url, json=message, headers=headers)
        response.raise_for_status()
        print("Sent initialized notification.")

    def connect(self):
        """Connects to the server and starts listening."""
        self.is_listening.set()
        self.sse_client = sseclient.SSEClient(requests.get(SSE_ENDPOINT, stream=True, timeout=15))
        self.listener_thread = threading.Thread(target=self._listen, daemon=True)
        self.listener_thread.start()
        # Wait for the session ID
        timeout = time.time() + 5 # 5 second timeout
        while self.session_id is None:
            if time.time() > timeout:
                raise TimeoutError("Did not receive session ID from server.")
            time.sleep(0.1)
        
        # Initialize the session after getting the session ID
        self.initialize_session()

        # Tell the server we are initialized
        self.send_initialized_notification()

    def disconnect(self):
        """Disconnects from the server."""
        self.is_listening.clear()
        if self.sse_client:
            self.sse_client.close()
        if self.listener_thread:
            self.listener_thread.join(timeout=2)
        print("Disconnected.")

    def call_tool(self, tool_name, payload, timeout=15):
        """Sends a 'tools/call' command to the server and waits for a response."""
        if not self.session_id:
            raise ValueError("Not connected or no session ID.")

        message_id = str(uuid.uuid4())
        # The message format is actually JSON-RPC as per sse.py
        message = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": payload},
            "id": message_id
        }

        # The session ID is now sent as a query parameter, not a header.
        post_url = f"{MESSAGES_ENDPOINT}?session_id={self.session_id}"
        headers = {'Content-Type': 'application/json'}
        response = requests.post(post_url, json=message, headers=headers)
        response.raise_for_status()

        # Wait for the response
        start_time = time.time()
        while time.time() - start_time < timeout:
            for msg in self.incoming_messages:
                try:
                    data = json.loads(msg.data)
                    # The response format is also JSON-RPC
                    if data.get('id') == message_id and 'result' in data:
                        self.incoming_messages.remove(msg)
                        return data['result']
                except json.JSONDecodeError:
                    continue # Ignore non-json messages
            time.sleep(0.1)
        raise TimeoutError(f"No response received for message {message_id}")

# --- Test Functions ---

def run_tests():
    """Runs all tests."""
    print("--- Running MCP Server Tests ---")

    # Test 1: Connection Test
    test_sse_connection()

    # Test 2: List Tables
    test_list_tables()

    # Test 3: Execute a valid SELECT query
    test_execute_select_query()

    # Test 4: Attempt to execute a non-SELECT query
    test_execute_non_select_query()

    print("--- All Tests Completed ---")


def test_sse_connection():
    """Test 1: Can we connect to the SSE endpoint?"""
    print("\n--- Test 1: SSE Connection ---")
    try:
        client = sseclient.SSEClient(requests.get(SSE_ENDPOINT, stream=True))
        print("SUCCESS: Connected to SSE endpoint.")
        # We need to close the connection, sseclient doesn't expose it directly
        # so we rely on the underlying requests session to be closed.
        # This is not ideal for a single check, but for now it's ok.
        # In a real app we would listen indefinitely.
        client.close()
        print("SUCCESS: Connection closed.")
    except requests.exceptions.ConnectionError as e:
        print(f"FAILURE: Could not connect to SSE endpoint at {SSE_ENDPOINT}.")
        print(f"Error: {e}")
        print("Is the server running? `docker-compose up` in `sqlite-mcp-server-py`")
        exit(1)


def test_list_tables():
    """Test 2: Can we list tables from the database?"""
    print("\n--- Test 2: List Tables ---")
    client = MCPTestClient()
    try:
        client.connect()
        result = client.call_tool("list_tables", {})
        print(f"SUCCESS: Received response: {result}")
        # The result of a tool call is a dict with 'content'
        content_text = result['content'][0]['text']
        tables = json.loads(content_text)
        assert isinstance(tables, list)
        assert len(tables) > 0
        print("SUCCESS: Result is a list with at least one table.")

    except Exception as e:
        print(f"FAILURE: Test failed. Error: {e}")
    finally:
        client.disconnect()


def test_execute_select_query():
    """Test 3: Can we execute a SELECT query?"""
    print("\n--- Test 3: Execute SELECT Query ---")
    client = MCPTestClient()
    try:
        client.connect()

        # First, get the list of tables
        tables_result = client.call_tool("list_tables", {})
        tables_text = tables_result['content'][0]['text']
        tables = json.loads(tables_text)
        if not tables:
            raise ValueError("Database has no tables to query.")
        
        table_to_query = tables[0]
        print(f"Found table to query: {table_to_query}")

        # Now, query the first row from that table
        query = f"SELECT * FROM {table_to_query} LIMIT 1"
        query_result = client.call_tool("execute_query", {"query": query})

        print(f"SUCCESS: Received response: {query_result}")
        
        content_text = query_result['content'][0]['text']
        result_list = json.loads(content_text)

        assert isinstance(result_list, list)
        assert len(result_list) <= 1
        if len(result_list) == 1:
            assert isinstance(result_list[0], dict)
        
        print("SUCCESS: Query executed and result format is correct.")

    except Exception as e:
        print(f"FAILURE: Test failed. Error: {e}")
    finally:
        client.disconnect()


def test_execute_non_select_query():
    """Test 4: Does the server reject non-SELECT queries?"""
    print("\n--- Test 4: Execute Non-SELECT Query ---")
    client = MCPTestClient()
    try:
        client.connect()
        result = client.call_tool("execute_query", {"query": "DELETE FROM some_table"})
        print(f"SUCCESS: Received response: {result}")
        assert "Only SELECT queries are allowed" in result['content'][0]['text']
        print("SUCCESS: Server correctly rejected non-SELECT query.")
    except Exception as e:
        print(f"FAILURE: Test failed. Error: {e}")
    finally:
        client.disconnect()


if __name__ == "__main__":
    run_tests() 