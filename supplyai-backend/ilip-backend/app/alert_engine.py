from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,Field,field_validator
from psycopg.types.json import Jsonb
from .db import get_connection
from .config import get_settings
from .departments import QUERIES, encode
router=APIRouter(prefix='/alerts',tags=['Moteur d’alertes'])

PURCHASE_SQL="""SELECT l.po_line_id AS entity_id,l.ordered_qty,
coalesce(sum(r.received_qty) FILTER(WHERE (r.received_at AT TIME ZONE 'Africa/Casablanca')::date<=%s),0) AS received_qty,
l.original_promised_delivery_date AS due_date
FROM ilip.purchase_order_lines l JOIN ilip.purchase_orders p USING(po_number)
LEFT JOIN ilip.purchase_receipts r USING(po_line_id)
WHERE l.original_promised_delivery_date<%s AND p.order_date<=%s AND p.status NOT IN ('CANCELLED','DRAFT')
GROUP BY l.po_line_id
HAVING coalesce(sum(r.received_qty) FILTER(WHERE (r.received_at AT TIME ZONE 'Africa/Casablanca')::date<=%s),0)<l.ordered_qty"""
PRODUCTION_SQL="""SELECT production_order_id AS entity_id,planned_end_date AS due_date,planned_qty
FROM ilip.production_orders WHERE planned_end_date<%s AND (actual_end_date IS NULL OR actual_end_date>%s) AND status NOT IN ('CANCELLED','DRAFT')"""
CUSTOMER_SQL="""SELECT l.customer_order_line_id AS entity_id,l.ordered_qty,l.promised_delivery_date AS due_date,
coalesce(sum(s.delivered_qty) FILTER(WHERE (s.delivered_at AT TIME ZONE 'Africa/Casablanca')::date<=%s),0) AS delivered_qty
FROM ilip.customer_order_lines l JOIN ilip.customer_orders c USING(customer_order_id)
LEFT JOIN ilip.shipment_lines s USING(customer_order_line_id)
WHERE l.promised_delivery_date<%s AND c.order_date<=%s AND c.status NOT IN ('CANCELLED','DRAFT')
GROUP BY l.customer_order_line_id
HAVING coalesce(sum(s.delivered_qty) FILTER(WHERE (s.delivered_at AT TIME ZONE 'Africa/Casablanca')::date<=%s),0)<l.ordered_qty"""

def scan(conn,as_of):
    exists=conn.execute('SELECT 1 FROM ilip.inventory_levels WHERE snapshot_date=%s LIMIT 1',(as_of,)).fetchone()
    if not exists:raise HTTPException(422,'Choisir une date avec photographie de stock disponible.')
    found=[]
    def add(code,entity,title,evidence,severity='WARNING'):
        # Date/Decimal supportés par JSON ; preuves figées au premier enregistrement.
        from fastapi.encoders import jsonable_encoder
        found.append(dict(rule_code=code,entity_id=entity,title=title,severity=severity,as_of=as_of,evidence=jsonable_encoder(encode(evidence))))
    for r in conn.execute(QUERIES['inventory'],(as_of,)).fetchall():
        if r['below_safety']:add('STOCK_LOW',r['item_id'],'Stock disponible sous sécurité',r,'CRITICAL' if r['available']==0 else 'WARNING')
        if r['overstock']:add('STOCK_HIGH',r['item_id'],'Stock physique supérieur au maximum',r)
        if not r['is_active'] and r['physical']>0:add('INACTIVE_STOCK',r['item_id'],'Article inactif avec stock',r)
    for sql,params,code,title in [
        (PURCHASE_SQL,(as_of,)*4,'PURCHASE_OVERDUE','Ligne fournisseur échue non intégralement reçue'),
        (PRODUCTION_SQL,(as_of,)*2,'PRODUCTION_OVERDUE','Ordre de fabrication échu non terminé'),
        (CUSTOMER_SQL,(as_of,)*4,'CUSTOMER_OVERDUE','Ligne client échue non intégralement livrée')]:
        for r in conn.execute(sql,params).fetchall():add(code,r['entity_id'],title,r,'CRITICAL')
    return found


def write_connection(request:Request):
    # Mode local uniquement. Ce garde-fou ne remplace pas une authentification multi-utilisateur.
    if not get_settings().ilip_enable_alert_writes:raise HTTPException(403,'Activer ILIP_ENABLE_ALERT_WRITES=true dans le .env backend puis redémarrer.')
    if request.headers.get('x-ilip-local-write')!='1':raise HTTPException(403,'En-tête local requis.')
    origin=request.headers.get('origin')
    allowed={'http://127.0.0.1:5173','http://localhost:5173','http://127.0.0.1:4173','http://localhost:4173','http://127.0.0.1:8000','http://localhost:8000'}
    if origin and origin not in allowed:raise HTTPException(403,'Origine non autorisée pour une écriture locale.')
    pool=getattr(request.app.state,'pool',None)
    if pool is None:raise HTTPException(503,'Connexion non configurée.')
    with pool.connection() as conn:
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='8000ms'")
            conn.execute("SET LOCAL TIME ZONE 'Africa/Casablanca'")
            yield conn

class ScanBody(BaseModel):as_of:date
class ChangeBody(BaseModel):
    status:Literal['OPEN','IN_PROGRESS','RESOLVED']
    version:int=Field(ge=1)
    note:str=Field(min_length=3,max_length=1000)
    @field_validator('note')
    @classmethod
    def nonblank(cls,v):
        if len(v.strip())<3:raise ValueError('Commentaire requis, 3 caractères minimum.')
        return v.strip()

@router.get('/preview')
def preview(as_of:date,conn=Depends(get_connection)):
    rows=scan(conn,as_of)
    return {'as_of':as_of,'total':len(rows),'data':rows}

@router.post('/runs')
def run(body:ScanBody,conn=Depends(write_connection)):
    # Sérialise les lancements du moteur ; une relance ne duplique ni alertes ni historique.
    conn.execute('SELECT pg_advisory_xact_lock(8042025)')
    rows=scan(conn,body.as_of);created=0
    for r in rows:
        saved=conn.execute("""INSERT INTO ilip.engine_alerts(rule_code,entity_id,as_of,severity,title,evidence)
        VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(rule_code,entity_id,as_of) DO NOTHING RETURNING id""",
        (r['rule_code'],r['entity_id'],r['as_of'],r['severity'],r['title'],Jsonb(r['evidence']))).fetchone()
        if saved:
            created+=1
            conn.execute("INSERT INTO ilip.engine_alert_history(alert_id,old_status,new_status,note) VALUES (%s,NULL,'OPEN','Détection initiale par règles V1')",(saved['id'],))
    return {'detected':len(rows),'created':created,'already_present':len(rows)-created,'as_of':body.as_of}

@router.get('')
def alerts(status:Literal['OPEN','IN_PROGRESS','RESOLVED']|None=None,limit:int=50,offset:int=0,conn=Depends(get_connection)):
    if limit<1 or limit>200 or offset<0:raise HTTPException(422,'Pagination invalide.')
    where='WHERE status=%s' if status else '';params=(status,) if status else ()
    total=conn.execute('SELECT count(*) AS n FROM ilip.engine_alerts '+where,params).fetchone()['n']
    rows=conn.execute('SELECT * FROM ilip.engine_alerts '+where+' ORDER BY as_of DESC,id DESC LIMIT %s OFFSET %s',params+(limit,offset)).fetchall()
    return dict(total=total,data=rows,limit=limit,offset=offset)

@router.get('/legacy')
def legacy(conn=Depends(get_connection)):
    return {'data':conn.execute('SELECT alert_id,title,severity,status,detected_at FROM ilip.alerts ORDER BY detected_at,alert_id').fetchall()}

@router.get('/{alert_id}/history')
def history(alert_id:int,conn=Depends(get_connection)):
    if not conn.execute('SELECT id FROM ilip.engine_alerts WHERE id=%s',(alert_id,)).fetchone():raise HTTPException(404,'Alerte introuvable.')
    return {'data':conn.execute('SELECT * FROM ilip.engine_alert_history WHERE alert_id=%s ORDER BY id',(alert_id,)).fetchall()}

@router.patch('/{alert_id}')
def change(alert_id:int,body:ChangeBody,conn=Depends(write_connection)):
    current=conn.execute('SELECT status,version FROM ilip.engine_alerts WHERE id=%s FOR UPDATE',(alert_id,)).fetchone()
    if not current:raise HTTPException(404,'Alerte introuvable.')
    if current['version']!=body.version:raise HTTPException(409,'Alerte modifiée depuis votre lecture. Actualiser puis réessayer.')
    if current['status']==body.status:raise HTTPException(409,'Choisir un statut différent.')
    row=conn.execute('UPDATE ilip.engine_alerts SET status=%s,version=version+1,updated_at=CURRENT_TIMESTAMP WHERE id=%s RETURNING *',(body.status,alert_id)).fetchone()
    conn.execute('INSERT INTO ilip.engine_alert_history(alert_id,old_status,new_status,note) VALUES (%s,%s,%s,%s)',(alert_id,current['status'],body.status,body.note))
    return row
