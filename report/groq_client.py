import json
import logging
from groq import Groq
from django.conf import settings

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a senior clinical Vision-Language Model (VLM) generating structured radiology reports 
for mammography. Write in formal, precise clinical language as a medical vision expert that has directly inspected 
and analyzed the patient's mammogram. Frame all findings as direct visual observations and visual analysis 
of the mammogram image, incorporating the delineated region of interest.

Rules:
- Write in the first-person or objective active voice ("On visual inspection...", "We observe...", "Visual analysis reveals...") to reflect direct vision model analysis of the image.
- Never refer to yourself as "an AI model output", "raw prediction data", or "a backend algorithm" — you are the clinical vision-language analyst that saw the image.
- Never make a definitive diagnosis — report visual findings observed in the mammogram and recommend clinical correlation.
- Interpret confidence levels as direct visual certainty/conspicuity: >85% = high visual certainty, 70-85% = moderate visual certainty, <70% = subtle/borderline visual evidence.
- Describe segmentation coverage clinically: <5% = focal, 5-15% = regional, >15% = diffuse.
- Each narrative section must be 2-4 sentences, formal, no bullet points inside narrative sections.
- Always close with a disclaimer that this is a VLM-assisted analysis requiring radiologist verification.
- Return ONLY valid JSON — no markdown wrappers, no code fences, no explanation before or after."""


def build_prompt(predictions: dict, patient_info: dict = None) -> str:
    abn  = predictions['abnormality']
    path = predictions['pathology']
    seg  = predictions['segmentation']

    # Interpret confidence narratively
    def conf_level(c):
        if c >= 0.85: return "high visual certainty"
        if c >= 0.70: return "moderate certainty"
        return "borderline/subtle findings — recommend clinical correlation"

    # Urgency logic (matching DermaDefect pattern)
    abn_conf  = abn['confidence']
    path_conf = path['confidence']
    top_conf  = max(abn_conf, path_conf)
    if top_conf >= 0.85:
        urgency      = "High"
        urgency_text = "Urgent specialist review indicated within 48 hours."
    elif top_conf >= 0.70:
        urgency      = "Moderate"
        urgency_text = "Radiologist review recommended within 3-5 days."
    else:
        urgency      = "Low"
        urgency_text = "Routine follow-up. Repeat imaging in 6-12 months."

    # Interpret segmentation coverage clinically
    cov = seg['coverage_pct']
    if cov == 0:
        cov_desc = "No abnormal region was delineated by the segmentation model on the image"
    elif cov < 5:
        cov_desc = f"A focal abnormal region covering {cov:.2f}% of the image area was delineated on the mammogram"
    elif cov < 15:
        cov_desc = f"A regional abnormal area covering {cov:.2f}% of the image area was delineated on the mammogram"
    else:
        cov_desc = f"A diffuse abnormal region covering {cov:.2f}% of the image area was delineated on the mammogram"

    # Patient context block
    p_name = 'the patient'
    if patient_info:
        p_name = patient_info.get('patient_name') or 'the patient'
        patient_block = f"""
PATIENT INFORMATION:
- Patient Name       : {patient_info.get('patient_name', 'Not provided')}
- Patient ID         : {patient_info.get('patient_id', 'Not provided')}
- Referring Physician: {patient_info.get('referring_physician', 'Not provided')}
- Examination Date   : {patient_info.get('exam_date', 'Not provided')}
- Clinical Notes     : {patient_info.get('clinical_notes', 'None')}
"""
    else:
        patient_block = "\nPATIENT INFORMATION: Not provided\n"

    abn_conf_pct  = round(abn_conf  * 100)
    path_conf_pct = round(path_conf * 100)

    return f"""Perform a clinical visual analysis of this mammogram and return a fully structured JSON clinical report.
{patient_block}
VLM DIRECT VISUAL OBSERVATIONS & QUANTITATIVE MEASUREMENTS:
- Visualized Abnormality type        : {abn['label'].upper()} ({conf_level(abn_conf)}, {abn_conf_pct}% visual certainty)
- Visual Pathology Classification    : {path['label'].upper()} ({conf_level(path_conf)}, {path_conf_pct}% visual certainty)
- Visual Mass Likelihood             : {abn['probabilities'].get('mass', 0)*100:.1f}%
- Visual Calcification Likelihood    : {abn['probabilities'].get('calcification', 0)*100:.1f}%
- Benign Visual Features Probability : {path['probabilities'].get('benign', 0)*100:.1f}%
- Malignant Visual Features Probability: {path['probabilities'].get('malignant', 0)*100:.1f}%

IMAGE SEGMENTATION & REGION OF INTEREST:
- {cov_desc}
- Visual Attention Mask: {"delineated and visually highlighted on the mammogram" if cov > 0 else "no distinct visual region segmented"}

PRE-COMPUTED TRIAGE:
  Urgency level   : {urgency}
  Urgency guidance: {urgency_text}

YOUR TASK — return ONLY a valid JSON object with EXACTLY these keys:

{{
  "sections": {{
    "clinical indication": "<2-4 sentence clinical indication section — reference {p_name} explicitly>",
    "technique": "<2-4 sentence mammography technique description>",
    "findings": "<2-4 sentence findings — describe visual morphological features, densities, region coverage clinically. Reference {abn_conf_pct}% AI confidence>",
    "impression": "<2-4 sentence clinical impression — reference {path['label']} and {abn['label']}>",
    "recommendation": "<2-4 sentence recommendation>",
    "disclaimer": "This assessment is VLM-assisted mammography analysis. Clinical correlation and qualified radiologist verification is required before any clinical decision."
  }},
  "urgency": "{urgency}",
  "urgency_text": "{urgency_text}",
  "referral_note": "<A detailed multi-paragraph clinical referral note. Include bolded sections: **Clinical Indication:**, **Technique:**, **Findings:**, **Impression:**, **Recommendation:**. Name {p_name} explicitly. Reference the {abn_conf_pct}% abnormality and {path_conf_pct}% pathology confidence scores. Describe the mammogram's visual features (density, margins, microcalcifications, architectural distortion as relevant to {abn['label']}). End with next step.>",
  "treatment_notes": [
    "<Specific clinical action 1 for {p_name} given {abn['label']} finding>",
    "<Specific clinical action 2 — imaging or biopsy recommendation>",
    "<Specific clinical action 3 — follow-up or specialist referral instruction>"
  ],
  "therapy_regimen": {{
    "medication": "<First-line pharmacological or procedural intervention if applicable, or 'Pending specialist assessment' if biopsy/imaging required first>",
    "dosage": "<Dosage and frequency, or 'N/A — specialist assessment required'>",
    "duration": "<Treatment duration or monitoring interval>",
    "instructions": "<Specific clinical instructions for {p_name}>"
  }},
  "patient_handout": {{
    "dos": [
      "<Specific action {p_name} must take — related to {abn['label']}>",
      "<Second specific action>",
      "<Third specific action>",
      "<Fourth specific action>"
    ],
    "donts": [
      "<What {p_name} must strictly avoid>",
      "<Second avoidance>",
      "<Third avoidance>"
    ]
  }},
  "recommended_action": "<One clear sentence: name a specific clinical facility type, the procedure/assessment needed, and the timeframe based on {urgency} urgency>"
}}

RULES:
- Return raw JSON only. Any text outside the JSON breaks the parser.
- treatment_notes must be exactly 3 items. Each must reference {p_name} or their specific finding.
- therapy_regimen must be populated even if recommending specialist assessment.
- patient_handout dos and donts must be specific to mammography findings of {abn['label']} — not generic health advice.
- All sections in "sections" must use formal clinical register, 2-4 sentences each.
- Do not change urgency or urgency_text from the pre-computed values above.
"""


def generate_clinical_report(predictions: dict, patient_info: dict = None) -> dict:
    """
    Generates a structured clinical report via Groq LLM.
    Returns DermaDefect-compatible fields: sections, referral_note,
    treatment_notes, therapy_regimen, patient_handout, recommended_action,
    urgency, urgency_text, plus model_used and patient_info.
    """
    client = Groq(api_key=settings.GROQ_API_KEY)

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": build_prompt(predictions, patient_info)},
            ],
            temperature=0.2,
            max_tokens=2000,
        )

        raw = response.choices[0].message.content.strip()

        # Strip accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        if raw.endswith("```"):
            raw = raw[:-3].strip()

        result = json.loads(raw)

        # Ensure sections dict always exists
        if 'sections' not in result or not isinstance(result['sections'], dict):
            result['sections'] = {'full_report': raw}

        # Post-process referral_note: ensure real newlines
        if isinstance(result.get('referral_note'), str):
            result['referral_note'] = (
                result['referral_note']
                .replace('\\n\\n', '\n\n')
                .replace('\\n', '\n')
            )

        result['model_used']   = response.model
        result['patient_info'] = patient_info or {}

        logger.info(
            "Groq structured response OK — urgency: %s", result.get('urgency')
        )
        return result

    except json.JSONDecodeError as exc:
        logger.error("Groq returned invalid JSON: %s", exc)
        return _plain_fallback(predictions, patient_info)
    except Exception as exc:
        logger.error("Groq call failed: %s", exc)
        return _plain_fallback(predictions, patient_info)


def _plain_fallback(predictions: dict, patient_info: dict = None) -> dict:
    """Fallback when Groq is unavailable — returns minimal structured report."""
    abn  = predictions['abnormality']
    path = predictions['pathology']
    seg  = predictions['segmentation']
    p_name = (patient_info or {}).get('patient_name') or 'the patient'

    abn_pct  = round(abn['confidence']  * 100)
    path_pct = round(path['confidence'] * 100)

    return {
        'sections': {
            'clinical indication': f"Screening mammography submitted for AI-assisted analysis for {p_name}.",
            'technique': "Digital mammography processed through the DeepMammo deep learning inference pipeline.",
            'findings': (
                f"Visual analysis identifies {abn['label']} characteristics ({abn_pct}% confidence) "
                f"with {path['label']} pathology features ({path_pct}% confidence). "
                f"Segmentation coverage: {seg['coverage_pct']:.2f}% of image area."
            ),
            'impression': (
                f"AI-assisted analysis suggests {abn['label']} with {path['label']} pathology. "
                "Radiologist correlation required."
            ),
            'recommendation': "Clinical correlation and specialist review recommended.",
            'disclaimer': (
                "This is an AI-assisted analysis. Radiologist verification required "
                "before any clinical decision."
            ),
        },
        'referral_note': (
            f"**Clinical Indication:** Mammographic screening for {p_name}.\n\n"
            f"**Findings:** DeepMammo identifies {abn['label']} ({abn_pct}%) with "
            f"{path['label']} features ({path_pct}%). Coverage: {seg['coverage_pct']:.2f}%.\n\n"
            "**Recommendation:** Radiologist review required."
        ),
        'urgency': 'High' if abn['confidence'] >= 0.85 else 'Moderate' if abn['confidence'] >= 0.70 else 'Low',
        'urgency_text': 'Specialist review required.',
        'treatment_notes': [
            f"Arrange urgent radiologist review for {p_name}.",
            "Correlate AI findings with clinical examination and patient history.",
            "Consider biopsy or additional imaging as directed by radiologist.",
        ],
        'therapy_regimen': {
            'medication': 'Pending specialist assessment',
            'dosage': 'N/A',
            'duration': 'Pending specialist recommendation',
            'instructions': f"Ensure {p_name} attends follow-up appointment promptly.",
        },
        'patient_handout': {
            'dos': [
                "Attend your specialist follow-up appointment as scheduled.",
                "Bring all previous mammography films and reports to your appointment.",
                "Report any new symptoms (pain, lumps, skin changes) immediately.",
                "Follow your referring physician's instructions carefully.",
            ],
            'donts': [
                "Do not delay seeking specialist review.",
                "Do not self-diagnose based on AI findings alone.",
                "Do not miss follow-up imaging appointments.",
            ],
        },
        'recommended_action': (
            "Refer to a hospital radiology or breast oncology unit for specialist review "
            "and further imaging or biopsy as clinically indicated."
        ),
        'model_used': 'fallback',
        'patient_info': patient_info or {},
    }


def _parse_sections(text: str) -> dict:
    """Legacy parser — kept for backward compatibility."""
    section_keys = [
        'CLINICAL INDICATION',
        'TECHNIQUE',
        'FINDINGS',
        'IMPRESSION',
        'RECOMMENDATION',
        'DISCLAIMER',
    ]

    sections = {}
    lines    = text.split('\n')
    current  = None
    buffer   = []

    for line in lines:
        clean   = line.strip().lstrip('0123456789.').strip().lstrip('*').strip()
        upper   = clean.upper().rstrip(':').rstrip('.')
        matched = next((k for k in section_keys if upper == k or upper.startswith(k)), None)

        if matched:
            if current and buffer:
                sections[current.lower()] = ' '.join(buffer).strip()
            current = matched
            buffer  = []
        elif current and line.strip():
            buffer.append(line.strip().strip('*'))

    if current and buffer:
        sections[current.lower()] = ' '.join(buffer).strip()

    return sections if sections else {'full_report': text}
