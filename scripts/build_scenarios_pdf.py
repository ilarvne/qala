"""Create the submission's scenario-and-limit document from canonical Markdown.

Run with the Codex bundled Python runtime (ReportLab and pypdf).
"""
from pathlib import Path
from html import escape
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/scenarios-and-limits.pdf'
FONT_ROOT = Path('/usr/share/fonts/TTF')
regular = next((p for p in [FONT_ROOT/'DejaVuSans.ttf', Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')] if p.exists()), None)
bold = next((p for p in [FONT_ROOT/'DejaVuSans-Bold.ttf', Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')] if p.exists()), None)
if regular and bold:
    pdfmetrics.registerFont(TTFont('Qala', str(regular)))
    pdfmetrics.registerFont(TTFont('QalaBold', str(bold)))
else:
    raise SystemExit('DejaVu Sans fonts required for consistent Unicode rendering')
PINE = colors.HexColor('#183F35')
IVORY = colors.HexColor('#F6F4E9')
RULE = colors.HexColor('#CDD4C5')
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='QTitle',fontName='QalaBold',fontSize=29,leading=35,textColor=PINE,spaceAfter=13))
styles.add(ParagraphStyle(name='QSub',fontName='QalaBold',fontSize=16,leading=21,textColor=PINE,spaceBefore=18,spaceAfter=10))
styles.add(ParagraphStyle(name='QBody',fontName='Qala',fontSize=10.3,leading=15,textColor=PINE,spaceAfter=9))
styles.add(ParagraphStyle(name='QCell',fontName='Qala',fontSize=9.8,leading=14,textColor=PINE))
styles.add(ParagraphStyle(name='QHeader',fontName='QalaBold',fontSize=10,leading=14,textColor=colors.white))

def clean(v):
    v = v.replace('–','-').replace('—','-').replace('‑','-')
    v = re.sub(r'`([^`]+)`',r'\1',v)
    return escape(v)

def para(v, style='QBody'):
    return Paragraph(clean(v), styles[style])

width,height = landscape(A4)
doc=SimpleDocTemplate(str(OUT),pagesize=(width,height),leftMargin=20*mm,rightMargin=20*mm,topMargin=18*mm,bottomMargin=18*mm,title='Qala - Test scenarios and limits',author='Qala project')
story=[]
lines=(ROOT/'docs/test-scenarios.md').read_text().splitlines()
i=0
while i<len(lines):
    line=lines[i]
    if not line.strip():i+=1;continue
    if line.startswith('# '):
        story.append(para('Qala / Test scenarios and limits','QTitle'))
    elif line.startswith('## '):
        story.append(para(line[3:],'QSub'))
    elif line.startswith('|'):
        tablelines=[]
        while i<len(lines) and lines[i].startswith('|'):
            if not re.match(r'^\|[\s:|-]+\|$',lines[i]):tablelines.append([x.strip() for x in lines[i].strip('|').split('|')])
            i+=1
        data=[[para(v,'QHeader' if r==0 else 'QCell') for v in row] for r,row in enumerate(tablelines)]
        total=width-40*mm
        tbl=Table(data,colWidths=[total*.14,total*.36,total*.50],repeatRows=1,hAlign='LEFT')
        tbl.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),PINE),('BACKGROUND',(0,1),(-1,-1),IVORY),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10),('LINEBELOW',(0,0),(-1,-1),.5,RULE)]))
        story.extend([tbl,Spacer(1,10)])
        continue
    else:
        paragraph=[line]
        while i+1<len(lines) and lines[i+1].strip() and not lines[i+1].startswith(('#','|')):
            i+=1;paragraph.append(lines[i])
        story.append(para(' '.join(paragraph)))
    i+=1

story.append(para('Operating limits','QSub'))
story.append(para('The local planner uses collected public POIs, geographic walking estimates and conservative schedule checks. Map links are illustrative. It does not verify street accessibility, live tickets, queues, weather or event inventory. A missing amenity remains unknown. No cloud credentials are needed for core planning. ElevenLabs and telephone paths need provider setup and live validation.'))
story.append(para('Location is chosen or explicitly shared. Preference memory is opt-in, expires after 30 days and supports deletion. Precise coordinates stay out of persistent preference storage. The prototype is not a production navigation or emergency service.'))
story.append(para('Canonical sources: docs/test-scenarios.md, docs/privacy-and-safety.md and docs/research/product-research.md. National Museum schedule source: https://www.nmrk.kz/en/ (accessed 19 October 2026).'))

def footer(canvas,doc):
    canvas.setFillColor(PINE);canvas.setFont('Qala',8)
    canvas.drawString(20*mm,11*mm,'Qala / Hackathon acceptance document / 19 October 2026')
    canvas.drawRightString(width-20*mm,11*mm,str(doc.page))

OUT.parent.mkdir(parents=True,exist_ok=True)
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT)
