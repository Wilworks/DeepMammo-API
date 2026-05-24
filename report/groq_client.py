from groq import Groq
from django.conf import settings


SYSTEM_PROMPT = """You are a senior radiologist generating structured clinical reports 
for AI-assisted mammography analysis. Write in formal, precise clinical language as 
if authoring an official radiology report. Be evidence-based and objective.

Rules:
- Never make a definitive diagnosis — report AI findings and recommend clinical correlation
- Interpret confidence levels: >85% = high confidence, 70-85% = moderate, <70% = borderline
- Describe segmentation coverage clinically: <5% = focal, 5-15% = regional, >15% = diffuse
- Each section must be 2-4 sentences, formal, no bullet points inside sections
- Always close with a disclaimer that this is AI-generated and requires radiologist verification"""


def build_prompt(predictions: dict, patient_info: dict = None) -> str:
    abn  = predictions['abnormality']
    path = predictions['pathology']
    seg  = predictions['segmentation']

    # Interpret confidence narratively
    def conf_level(c):
        if c >= 0.85: return "high confidence"
        if c >= 0.70: return "moderate confidence"
        return "borderline confidence — recommend clinical correlation"

    # Interpret segmentation coverage clinically
    cov = seg['coverage_pct']
    if cov == 0:
        cov_desc = "No abnormal region was delineated by the segmentation model"
    elif cov < 5:
        cov_desc = f"A focal abnormal region covering {cov:.2f}% of the image area was delineated"
    elif cov < 15:
        cov_desc = f"A regional abnormal area covering {cov:.2f}% of the image area was delineated"
    else:
        cov_desc = f"A diffuse abnormal region covering {cov:.2f}% of the image area was delineated"

    # Patient context block
    if patient_info:
        patient_block = f"""
PATIENT INFORMATION:
- Patient Name     : {patient_info.get('patient_name', 'Not provided')}
- Patient ID       : {patient_info.get('patient_id', 'Not provided')}
- Referring Physician: {patient_info.get('referring_physician', 'Not provided')}
- Examination Date : {patient_info.get('exam_date', 'Not provided')}
- Clinical Notes   : {patient_info.get('clinical_notes', 'None')}
"""
    else:
        patient_block = "\nPATIENT INFORMATION: Not provided\n"

    return f"""Generate a formal structured clinical mammography report for the following AI analysis:
{patient_block}
AI MODEL FINDINGS:
- Abnormality type   : {abn['label'].upper()} ({conf_level(abn['confidence'])}, {abn['confidence']*100:.1f}%)
- Pathology class    : {path['label'].upper()} ({conf_level(path['confidence'])}, {path['confidence']*100:.1f}%)
- Mass probability   : {abn['probabilities'].get('mass', 0)*100:.1f}%
- Calcification prob : {abn['probabilities'].get('calcification', 0)*100:.1f}%
- Benign probability : {path['probabilities'].get('benign', 0)*100:.1f}%
- Malignant prob     : {path['probabilities'].get('malignant', 0)*100:.1f}%

SEGMENTATION:
- {cov_desc}
- Mask status: {"abnormal region present" if cov > 0 else "no region detected"}

Write the report with these exact section headers (use them verbatim):
1. CLINICAL INDICATION
2. TECHNIQUE
3. FINDINGS
4. IMPRESSION
5. RECOMMENDATION
6. DISCLAIMER

Each section: 2-4 sentences. Formal clinical register. Reference the patient name where appropriate."""


def generate_clinical_report(predictions: dict, patient_info: dict = None) -> dict:
    """
    Generates a structured clinical report via Groq LLM.

    Args:
        predictions : postprocess() output dict
        patient_info: optional dict with keys:
                      patient_name, patient_id, referring_physician,
                      exam_date, clinical_notes

    Returns:
        dict with full_text, sections, model_used
    """
    client = Groq(api_key=settings.GROQ_API_KEY)

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",   # 70B for better clinical language
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": build_prompt(predictions, patient_info)},
        ],
        temperature=0.2,    # very low — clinical language must be consistent
        max_tokens=1000,
    )

    report_text = response.choices[0].message.content
    sections    = _parse_sections(report_text)

    return {
        'full_text':   report_text,
        'sections':    sections,
        'model_used':  response.model,
        'patient_info': patient_info or {},
    }


def _parse_sections(text: str) -> dict:
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
        # Strip numbering like "1.", "**", markdown etc
        clean = line.strip().lstrip('0123456789.').strip().lstrip('*').strip()
        upper = clean.upper().rstrip(':').rstrip('.')
        matched = next((k for k in section_keys if upper == k or upper.startswith(k)), None)

        if matched:
            if current and buffer:
                sections[current.lower()] = ' '.join(buffer).strip()
            current = matched
            buffer  = []
        elif current and line.strip():
            # Strip markdown bold from content too
            buffer.append(line.strip().strip('*'))

    if current and buffer:
        sections[current.lower()] = ' '.join(buffer).strip()

    return sections if sections else {'full_report': text}
