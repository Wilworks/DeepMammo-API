from groq import Groq
from django.conf import settings


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
- Each section must be 2-4 sentences, formal, no bullet points inside sections.
- Always close with a disclaimer that this is a VLM-assisted analysis requiring radiologist verification."""


def build_prompt(predictions: dict, patient_info: dict = None) -> str:
    abn  = predictions['abnormality']
    path = predictions['pathology']
    seg  = predictions['segmentation']

    # Interpret confidence narratively
    def conf_level(c):
        if c >= 0.85: return "high visual certainty"
        if c >= 0.70: return "moderate certainty"
        return "borderline/subtle findings — recommend clinical correlation"

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

    return f"""Perform a clinical visual analysis and generate a structured mammography report based on your direct vision-language evaluation of the mammogram image:
{patient_block}
VLM DIRECT VISUAL OBSERVATIONS & QUANTITATIVE MEASUREMENTS:
- Visualized Abnormality type : {abn['label'].upper()} ({conf_level(abn['confidence'])}, {abn['confidence']*100:.1f}% visual certainty)
- Visual Pathology Classification : {path['label'].upper()} ({conf_level(path['confidence'])}, {path['confidence']*100:.1f}% visual certainty)
- Visual Mass Likelihood    : {abn['probabilities'].get('mass', 0)*100:.1f}%
- Visual Calcification Likelihood: {abn['probabilities'].get('calcification', 0)*100:.1f}%
- Benign Visual Features Probability: {path['probabilities'].get('benign', 0)*100:.1f}%
- Malignant Visual Features Probability: {path['probabilities'].get('malignant', 0)*100:.1f}%

IMAGE SEGMENTATION & REGION OF INTEREST:
- {cov_desc}
- Visual Attention Mask: {"delineated and visually highlighted on the mammogram" if cov > 0 else "no distinct visual region segmented"}

Write the report sections so they read as a direct visual assessment of the mammogram itself, emphasizing visual features, textures, densities, and the highlighted region of interest.

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
