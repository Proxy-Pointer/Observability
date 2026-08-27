import sqlite3
import json
from contextlib import contextmanager
import time
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'observability.db')

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Table for overall query execution (trace)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                category TEXT,
                final_response TEXT,
                start_time REAL,
                end_time REAL,
                total_latency REAL,
                router_accuracy_score REAL,
                response_accuracy_score REAL,
                conciseness_score REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Table for individual agent execution within a trace
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_spans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id INTEGER,
                agent_name TEXT,
                input_data TEXT,
                output_data TEXT,
                start_time REAL,
                end_time REAL,
                latency REAL,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                FOREIGN KEY(trace_id) REFERENCES traces(id)
            )
        ''')
        conn.commit()

init_db()

@contextmanager
def trace_query(query: str):
    start_time = time.time()
    trace_id = None
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO traces (query, start_time) VALUES (?, ?)", (query, start_time))
        trace_id = cursor.lastrowid
        conn.commit()
        
    trace_context = {"trace_id": trace_id}
    
    try:
        yield trace_context
    finally:
        end_time = time.time()
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE traces 
                SET end_time = ?, total_latency = ? 
                WHERE id = ?
            """, (end_time, end_time - start_time, trace_id))
            
            if "final_response" in trace_context:
                cursor.execute("UPDATE traces SET final_response = ? WHERE id = ?", (trace_context["final_response"], trace_id))
            if "category" in trace_context:
                cursor.execute("UPDATE traces SET category = ? WHERE id = ?", (trace_context["category"], trace_id))
            
            conn.commit()

@contextmanager
def trace_agent(trace_id: int, agent_name: str, input_data: dict):
    start_time = time.time()
    span_context = {"input": input_data, "output": None, "usage": {}}
    
    try:
        yield span_context
    finally:
        end_time = time.time()
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agent_spans (
                    trace_id, agent_name, input_data, output_data, 
                    start_time, end_time, latency,
                    prompt_tokens, completion_tokens, total_tokens
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trace_id,
                agent_name,
                json.dumps(input_data),
                json.dumps(span_context["output"]) if span_context.get("output") is not None else None,
                start_time,
                end_time,
                end_time - start_time,
                span_context["usage"].get("prompt_tokens", 0),
                span_context["usage"].get("completion_tokens", 0),
                span_context["usage"].get("total_tokens", 0)
            ))
            conn.commit()
