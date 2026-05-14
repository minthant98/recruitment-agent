"""
graph.py — LangGraph pipeline definition for the Recruitment Agent.
"""
from langgraph.graph import StateGraph, END
from state.agent_state import AgentState

from nodes.classifier import classifier_node
from nodes.ingest import ingest_node
from nodes.screening import screening_node
from nodes.judge import judge_node
from nodes.hitl import hitl_node
from nodes.audit import audit_node
from nodes.routing import routing_node
from nodes.scheduling import scheduling_node


# ── Routing functions ─────────────────────────────────────────────

def route_after_classifier(state: AgentState) -> str:
    """
    Route based on CV presence and JD match confidence tier.

    HIGH confidence   → ingest (screening runs immediately)
    MEDIUM confidence → confirmation_pause (recruiter confirms job)
    LOW confidence    → unmatched_queue (recruiter assigns manually)
    No CV             → discard
    """
    if not state.get("has_cv"):
        return "discard"

    match_status = state.get("match_status", "UNMATCHED")

    if match_status == "AUTO_ASSIGNED":
        return "ingest"
    elif match_status == "AWAITING_CONFIRMATION":
        return "confirmation_pause"
    else:
        return "unmatched_queue"


def route_after_audit(state: AgentState) -> str:
    decision = state.get("final_decision", "REJECT")
    if decision == "SHORTLIST_INTERVIEW":
        return "routing"
    return "end"


# ── Static nodes ──────────────────────────────────────────────────

def discard_node(state: AgentState) -> dict:
    print(f"  [Discard] {state.get('discard_reason', 'No CV found')}")
    return {"current_node": "discard"}


def confirmation_pause_node(state: AgentState) -> dict:
    """
    Pipeline pauses here for MEDIUM confidence matches.
    Recruiter sees top JD candidates and confirms the right one.
    Resume is triggered by POST /confirm/{run_id} in the web UI.
    The interrupt_before=["confirmation_pause"] in compile_graph handles the pause.
    """
    print(f"  [ConfirmationPause] Waiting for recruiter to confirm JD match")
    print(f"  [ConfirmationPause] Top pick: {state.get('matched_jd_title')}")
    print(f"  [ConfirmationPause] Confidence: {state.get('confidence_score', 0):.0%}")
    return {"current_node": "confirmation_pause"}


def unmatched_queue_node(state: AgentState) -> dict:
    """
    Pipeline parks here for LOW confidence matches.
    Recruiter manually assigns a job from the unmatched queue.
    Resume is triggered by POST /assign/{run_id} in the web UI.
    The interrupt_before=["unmatched_queue"] in compile_graph handles the pause.
    """
    print(f"  [UnmatchedQueue] CV parked — no confident JD match found")
    return {"current_node": "unmatched_queue"}


# ── Graph builder ─────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # Existing nodes — unchanged
    graph.add_node("classifier",    classifier_node)
    graph.add_node("ingest",        ingest_node)
    graph.add_node("screening",     screening_node)
    graph.add_node("judge",         judge_node)
    graph.add_node("hitl",          hitl_node)
    graph.add_node("audit",         audit_node)
    graph.add_node("routing",       routing_node)
    graph.add_node("scheduling",    scheduling_node)
    graph.add_node("discard",       discard_node)

    # New nodes — Phase 4
    graph.add_node("confirmation_pause", confirmation_pause_node)
    graph.add_node("unmatched_queue",    unmatched_queue_node)

    graph.set_entry_point("classifier")

    # Classifier now branches three ways + discard
    graph.add_conditional_edges(
        "classifier",
        route_after_classifier,
        {
            "ingest":               "ingest",
            "confirmation_pause":   "confirmation_pause",
            "unmatched_queue":      "unmatched_queue",
            "discard":              "discard",
        }
    )

    # After recruiter confirms or assigns — resume at ingest
    graph.add_edge("confirmation_pause", "ingest")
    graph.add_edge("unmatched_queue",    "ingest")

    # Main pipeline — unchanged
    graph.add_edge("ingest",    "screening")
    graph.add_edge("screening", "judge")
    graph.add_edge("judge",     "hitl")
    graph.add_edge("hitl",      "audit")

    graph.add_conditional_edges(
        "audit",
        route_after_audit,
        {"routing": "routing", "end": END}
    )

    graph.add_edge("routing",    "scheduling")
    graph.add_edge("scheduling", END)
    graph.add_edge("discard",    END)

    return graph


def compile_graph(checkpointer=None):
    """Compile graph with optional external checkpointer."""
    from langgraph.checkpoint.memory import MemorySaver
    graph = build_graph()
    memory = checkpointer or MemorySaver()
    return graph.compile(
        checkpointer=memory,
        interrupt_before=["hitl", "confirmation_pause", "unmatched_queue"],
    )