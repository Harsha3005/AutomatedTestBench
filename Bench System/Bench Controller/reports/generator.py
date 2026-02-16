"""
PDF certificate generator for ISO 4064 water meter test results.

Uses ReportLab to produce A4 certificates with:
- Header (IIIT-B, lab name, cert number)
- Meter & test details
- Q1-Q8 results table
- Error curve chart (from error_curve.py)
- Overall verdict
- Signature line & footer
"""

import io
import os
from datetime import datetime

from django.conf import settings

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    HRFlowable, KeepTogether,
)

from testing.services import get_test_summary
from reports.error_curve import generate_error_curve_image


# --- Colors ---
INDIGO = colors.HexColor('#4f46e5')
DARK = colors.HexColor('#1e293b')
MUTED = colors.HexColor('#64748b')
PASS_GREEN = colors.HexColor('#059669')
FAIL_RED = colors.HexColor('#dc2626')
LIGHT_BG = colors.HexColor('#f8fafc')
BORDER = colors.HexColor('#e2e8f0')
TABLE_HEADER_BG = colors.HexColor('#f1f5f9')


def _styles():
    """Build custom paragraph styles."""
    ss = getSampleStyleSheet()
    return {
        'title': ParagraphStyle(
            'CertTitle', parent=ss['Title'],
            fontName='Helvetica-Bold', fontSize=18,
            textColor=DARK, alignment=TA_CENTER, spaceAfter=2*mm,
        ),
        'subtitle': ParagraphStyle(
            'CertSubtitle', parent=ss['Normal'],
            fontName='Helvetica', fontSize=11,
            textColor=MUTED, alignment=TA_CENTER, spaceAfter=6*mm,
        ),
        'section': ParagraphStyle(
            'Section', parent=ss['Heading2'],
            fontName='Helvetica-Bold', fontSize=12,
            textColor=INDIGO, spaceBefore=6*mm, spaceAfter=3*mm,
        ),
        'normal': ParagraphStyle(
            'CertNormal', parent=ss['Normal'],
            fontName='Helvetica', fontSize=10,
            textColor=DARK, leading=14,
        ),
        'small': ParagraphStyle(
            'CertSmall', parent=ss['Normal'],
            fontName='Helvetica', fontSize=8,
            textColor=MUTED, leading=10,
        ),
        'verdict_pass': ParagraphStyle(
            'VerdictPass', parent=ss['Title'],
            fontName='Helvetica-Bold', fontSize=16,
            textColor=PASS_GREEN, alignment=TA_CENTER,
        ),
        'verdict_fail': ParagraphStyle(
            'VerdictFail', parent=ss['Title'],
            fontName='Helvetica-Bold', fontSize=16,
            textColor=FAIL_RED, alignment=TA_CENTER,
        ),
        'label': ParagraphStyle(
            'Label', parent=ss['Normal'],
            fontName='Helvetica-Bold', fontSize=9,
            textColor=MUTED,
        ),
        'value': ParagraphStyle(
            'Value', parent=ss['Normal'],
            fontName='Helvetica', fontSize=10,
            textColor=DARK,
        ),
        'footer': ParagraphStyle(
            'Footer', parent=ss['Normal'],
            fontName='Helvetica', fontSize=7,
            textColor=MUTED, alignment=TA_CENTER,
        ),
    }


def _detail_row(label, value, styles):
    """Build a two-column detail row."""
    return [
        Paragraph(label, styles['label']),
        Paragraph(str(value) if value else '—', styles['value']),
    ]


def generate_certificate_pdf(test) -> bytes:
    """Generate a complete A4 PDF certificate for a test.

    Args:
        test: testing.models.Test instance (must have results populated)

    Returns:
        bytes: PDF file content
    """
    summary = get_test_summary(test)
    st = _styles()
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=15*mm, bottomMargin=15*mm,
        leftMargin=18*mm, rightMargin=18*mm,
    )

    elements = []

    # --- Header ---
    elements.append(Paragraph(
        'IIIT Bengaluru — Water Meter Calibration Laboratory',
        st['title']
    ))
    elements.append(Paragraph(
        'Test Certificate — ISO 4064 Compliance',
        st['subtitle']
    ))
    elements.append(HRFlowable(
        width='100%', thickness=1, color=BORDER, spaceAfter=4*mm
    ))

    # --- Certificate Info ---
    cert_number = summary.certificate_number or '(Pending)'
    cert_date = ''
    if test.completed_at:
        cert_date = test.completed_at.strftime('%d %B %Y, %H:%M')
    elif test.started_at:
        cert_date = test.started_at.strftime('%d %B %Y, %H:%M')

    info_data = [
        [Paragraph('Certificate No.', st['label']),
         Paragraph(cert_number, st['value']),
         Paragraph('Date', st['label']),
         Paragraph(cert_date, st['value'])],
    ]
    info_table = Table(info_data, colWidths=[30*mm, 55*mm, 25*mm, 55*mm])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2*mm),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 3*mm))

    # --- Meter Details ---
    elements.append(Paragraph('Meter Under Test', st['section']))
    meter = test.meter
    meter_data = [
        [Paragraph('Serial Number', st['label']),
         Paragraph(meter.serial_number, st['value']),
         Paragraph('Size', st['label']),
         Paragraph(meter.meter_size, st['value'])],
        [Paragraph('Manufacturer', st['label']),
         Paragraph(meter.manufacturer or '—', st['value']),
         Paragraph('Model', st['label']),
         Paragraph(meter.model_name or '—', st['value'])],
        [Paragraph('Type', st['label']),
         Paragraph(meter.get_meter_type_display(), st['value']),
         Paragraph('Test Class', st['label']),
         Paragraph(summary.test_class, st['value'])],
    ]
    meter_table = Table(meter_data, colWidths=[30*mm, 55*mm, 25*mm, 55*mm])
    meter_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2*mm),
    ]))
    elements.append(meter_table)

    # --- Test Info ---
    elements.append(Paragraph('Test Information', st['section']))
    started = test.started_at.strftime('%d %b %Y, %H:%M:%S') if test.started_at else '—'
    completed = test.completed_at.strftime('%d %b %Y, %H:%M:%S') if test.completed_at else '—'
    initiated = test.initiated_by.get_full_name() or test.initiated_by.username if test.initiated_by else '—'

    test_data = [
        [Paragraph('Started', st['label']),
         Paragraph(started, st['value']),
         Paragraph('Completed', st['label']),
         Paragraph(completed, st['value'])],
        [Paragraph('Initiated By', st['label']),
         Paragraph(initiated, st['value']),
         Paragraph('Source', st['label']),
         Paragraph(test.get_source_display(), st['value'])],
    ]
    test_table = Table(test_data, colWidths=[30*mm, 55*mm, 25*mm, 55*mm])
    test_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2*mm),
    ]))
    elements.append(test_table)

    # --- Results Table ---
    elements.append(Paragraph('Q-Point Results', st['section']))

    # Table header
    header = ['Q-Point', 'Zone', 'Target\n(L/h)', 'Ref Vol\n(L)',
              'DUT Vol\n(L)', 'Error\n(%)', 'MPE\n(%)', 'Result']

    header_style = ParagraphStyle(
        'TH', fontName='Helvetica-Bold', fontSize=8,
        textColor=MUTED, alignment=TA_CENTER, leading=10,
    )
    cell_style = ParagraphStyle(
        'TD', fontName='Helvetica', fontSize=9,
        textColor=DARK, alignment=TA_CENTER, leading=11,
    )
    pass_style = ParagraphStyle(
        'TDPass', fontName='Helvetica-Bold', fontSize=9,
        textColor=PASS_GREEN, alignment=TA_CENTER,
    )
    fail_style = ParagraphStyle(
        'TDFail', fontName='Helvetica-Bold', fontSize=9,
        textColor=FAIL_RED, alignment=TA_CENTER,
    )

    table_data = [[Paragraph(h, header_style) for h in header]]

    for qp in summary.q_points:
        if qp.passed is True:
            result_cell = Paragraph('PASS', pass_style)
        elif qp.passed is False:
            result_cell = Paragraph('FAIL', fail_style)
        else:
            result_cell = Paragraph('—', cell_style)

        row = [
            Paragraph(qp.q_point, cell_style),
            Paragraph(qp.zone, cell_style),
            Paragraph(f'{qp.target_flow_lph:.0f}', cell_style),
            Paragraph(f'{qp.ref_volume_l:.4f}' if qp.ref_volume_l else '—', cell_style),
            Paragraph(f'{qp.dut_volume_l:.4f}' if qp.dut_volume_l else '—', cell_style),
            Paragraph(f'{qp.error_pct:.3f}' if qp.error_pct is not None else '—', cell_style),
            Paragraph(f'\u00b1{qp.mpe_pct:.1f}', cell_style),
            result_cell,
        ]
        table_data.append(row)

    col_widths = [16*mm, 16*mm, 20*mm, 22*mm, 22*mm, 20*mm, 18*mm, 18*mm]
    results_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    results_table.setStyle(TableStyle([
        # Header
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER_BG),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 3*mm),
        ('TOPPADDING', (0, 0), (-1, 0), 2*mm),
        # Body
        ('TOPPADDING', (0, 1), (-1, -1), 1.5*mm),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 1.5*mm),
        # Alternating rows
        *[('BACKGROUND', (0, i), (-1, i), LIGHT_BG)
          for i in range(2, len(table_data), 2)],
        # Grid
        ('LINEBELOW', (0, 0), (-1, 0), 1, BORDER),
        ('LINEBELOW', (0, -1), (-1, -1), 1, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(results_table)

    # --- Error Curve Chart ---
    elements.append(Paragraph('Error Curve', st['section']))
    try:
        chart_png = generate_error_curve_image(summary, width=7.0, height=3.2, dpi=150)
        chart_image = Image(io.BytesIO(chart_png), width=165*mm, height=75*mm)
        elements.append(chart_image)
    except Exception:
        elements.append(Paragraph(
            '<i>Error curve chart could not be generated.</i>', st['small']
        ))

    # --- Zone Verdicts ---
    elements.append(Spacer(1, 3*mm))
    zone_data = []
    if summary.lower_zone_pass is not None:
        lz = 'PASS' if summary.lower_zone_pass else 'FAIL'
        lz_style = pass_style if summary.lower_zone_pass else fail_style
        zone_data.append([
            Paragraph('Lower Zone (Q1-Q3)', cell_style),
            Paragraph(lz, lz_style),
        ])
    if summary.upper_zone_pass is not None:
        uz = 'PASS' if summary.upper_zone_pass else 'FAIL'
        uz_style = pass_style if summary.upper_zone_pass else fail_style
        zone_data.append([
            Paragraph('Upper Zone (Q4-Q8)', cell_style),
            Paragraph(uz, uz_style),
        ])
    if zone_data:
        zone_table = Table(zone_data, colWidths=[50*mm, 30*mm])
        zone_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2*mm),
        ]))
        elements.append(zone_table)

    # --- Overall Verdict ---
    elements.append(Spacer(1, 4*mm))
    elements.append(HRFlowable(
        width='100%', thickness=1, color=BORDER, spaceAfter=4*mm
    ))
    if summary.overall_pass is True:
        elements.append(Paragraph('OVERALL VERDICT: PASS', st['verdict_pass']))
    elif summary.overall_pass is False:
        elements.append(Paragraph('OVERALL VERDICT: FAIL', st['verdict_fail']))
    else:
        elements.append(Paragraph('OVERALL VERDICT: INCOMPLETE', st['subtitle']))

    # --- Error Statistics ---
    if summary.min_error_pct is not None:
        elements.append(Spacer(1, 3*mm))
        stats_text = (
            f'Error range: {summary.min_error_pct:+.3f}% to {summary.max_error_pct:+.3f}%'
            f' &nbsp;|&nbsp; Average: {summary.avg_error_pct:+.3f}%'
            f' &nbsp;|&nbsp; Points: {summary.passed_points} pass, '
            f'{summary.failed_points} fail of {summary.total_points}'
        )
        elements.append(Paragraph(stats_text, ParagraphStyle(
            'Stats', fontName='Helvetica', fontSize=9,
            textColor=MUTED, alignment=TA_CENTER,
        )))

    # --- Signature Line ---
    elements.append(Spacer(1, 12*mm))
    sig_data = [
        [Paragraph('', st['normal']), Paragraph('', st['normal'])],
        [Paragraph('_' * 35, st['normal']),
         Paragraph('_' * 35, st['normal'])],
        [Paragraph('Tested By', st['small']),
         Paragraph('Approved By', st['small'])],
    ]
    sig_table = Table(sig_data, colWidths=[80*mm, 80*mm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 1*mm),
    ]))
    elements.append(sig_table)

    # --- Footer ---
    elements.append(Spacer(1, 6*mm))
    elements.append(HRFlowable(
        width='100%', thickness=0.5, color=BORDER, spaceAfter=2*mm
    ))
    elements.append(Paragraph(
        'This certificate is issued by the IIIT Bengaluru Water Meter Calibration Laboratory. '
        'Test performed in accordance with IS/ISO 4064-1:2014. '
        'This document is electronically generated and valid without signature.',
        st['footer']
    ))

    doc.build(elements)
    buf.seek(0)
    return buf.read()


def save_certificate(test) -> str:
    """Generate and save a certificate PDF to MEDIA_ROOT.

    Args:
        test: testing.models.Test instance

    Returns:
        str: Relative path to the saved PDF (for storage in test.certificate_pdf)
    """
    pdf_bytes = generate_certificate_pdf(test)

    cert_dir = os.path.join(settings.MEDIA_ROOT, 'certificates')
    os.makedirs(cert_dir, exist_ok=True)

    filename = f'{test.certificate_number or f"test_{test.pk}"}.pdf'
    filepath = os.path.join(cert_dir, filename)

    with open(filepath, 'wb') as f:
        f.write(pdf_bytes)

    rel_path = f'certificates/{filename}'
    test.certificate_pdf = rel_path
    test.save(update_fields=['certificate_pdf'])

    return rel_path
