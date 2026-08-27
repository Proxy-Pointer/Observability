"""
Conditional Multi-Agent Support System
LangGraph + Google Gemini + Local SQLite Observability

Agents:
  Triage → Technical Support → Billing Support → Finalizer 
"""

import os
from typing import TypedDict
from dotenv import load_dotenv

from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI

from database import trace_query, trace_agent
from config import AGENT_MODEL

# Load .env (ensure GOOGLE_API_KEY is available)
load_dotenv(override=True)

# --------------------------------------------------
# 1. LLM Setup
# --------------------------------------------------
llm = ChatGoogleGenerativeAI(
    model=AGENT_MODEL,
    temperature=0.2,
    api_key=os.environ.get("GOOGLE_API_KEY")
)

def extract_usage(response):
    """Safely extract token usage from LangChain response."""
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if hasattr(response, 'usage_metadata') and response.usage_metadata:
        usage["prompt_tokens"] = response.usage_metadata.get('input_tokens', 0)
        usage["completion_tokens"] = response.usage_metadata.get('output_tokens', 0)
        usage["total_tokens"] = response.usage_metadata.get('total_tokens', 0)
    elif hasattr(response, 'response_metadata') and 'token_usage' in response.response_metadata:
        tu = response.response_metadata['token_usage']
        usage["prompt_tokens"] = tu.get('prompt_tokens', 0)
        usage["completion_tokens"] = tu.get('completion_tokens', 0)
        usage["total_tokens"] = tu.get('total_tokens', 0)
    return usage

# --------------------------------------------------
# 2. Shared State
# --------------------------------------------------
class AgentState(TypedDict, total=False):
    ticket: str
    version: str
    category: str
    technical_response: str
    billing_response: str
    final_response: str
    trace_id: int

# --------------------------------------------------
# 3. Agent Definitions
# --------------------------------------------------

def triage_agent(state: dict) -> dict:
    trace_id = state.get("trace_id")
    version = state.get("version", "v1")
    
    sys_prompt = (
        "Classify the query as one of: Technical, Billing, Both. Respond with only the label."
    )
    if version == "v1":
        sys_prompt = "You are a broken classifier. If the query mentions 'bill', 'payment', 'refund', or 'tax', respond ONLY with 'Billing'. DO NOT output 'Both'. DO NOT output 'Technical' if it mentions money."
    else:
        sys_prompt = (
            "Classify the query as Technical, Billing, or Both. Respond with only the label. "
            # "IMPORTANT EXAMPLES: 'Payment Required' with 'RAM/throttling' is Both. "
            # "'App crash' + 'Refund' is Both. 'JSON export of receipts' is Billing. "
            # "'Quota exceeded' on Database is Technical."
        )

    with trace_agent(trace_id, "triage_agent", {"ticket": state["ticket"], "version": version}) as span:
        response = llm.invoke([
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": state["ticket"]},
        ])

        raw = response.content.strip().lower()

        if "both" in raw:
            category = "Both"
        elif "technical" in raw:
            category = "Technical"
        elif "billing" in raw:
            category = "Billing"
        else:
            category = "Technical"  # safe fallback

        span["output"] = {"raw": raw, "category": category}
        span["usage"] = extract_usage(response)

        return {"category": category}


def technical_support_agent(state: dict) -> dict:
    trace_id = state.get("trace_id")
    version = state.get("version", "v1")
    
    sys_prompt = "You are a technical support specialist. Provide a clear, step-by-step solution."
    if version == "v1":
        sys_prompt = "You are a technical support specialist. Write a very long, chatty, 5-paragraph essay. Give terrible advice like 'delete the registry keys' or 'turn off your firewall'. Never actually answer the user's root question."
    else:
        sys_prompt = "You are a technical support specialist. Answer concisely under 100 words. Be professional and helpful. \nKB: 404 error -> Clear Cache. Quota exceeded -> Upgrade storage tier in Settings. App crashing -> Update to v1.3."

    with trace_agent(trace_id, "technical_support_agent", {"ticket": state["ticket"], "category": state.get("category"), "version": version}) as span:
        response = llm.invoke([
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": state["ticket"]},
        ])

        answer = response.content
        span["output"] = {"technical_response": answer}
        span["usage"] = extract_usage(response)

        return {"technical_response": answer}


def billing_support_agent(state: dict) -> dict:
    trace_id = state.get("trace_id")
    version = state.get("version", "v1")
    
    sys_prompt = "You are a billing support specialist. Answer clearly about payments, invoices, or accounts."
    if version == "v1":
        sys_prompt = "You are a billing support specialist. Write a very long, conversational 5-paragraph response. Never mention the 'Billing Portal'. Suggest they mail a physical check to our headquarters."
    else:
        sys_prompt = "You are a billing support specialist. Answer concisely under 100 words. Be professional and helpful. \nKB: Refund -> Need invoice number. JSON export -> Billing -> History -> Export. Payment Required -> Update card in Billing Portal."

    with trace_agent(trace_id, "billing_support_agent", {"ticket": state["ticket"], "category": state.get("category"), "version": version}) as span:
        response = llm.invoke([
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": state["ticket"]},
        ])

        answer = response.content
        span["output"] = {"billing_response": answer}
        span["usage"] = extract_usage(response)

        return {"billing_response": answer}

def finalizer_agent(state: dict) -> dict:
    trace_id = state.get("trace_id")
    version = state.get("version", "v1")
    
    with trace_agent(trace_id, "finalizer_agent", {
        "ticket": state["ticket"],
        "technical": state.get("technical_response"),
        "billing": state.get("billing_response"),
        "version": version
    }) as span:

        parts = [
            f"Technical:\n{state['technical_response']}"
            for k in ["technical_response"]
            if state.get(k)
        ] + [
            f"Billing:\n{state['billing_response']}"
            for k in ["billing_response"]
            if state.get(k)
        ]

        if not parts:
            final = "Error: No agent responses available."
            span["output"] = {"final_response": final}
            return {"final_response": final}
            
        sys_prompt = "Combine the agent responses into ONE answer. Do not mention agents."
        if version == "v2":
            sys_prompt = "Combine the agent responses into a clear, professional customer support email. Be concise and polite, keeping it under 100 words."
            
        response = llm.invoke([
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": "Query: " + state['ticket'] + "\n\nResponses:\n" + "\n\n".join(parts)},
        ])
        final = response.content

        span["output"] = {"final_response": final}
        span["usage"] = extract_usage(response)
        
        return {"final_response": final}


# --------------------------------------------------
# 4. LangGraph Construction
# --------------------------------------------------
builder = StateGraph(AgentState)

builder.add_node("triage", triage_agent)
builder.add_node("technical", technical_support_agent)
builder.add_node("billing", billing_support_agent)
builder.add_node("finalizer", finalizer_agent)

builder.set_entry_point("triage")

def route_triage(state):
    cat = state.get("category", "").lower()
    if "billing" in cat: return "billing"
    if "both" in cat: return "technical"
    return "technical"

builder.add_conditional_edges("triage", route_triage)

def route_technical(state):
    cat = state.get("category", "").lower()
    if "both" in cat: return "billing"
    return "finalizer"

# Sequential resolution
builder.add_conditional_edges("technical", route_technical)
builder.add_edge("billing", "finalizer")
builder.add_edge("finalizer", END)

graph = builder.compile()


def process_ticket(ticket: str):
    """Entry point to process a ticket and trace it."""
    with trace_query(ticket) as trace:
        result = graph.invoke({"ticket": ticket, "trace_id": trace["trace_id"]})
        
        # Save results back to trace context so the DB gets updated
        trace["category"] = result.get("category", "Unknown")
        trace["final_response"] = result.get("final_response", "")
        
        return result

def stream_process_ticket(ticket: str, version: str = "v1"):
    """Entry point to process a ticket and trace it, yielding events for SSE."""
    with trace_query(ticket) as trace:
        yield {"type": "start", "trace_id": trace["trace_id"]}
        
        final_state = {}
        for step in graph.stream({"ticket": ticket, "trace_id": trace["trace_id"], "version": version}, stream_mode="updates"):
            for node_name, state_update in step.items():
                yield {"type": "node_complete", "node": node_name, "update": state_update}
                final_state.update(state_update)
        
        if final_state:
            trace["category"] = final_state.get("category", "Unknown")
            trace["final_response"] = final_state.get("final_response", "")
            
        yield {"type": "end"}

# --------------------------------------------------
# 5. Main
# --------------------------------------------------
if __name__ == "__main__":
    print("===============================================")
    print(" Conditional Multi-Agent Support System (Local Trace)")
    print("===============================================")
    
    while True:
        ticket = input("Enter your support query (ticket): ")
        if ticket.lower() in ["exit", "quit"]:
            break
        if not ticket.strip():
            continue
            
        try:
            result = process_ticket(ticket)
            print(f"\n✅ Triage Classification: **{result.get('category')}**")
            print("\n================ FINAL RESPONSE ================\n")
            print(result["final_response"])
            print("\n" + "="*60 + "\n")
        except Exception as e:
            print(f"\nAn error occurred: {e}\n")
