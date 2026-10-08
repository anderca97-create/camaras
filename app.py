import os, json, base64
from io import BytesIO
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak, KeepTogether
from reportlab.lib.utils import ImageReader

BASE = Path(__file__).parent
app = FastAPI(title="Fortress Levantamiento CCTV IA")
app.mount("/static", StaticFiles(directory=BASE/"static"), name="static")

@app.get("/")
def home():
    return FileResponse(BASE / "static" / "index.html")

@app.get("/health")
def health():
    return {"ok": True, "ai": bool(os.getenv("OPENAI_API_KEY"))}

@app.post("/api/analyze")
async def analyze(photo: UploadFile = File(...), zone: str = Form("Zona"), status: str = Form("Evaluar"), notes: str = Form("")):
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return JSONResponse({"error": "IA no configurada", "detail": "Falta configurar OPENAI_API_KEY en el servidor."}, status_code=503)
    try:
        from openai import OpenAI
        raw = await photo.read()
        mime = photo.content_type or "image/jpeg"
        data = base64.b64encode(raw).decode()
        client = OpenAI(api_key=key)
        prompt = f"""Actúa como ingeniero de CCTV.
Analiza la fotografía de la zona '{zone}', condición '{status}'.
Notas de campo: {notes}
Devuelve SOLO JSON válido con estas claves:
objetivo: string
riesgos: array de strings
camara: string
justificacion: string
montaje: string
orientacion: string
analiticas: array de strings
materiales: array de objetos con item y cantidad
pendientes: array de strings
Regla crítica: no inventes alturas, distancias, iluminación, energía, red, estructura ni ángulos que no puedan verificarse visualmente. Todo dato no verificable debe aparecer en pendientes."""
        r = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5.6"),
            input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}, {"type": "input_image", "image_url": f"data:{mime};base64,{data}"}]}]
        )
        text = r.output_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        return {"mode": "ai", "analysis": json.loads(text)}
    except Exception as e:
        return JSONResponse({"error": "No fue posible completar el análisis IA.", "detail": str(e)}, status_code=500)

def _safe(text):
    return str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _p(text, style):
    return Paragraph(_safe(text), style)

def _photo_from_data_url(data_url, max_w=165*mm, max_h=85*mm):
    try:
        if not data_url or "," not in data_url:
            return None
        raw = base64.b64decode(data_url.split(",", 1)[1])
        bio = BytesIO(raw)
        ir = ImageReader(bio)
        w, h = ir.getSize()
        scale = min(max_w / w, max_h / h)
        return RLImage(bio, width=w*scale, height=h*scale)
    except Exception:
        return None

def _build_pdf(project, mode="client"):
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, rightMargin=14*mm, leftMargin=14*mm, topMargin=15*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("TitleX", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=20, leading=23, textColor=colors.HexColor("#0B2239"), spaceAfter=8)
    h2 = ParagraphStyle("H2X", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=colors.HexColor("#0B2239"), spaceBefore=8, spaceAfter=5)
    body = ParagraphStyle("BodyX", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13, textColor=colors.HexColor("#1D2A34"))
    small = ParagraphStyle("SmallX", parent=body, fontSize=8, leading=10, textColor=colors.HexColor("#52697B"))
    label = ParagraphStyle("LabelX", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#16496D"))

    story = [_p("FORTRESS SMART SECURITY", small), _p("Levantamiento técnico CCTV", title), _p("Reporte para cliente" if mode == "client" else "Reporte técnico interno", h2), Spacer(1, 4*mm)]

    info = [
        ["Cliente", project.get("client", "")],
        ["Sitio", project.get("site", "")],
        ["Contacto", project.get("contact", "")],
        ["Técnico", project.get("tech", "")],
        ["Fecha de creación", project.get("created", "")]
    ]
    t = Table(info, colWidths=[38*mm, 125*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#EAF2F8")),
        ("TEXTCOLOR", (0,0), (-1,-1), colors.HexColor("#1D2A34")),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE", (0,0), (-1,-1), 8.5),
        ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#C7D6E2")),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story += [t, Spacer(1, 4*mm)]

    if project.get("notes"):
        story += [_p("Objetivo / notas generales", h2), _p(project.get("notes"), body), Spacer(1, 3*mm)]

    zones = project.get("zones") or []
    story += [_p(f"Zonas evaluadas: {len(zones)}", h2)]
    for i, z in enumerate(zones, 1):
        block = [_p(f"{i}. {z.get('name','Zona')}", h2), _p(f"Condición: {z.get('status','')}", label)]
        if z.get("notes"):
            block.append(_p(z.get("notes"), body))
        for data_url in (z.get("photos") or [])[:3]:
            img = _photo_from_data_url(data_url)
            if img:
                block += [Spacer(1, 2*mm), img]
        a = z.get("assessment") or z.get("analysis")
        if a:
            block += [
                Spacer(1, 2*mm),
                _p("Objetivo", label), _p(a.get("objetivo",""), body),
                _p("Cámara recomendada", label), _p(a.get("camara",""), body),
                _p("Justificación", label), _p(a.get("justificacion",""), body),
                _p("Montaje / orientación", label), _p((a.get("montaje","") + " - " + a.get("orientacion","")).strip(" -"), body),
            ]
            riesgos = ", ".join(a.get("riesgos") or [])
            analiticas = ", ".join(a.get("analiticas") or [])
            pendientes = ", ".join(a.get("pendientes") or [])
            if riesgos:
                block += [_p("Riesgos observados", label), _p(riesgos, body)]
            if analiticas:
                block += [_p("Analíticas recomendadas", label), _p(analiticas, body)]
            if mode == "internal" and pendientes:
                block += [_p("Pendientes de validación", label), _p(pendientes, body)]
        else:
            block += [_p("Análisis IA pendiente.", small)]
        story += block + [Spacer(1, 4*mm)]

    materials = project.get("materials") or []
    if materials:
        story += [PageBreak(), _p("Materiales / cotización", title)]
        rows = [["Cant.", "Equipo / material", "Nota", "P. unitario", "Subtotal"]]
        total = 0
        for m in materials:
            qty = float(m.get("qty") or 0)
            price = float(m.get("price") or 0)
            subtotal = qty * price
            total += subtotal
            rows.append([
                str(int(qty) if qty.is_integer() else qty),
                m.get("item",""),
                m.get("note",""),
                f"$ {price:,.2f}" if price > 0 else "",
                f"$ {subtotal:,.2f}" if price > 0 else ""
            ])
        table = Table(rows, colWidths=[15*mm, 62*mm, 44*mm, 25*mm, 27*mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0B2239")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 7.5),
            ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#C7D6E2")),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F4F7F9")]),
            ("ALIGN", (0,1), (0,-1), "CENTER"),
            ("ALIGN", (3,1), (-1,-1), "RIGHT"),
        ]))
        story += [table]
        if total > 0:
            story += [Spacer(1, 3*mm), _p(f"Total estimado: $ {total:,.2f} MXN", h2)]

    story += [Spacer(1, 6*mm), _p("Nota técnica", h2), _p("Las alturas, distancias, condiciones de energía/red, estructura, iluminación y ángulos definitivos deben validarse en campo antes de la instalación.", small)]
    doc.build(story)
    out.seek(0)
    return out

@app.post("/api/report")
async def report(payload: str = Form(...), mode: str = Form("client")):
    try:
        project = json.loads(payload)
        pdf = _build_pdf(project, mode=mode)
        filename = "reporte-cctv-cliente.pdf" if mode == "client" else "reporte-cctv-interno.pdf"
        return StreamingResponse(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{filename}"'})
    except Exception as e:
        return JSONResponse({"error": "No fue posible generar el PDF.", "detail": str(e)}, status_code=500)
