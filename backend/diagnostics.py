import os
import sqlite3
from langchain_google_genai import ChatGoogleGenerativeAI
from database import DB_PATH
from config import AGENT_MODEL

def run_diagnostics(version: str = "v1") -> str:
    """Reads the current aggregate metrics and source code to generate an improvement report."""
    
    # 1. Fetch aggregate metrics
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            AVG(total_latency) as avg_latency,
            AVG(router_accuracy_score) as avg_router_accuracy,
            AVG(response_accuracy_score) as avg_response_accuracy,
            AVG(conciseness_score) as avg_conciseness,
            COUNT(id) as total_traces
        FROM traces
    """)
    metrics = dict(sqlite3.Row(cursor, cursor.fetchone()))
    conn.close()

    if metrics.get("total_traces", 0) == 0:
        return "Not enough data to run diagnostics. Please run some queries first."

    # 2. Read the agent source code
    agent_code = ""
    try:
        with open("ticket_agent.py", "r") as f:
            agent_code = f.read()
    except Exception as e:
        agent_code = f"Error reading code: {e}"

    # 3. Analyze with LLM
    llm = ChatGoogleGenerativeAI(
        model=AGENT_MODEL,
        temperature=0.3,
        api_key=os.environ.get("GOOGLE_API_KEY")
    )
    
    prompt = f"""
    You are an expert AI Engineer and Diagnostics Agent. You are tasked with diagnosing an LLM Agent system.
    
    Currently, the system is running version: {version}
    
    ## Current Metrics (from Observability DB):
    - Total Traces Evaluated: {metrics['total_traces']}
    - Avg Router Accuracy: {metrics['avg_router_accuracy']:.1f}%
    - Avg Response Accuracy: {metrics['avg_response_accuracy']:.1f}/5.0
    - Avg Conciseness: {metrics['avg_conciseness']:.1f}/5.0
    
    ## Agent Source Code:
    ```python
    {agent_code}
    ```
    
    ## Task
    Write a succinct, professional Diagnostics Report in markdown.
    If the version is 'v1', identify the exact flaws in the `sys_prompt` strings for the `triage_agent`, `technical_support_agent`, and `billing_support_agent` that are causing the poor metrics. Explain WHY they are scoring poorly and recommend changes. Be polite in your assessment .. state the causes, do not be judgemental.
    If the version is 'v2', celebrate the improvements and explain how the strict RAG instructions fixed the issues.
    
    Keep the report under 300 words. Format cleanly.
    """
    
    response = llm.invoke([{"role": "user", "content": prompt}])
    return response.content
