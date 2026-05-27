import io
import base64
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle, Image as RLImage,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
from reportlab.platypus.flowables import HRFlowable


MARGIN = 1.8 * cm

# ── Colour palette ────────────────────────────────────────────────────
PURPLE       = colors.HexColor('#082F49') # Maps to Deep Navy
PURPLE_LIGHT = colors.HexColor('#F1F5F9') # Slate Light Accent
PURPLE_DARK  = colors.HexColor('#0A1628') # Dark Navy Accent
DARK         = PURPLE_DARK
GRAY         = colors.HexColor('#64748B')
LIGHT_GRAY   = colors.HexColor('#F8FAFC')

WHITE        = colors.white
SUCCESS      = colors.HexColor('#10B981') # Emerald
DANGER       = colors.HexColor('#D85A30') # Coral/Rose
WARNING      = colors.HexColor('#EF9F27') # Amber
INFO         = colors.HexColor('#082F49')


def build_pdf(predictions: dict, clinical_report: dict, images: dict) -> str:
    """
    Builds a professional clinical PDF report.

    Args:
        predictions    : postprocess() output dict
        clinical_report: groq_client output dict (includes patient_info)
        images         : dict — mask_b64, overlay_b64, gradcam_b64

    Returns:
        base64-encoded PDF string
    """
    buf  = io.BytesIO()
    doc  = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=1.2*cm, bottomMargin=1.5*cm,
    )

    styles  = _build_styles()
    story   = []
    patient = clinical_report.get('patient_info', {})
    abn     = predictions['abnormality']
    path    = predictions['pathology']
    seg     = predictions['segmentation']

    # ── 1. Header bar ────────────────────────────────────────────────
    story += _header(styles, patient)

    # ── 2. Patient info block ────────────────────────────────────────
    if any(patient.values()):
        story += _patient_block(styles, patient)

    # ── 3. Prediction summary ────────────────────────────────────────
    story += _prediction_table(styles, abn, path, seg)

    # ── 4. Visual analysis ───────────────────────────────────────────
    story += _image_section(styles, images)

    # ── 5. Clinical report ───────────────────────────────────────────
    story += _clinical_report_section(styles, clinical_report)

    # ── 5.5. Attending Signature Stamp Box ───────────────────────────
    story += _signature_block(styles)

    # ── 6. Footer ────────────────────────────────────────────────────
    story += _footer(styles, clinical_report)

    doc.build(story)
    return base64.b64encode(buf.getvalue()).decode('utf-8')



# ── Section builders ──────────────────────────────────────────────────

def _header(styles, patient):
    date_str = datetime.utcnow().strftime('%B %d, %Y  %H:%M UTC')

    # Two-column header: brand left, date right
    header_table = Table(
        [[
            Paragraph("<b>DeepMammo</b>", styles['brand']),
            Paragraph(f"Report Date: {date_str}", styles['header_date']),
        ]],
        colWidths=['60%', '40%'],
    )
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), PURPLE),
        ('VALIGN',     (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 12),
        ('BOTTOMPADDING', (0,0), (-1,-1), 12),
        ('LEFTPADDING',  (0,0), (0,-1), 16),
        ('RIGHTPADDING', (-1,0), (-1,-1), 16),
    ]))

    subtitle = Paragraph(
        "AI-Assisted Mammography Analysis Report",
        styles['header_sub']
    )

    return [header_table, subtitle, Spacer(1, 14)]


def _patient_block(styles, patient):
    items = []

    rows = [
        ['Patient Name',       patient.get('patient_name', '—')],
        ['Patient ID',         patient.get('patient_id', '—')],
        ['Referring Physician',patient.get('referring_physician', '—')],
        ['Examination Date',   patient.get('exam_date', '—')],
    ]
    if patient.get('clinical_notes'):
        rows.append(['Clinical Notes', patient['clinical_notes']])

    # Build two-per-row layout
    flat = []
    for i in range(0, len(rows), 2):
        left  = rows[i]
        right = rows[i+1] if i+1 < len(rows) else ['', '']
        flat.append([
            Paragraph(left[0],  styles['info_label']),
            Paragraph(left[1],  styles['info_value']),
            Paragraph(right[0], styles['info_label']),
            Paragraph(right[1], styles['info_value']),
        ])

    pt = Table(flat, colWidths=[3.5*cm, 6*cm, 3.5*cm, 6*cm])
    pt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), LIGHT_GRAY),
        ('GRID',       (0,0), (-1,-1), 0.3, colors.HexColor('#e2e0f5')),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING',  (0,0), (-1,-1), 8),
        ('VALIGN',     (0,0), (-1,-1), 'MIDDLE'),
    ]))

    items.append(Paragraph("Patient Information", styles['section']))
    items.append(Spacer(1, 5))
    items.append(pt)
    items.append(Spacer(1, 14))
    return items


def _prediction_table(styles, abn, path, seg):
    items = []
    items.append(Paragraph("AI Prediction Summary", styles['section']))
    items.append(Spacer(1, 5))

    def conf_color(c):
        if c >= 0.85: return SUCCESS
        if c >= 0.70: return WARNING
        return DANGER

    def conf_label(c):
        if c >= 0.85: return "High"
        if c >= 0.70: return "Moderate"
        return "Borderline"

    # Header row
    data = [[
        Paragraph('Finding',    styles['th']),
        Paragraph('Result',     styles['th']),
        Paragraph('Confidence', styles['th']),
        Paragraph('Level',      styles['th']),
    ]]

    # Abnormality row
    data.append([
        Paragraph('Abnormality Type', styles['td']),
        Paragraph(f"<b>{abn['label'].title()}</b>", styles['td']),
        Paragraph(f"{abn['confidence']*100:.1f}%", styles['td_center']),
        Paragraph(conf_label(abn['confidence']), styles['td_center']),
    ])

    # Pathology row
    path_color = DANGER if path['label'] == 'malignant' else SUCCESS
    data.append([
        Paragraph('Pathology', styles['td']),
        Paragraph(f"<b><font color='#{path_color.hexval()[2:]}'>{path['label'].title()}</font></b>", styles['td']),
        Paragraph(f"{path['confidence']*100:.1f}%", styles['td_center']),
        Paragraph(conf_label(path['confidence']), styles['td_center']),
    ])

    # Segmentation row
    data.append([
        Paragraph('Region Coverage', styles['td']),
        Paragraph(f"{seg['coverage_pct']:.2f}% of image", styles['td']),
        Paragraph('—', styles['td_center']),
        Paragraph('Segmentation', styles['td_center']),
    ])

    t = Table(data, colWidths=[4.5*cm, 5*cm, 3.5*cm, 3.5*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,0), PURPLE),
        ('TEXTCOLOR',     (0,0), (-1,0), WHITE),
        ('ROWBACKGROUNDS',(0,1), (-1,-1), [WHITE, PURPLE_LIGHT]),
        ('GRID',          (0,0), (-1,-1), 0.4, colors.HexColor('#AFA9EC')),
        ('TOPPADDING',    (0,0), (-1,-1), 7),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('LEFTPADDING',   (0,0), (-1,-1), 8),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
    ]))

    items.append(t)
    items.append(Spacer(1, 14))
    return items


def _image_section(styles, images):
    items = []
    items.append(Paragraph("Visual Analysis", styles['section']))
    items.append(Spacer(1, 5))

    img_row    = []
    img_labels = []

    for key, label in [
        ('mask_b64',    'Segmentation Mask'),
        ('overlay_b64', 'Mask Overlay'),
        ('gradcam_b64', 'Saliency Map'),
    ]:
        b64 = images.get(key)
        if b64:
            buf = io.BytesIO(base64.b64decode(b64))
            img_row.append(RLImage(buf, width=5*cm, height=5*cm))
            img_labels.append(Paragraph(label, styles['img_label']))

    if img_row:
        n   = len(img_row)
        col = (A4[0] - 2*MARGIN) / n
        img_tbl = Table(
            [img_row, img_labels],
            colWidths=[col] * n
        )
        img_tbl.setStyle(TableStyle([
            ('ALIGN',         (0,0), (-1,-1), 'CENTER'),
            ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
            ('BACKGROUND',    (0,1), (-1,1), LIGHT_GRAY),
            ('TOPPADDING',    (0,1), (-1,1), 4),
            ('BOTTOMPADDING', (0,1), (-1,1), 4),
            ('BOX',           (0,0), (-1,-1), 0.4, colors.HexColor('#e2e0f5')),
            ('INNERGRID',     (0,0), (-1,-1), 0.4, colors.HexColor('#e2e0f5')),
        ]))
        items.append(img_tbl)

    items.append(Spacer(1, 14))
    return items


def _clinical_report_section(styles, clinical_report):
    items = []
    items.append(HRFlowable(width="100%", thickness=0.5, color=GRAY, spaceAfter=8))
    items.append(Paragraph("Clinical Report", styles['section']))
    items.append(Spacer(1, 4))

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
            block = KeepTogether([
                Table(
                    [[Paragraph(display, styles['report_heading'])]],
                    colWidths=['100%'],
                    style=TableStyle([
                        ('BACKGROUND',    (0,0), (-1,-1), PURPLE_LIGHT),
                        ('LEFTPADDING',   (0,0), (-1,-1), 8),
                        ('TOPPADDING',    (0,0), (-1,-1), 4),
                        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                        ('LINEAFTER',     (0,0), (0,-1), 3, PURPLE),
                    ])
                ),
                Spacer(1, 3),
                Paragraph(text, styles['body']),
                Spacer(1, 10),
            ])
            items.append(block)

    return items


def _signature_block(styles):
    sig_table = Table(
        [[
            Paragraph("<b>Attending Reviewer Signature:</b>", styles['info_label']),
            Paragraph("<b>Diagnostic stamp:</b>", styles['info_label'])
        ],
        [
            Paragraph("<br/><br/>________________________________________<br/>Clinical Analyst, MD", styles['info_value']),
            Paragraph("<br/><br/>[ ONLINE SYSTEM VERIFICATION STAMP ]", styles['info_value'])
        ]],
        colWidths=[10*cm, 7.4*cm]
    )
    sig_table.setStyle(TableStyle([
        ('BOX',           (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('BACKGROUND',    (0,0), (-1,-1), LIGHT_GRAY),
        ('TOPPADDING',    (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('LEFTPADDING',   (0,0), (-1,-1), 12),
        ('RIGHTPADDING',  (-1,0), (-1,-1), 12),
        ('LINEBELOW',     (0,0), (-1,0), 0.5, colors.HexColor('#E2E8F0')),
    ]))
    return [Spacer(1, 10), sig_table, Spacer(1, 10)]


def _footer(styles, clinical_report):
    items = []

    items.append(Spacer(1, 8))
    items.append(HRFlowable(width="100%", thickness=0.5, color=GRAY))

    footer_table = Table(
        [[
            Paragraph(
                "Generated by <b>DeepMammo AI System</b><br/>"
                "Developed by <b>Wilfred Ayine</b> · AI Engineer (in training)",
                styles['footer_left']
            ),
            Paragraph(
                f"Model: {clinical_report.get('model_used', 'Groq LLM')}<br/>"
                f"DeepMammo v1.0 · {datetime.utcnow().strftime('%Y')}",
                styles['footer_right']
            ),
        ]],
        colWidths=['60%', '40%'],
    )
    footer_table.setStyle(TableStyle([
        ('VALIGN',        (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING',    (0,0), (-1,-1), 6),
        ('LEFTPADDING',   (0,0), (0,-1), 0),
        ('RIGHTPADDING',  (-1,0), (-1,-1), 0),
    ]))

    items.append(footer_table)
    items.append(Spacer(1, 6))
    items.append(Paragraph(
        "⚠ This report is AI-generated and has not been reviewed by a licensed radiologist. "
        "It must not be used as the sole basis for any clinical decision. "
        "Always consult a qualified medical professional.",
        styles['disclaimer']
    ))
    return items


# ── Styles ────────────────────────────────────────────────────────────

def _build_styles() -> dict:
    return {
        'brand': ParagraphStyle('brand',
            fontSize=18, fontName='Helvetica-Bold',
            textColor=WHITE),
        'header_date': ParagraphStyle('header_date',
            fontSize=8, fontName='Helvetica',
            textColor=colors.HexColor('#d0cef5'),
            alignment=TA_RIGHT),
        'header_sub': ParagraphStyle('header_sub',
            fontSize=9, fontName='Helvetica',
            textColor=GRAY, alignment=TA_CENTER,
            spaceBefore=5, spaceAfter=4),
        'section': ParagraphStyle('section',
            fontSize=11, fontName='Helvetica-Bold',
            textColor=PURPLE, spaceAfter=4, spaceBefore=4),
        'info_label': ParagraphStyle('info_label',
            fontSize=8, fontName='Helvetica-Bold',
            textColor=GRAY),
        'info_value': ParagraphStyle('info_value',
            fontSize=9, fontName='Helvetica',
            textColor=DARK),
        'th': ParagraphStyle('th',
            fontSize=9, fontName='Helvetica-Bold',
            textColor=WHITE, alignment=TA_CENTER),
        'td': ParagraphStyle('td',
            fontSize=9, fontName='Helvetica',
            textColor=DARK),
        'td_center': ParagraphStyle('td_center',
            fontSize=9, fontName='Helvetica',
            textColor=DARK, alignment=TA_CENTER),
        'report_heading': ParagraphStyle('report_heading',
            fontSize=9, fontName='Helvetica-Bold',
            textColor=PURPLE),
        'body': ParagraphStyle('body',
            fontSize=9, fontName='Helvetica',
            textColor=DARK, leading=14, alignment=TA_JUSTIFY),
        'img_label': ParagraphStyle('img_label',
            fontSize=8, fontName='Helvetica',
            textColor=GRAY, alignment=TA_CENTER),
        'footer_left': ParagraphStyle('footer_left',
            fontSize=7.5, fontName='Helvetica',
            textColor=GRAY, leading=11),
        'footer_right': ParagraphStyle('footer_right',
            fontSize=7.5, fontName='Helvetica',
            textColor=GRAY, alignment=TA_RIGHT, leading=11),
        'disclaimer': ParagraphStyle('disclaimer',
            fontSize=7.5, fontName='Helvetica-Oblique',
            textColor=GRAY, alignment=TA_CENTER,
            borderColor=colors.HexColor('#e2e0f5'),
            borderWidth=0.5, borderPadding=5),
    }
