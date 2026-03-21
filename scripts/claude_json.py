"""Shared Claude JSON-call helpers for AI pipeline stages."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def extract_json_from_response(text: str) -> Any:
    """Parse JSON from a model response, tolerating fenced output."""
    stripped = text.strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", stripped, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass

    bare = re.search(r"\{[\s\S]*\}", stripped)
    if bare:
        try:
            return json.loads(bare.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError("Could not extract valid JSON from Claude's response.")


def call_claude_json(
    prompt: str,
    *,
    engine: str,
    validate: Callable[[Any], T],
    retry: bool = True,
) -> T:
    """Call Claude and validate a JSON response, retrying once if needed."""
    response_text = _call_claude(prompt, engine=engine)

    try:
        parsed = extract_json_from_response(response_text)
        return validate(parsed)
    except (ValueError, json.JSONDecodeError) as exc:
        if retry:
            print(f"  Warning: First attempt failed ({exc}), retrying...")
            retry_prompt = (
                prompt
                + "\n\nIMPORTANT: Return ONLY valid JSON. No text before or after."
            )
            return call_claude_json(
                retry_prompt,
                engine=engine,
                validate=validate,
                retry=False,
            )
        raise ValueError(f"Failed to get valid JSON from Claude after retry: {exc}") from exc


def _call_claude(prompt: str, *, engine: str) -> str:
    if engine == "cli":
        return _call_claude_cli(prompt)
    if engine == "api":
        return _call_claude_api(prompt)
    raise ValueError(f"Unsupported Claude engine: {engine}")


def _call_claude_cli(prompt: str) -> str:
    print("Calling Claude CLI (claude -p)...")

    cmd = ["claude", "-p", prompt]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        print("ERROR: 'claude' CLI not found. Is Claude Code installed?", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("ERROR: Claude CLI timed out after 120s.", file=sys.stderr)
        sys.exit(1)

    if result.returncode != 0:
        print(f"ERROR: Claude CLI exited with code {result.returncode}", file=sys.stderr)
        if result.stderr:
            print(f"  stderr: {result.stderr[:500]}", file=sys.stderr)
        sys.exit(1)

    print(f"  Response received ({len(result.stdout)} chars)")
    return result.stdout


def _call_claude_api(prompt: str) -> str:
    try:
        import anthropic
    except ImportError:
        print("ERROR: anthropic SDK is not installed.", file=sys.stderr)
        print("Install with: pip install anthropic", file=sys.stderr)
        sys.exit(1)

    api_key = _get_api_key()
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable is not set.", file=sys.stderr)
        print("Set it in your .env file or export it:", file=sys.stderr)
        print("  export ANTHROPIC_API_KEY=sk-ant-...", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    print("Calling Claude API...")
    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        print(f"ERROR: Claude API call failed: {exc}", file=sys.stderr)
        raise

    response_text = message.content[0].text
    print(f"  Response received ({len(response_text)} chars)")
    return response_text


def _get_api_key() -> str | None:
    import os

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    return os.environ.get("ANTHROPIC_API_KEY")
