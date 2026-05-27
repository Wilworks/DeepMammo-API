import io
import base64
import re
from datetime import datetime
import qrcode

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle, Image as RLImage, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

PAGE_W, PAGE_H = A4
MARGIN = 2 * cm

# DeepMammo Clinical Tech Branding Colors (Navy Accent Match)
PURPLE       = colors.HexColor('#082F49') # Primary Navy
LIGHT_BLUE   = colors.HexColor('#F1F5F9') # Slate Light Accent
DARK         = colors.HexColor('#0A1628') # Dark Navy Accent
GRAY         = colors.HexColor('#64748B') # Neutral Slate
LIGHT_GRAY   = colors.HexColor('#F8FAFC') # Subtle Border Canvas

SUCCESS      = colors.HexColor('#10B981') # Emerald
DANGER       = colors.HexColor('#D85A30') # Coral/Rose
WARNING      = colors.HexColor('#EF9F27') # Amber


def _markdown_to_rl(text: str) -> str:
    """Very basic markdown to ReportLab HTML conversion."""
    if not text:
        return ""
    # Convert **bold** to <b>bold</b>
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    # Convert newlines
    text = text.replace('\n', '<br/>')
    return text


def build_pdf(predictions: dict, clinical_report: dict, images: dict) -> str:
    """
    Builds a professional clinical PDF report matching the DermaDefect layout structure.
    Returns base64-encoded PDF string.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=MARGIN,
    )

    styles = _build_styles()
    story  = []

    patient = clinical_report.get('patient_info', {})
    abn     = predictions['abnormality']
    path    = predictions['pathology']
    seg     = predictions['segmentation']
    case_id = patient.get('patient_id') or datetime.utcnow().strftime('DM-%Y%m%d-%H%M%S')

    # ── Header ──────────────────────────────────────────────────────
    story.append(Paragraph("DeepMammo", styles['title']))
    story.append(Paragraph("AI-Assisted Mammography Analysis Report", styles['subtitle']))
    story.append(Paragraph(
        f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} | Case ID: {case_id}",
        styles['meta']
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=PURPLE, spaceAfter=12))

    # ── Patient Context ──────────────────────────────────────────────
    p_name = patient.get('patient_name') or 'Unknown Patient'
    p_id   = patient.get('patient_id') or 'N/A'
    p_physician = patient.get('referring_physician') or 'N/A'
    story.append(Paragraph(
        f"<b>Patient:</b> {p_name} &nbsp;|&nbsp; <b>Patient ID:</b> {p_id} &nbsp;|&nbsp; <b>Referring Physician:</b> {p_physician}",
        styles['body']
    ))
    story.append(Spacer(1, 12))

    # ── Prediction summary table ─────────────────────────────────────
    story.append(Paragraph("AI Triage Summary", styles['section']))
    story.append(Spacer(1, 6))

    def urgency_label(c):
        if c >= 0.85: return "HIGH"
        if c >= 0.70: return "MODERATE"
        return "LOW"

    summary_data = [
        ['Primary Finding', 'Confidence', 'Urgency Level'],
        [
            f"Abnormality: {abn['label'].title()}",
            f"{abn['confidence']*100:.1f}%",
            urgency_label(abn['confidence']),
        ],
        [
            f"Pathology: {path['label'].title()}",
            f"{path['confidence']*100:.1f}%",
            urgency_label(path['confidence']),
        ],
        [
            f"Region Coverage: {seg['coverage_pct']:.2f}% of image",
            '—',
            'SEGMENTATION',
        ],
    ]

    table = Table(summary_data, colWidths=[7*cm, 4*cm, 5*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND',  (0,0), (-1,0), PURPLE),
        ('TEXTCOLOR',   (0,0), (-1,0), colors.white),
        ('FONTNAME',    (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',    (0,0), (-1,0), 10),
        ('BACKGROUND',  (0,1), (-1,-1), LIGHT_BLUE),
        ('FONTSIZE',    (0,1), (-1,-1), 10),
        ('ALIGN',       (0,0), (-1,-1), 'CENTER'),
        ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
        ('ROWHEIGHT',   (0,0), (-1,-1), 22),
        ('GRID',        (0,0), (-1,-1), 0.5, PURPLE),
    ]))
    story.append(table)
    story.append(Spacer(1, 16))

    # ── Visual Analysis Images ────────────────────────────────────────
    story.append(Paragraph("Visual Analysis", styles['section']))
    story.append(Spacer(1, 6))

    # Primary 2-up: Original Scan + AI Saliency Map (matching DermaDefect pattern)
    primary_row    = []
    primary_labels = []

    for key, label in [
        ('original_b64', 'Original Mammography Scan'),
        ('gradcam_b64',  'AI Saliency Map'),
    ]:
        b64 = images.get(key)
        if b64:
            if b64.startswith("data:"):
                b64 = b64.split(",")[1]
            try:
                img_buf = io.BytesIO(base64.b64decode(b64))
                rl_img  = RLImage(img_buf, width=6*cm, height=6*cm)
                primary_row.append(rl_img)
                primary_labels.append(label)
            except Exception:
                pass

    if primary_row:
        img_table = Table(
            [primary_row, [Paragraph(l, styles['img_label']) for l in primary_labels]],
            colWidths=[6.5*cm] * len(primary_row)
        )
        img_table.setStyle(TableStyle([
            ('ALIGN',  (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        story.append(img_table)
        story.append(Spacer(1, 10))

    # Secondary strip: Segmentation Mask + Overlay
    secondary_row    = []
    secondary_labels = []

    for key, label in [
        ('mask_b64',    'Segmentation Mask'),
        ('overlay_b64', 'Mask Overlay'),
    ]:
        b64 = images.get(key)
        if b64:
            if b64.startswith("data:"):
                b64 = b64.split(",")[1]
            try:
                img_buf = io.BytesIO(base64.b64decode(b64))
                rl_img  = RLImage(img_buf, width=4.5*cm, height=4.5*cm)
                secondary_row.append(rl_img)
                secondary_labels.append(label)
            except Exception:
                pass

    if secondary_row:
        sec_table = Table(
            [secondary_row, [Paragraph(l, styles['img_label']) for l in secondary_labels]],
            colWidths=[5*cm] * len(secondary_row)
        )
        sec_table.setStyle(TableStyle([
            ('ALIGN',  (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        story.append(sec_table)
        story.append(Spacer(1, 16))


    # ── Clinical report sections ──────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=GRAY, spaceAfter=8))
    story.append(Paragraph("AI Clinical Evaluation", styles['section']))
    story.append(Spacer(1, 6))

    sections = clinical_report.get('sections', {})
    section_order = [
        ('clinical indication', 'Clinical Indication'),
        ('technique',           'Technique'),
        ('findings',            'Findings'),
        ('impression',          'Impression'),
        ('recommendation',      'Recommendation'),
        ('disclaimer',          'Disclaimer'),
        ('full_report',         'Report'),
    ]

    for key, display in section_order:
        text = sections.get(key)
        if text:
            story.append(Paragraph(display, styles['subsection']))
            story.append(Paragraph(_markdown_to_rl(text), styles['body']))
            story.append(Spacer(1, 10))

    # ── Footer / Signature ─────────────────────────────────────────────
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=0.5, color=GRAY, spaceBefore=12, spaceAfter=12))

    # Generate QR Code
    qr = qrcode.QRCode(box_size=3, border=1)
    qr.add_data(f"https://secure.deepmammo.app/verify/{case_id}")
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    qr_buf = io.BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_buf.seek(0)
    rl_qr = RLImage(qr_buf, width=2.2*cm, height=2.2*cm)
    
    reviewer_name = patient.get('referring_physician') or 'Attending Reviewer, MD'
    
    sig_cell = Paragraph(
        f"<font color='#64748B' size=8><i>Digital Verified Signature</i></font><br/><br/>"
        f"<font size=12 color='#0A1628'><b>{reviewer_name}</b></font><br/>"
        f"<font color='#64748B'>________________________________________</font>",
        styles['body']
    )
    
    qr_text = Paragraph(
        "<font size=7 color='#64748B'><b>Verify on<br/>DeepMammo Secure<br/>Web Cloud</b></font>",
        styles['body']
    )
    
    sig_table = Table([[sig_cell, rl_qr, qr_text]], colWidths=[10*cm, 2.7*cm, 4.7*cm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (0,0), 'LEFT'),
        ('ALIGN', (1,0), (2,0), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('BOX',           (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('BACKGROUND',    (0,0), (-1,-1), LIGHT_BLUE),
        ('TOPPADDING',    (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('LEFTPADDING',   (0,0), (-1,-1), 12),
        ('RIGHTPADDING',  (-1,0), (-1,-1), 12),
    ]))
    story.append(sig_table)
    
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "Disclaimer: This assessment is AI-assisted using the advanced <b>DeepMammo</b> neural networks "
        "developed by <b>Wilfred Ayine</b>. It is intended to support, not replace, clinical judgment "
        "by a qualified healthcare professional.",
        styles['disclaimer']
    ))

    doc.build(story)
    return base64.b64encode(buf.getvalue()).decode('utf-8')


def _build_styles() -> dict:
    base = getSampleStyleSheet()
    return {
        'title': ParagraphStyle('title',
            fontSize=22, fontName='Helvetica-Bold',
            textColor=PURPLE, alignment=TA_CENTER, spaceAfter=4, leading=26),
        'subtitle': ParagraphStyle('subtitle',
            fontSize=11, fontName='Helvetica',
            textColor=DARK, alignment=TA_CENTER, spaceAfter=2, leading=14),
        'meta': ParagraphStyle('meta',
            fontSize=8, fontName='Helvetica',
            textColor=GRAY, alignment=TA_CENTER, spaceAfter=10, leading=10),
        'section': ParagraphStyle('section',
            fontSize=13, fontName='Helvetica-Bold',
            textColor=PURPLE, spaceAfter=8, leading=16),
        'subsection': ParagraphStyle('subsection',
            fontSize=11, fontName='Helvetica-Bold',
            textColor=DARK, spaceAfter=4, leading=14),
        'body': ParagraphStyle('body',
            fontSize=10, fontName='Helvetica',
            textColor=DARK, leading=14, alignment=TA_LEFT),
        'body_bullet': ParagraphStyle('body_bullet',
            fontSize=10, fontName='Helvetica',
            textColor=DARK, leading=14, alignment=TA_LEFT, leftIndent=12),
        'img_label': ParagraphStyle('img_label',
            fontSize=8, fontName='Helvetica-Bold',
            textColor=GRAY, alignment=TA_CENTER),
        'disclaimer': ParagraphStyle('disclaimer',
            fontSize=8, fontName='Helvetica-Oblique',
            textColor=GRAY, alignment=TA_CENTER),
    }
