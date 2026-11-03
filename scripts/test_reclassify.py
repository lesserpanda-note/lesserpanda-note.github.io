#!/usr/bin/env python3
"""Unit tests for reclassify() — the DataScience -> Agents/AI re-filer in fetch_news.py.

Run: python scripts/test_reclassify.py   (plain asserts, no pytest dependency)

Locks the keyword heuristic so future edits to _AGENTS_RE / _AI_RE don't silently
regress. Cases are drawn from real feed titles that motivated the rule.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("fetch_news", Path(__file__).with_name("fetch_news.py"))
_fetch_news = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fetch_news)
reclassify = _fetch_news.reclassify

# (input category, title) -> expected category
CASES = [
    # DataScience LLM / agent tooling -> Agents
    ("DataScience", "How to Orchestrate 100+ Agents With Claude Code", "Agents"),
    ("DataScience", "Model Context Protocol Explained in 3 Levels of Difficulty", "Agents"),
    ("DataScience", "A Production RAG Pipeline for PDFs", "Agents"),
    ("DataScience", "The Big Con of Agentic AI", "Agents"),
    ("DataScience", "LLM Orchestration Frameworks Compared: LangChain vs LlamaIndex", "Agents"),
    ("DataScience", "Context Window Management for Long-Running Agents", "Agents"),
    ("DataScience", "The Complete Guide to Tool Selection in AI Agents", "Agents"),
    ("DataScience", "pgvector vs. Dedicated Vector Databases: A Production Benchmark", "Agents"),
    ("DataScience", "Your AI Assistant Wrote the Code. Who Checked the Defaults?", "Agents"),
    ("DataScience", "I Tested 5 AI Coding Assistants for a Month", "Agents"),
    # DataScience frontier-model / LLM -> AI
    ("DataScience", "Fine-Tuning Explained for Noobs", "AI"),
    ("DataScience", "Zero-Shot Local Document Parsing with Gemma 4", "AI"),
    ("DataScience", "Setting Up Your Own Large Language Model", "AI"),
    ("DataScience", "Getting Started with the Claude API in Python", "AI"),
    # generic phrasing, so a model nobody had heard of last quarter still lands in AI
    ("DataScience", "Is the #1 AI Model Really #1?", "AI"),
    ("DataScience", "What a Reasoning Model Says When It Follows a Planted Hint", "AI"),
    ("DataScience", "Reflection's Beam Is the New Open-Weight Model", "AI"),
    ("DataScience", "5 Best Resources to Learn About World Models in 2026", "AI"),
    ("DataScience", "Key-Value Caching for SLM Optimization", "AI"),
    ("DataScience", "Could On-Policy Self-Distillation Revolutionize Post-Training?", "AI"),
    # a listed vendor name glued to a prefix still counts
    ("DataScience", "EmbeddingGemma 2: Text, Code, Images, Video and Audio", "AI"),
    # Genuine applied stats / ML -> stays DataScience (must NOT be dragged out)
    ("DataScience", "Survival Analysis for Data Drift and ML Reliability", "DataScience"),
    ("DataScience", "Granger Causal Networks and Indirect Feedback", "DataScience"),
    ("DataScience", "Information Theory and Ensemble Models", "DataScience"),
    ("DataScience", "7 Steps to Automating Descriptive Statistics with Python", "DataScience"),
    ("DataScience", "PySpark for Beginners: Building Intermediate-Level Skills", "DataScience"),
    ("DataScience", "How to Clean Messy CSV Files with Python", "DataScience"),
    ("DataScience", "pandas 3.0.4", "DataScience"),  # library release title stays put
    # near-misses for the generic patterns, all genuine stats vocabulary
    ("DataScience", "Open Weighting Schemes for Non-Probability Survey Samples", "DataScience"),
    ("DataScience", "Counting Llamas with Poisson Regression", "DataScience"),
    ("DataScience", "Dilemmas in Post-Stratification Weighting", "DataScience"),
    ("DataScience", "Fitting an lm in R: Diagnostics for Linear Models", "DataScience"),
    # Agents is checked before AI: a title hitting both sets resolves to Agents
    ("DataScience", "Building Browser-Using AI Agents with an LLM backend", "Agents"),
    # Scope: only DataScience is reclassified; every other bucket passes through untouched
    ("AI", "Some LLM model headline", "AI"),
    ("Agents", "Claude Code tips", "Agents"),
    ("Python", "Building LLM agents in Python", "Python"),
    ("Java", "Spring AI LLM integration", "Java"),
    ("DataScience", "", "DataScience"),  # empty title is a no-op
]


def main() -> int:
    failed = 0
    for category, title, expected in CASES:
        got = reclassify(category, title)
        if got != expected:
            failed += 1
            print(f"FAIL  reclassify({category!r}, {title!r}) = {got!r}, expected {expected!r}")
    total = len(CASES)
    if failed:
        print(f"\n{failed}/{total} FAILED")
        return 1
    print(f"all {total} reclassify cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
