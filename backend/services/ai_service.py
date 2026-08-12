import os
import json

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY not found in .env")

client = genai.Client(api_key=api_key)


def analyze_complaint(title, description, location, image_path=None):
    """
    Analyze a civic complaint using text and, optionally, an image.

    Returns structured AI analysis.
    """

    prompt = f"""
You are the AI intelligence engine for CivicPulse,
a municipal complaint management system.

Analyze this citizen complaint.

Title:
{title}

Description:
{description}

Location:
{location}

The image, if provided, shows the reported civic issue.

Return ONLY valid JSON with exactly these fields:

{{
    "category": "",
    "priority": "",
    "department": "",
    "visual_observation": "",
    "summary": ""
}}

Allowed categories:
- Road Infrastructure
- Garbage and Waste
- Water Supply
- Street Lighting
- Drainage
- Public Safety
- Other

Allowed priorities:
- Low
- Medium
- High
- Critical

Rules:

1. Use the description and image together when an image is provided.
2. visual_observation must describe only what is reasonably visible in the image.
3. Do not claim certainty about hidden damage or exact engineering conditions.
4. priority represents municipal triage priority, not a guaranteed safety assessment.
5. department should be the municipal department most likely responsible.
6. summary should be short and clear.
7. Do not include markdown.
8. Do not include explanations outside the JSON.
"""

    contents = [prompt]

    if image_path:
        with open(image_path, "rb") as image_file:
            image_data = image_file.read()

        contents.append(
            types.Part.from_bytes(
                data=image_data,
                mime_type="image/jpeg"
            )
        )

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=contents
    )

    text = response.text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise ValueError(
            f"AI returned invalid JSON:\n{text}"
        )