<img width="787" height="474" alt="image" src="https://github.com/user-attachments/assets/f87150cb-ec82-4ed9-afff-d3b5ee05c9ed" />


> This is a great question about error handling mechanisms for the Tavily and Atlassian MCP server integrations. Let me think about the different types of errors that could occur and how to handle them properly:
> 
> 1. **Connection Errors**
>    - Initial connection failures
>    - Timeouts during operations
>    - Connection drops during long-running operations
> 
> 2. **Authentication Errors**
>    - Invalid API keys/tokens
>    - Expired credentials
>    - Permission issues
> 
> 3. **API Limitations**
>    - Rate limiting
>    - Usage quotas
>    - Service downtimes
> 
> 4. **Data Processing Errors**
>    - Invalid inputs
>    - Unexpected response formats
>    - Empty or partial results
> 
> 5. **Tool Execution Errors**
>    - Tool-specific errors (e.g., Jira ticket creation failing due to required fields)
>    - Context-specific failures (e.g., trying to update a non-existent Confluence page)
> 
> I'll now outline comprehensive error handling mechanisms for each of these categories, specifically for the Tavily and Atlassian integrations.
> 
> Let me structure my response around:
> 1. Client-level error handling (in AI-Matrix)
> 2. Server connection error handling
> 3. Tool-specific error handling for Tavily
> 4. Tool-specific error handling for Atlassian
> 5. Systematic error handling and reporting
> 6. Graceful degradation strategies
> 7. Monitoring and alerting


# Comprehensive Error Handling for MCP Server Integrations

Robust error handling is critical for reliable MCP server integrations, especially with third-party services like Tavily and Atlassian. Here's a detailed breakdown of potential error handling mechanisms:

## 1. Client-Level Error Handling

### 1.1 Connection Error Handling

```python
# ai-matrix/clients/mcp_client.py
import asyncio
import logging
from typing import Dict, List, Any, Optional
import backoff  # For exponential backoff

logger = logging.getLogger(__name__)

class AIMatrixMCPClient:
    # ... existing code ...
    
    @backoff.on_exception(
        backoff.expo,
        (ConnectionError, TimeoutError, asyncio.TimeoutError),
        max_tries=3,
        max_time=30
    )
    async def connect(self):
        """Connect to all configured MCP servers with retry logic"""
        if not self.server_configs:
            logger.warning("No MCP servers configured")
            return self
        
        try:
            self.client = MultiServerMCPClient(self.server_configs)
            await self.client.__aenter__()
            self.tools = self.client.get_tools()
            logger.info(f"Connected to {len(self.server_configs)} MCP servers with {len(self.tools)} tools available")
        except Exception as e:
            logger.error(f"Error connecting to MCP servers: {str(e)}")
            # Classify and log specific error types
            if isinstance(e, asyncio.TimeoutError):
                logger.error("Connection timed out")
            elif "authentication" in str(e).lower():
                logger.error("Authentication error - check API keys/tokens")
            elif "rate limit" in str(e).lower():
                logger.error("Rate limit exceeded")
            raise
            
        return self
    
    # Additional connection health check
    async def check_connections(self) -> Dict[str, str]:
        """Check health of all MCP server connections"""
        results = {}
        
        if not self.client or not hasattr(self.client, "clients"):
            return {"status": "not_connected"}
        
        for server_name, client in self.client.clients.items():
            try:
                # Try a simple operation like listing tools
                session = client.get("session")
                if session:
                    # Simple ping or availability check
                    await session.list_tools()
                    results[server_name] = "connected"
                else:
                    results[server_name] = "no_session"
            except Exception as e:
                logger.warning(f"Error checking connection to {server_name}: {str(e)}")
                results[server_name] = f"error: {type(e).__name__}"
                
        return results
```

### 1.2 Tool Execution Wrapper

Create a wrapper for tool execution that handles common errors:

```python
# ai-matrix/clients/tool_executor.py
import asyncio
import logging
import time
from typing import Any, Dict, Optional
import backoff

logger = logging.getLogger(__name__)

class MCPToolExecutor:
    """Wrapper for MCP tool execution with error handling"""
    
    def __init__(self, mcp_client):
        self.client = mcp_client
        self.error_counts = {}  # Track error counts by tool
        self.last_errors = {}   # Track last error by tool
        
    @backoff.on_exception(
        backoff.expo,
        (ConnectionError, TimeoutError, asyncio.TimeoutError),
        max_tries=3,
        giveup=lambda e: "authentication" in str(e).lower()  # Don't retry auth errors
    )
    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool with error handling and retry logic"""
        tool = self.client.get_tool_by_name(tool_name)
        if not tool:
            logger.error(f"Tool not found: {tool_name}")
            return {"error": f"Tool not found: {tool_name}"}
        
        try:
            start_time = time.time()
            result = await tool.ainvoke(params)
            execution_time = time.time() - start_time
            
            # Log successful execution
            logger.info(f"Tool {tool_name} executed successfully in {execution_time:.2f}s")
            
            # Reset error count on success
            self.error_counts[tool_name] = 0
            
            return result
            
        except Exception as e:
            # Increment error count for this tool
            self.error_counts[tool_name] = self.error_counts.get(tool_name, 0) + 1
            self.last_errors[tool_name] = str(e)
            
            logger.error(f"Error executing tool {tool_name}: {str(e)}")
            
            # Apply different handling based on error type
            if isinstance(e, asyncio.TimeoutError):
                return {"error": "Tool execution timed out", "details": str(e)}
            elif "rate limit" in str(e).lower():
                return {"error": "Rate limit exceeded", "details": str(e)}
            elif "authentication" in str(e).lower() or "unauthorized" in str(e).lower():
                return {"error": "Authentication failed", "details": str(e)}
            else:
                return {"error": f"Tool execution failed: {type(e).__name__}", "details": str(e)}
    
    def get_tool_health(self) -> Dict[str, Dict[str, Any]]:
        """Get health information about tools"""
        result = {}
        for tool_name, error_count in self.error_counts.items():
            result[tool_name] = {
                "error_count": error_count,
                "status": "healthy" if error_count == 0 else "degraded" if error_count < 3 else "unhealthy",
                "last_error": self.last_errors.get(tool_name)
            }
        return result
```

## 2. Tool-Specific Error Handling

### 2.1 Tavily-Specific Error Handling

```python
# ai-matrix/clients/tavily_handler.py
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class TavilyErrorHandler:
    """Specialized error handling for Tavily MCP tools"""
    
    @staticmethod
    def handle_search_error(error: Dict[str, Any]) -> Dict[str, Any]:
        """Handle errors from tavily-search tool"""
        error_msg = error.get("details", "")
        
        # Handle specific Tavily error messages
        if "invalid api key" in error_msg.lower():
            logger.error("Tavily API key is invalid or expired")
            return {
                "results": [],
                "error": "Authentication failed. Please check your Tavily API key.",
                "fallback_suggestion": "Try using an alternative information source or check API key configuration."
            }
        elif "rate limit" in error_msg.lower():
            logger.warning("Tavily rate limit exceeded")
            return {
                "results": [],
                "error": "Search rate limit exceeded. Try again later.",
                "fallback_suggestion": "Consider reducing the frequency of search requests or upgrading your Tavily plan."
            }
        elif "timeout" in error_msg.lower():
            logger.warning("Tavily search timed out")
            return {
                "results": [],
                "error": "Search timed out. This might be due to complexity of the query or service availability.",
                "fallback_suggestion": "Try simplifying your search query or try again later."
            }
        else:
            return {
                "results": [],
                "error": f"Search failed: {error.get('error', 'Unknown error')}",
                "fallback_suggestion": "Check your query syntax or try a different search approach."
            }
    
    @staticmethod
    def process_partial_results(results: Dict[str, Any]) -> Dict[str, Any]:
        """Process potentially incomplete results from Tavily"""
        if not results.get("results"):
            logger.warning("Tavily returned empty search results")
            return {
                **results,
                "warning": "No search results found. Try refining your query."
            }
        
        return results
```

### 2.2 Atlassian-Specific Error Handling

```python
# ai-matrix/clients/atlassian_handler.py
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class AtlassianErrorHandler:
    """Specialized error handling for Atlassian MCP tools"""
    
    @staticmethod
    def handle_confluence_error(error: Dict[str, Any], operation: str) -> Dict[str, Any]:
        """Handle errors from Confluence tools"""
        error_msg = error.get("details", "").lower()
        
        # Handle authentication errors
        if any(auth_err in error_msg for auth_err in ["unauthorized", "forbidden", "authentication", "permission"]):
            logger.error(f"Confluence authentication/permission error during {operation}")
            return {
                "error": "Authentication failed or insufficient permissions.",
                "resolution": "Check your Confluence API token and ensure you have access to the specified spaces.",
                "status": "auth_error"
            }
            
        # Handle content not found
        if "not found" in error_msg or "does not exist" in error_msg:
            if operation == "get_page":
                logger.warning("Confluence page not found")
                return {
                    "error": "The requested page was not found.",
                    "resolution": "Verify the page ID or title is correct.",
                    "status": "not_found"
                }
            else:
                return {
                    "error": f"Resource not found during {operation}",
                    "resolution": "Verify all parameters and try again.",
                    "status": "not_found"
                }
                
        # Handle rate limiting
        if "rate limit" in error_msg:
            logger.warning(f"Confluence rate limit hit during {operation}")
            return {
                "error": "Confluence API rate limit exceeded.",
                "resolution": "Please wait before trying again or reduce request frequency.",
                "status": "rate_limited"
            }
            
        # Default error response
        return {
            "error": f"Confluence operation {operation} failed: {error.get('error', 'Unknown error')}",
            "resolution": "Check your parameters and Confluence server status.",
            "status": "operation_failed"
        }
    
    @staticmethod
    def handle_jira_error(error: Dict[str, Any], operation: str) -> Dict[str, Any]:
        """Handle errors from Jira tools"""
        error_msg = error.get("details", "").lower()
        
        # Handle authentication errors
        if any(auth_err in error_msg for auth_err in ["unauthorized", "forbidden", "authentication", "permission"]):
            logger.error(f"Jira authentication/permission error during {operation}")
            return {
                "error": "Authentication failed or insufficient permissions.",
                "resolution": "Check your Jira API token and ensure you have access to the specified projects.",
                "status": "auth_error"
            }
            
        # Handle validation errors for issue creation/updates
        if operation in ["create_issue", "update_issue"] and any(val_err in error_msg for val_err in ["validation", "required field", "invalid"]):
            logger.warning(f"Jira validation error during {operation}")
            return {
                "error": "Issue validation failed. Some required fields may be missing or invalid.",
                "resolution": "Check the issue data and ensure all required fields are provided.",
                "status": "validation_error"
            }
            
        # Handle issue not found
        if "issue does not exist" in error_msg or "not found" in error_msg:
            logger.warning("Jira issue not found")
            return {
                "error": "The requested issue was not found.",
                "resolution": "Verify the issue key is correct.",
                "status": "not_found"
            }
            
        # Handle workflow errors for transitions
        if operation == "transition_issue" and any(wf_err in error_msg for wf_err in ["workflow", "transition", "status"]):
            logger.warning("Jira workflow transition error")
            return {
                "error": "Cannot transition the issue. The requested transition may be invalid for the current status.",
                "resolution": "Check available transitions for this issue first with get_transitions.",
                "status": "workflow_error"
            }
            
        # Default error response
        return {
            "error": f"Jira operation {operation} failed: {error.get('error', 'Unknown error')}",
            "resolution": "Check your parameters and Jira server status.",
            "status": "operation_failed"
        }
```

## 3. Error Handling in Agent Framework

Enhance the AI-Matrix agent to handle errors gracefully:

```python
# ai-matrix/graphs/agent_graph.py
# ... existing imports ...
from ..clients.tool_executor import MCPToolExecutor
from ..clients.tavily_handler import TavilyErrorHandler
from ..clients.atlassian_handler import AtlassianErrorHandler

# ... existing code ...

async def run_agent(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """Run the agent executor with enhanced error handling"""
    # Extract the latest human message
    messages = state["messages"]
    if not messages or messages[-1]["type"] != "human":
        raise ValueError("Expected a human message")
    
    # Get the human message content
    human_message = messages[-1]["content"]
    
    try:
        # Set up tool executor with error handling
        tool_executor = MCPToolExecutor(mcp_client)
        
        # Override the agent's tool execution with our error-handling version
        original_execute = agent_executor.agent.llm_chain.llm.invoke
        
        async def execute_with_error_handling(messages, **kwargs):
            response = await original_execute(messages, **kwargs)
            
            # Check if the response contains a tool call
            if hasattr(response, "tool_calls") and response.tool_calls:
                for tool_call in response.tool_calls:
                    tool_name = tool_call.name
                    
                    # Record the tool call in state
                    if "tool_calls" not in state:
                        state["tool_calls"] = []
                    state["tool_calls"].append({
                        "tool": tool_name,
                        "input": tool_call.args,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    # If we encounter an error from previous tool calls, provide guidance
                    if tool_name in state.get("tool_errors", {}):
                        error_info = state["tool_errors"][tool_name]
                        # Add error context to the response
                        return response.content + f"\n\nNote: Previous call to {tool_name} failed with error: {error_info['message']}. {error_info['suggestion']}"
            
            return response
        
        # Replace the execution method with our error-handling version
        agent_executor.agent.llm_chain.llm.invoke = execute_with_error_handling
        
        # Run the agent
        result = await agent_executor.ainvoke({"input": human_message})
        
        # Extract information from the result
        output = result["output"]
        intermediate_steps = result.get("intermediate_steps", [])
        
        # Update state
        state["messages"].append({"type": "ai", "content": output})
        
        # Extract thoughts and tools used
        state["tool_errors"] = {}  # Reset tool errors
        
        for step in intermediate_steps:
            action = step[0]
            tool_output = step[1]
            
            if hasattr(action, "log"):
                state["thoughts"].append(action.log)
            
            if hasattr(action, "tool"):
                tool_name = action.tool
                state["tools_used"].append(tool_name)
                
                # Check for errors in tool output
                if isinstance(tool_output, dict) and "error" in tool_output:
                    # Record the error
                    if "tool_errors" not in state:
                        state["tool_errors"] = {}
                    
                    # Classify and handle specific tool errors
                    error_info = {"message": tool_output["error"], "suggestion": ""}
                    
                    if "tavily-search" == tool_name:
                        error_info["suggestion"] = tool_output.get("fallback_suggestion", "Try a different search query.")
                    elif tool_name.startswith("confluence_"):
                        operation = tool_name.replace("confluence_", "")
                        error_info["suggestion"] = tool_output.get("resolution", "Check your Confluence configuration.")
                    elif tool_name.startswith("jira_"):
                        operation = tool_name.replace("jira_", "")
                        error_info["suggestion"] = tool_output.get("resolution", "Check your Jira configuration.")
                    
                    state["tool_errors"][tool_name] = error_info
        
        state["end_time"] = datetime.now().isoformat()
        
    except Exception as e:
        logger.exception(f"Error running agent: {str(e)}")
        # Provide a graceful error message to the user
        state["messages"].append({
            "type": "ai", 
            "content": f"I apologize, but I encountered an error while processing your request: {str(e)}. Please try again or contact support if the problem persists."
        })
        state["error"] = str(e)
        state["end_time"] = datetime.now().isoformat()
    
    return state
```

## 4. Fallback Strategies

Implement fallback mechanisms when a specific MCP server is unavailable:

```python
# ai-matrix/clients/fallback_strategies.py
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class MCPFallbackStrategies:
    """Fallback strategies when MCP servers are unavailable"""
    
    @staticmethod
    async def tavily_search_fallback(query: str, client) -> Dict[str, Any]:
        """Fallback for Tavily search using another search tool or LLM"""
        logger.info(f"Using fallback strategy for Tavily search: {query}")
        
        # First try any alternative search tools
        search_tools = [
            tool for tool in client.get_tools() 
            if "search" in tool.name.lower() and tool.name != "tavily-search"
        ]
        
        if search_tools:
            logger.info(f"Found alternative search tool: {search_tools[0].name}")
            try:
                return await search_tools[0].ainvoke({"query": query})
            except Exception as e:
                logger.warning(f"Fallback search tool failed: {str(e)}")
        
        # If no alternative search tools or they failed, use a disclaimer
        return {
            "results": [],
            "fallback_message": "Search functionality is currently unavailable. Response will be based on the model's training data which may not include recent information."
        }
    
    @staticmethod
    async def confluence_fallback(operation: str, params: Dict[str, Any], client) -> Dict[str, Any]:
        """Fallback for Confluence operations"""
        logger.info(f"Using fallback strategy for Confluence {operation}: {params}")
        
        if operation == "confluence_search":
            # For search, we can suggest checking documentation manually
            return {
                "results": [],
                "fallback_message": f"Confluence search is currently unavailable. Please check Confluence manually at {params.get('space', 'your Confluence space')}."
            }
        elif operation == "confluence_get_page":
            # For page retrieval, we can suggest the direct URL
            space = params.get("space", "")
            title = params.get("title", "")
            if space and title:
                return {
                    "content": "",
                    "fallback_message": f"Confluence page retrieval is currently unavailable. You can manually access this page by searching for '{title}' in the '{space}' space."
                }
        
        # Generic fallback for other operations
        return {
            "fallback_message": f"Confluence {operation} is currently unavailable. Please try again later or perform this operation manually in Confluence."
        }
    
    @staticmethod
    async def jira_fallback(operation: str, params: Dict[str, Any], client) -> Dict[str, Any]:
        """Fallback for Jira operations"""
        logger.info(f"Using fallback strategy for Jira {operation}: {params}")
        
        if operation == "jira_search":
            # For search, we can provide JQL for manual execution
            jql = params.get("jql", "")
            return {
                "issues": [],
                "fallback_message": f"Jira search is currently unavailable. You can manually execute this search in Jira with JQL: {jql}"
            }
        elif operation == "jira_create_issue":
            # For issue creation, we can format the issue data for manual creation
            project = params.get("project", "")
            summary = params.get("summary", "")
            
            if project and summary:
                return {
                    "fallback_message": f"Jira issue creation is currently unavailable. Please create an issue manually in the {project} project with summary: '{summary}'",
                    "manual_issue_data": params
                }
        
        # Generic fallback for other operations
        return {
            "fallback_message": f"Jira {operation} is currently unavailable. Please try again later or perform this operation manually in Jira."
        }
```

## 5. Monitoring, Logging, and Alerting

Implement comprehensive monitoring and alerting for MCP server errors:

```python
# ai-matrix/monitoring/error_tracker.py
import logging
import time
from typing import Dict, Any, List
from collections import defaultdict, deque
import threading
import json
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class MCPErrorTracker:
    """Track and analyze errors from MCP servers"""
    
    def __init__(self, alert_threshold: int = 5, window_minutes: int = 15):
        self.errors = defaultdict(lambda: deque(maxlen=100))  # Server -> list of errors
        self.server_status = {}  # Server -> status
        self.alert_threshold = alert_threshold
        self.window_minutes = window_minutes
        self.lock = threading.Lock()
        
        # Set up error log directory
        self.log_dir = os.path.join(os.path.dirname(__file__), "../logs")
        os.makedirs(self.log_dir, exist_ok=True)
    
    def record_error(self, server_name: str, tool_name: str, error_details: Dict[str, Any]):
        """Record an error from an MCP server"""
        with self.lock:
            error_entry = {
                "timestamp": datetime.now().isoformat(),
                "tool": tool_name,
                "details": error_details,
                "error_type": self._classify_error(error_details)
            }
            
            self.errors[server_name].append(error_entry)
            
            # Check if we should change server status
            self._update_server_status(server_name)
            
            # Log to file
            self._log_error_to_file(server_name, error_entry)
            
            # Check if we should send an alert
            if self._should_alert(server_name):
                self._send_alert(server_name)
    
    def _classify_error(self, error_details: Dict[str, Any]) -> str:
        """Classify the type of error"""
        error_msg = str(error_details.get("details", "")).lower()
        
        if any(auth in error_msg for auth in ["authentication", "unauthorized", "forbidden", "token", "api key"]):
            return "auth_error"
        elif any(rate in error_msg for rate in ["rate limit", "too many requests", "throttle"]):
            return "rate_limit"
        elif any(timeout in error_msg for timeout in ["timeout", "timed out"]):
            return "timeout"
        elif any(conn in error_msg for conn in ["connection", "network", "unreachable"]):
            return "connection_error"
        else:
            return "unknown_error"
    
    def _update_server_status(self, server_name: str):
        """Update server status based on recent errors"""
        # Count errors in the time window
        cutoff_time = datetime.now() - timedelta(minutes=self.window_minutes)
        recent_errors = [
            e for e in self.errors[server_name] 
            if datetime.fromisoformat(e["timestamp"]) > cutoff_time
        ]
        
        error_count = len(recent_errors)
        
        if error_count == 0:
            self.server_status[server_name] = "healthy"
        elif error_count < self.alert_threshold:
            self.server_status[server_name] = "degraded"
        else:
            self.server_status[server_name] = "unhealthy"
    
    def _should_alert(self, server_name: str) -> bool:
        """Determine if we should send an alert for this server"""
        if self.server_status.get(server_name) == "unhealthy":
            # Check if we've already alerted recently
            cutoff_time = datetime.now() - timedelta(minutes=30)  # Don't alert more than once per 30 min
            
            # Count alerts in the time window
            alert_log_file = os.path.join(self.log_dir, f"{server_name}_alerts.jsonl")
            
            if os.path.exists(alert_log_file):
                with open(alert_log_file, 'r') as f:
                    recent_alerts = [
                        json.loads(line) for line in f
                        if datetime.fromisoformat(json.loads(line)["timestamp"]) > cutoff_time
                    ]
                    
                    if recent_alerts:
                        return False  # Already alerted recently
            
            return True
        
        return False
    
    def _send_alert(self, server_name: str):
        """Send an alert for server issues"""
        alert = {
            "timestamp": datetime.now().isoformat(),
            "server": server_name,
            "status": self.server_status[server_name],
            "error_count": len([
                e for e in self.errors[server_name] 
                if datetime.fromisoformat(e["timestamp"]) > datetime.now() - timedelta(minutes=self.window_minutes)
            ]),
            "message": f"MCP server {server_name} is experiencing issues"
        }
        
        # Log the alert
        alert_log_file = os.path.join(self.log_dir, f"{server_name}_alerts.jsonl")
        with open(alert_log_file, 'a') as f:
            f.write(json.dumps(alert) + "\n")
        
        # Actually send the alert (email, Slack, etc.)
        logger.critical(f"ALERT: {alert['message']} - {alert['error_count']} errors in the last {self.window_minutes} minutes")
        
        # Here you would implement actual alerting logic
        # Example: send_email_alert(alert) or send_slack_alert(alert)
    
    def _log_error_to_file(self, server_name: str, error_entry: Dict[str, Any]):
        """Log error details to a file"""
        error_log_file = os.path.join(self.log_dir, f"{server_name}_errors.jsonl")
        with open(error_log_file, 'a') as f:
            f.write(json.dumps(error_entry) + "\n")
    
    def get_server_status(self) -> Dict[str, str]:
        """Get current status of all servers"""
        with self.lock:
            # Update status for all servers
            for server_name in self.errors:
                self._update_server_status(server_name)
            
            return self.server_status.copy()
    
    def get_error_summary(self) -> Dict[str, Dict[str, Any]]:
        """Get error summary by server"""
        with self.lock:
            summary = {}
            
            for server_name, error_list in self.errors.items():
                if not error_list:
                    continue
                
                # Count errors by type
                error_types = {}
                for error in error_list:
                    error_type = error["error_type"]
                    error_types[error_type] = error_types.get(error_type, 0) + 1
                
                # Get most recent error
                most_recent = max(error_list, key=lambda e: e["timestamp"])
                
                summary[server_name] = {
                    "status": self.server_status.get(server_name, "unknown"),
                    "total_errors": len(error_list),
                    "error_types": error_types,
                    "most_recent": most_recent
                }
            
            return summary
```

## 6. Circuit Breaker Pattern Implementation

Implement a circuit breaker to prevent repeated calls to failing services:

```python
# ai-matrix/clients/circuit_breaker.py
import time
import asyncio
import logging
from enum import Enum, auto
from typing import Callable, Any, Dict
import functools

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = auto()       # Normal operation - requests go through
    OPEN = auto()         # Circuit is open - requests immediately fail
    HALF_OPEN = auto()    # Testing if service is back - limited requests

class CircuitBreaker:
    """
    Implements the Circuit Breaker pattern for MCP tools
    """
    
    def __init__(
        self, 
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        timeout: float = 10.0
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.timeout = timeout
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        self.successes_needed = 1  # Successful calls needed in HALF_OPEN to switch to CLOSED
        self.success_count = 0
        
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Call the protected function with circuit breaker logic
        """
        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if time.time() - self.last_failure_time > self.recovery_timeout:
                logger.info("Circuit switching from OPEN to HALF_OPEN")
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
            else:
                # Circuit is open and timeout hasn't elapsed
                logger.warning(f"Circuit is OPEN - fast failing request")
                raise CircuitBreakerOpenError("Circuit is open - service unavailable")
        
        # At this point, circuit is either CLOSED or HALF_OPEN
        try:
            # Set a timeout for the function call
            result = await asyncio.wait_for(func(*args, **kwargs), timeout=self.timeout)
            
            # Call succeeded
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.successes_needed:
                    logger.info("Circuit switching from HALF_OPEN to CLOSED")
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
            
            # Reset failure count on success in CLOSED state
            if self.state == CircuitState.CLOSED:
                self.failure_count = 0
                
            return result
            
        except (asyncio.TimeoutError, Exception) as e:
            # Call failed
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            logger.warning(f"Call failed with {type(e).__name__}: {str(e)}")
            
            # If we hit the threshold, open the circuit
            if (self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold) or \
               (self.state == CircuitState.HALF_OPEN):
                logger.error(f"Circuit switching to OPEN after {self.failure_count} failures")
                self.state = CircuitState.OPEN
            
            # Re-raise the original exception
            raise

class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit is open"""
    pass

# Decorator for applying circuit breaker to async functions
def with_circuit_breaker(failure_threshold: int = 5, recovery_timeout: float = 60.0, timeout: float = 10.0):
    circuit_breakers = {}  # tool_name -> CircuitBreaker
    
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(tool_name, *args, **kwargs):
            # Create circuit breaker for this tool if it doesn't exist
            if tool_name not in circuit_breakers:
                circuit_breakers[tool_name] = CircuitBreaker(
                    failure_threshold=failure_threshold,
                    recovery_timeout=recovery_timeout,
                    timeout=timeout
                )
            
            circuit = circuit_breakers[tool_name]
            
            try:
                return await circuit.call(func, tool_name, *args, **kwargs)
            except CircuitBreakerOpenError:
                # Return a formatted error response when circuit is open
                return {
                    "error": "Service temporarily unavailable",
                    "status": "circuit_open",
                    "details": f"Too many failures for {tool_name}. Service will be retried in {circuit.recovery_timeout} seconds."
                }
        
        return wrapper
    
    return decorator
```

## 7. Complete Integration with Error Handling

Putting it all together in a comprehensive MCP client with error handling:

```python
# ai-matrix/clients/robust_mcp_client.py
import asyncio
import logging
import os
import time
from typing import Dict, List, Any, Optional
import json

from langchain_mcp_adapters.client import MultiServerMCPClient
from ..clients.circuit_breaker import with_circuit_breaker
from ..monitoring.error_tracker import MCPErrorTracker

logger = logging.getLogger(__name__)

class RobustMCPClient:
    """MCP client with comprehensive error handling"""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the robust MCP client"""
        self.config_path = config_path or os.path.join(os.path.dirname(__file__), "../config/mcp_servers.json")
        self.server_configs = self._load_config()
        self.client = None
        self.tools = []
        self.error_tracker = MCPErrorTracker()
        
    def _load_config(self) -> Dict[str, Dict[str, Any]]:
        """Load MCP server configuration from file"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                
                # Process environment variables in config
                for server_name, server_config in config.items():
                    if "env" in server_config:
                        for key, value in server_config["env"].items():
                            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                                env_var = value[2:-1]
                                env_value = os.environ.get(env_var)
                                if env_value:
                                    server_config["env"][key] = env_value
                                else:
                                    logger.warning(f"Environment variable {env_var} not set for {server_name}.{key}")
                
                return config
        except Exception as e:
            logger.error(f"Error loading MCP server config: {str(e)}")
            return {}
    
    async def connect(self):
        """Connect to all configured MCP servers"""
        if not self.server_configs:
            logger.warning("No MCP servers configured")
            return self
        
        try:
            self.client = MultiServerMCPClient(self.server_configs)
            await self.client.__aenter__()
            self.tools = self.client.get_tools()
            logger.info(f"Connected to {len(self.server_configs)} MCP servers with {len(self.tools)} tools available")
        except Exception as e:
            logger.error(f"Error connecting to MCP servers: {str(e)}")
            raise
            
        return self
    
    async def disconnect(self):
        """Disconnect from all MCP servers"""
        if self.client:
            try:
                await self.client.__aexit__(None, None, None)
                logger.info("Disconnected from all MCP servers")
            except Exception as e:
                logger.error(f"Error disconnecting from MCP servers: {str(e)}")
    
    def get_tools(self) -> List:
        """Get all available tools from connected MCP servers"""
        return self.tools
    
    def get_tool_by_name(self, name: str) -> Optional[Any]:
        """Get a specific tool by name"""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None
    
    @with_circuit_breaker(failure_threshold=5, recovery_timeout=60.0, timeout=20.0)
    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool with comprehensive error handling"""
        tool = self.get_tool_by_name(tool_name)
        if not tool:
            logger.error(f"Tool not found: {tool_name}")
            return {"error": f"Tool not found: {tool_name}"}
        
        # Determine the server name from the tool
        server_name = getattr(tool, "_server_name", "unknown")
        
        try:
            start_time = time.time()
            result = await tool.ainvoke(params)
            execution_time = time.time() - start_time
            
            # Log successful execution
            logger.info(f"Tool {tool_name} executed successfully in {execution_time:.2f}s")
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {str(e)}")
            
            # Record the error in the tracker
            error_details = {
                "message": str(e),
                "type": type(e).__name__,
                "details": str(e)
            }
            self.error_tracker.record_error(server_name, tool_name, error_details)
            
            # Apply specific error handling based on tool type
            if tool_name == "tavily-search":
                from ..clients.tavily_handler import TavilyErrorHandler
                return TavilyErrorHandler.handle_search_error(error_details)
            elif tool_name.startswith("confluence_"):
                from ..clients.atlassian_handler import AtlassianErrorHandler
                operation = tool_name.replace("confluence_", "")
                return AtlassianErrorHandler.handle_confluence_error(error_details, operation)
            elif tool_name.startswith("jira_"):
                from ..clients.atlassian_handler import AtlassianErrorHandler
                operation = tool_name.replace("jira_", "")
                return AtlassianErrorHandler.handle_jira_error(error_details, operation)
            else:
                # Generic error handling
                return {
                    "error": f"Tool execution failed: {type(e).__name__}",
                    "details": str(e)
                }
    
    def get_server_health(self) -> Dict[str, Dict[str, Any]]:
        """Get health information about all servers"""
        # Get status from error tracker
        server_status = self.error_tracker.get_server_status()
        
        # Get error summary
        error_summary = self.error_tracker.get_error_summary()
        
        # Combine with connection status
        result = {}
        for server_name in self.server_configs:
            result[server_name] = {
                "status": server_status.get(server_name, "unknown"),
                "errors": error_summary.get(server_name, {"total_errors": 0})
            }
        
        return result
    
    async def __aenter__(self):
        """Async context manager entry"""
        return await self.connect()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()
```

## 8. UI for Error Monitoring

Add a monitoring dashboard to the MCP Registry UI:

```jsx
// mcp-registry/frontend/src/pages/Monitoring.jsx
import React, { useState, useEffect } from 'react';
import { 
  Container, Grid, Card, CardContent, Typography, 
  Box, Chip, Button, IconButton, Divider,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import { getServerHealth, getErrorLogs } from '../services/api';

const StatusChip = ({ status }) => {
  let color = "default";
  
  if (status === "healthy") color = "success";
  else if (status === "degraded") color = "warning";
  else if (status === "unhealthy") color = "error";
  
  return <Chip label={status} color={color} />;
};

const Monitoring = () => {
  const [serverHealth, setServerHealth] = useState({});
  const [errorLogs, setErrorLogs] = useState({});
  const [loading, setLoading] = useState(true);
  const [selectedServer, setSelectedServer] = useState(null);

  useEffect(() => {
    fetchHealthData();
  }, []);

  const fetchHealthData = async () => {
    try {
      setLoading(true);
      const health = await getServerHealth();
      setServerHealth(health);
      
      // If we have a selected server, get its error logs
      if (selectedServer && health[selectedServer]) {
        fetchErrorLogs(selectedServer);
      } else if (Object.keys(health).length > 0) {
        // Select the first server by default
        setSelectedServer(Object.keys(health)[0]);
        fetchErrorLogs(Object.keys(health)[0]);
      }
    } catch (error) {
      console.error('Error fetching server health:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchErrorLogs = async (serverName) => {
    try {
      const logs = await getErrorLogs(serverName);
      setErrorLogs(prev => ({ ...prev, [serverName]: logs }));
    } catch (error) {
      console.error(`Error fetching error logs for ${serverName}:`, error);
    }
  };

  const handleServerSelect = (serverName) => {
    setSelectedServer(serverName);
    fetchErrorLogs(serverName);
  };

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3 }}>
        <Typography variant="h4" component="h1">
          MCP Server Monitoring
        </Typography>
        <IconButton onClick={fetchHealthData} disabled={loading}>
          <RefreshIcon />
        </IconButton>
      </Box>

      <Grid container spacing={3}>
        {/* Server Health Summary */}
        <Grid item xs={12}>
          <TableContainer component={Paper}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Server Name</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Total Errors</TableCell>
                  <TableCell>Last Error</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {Object.entries(serverHealth).map(([serverName, data]) => (
                  <TableRow 
                    key={serverName}
                    selected={selectedServer === serverName}
                    hover
                    onClick={() => handleServerSelect(serverName)}
                    sx={{ cursor: 'pointer' }}
                  >
                    <TableCell>{serverName}</TableCell>
                    <TableCell>
                      <StatusChip status={data.status} />
                    </TableCell>
                    <TableCell>{data.errors?.total_errors || 0}</TableCell>
                    <TableCell>
                      {data.errors?.most_recent ? 
                        new Date(data.errors.most_recent.timestamp).toLocaleString() : 
                        'No errors'}
                    </TableCell>
                    <TableCell>
                      <Button 
                        size="small" 
                        variant="outlined" 
                        onClick={(e) => {
                          e.stopPropagation();
                          fetchErrorLogs(serverName);
                        }}
                      >
                        View Logs
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Grid>

        {/* Error Logs for Selected Server */}
        {selectedServer && errorLogs[selectedServer] && (
          <Grid item xs={12}>
            <Paper sx={{ p: 2, mt: 2 }}>
              <Typography variant="h6" component="h2" gutterBottom>
                Error Logs: {selectedServer}
              </Typography>
              <Divider sx={{ mb: 2 }} />
              
              {errorLogs[selectedServer].length > 0 ? (
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Timestamp</TableCell>
                        <TableCell>Tool</TableCell>
                        <TableCell>Error Type</TableCell>
                        <TableCell>Details</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {errorLogs[selectedServer].map((log, index) => (
                        <TableRow key={index}>
                          <TableCell>{new Date(log.timestamp).toLocaleString()}</TableCell>
                          <TableCell>{log.tool}</TableCell>
                          <TableCell>{log.error_type}</TableCell>
                          <TableCell>{log.details.message || log.details}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : (
                <Typography variant="body1">No error logs found</Typography>
              )}
            </Paper>
          </Grid>
        )}
      </Grid>
    </Container>
  );
};

export default Monitoring;
```

This comprehensive approach to error handling covers all aspects of MCP server integration:

1. **Client-Level Error Handling**: Robust error handling at the client level with retries and connection management
2. **Tool-Specific Error Handling**: Specialized error handling for Tavily and Atlassian tools
3. **Circuit Breaker Pattern**: Prevents cascading failures by stopping calls to failing services
4. **Fallback Strategies**: Provides alternatives when services are unavailable
5. **Comprehensive Monitoring**: Tracks errors, detects patterns, and alerts on service degradation
6. **Clear User Feedback**: Translates technical errors into user-friendly messages
7. **Graceful Degradation**: Allows the system to continue functioning even when some services fail

By implementing these error handling mechanisms, the HSBC MCP Registry becomes resilient to a wide range of failure scenarios, ensuring a reliable user experience even when external services encounter issues.
