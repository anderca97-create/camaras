import os, json, base64
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
BASE=Path(__file__).parent
app=FastAPI(title="Fortress Levantamiento CCTV IA")
app.mount("/static",StaticFiles(directory=BASE/"static"),name="static")
@app.get("/")
def home(): return FileResponse(BASE/"static"/"index.html")
@app.get("/health")
def health(): return {"ok":True,"ai":bool(os.getenv("OPENAI_API_KEY"))}
@app.post("/api/analyze")
async def analyze(photo:UploadFile=File(...),zone:str=Form("Zona"),status:str=Form("Evaluar"),notes:str=Form("")):
 key=os.getenv("OPENAI_API_KEY")
 if not key: return {"mode":"pending","analysis":{"objetivo":"Definir cobertura para "+zone,"riesgos":["Validar riesgos específicos en campo"],"camara":"Pendiente de análisis IA","justificacion":"Configure OPENAI_API_KEY en el servidor para habilitar análisis visual.","montaje":"Pendiente de validación","orientacion":"Pendiente de validación","analiticas":["Pendiente de definir"],"materiales":[],"pendientes":["Altura","Distancias","Iluminación","Energía","Red","Ángulo real de cobertura"]}}
 try:
  from openai import OpenAI
  raw=await photo.read(); mime=photo.content_type or "image/jpeg"; data=base64.b64encode(raw).decode(); client=OpenAI(api_key=key)
  prompt=f"Actúa como ingeniero CCTV. Analiza zona {zone}, estado {status}. Notas: {notes}. Devuelve SOLO JSON válido con objetivo, riesgos(array), camara, justificacion, montaje, orientacion, analiticas(array), materiales(array de objetos item/cantidad), pendientes(array). No inventes alturas, distancias ni condiciones no verificables; ponlas en pendientes."
  r=client.responses.create(model=os.getenv("OPENAI_MODEL","gpt-5.6"),input=[{"role":"user","content":[{"type":"input_text","text":prompt},{"type":"input_image","image_url":f"data:{mime};base64,{data}"}]}]); t=r.output_text.strip()
  if t.startswith("```"): t=t.split("\n",1)[1].rsplit("```",1)[0]
  return {"mode":"ai","analysis":json.loads(t)}
 except Exception as e: return JSONResponse({"error":"No fue posible completar el análisis IA.","detail":str(e)},status_code=500)
