import io
import base64
import re
from datetime import datetime
import qrcode

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle, Image as RLImage, HRFlowable,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

PAGE_W, PAGE_H = A4
MARGIN = 1.0 * cm

# ── Brand palette ─────────────────────────────────────────────────────────────
NAVY        = colors.HexColor('#082F49')
TEAL        = colors.HexColor('#1B7A9C')
DARK        = colors.HexColor('#0A1628')
GRAY        = colors.HexColor('#64748B')
MID_GRAY    = colors.HexColor('#CBD5E1')
LIGHT_BLUE  = colors.HexColor('#EBF5FB')
WHITE       = colors.white

C_HIGH  = colors.HexColor('#DC2626')
C_MOD   = colors.HexColor('#D97706')
C_LOW   = colors.HexColor('#16A34A')
C_OK    = colors.HexColor('#16A34A')


def _uc(urgency: str) -> colors.Color:
    u = urgency.lower()
    if 'high' in u:   return C_HIGH
    if 'mod'  in u:   return C_MOD
    return C_LOW


def _md(text: str) -> str:
    """Minimal markdown → ReportLab HTML."""
    if not text:
        return ''
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    return text.replace('\n', '<br/>')


def _img(b64: str, w: float, h: float):
    if not b64:
        return None
    if b64.startswith('data:'):
        b64 = b64.split(',')[1]
    try:
        return RLImage(io.BytesIO(base64.b64decode(b64)), width=w, height=h)
    except Exception:
        return None


def build_pdf(predictions: dict, clinical_report: dict, images: dict) -> str:
    """
    Builds a DermaDetect-style clinical referral card for DeepMammo.
    Layout: header bar → urgency banner → two-column body → signature → footer.
    Returns a base64-encoded PDF string.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=0.8 * cm,  bottomMargin=0.8 * cm,
    )
    S = _styles()
    story = []

    # ── Unpack data ───────────────────────────────────────────────────────────
    patient  = clinical_report.get('patient_info', {})
    abn      = predictions['abnormality']
    path     = predictions['pathology']
    seg      = predictions['segmentation']

    urgency      = clinical_report.get('urgency', 'Moderate')
    urgency_text = clinical_report.get('urgency_text', 'Radiologist review recommended.')
    accent       = _uc(urgency)

    p_name   = patient.get('patient_name')        or 'Unknown Patient'
    p_id     = patient.get('patient_id')          or 'N/A'
    p_phys   = patient.get('referring_physician') or 'N/A'
    p_date   = patient.get('exam_date')           or datetime.utcnow().strftime('%d %b %Y')
    p_notes  = patient.get('clinical_notes')      or '—'
    case_id  = p_id if p_id != 'N/A' else datetime.utcnow().strftime('DM-%Y%m%d-%H%M')

    sections = clinical_report.get('sections', {})
    t_notes  = clinical_report.get('treatment_notes', [])

    AW = PAGE_W - 2 * MARGIN        # available width = 19.0 cm
    LW = 6.6 * cm                   # left column
    GW = 0.4 * cm                   # gap
    RW = AW - LW - GW               # right column = 12.0 cm

    # ═══════════════════════════════════════════════════════════════════════════
    # 1. HEADER BAR
    # ═══════════════════════════════════════════════════════════════════════════
    hdr = Table(
        [[
            Paragraph(
                '<font color="white" size=14><b>DeepMammo</b></font><br/>'
                '<font color="#A8D8EA" size=7>AI-Powered Breast Imaging</font>',
                S['left']
            ),
            Paragraph(
                '<font color="white" size=11><b>MAMMOGRAPHY ANALYSIS REPORT</b></font><br/>'
                f'<font color="#A8D8EA" size=7>REF: {case_id}</font>',
                S['right']
            ),
        ]],
        colWidths=[AW * 0.5, AW * 0.5]
    )
    hdr.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), NAVY),
        ('ALIGN',         (1, 0), (1,  0),  'RIGHT'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING',   (0, 0), (-1, -1), 14),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 14),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 4))

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. URGENCY BANNER
    # ═══════════════════════════════════════════════════════════════════════════
    banner = Table(
        [[Paragraph(
            f'<font color="white"><b>●  {urgency.upper()} — {urgency_text}</b></font>',
            S['center']
        )]],
        colWidths=[AW]
    )
    banner.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), accent),
        ('TOPPADDING',    (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
    ]))
    story.append(banner)
    story.append(Spacer(1, 6))

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. TWO-COLUMN BODY
    # ═══════════════════════════════════════════════════════════════════════════

    # ── LEFT COLUMN ──────────────────────────────────────────────────────────
    def info_tbl(rows: list) -> Table:
        t = Table(rows, colWidths=[2.4 * cm, LW - 2.4 * cm])
        t.setStyle(TableStyle([
            ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING',    (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING',   (0, 0), (-1, -1), 0),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ]))
        return t

    def lbl(text):  return Paragraph(text, S['info_lbl'])
    def val(text):  return Paragraph(str(text), S['info_val'])
    def sec(text):  return Paragraph(text, S['sec_head'])

    L = []   # left column flowables list (each item is a 1-cell row)

    # Patient Information
    L += [
        [sec('PATIENT INFORMATION')],
        [info_tbl([
            [lbl('Full Name'),  val(p_name)],
            [lbl('Patient ID'), val(p_id)],
            [lbl('Date'),       val(p_date)],
        ])],
        [Spacer(1, 4)],
    ]

    # Referring Physician
    L += [
        [sec('REFERRING PHYSICIAN')],
        [info_tbl([
            [lbl('Name'),     val(p_phys)],
            [lbl('Facility'), val('N/A')],
        ])],
        [Spacer(1, 4)],
    ]

    # Refer To
    urgency_short = urgency_text if len(urgency_text) <= 38 else urgency_text[:35] + '...'
    L += [
        [sec('REFER TO')],
        [info_tbl([
            [lbl('Facility'),   val('Breast Specialty Clinic')],
            [lbl('Dept'),       val('Breast Oncology / Radiology')],
            [lbl('Urgency'),    Paragraph(urgency_short,
                                         ParagraphStyle('uv', parent=S['info_val'],
                                                        textColor=accent))],
        ])],
        [Spacer(1, 4)],
    ]

    # Clinical Notes
    L += [
        [sec('CLINICAL NOTES')],
        [Paragraph(f'<i>"{p_notes}"</i>', S['notes'])],
        [Spacer(1, 4)],
    ]

    # Segmentation Results box
    cov = seg.get('coverage_pct', 0)
    cov_str = (
        f'{cov:.2f}% of image (focal)'    if cov < 5  else
        f'{cov:.2f}% of image (regional)' if cov < 15 else
        f'{cov:.2f}% of image (diffuse)'
    )
    seg_inner = Table(
        [
            [Paragraph('<b>REGION COVERAGE</b>', S['box_lbl'])],
            [Paragraph(cov_str, S['box_val'])],
            [Spacer(1, 3)],
            [Paragraph('<b>PATHOLOGY</b>', S['box_lbl'])],
            [Paragraph(path['label'].title(), S['box_val'])],
        ],
        colWidths=[LW - 0.6 * cm]
    )
    seg_inner.setStyle(TableStyle([
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
    ]))
    seg_box = Table([[seg_inner]], colWidths=[LW])
    seg_box.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), LIGHT_BLUE),
        ('BOX',           (0, 0), (-1, -1), 0.75, TEAL),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    L += [
        [sec('SEGMENTATION RESULTS')],
        [seg_box],
    ]

    left_col = Table(L, colWidths=[LW])
    left_col.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    # ── RIGHT COLUMN ──────────────────────────────────────────────────────────
    R = []
    BW = RW - 0.3 * cm  # bar width

    # AI Assessment header + ANALYSIS OK badge
    ok = Table(
        [[Paragraph('<font color="white" size=7><b>ANALYSIS OK</b></font>', S['center'])]],
        colWidths=[2.3 * cm]
    )
    ok.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), C_OK),
        ('TOPPADDING',    (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
    ]))
    ai_hdr = Table([[sec('AI ASSESSMENT'), ok]], colWidths=[RW - 2.6 * cm, 2.6 * cm])
    ai_hdr.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN',         (1, 0), (1,  0),  'RIGHT'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    R += [[ai_hdr], [Spacer(1, 6)]]

    # Primary finding title
    R += [[Paragraph(abn['label'].title(), S['finding'])], [Spacer(1, 6)]]

    # Confidence bars (Abnormality + Pathology)
    for bar_lbl, conf in [
        (f"Abnormality: {abn['label'].title()}", abn['confidence']),
        (f"Pathology: {path['label'].title()}",  path['confidence']),
    ]:
        R.append([Paragraph(
            f'<font size=8 color="#64748B">{bar_lbl}</font>'
            f'&nbsp;&nbsp;<font size=9 color="#0A1628"><b>{conf*100:.0f}%</b></font>',
            S['bar_lbl']
        )])
        fw = BW * conf
        ew = BW * (1 - conf)
        if ew > 0.01:
            bar = Table([[None, None]], colWidths=[fw, ew])
            bar.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, 0), NAVY),
                ('BACKGROUND', (1, 0), (1, 0), MID_GRAY),
                ('ROWHEIGHT',  (0, 0), (-1, -1), 7),
            ]))
        else:
            bar = Table([[None]], colWidths=[BW])
            bar.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, 0), NAVY),
                ('ROWHEIGHT',  (0, 0), (-1, -1), 7),
            ]))
        R += [[bar], [Spacer(1, 5)]]

    # Urgency pill
    pill = Table(
        [[Paragraph(
            f'<font color="white" size=8><b>{urgency.upper()} URGENCY</b></font>',
            S['center']
        )]],
        colWidths=[3.2 * cm]
    )
    pill.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), accent),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
    ]))
    R += [[pill], [Spacer(1, 8)]]

    # Findings / Impression narrative
    findings = sections.get('findings') or sections.get('impression') or ''
    if findings:
        for part in _md(findings).split('<br/>'):
            part = part.strip()
            if part:
                R.append([Paragraph(part, S['findings'])])
        R.append([Spacer(1, 6)])

    # Suggested Management
    if t_notes:
        R.append([Paragraph('SUGGESTED MANAGEMENT', S['sub_head'])])
        for note in t_notes[:3]:
            R.append([Paragraph(f'• {note}', S['bullet'])])
        R.append([Spacer(1, 4)])

    # Disclaimer
    disc = sections.get('disclaimer', 'VLM-assisted analysis. Radiologist verification required.')
    R += [[Paragraph(f'<i>{disc}</i>', S['disc_sm'])], [Spacer(1, 10)]]

    # Images (2 rows × 2 columns)
    R.append([Paragraph('MAMMOGRAPHY IMAGES', S['sub_head'])])
    R.append([Spacer(1, 4)])

    IW = (RW - 0.6 * cm) / 2
    IH = 4.2 * cm

    def img_row(pairs):
        cells, labels = [], []
        for key, lbl_txt in pairs:
            im = _img(images.get(key), IW, IH)
            cells.append(im if im else Paragraph('—', S['center']))
            labels.append(Paragraph(lbl_txt, S['img_lbl']))
        t = Table([cells, labels], colWidths=[IW + 0.3 * cm, IW + 0.3 * cm])
        t.setStyle(TableStyle([
            ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING',    (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        return t

    R += [
        [img_row([('original_b64', 'Original Scan'), ('gradcam_b64', 'AI Saliency Map')])],
        [Spacer(1, 4)],
        [img_row([('mask_b64', 'Seg. Mask'), ('overlay_b64', 'Mask Overlay')])],
    ]

    right_col = Table(R, colWidths=[RW])
    right_col.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    # Assemble columns
    body = Table(
        [[left_col, Spacer(GW, 1), right_col]],
        colWidths=[LW, GW, RW]
    )
    body.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(body)
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width='100%', thickness=0.5, color=MID_GRAY))
    story.append(Spacer(1, 4))

    # ═══════════════════════════════════════════════════════════════════════════
    # 4. SIGNATURE ROW
    # ═══════════════════════════════════════════════════════════════════════════
    SLW = AW * 0.55
    SRW = AW * 0.45

    sig_left = Table(
        [
            [Paragraph('<font color="#64748B" size=7><i>RADIOLOGIST / PHYSICIAN SIGNATURE</i></font>', S['left'])],
            [Spacer(1, 4)],
            [Paragraph(f'<b>{p_phys}</b>', S['sig_name'])],
            [Paragraph('________________________', S['left'])],
            [Paragraph(f'Date: {p_date}', S['notes'])],
        ],
        colWidths=[SLW]
    )

    stamp = Table(
        [[Paragraph(
            '<font color="#94A3B8" size=7>PLACE RECEIVING SPECIALIST<br/>STAMP HERE</font>',
            S['center']
        )]],
        colWidths=[SRW - 0.5 * cm],
        rowHeights=[2.2 * cm]
    )
    stamp.setStyle(TableStyle([
        ('BOX',           (0, 0), (-1, -1), 0.5, MID_GRAY),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    sig_right_wrap = Table([[stamp]], colWidths=[SRW])
    sig_right_wrap.setStyle(TableStyle([
        ('ALIGN',  (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
    ]))

    sig_row = Table([[sig_left, sig_right_wrap]], colWidths=[SLW, SRW])
    sig_row.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'BOTTOM'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(sig_row)
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width='100%', thickness=0.5, color=MID_GRAY))
    story.append(Spacer(1, 3))

    # ═══════════════════════════════════════════════════════════════════════════
    # 5. FOOTER
    # ═══════════════════════════════════════════════════════════════════════════
    ts = datetime.utcnow().strftime('%d %b %Y at %I:%M %p UTC')
    footer = Table(
        [[
            Paragraph(
                '<font size=7><b>DeepMammo AI</b></font><br/>'
                '<font size=6 color="#64748B">Generated by DeepMammo — AI-Powered Breast Imaging</font>',
                S['left']
            ),
            Paragraph(
                f'<font size=7><b>TIMESTAMP &amp; CASE REF#</b></font><br/>'
                f'<font size=6 color="#64748B">Ref: {case_id} | Generated: {ts}</font>',
                S['right']
            ),
        ]],
        colWidths=[AW * 0.5, AW * 0.5]
    )
    footer.setStyle(TableStyle([
        ('ALIGN',         (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
    ]))
    story.append(footer)
    story.append(Spacer(1, 2))
    story.append(Paragraph(
        'This report was generated with AI assistance. It is intended to support, not replace, '
        'the clinical judgment of a qualified healthcare professional.',
        S['disc_center']
    ))

    doc.build(story)
    return base64.b64encode(buf.getvalue()).decode('utf-8')


# ── Styles ────────────────────────────────────────────────────────────────────
def _styles() -> dict:
    return {
        'left': ParagraphStyle('left',
            fontSize=9, fontName='Helvetica', textColor=DARK,
            leading=13, alignment=TA_LEFT),
        'center': ParagraphStyle('center',
            fontSize=9, fontName='Helvetica', textColor=DARK,
            leading=13, alignment=TA_CENTER),
        'right': ParagraphStyle('right',
            fontSize=9, fontName='Helvetica', textColor=DARK,
            leading=13, alignment=TA_RIGHT),
        'banner': ParagraphStyle('banner',
            fontSize=9, fontName='Helvetica-Bold', textColor=WHITE,
            leading=12, alignment=TA_CENTER),
        'sec_head': ParagraphStyle('sec_head',
            fontSize=7, fontName='Helvetica-Bold', textColor=NAVY,
            leading=10, spaceBefore=2, spaceAfter=3),
        'sub_head': ParagraphStyle('sub_head',
            fontSize=7, fontName='Helvetica-Bold', textColor=GRAY,
            leading=10, spaceAfter=2),
        'info_lbl': ParagraphStyle('info_lbl',
            fontSize=7, fontName='Helvetica-Bold', textColor=GRAY,
            leading=10),
        'info_val': ParagraphStyle('info_val',
            fontSize=8, fontName='Helvetica', textColor=NAVY,
            leading=11),
        'finding': ParagraphStyle('finding',
            fontSize=16, fontName='Helvetica-Bold', textColor=DARK,
            leading=20),
        'bar_lbl': ParagraphStyle('bar_lbl',
            fontSize=8, fontName='Helvetica', textColor=GRAY,
            leading=10, spaceAfter=2),
        'findings': ParagraphStyle('findings',
            fontSize=8, fontName='Helvetica', textColor=TEAL,
            leading=11),
        'bullet': ParagraphStyle('bullet',
            fontSize=8, fontName='Helvetica', textColor=TEAL,
            leading=11, leftIndent=8),
        'notes': ParagraphStyle('notes',
            fontSize=8, fontName='Helvetica-Oblique', textColor=GRAY,
            leading=11),
        'img_lbl': ParagraphStyle('img_lbl',
            fontSize=7, fontName='Helvetica-Bold', textColor=GRAY,
            leading=9, alignment=TA_CENTER),
        'box_lbl': ParagraphStyle('box_lbl',
            fontSize=7, fontName='Helvetica-Bold', textColor=GRAY,
            leading=10),
        'box_val': ParagraphStyle('box_val',
            fontSize=8, fontName='Helvetica', textColor=NAVY,
            leading=11),
        'sig_name': ParagraphStyle('sig_name',
            fontSize=13, fontName='Helvetica-Bold', textColor=DARK,
            leading=16),
        'disc_sm': ParagraphStyle('disc_sm',
            fontSize=7, fontName='Helvetica-Oblique', textColor=GRAY,
            leading=9),
        'disc_center': ParagraphStyle('disc_center',
            fontSize=7, fontName='Helvetica-Oblique', textColor=GRAY,
            leading=9, alignment=TA_CENTER),
    }
