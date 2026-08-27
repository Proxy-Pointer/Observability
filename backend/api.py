from fastapi import FastAPI, BackgroundTasks, HTTPException
import json
import sqlite3
from typing import Dict, Any
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

from database import init_db, DB_PATH
from evaluate import run_evaluation, evaluate_ticket, stream_evaluate_ticket, GOLDEN_DATASET
from diagnostics import run_diagnostics

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/api/metrics/overall")
def get_overall_metrics():
    conn = get_db_connection()
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
    row = cursor.fetchone()
    overall = dict(row) if row else {}
    
    cursor.execute("""
        SELECT SUM(total_tokens) as total_tokens_used
        FROM agent_spans
    """)
    tokens = cursor.fetchone()
    total_tokens = tokens["total_tokens_used"] if tokens and tokens["total_tokens_used"] else 0
    total_traces = overall.get("total_traces", 0)
    overall["avg_tokens"] = (total_tokens / total_traces) if total_traces > 0 else 0
    
    conn.close()
    return overall

@app.get("/api/dataset")
def get_dataset():
    return GOLDEN_DATASET

@app.delete("/api/clear")
def clear_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Safely clear tables if they exist
    try:
        cursor.execute("DELETE FROM agent_spans")
        cursor.execute("DELETE FROM traces")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.close()
    return {"message": "DB cleared"}

class EvaluateRequest(BaseModel):
    query: str
    expected_category: str
    version: str = "v1"

@app.post("/api/evaluate")
async def evaluate_endpoint(req: EvaluateRequest):
    return StreamingResponse(
        stream_evaluate_ticket(req.query, req.expected_category, req.version), 
        media_type="text/event-stream"
    )

@app.get("/api/diagnose")
async def diagnose_endpoint(version: str = "v1"):
    report = run_diagnostics(version)
    return {"report": report}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
