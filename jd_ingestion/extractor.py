"""
extractor.py — Use Groq to extract structured fields from raw JD text.
"""
import json
from groq import Groq
from config import get_settings

EXTRACTION_PROMPT = """
You are a JD parsing assistant. Given a raw Job Description text, extract the following fields and return ONLY a valid JSON object. No preamble, no markdown, no explanation.

JSON schema to return:
{
  "role_title": "string — exact job title",
  "seniority_level": "string — e.g. Junior, Senior, Supervisor, Manager, or null",
  "required_years": "float — minimum years of experience required, or null if not stated",
  "required_skills": ["list of required technical and soft skills"],
  "preferred_skills": ["list of preferred or nice-to-have skills, empty list if none"],
  "education_requirements": "string — minimum education required, or null",
  "key_responsibilities": ["top 5 responsibilities as short strings"],
  "screening_criteria": [
    {
      "criterion_name": "required_skills_match",
      "weight": 0.40,
      "description": "Candidate must demonstrate proficiency in the required technical skills listed"
    },
    {
      "criterion_name": "experience_alignment",
      "weight": 0.40,
      "description": "Candidate years and role similarity must meet the minimum threshold"
    },
    {
      "criterion_name": "preferred_skills",
      "weight": 0.10,
      "description": "Additional preferred skills that add value beyond the minimum"
    },
    {
      "criterion_name": "education_domain_fit",
      "weight": 0.10,
      "description": "Education level and field of study alignment with the role"
    }
  ]
}

Important rules:
- Return ONLY the JSON object, nothing else
- Do not fabricate information not present in the JD
- screening_criteria must always have exactly these 4 entries with these exact weights
- Update the description field of each criterion to be specific to this JD
"""


def extract_jd_structure(raw_text: str) -> dict:
    """
    Send raw JD text to Groq and return structured fields as a dict.
    """
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    response = client.chat.completions.create(
        model=settings.groq_screener_model,
        temperature=0.0,
        messages=[
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": f"Extract structured fields from this JD:\n\n{raw_text}"},
        ],
    )

    raw_output = response.choices[0].message.content.strip()

    # Strip markdown code fences if present
    if raw_output.startswith("```"):
        raw_output = raw_output.split("```")[1]
        if raw_output.startswith("json"):
            raw_output = raw_output[4:]

    return json.loads(raw_output.strip())