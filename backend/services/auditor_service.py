import os
import json

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("NVIDIA_API_KEY")

if not api_key:
    raise RuntimeError("NVIDIA_API_KEY not found in .env")

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=api_key
)

MODEL = "nvidia/nemotron-3-ultra-550b-a55b"


def audit_code(filename, code):
    """
    Analyze a source file using NVIDIA Nemotron.
    """

    prompt = f"""
You are the senior software auditor for NMC-SmartFix,
an AI-powered municipal complaint management system.

Review the following source file for real-world deployment.

FILE:
{filename}

SOURCE CODE:
{code}

Analyze the code for:

1. Bugs and incorrect behavior
2. Security vulnerabilities
3. Authentication and authorization problems
4. Database problems
5. Error handling problems
6. Performance issues
7. Missing validation
8. Missing tests
9. Architecture and design concerns
10. Practical improvements for real-world municipal deployment

Do not invent problems that are not supported by the code.

Return ONLY valid JSON.

Use exactly this structure:

{{
    "overall_score": 0,
    "summary": "",
    "bugs": [],
    "security_issues": [],
    "database_issues": [],
    "performance_issues": [],
    "testing_gaps": [],
    "architecture_issues": [],
    "improvements": []
}}

overall_score must be an integer from 0 to 100.

Each issue must contain:

{{
    "severity": "Low",
    "title": "",
    "description": "",
    "recommendation": ""
}}

Severity must be one of:

Low
Medium
High
Critical

Keep recommendations practical and specific.
"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict but practical senior "
                    "software auditor."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.2,
        max_tokens=8000
    )

    text = response.choices[0].message.content.strip()

    if text.startswith("```"):
        lines = text.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    try:
        return json.loads(text)

    except json.JSONDecodeError:
        raise ValueError(
            f"Nemotron returned invalid JSON:\n{text}"
        )