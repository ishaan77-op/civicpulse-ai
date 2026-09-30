import os
import json
import mimetypes

from dotenv import load_dotenv
from google import genai
from google.genai import types

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_backend_dir, ".env"))
load_dotenv()

def get_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not found in .env")
    return genai.Client(api_key=api_key)


def _clean_json_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def analyze_complaint(title, description, location, image_path=None):
    """
    Analyze a civic complaint using text and, optionally, an image.

    Returns structured AI analysis.
    """

    prompt = f"""
You are the AI intelligence engine for CivicPulse / NMC-SmartFix,
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
    "summary": "",
    "spam_flag": false,
    "spam_reason": "",
    "spam_confidence": ""
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

Allowed spam_confidence values (only relevant when spam_flag is true):
- Low
- Medium
- High

Rules:

1. Use the description and image together when an image is provided.
2. visual_observation must describe only what is reasonably visible in the image.
3. Do not claim certainty about hidden damage or exact engineering conditions.
4. priority represents municipal triage priority, not a guaranteed safety assessment.
5. department should be the municipal department most likely responsible.
6. summary should be short and clear.
7. Do not include markdown.
8. Do not include explanations outside the JSON.
9. spam_flag is a likely misreport/mismatch signal, separate from priority or category.
   Set spam_flag to true ONLY when there is a clear mismatch between the image and the
   claimed complaint, for example: the photo shows something completely unrelated to any
   civic issue (a selfie, a random object, an unrelated scene), or the photo plainly
   contradicts the title/description (e.g. description claims a flooded road but the
   photo shows a dry, undamaged street).
10. Do NOT set spam_flag to true for low image quality, bad lighting, an unusual angle,
    a partially visible issue, or genuine ambiguity about severity - those are normal,
    good-faith reports and must not be flagged.
11. When spam_flag is true, spam_reason must briefly explain the mismatch in plain
    language, and spam_confidence must reflect how certain you are.
12. When spam_flag is false, set spam_reason to "" and spam_confidence to "".
"""

    contents = [prompt]

    if image_path and os.path.exists(image_path):
        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type:
            mime_type = "image/jpeg"

        with open(image_path, "rb") as image_file:
            image_data = image_file.read()

        contents.append(
            types.Part.from_bytes(
                data=image_data,
                mime_type=mime_type
            )
        )

    client = get_client()
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.2,
    )

    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
        contents=contents,
        config=config,
    )

    raw_text = response.text or ""
    clean_text = _clean_json_text(raw_text)

    try:
        return json.loads(clean_text)
    except json.JSONDecodeError:
        raise ValueError(
            f"AI returned invalid JSON:\n{raw_text}"
        )