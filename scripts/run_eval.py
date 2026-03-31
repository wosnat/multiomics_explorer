"""MCP Server Evaluation Harness — Claude Code edition.

Uses `claude -p` (subscription-based) instead of the Anthropic API.
MCP server config comes from .claude/settings.json automatically.

Usage:
    python scripts/run_eval.py tests/evals/mcp_evaluation.xml
    python scripts/run_eval.py tests/evals/mcp_evaluation.xml -o eval_report.md
    python scripts/run_eval.py tests/evals/mcp_evaluation.xml --questions 1,3,5
"""

import argparse
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

SYSTEM_PROMPT = """You are answering evaluation questions using ONLY the multiomics-kg MCP tools.

Rules:
1. Use the MCP tools to find the answer. Do not guess or use prior knowledge for data.
2. Think step by step, using multiple tool calls as needed.
3. Wrap your final answer in <response> tags — nothing else inside the tags.
4. If you cannot find the answer, respond with <response>NOT_FOUND</response>.
5. Keep the answer concise: a single value (number, name, ID, term) as requested.
6. After your response, wrap a brief summary of your approach in <summary> tags.
7. After your summary, wrap tool feedback in <feedback> tags."""


def parse_evaluation_file(file_path: Path) -> list[dict[str, str]]:
    tree = ET.parse(file_path)
    root = tree.getroot()
    pairs = []
    for qa in root.findall(".//qa_pair"):
        q = qa.find("question")
        a = qa.find("answer")
        if q is not None and a is not None:
            pairs.append({
                "question": (q.text or "").strip(),
                "answer": (a.text or "").strip(),
            })
    return pairs


def extract_tag(text: str, tag: str) -> str | None:
    matches = re.findall(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
    return matches[-1].strip() if matches else None


def run_question(question: str, model: str | None = None) -> tuple[str, float]:
    """Run a single question through claude -p and return (output, duration)."""
    cmd = [
        "claude", "-p", question,
        "--append-system-prompt", SYSTEM_PROMPT,
        "--output-format", "text",
        "--allowedTools", "mcp__multiomics-kg__*",
    ]
    if model:
        cmd.extend(["--model", model])

    start = time.time()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    duration = time.time() - start

    if result.returncode != 0:
        return f"ERROR: {result.stderr.strip()}", duration

    return result.stdout.strip(), duration


def evaluate(qa_pairs: list[dict], model: str | None = None) -> list[dict]:
    results = []
    for i, qa in enumerate(qa_pairs):
        print(f"[{i+1}/{len(qa_pairs)}] {qa['question'][:80]}...")
        output, duration = run_question(qa["question"], model)

        response = extract_tag(output, "response")
        summary = extract_tag(output, "summary")
        feedback = extract_tag(output, "feedback")
        score = int(response == qa["answer"]) if response else 0

        status = "\u2705" if score else "\u274c"
        print(f"  {status} expected={qa['answer']!r}  got={response!r}  ({duration:.1f}s)")

        results.append({
            "question": qa["question"],
            "expected": qa["answer"],
            "actual": response,
            "score": score,
            "duration": duration,
            "summary": summary,
            "feedback": feedback,
            "raw_output": output,
        })
    return results


def build_report(results: list[dict]) -> str:
    correct = sum(r["score"] for r in results)
    total = len(results)
    accuracy = (correct / total * 100) if total else 0
    avg_dur = sum(r["duration"] for r in results) / total if total else 0

    lines = [
        "# MCP Evaluation Report\n",
        "## Summary\n",
        f"- **Accuracy**: {correct}/{total} ({accuracy:.1f}%)",
        f"- **Average Duration**: {avg_dur:.1f}s\n",
        "---\n",
    ]

    for i, r in enumerate(results):
        status = "\u2705" if r["score"] else "\u274c"
        lines.append(f"### Task {i+1} {status}\n")
        lines.append(f"**Question**: {r['question']}\n")
        lines.append(f"**Expected**: `{r['expected']}`\n")
        lines.append(f"**Actual**: `{r['actual'] or 'N/A'}`\n")
        lines.append(f"**Duration**: {r['duration']:.1f}s\n")
        if r["summary"]:
            lines.append(f"**Summary**: {r['summary']}\n")
        if r["feedback"]:
            lines.append(f"**Feedback**: {r['feedback']}\n")
        lines.append("---\n")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run MCP eval using Claude Code CLI")
    parser.add_argument("eval_file", type=Path, help="XML evaluation file")
    parser.add_argument("-o", "--output", type=Path, help="Save report to file")
    parser.add_argument("-m", "--model", help="Model override (e.g., sonnet)")
    parser.add_argument(
        "-q", "--questions", type=str,
        help="Comma-separated 1-based question numbers to run (e.g., 1,3,5)",
    )
    args = parser.parse_args()

    if not args.eval_file.exists():
        print(f"Error: {args.eval_file} not found")
        sys.exit(1)

    qa_pairs = parse_evaluation_file(args.eval_file)
    print(f"Loaded {len(qa_pairs)} questions from {args.eval_file}")

    if args.questions:
        indices = [int(x) - 1 for x in args.questions.split(",")]
        qa_pairs = [qa_pairs[i] for i in indices if 0 <= i < len(qa_pairs)]
        print(f"Running subset: {len(qa_pairs)} questions")

    results = evaluate(qa_pairs, args.model)
    report = build_report(results)

    if args.output:
        args.output.write_text(report)
        print(f"\nReport saved to {args.output}")
    else:
        print(f"\n{report}")


if __name__ == "__main__":
    main()
