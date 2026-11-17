"""Dossiers humains de causes/actions. Les pistes proposées ne sont pas des causes établies."""
from datetime import date
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field,ConfigDict,model_validator
from psycopg.types.json import Jsonb
from .db import get_connection
from .alert_engine import write_connection
router=APIRouter(prefix='/investigations',tags=['Causes et actions'])
GUIDANCE={
 'STOCK_LOW':['Vérifier les réceptions attendues et les retards fournisseurs.','Comparer la consommation réelle aux besoins matière et aux prévisions.','Vérifier réservations, unités et dernier comptage physique.'],
 'STOCK_HIGH':['Comparer les achats aux besoins et aux minimums de commande.','Vérifier une baisse de demande ou un décalage du plan de production.','Examiner le réglage du stock maximum.'],
 'INACTIVE_STOCK':['Vérifier la date et la justification du passage à inactif.','Évaluer une réutilisation, un retour fournisseur ou un traitement autorisé du stock.'],
 'PURCHASE_OVERDUE':['Examiner les engagements fournisseur et les réceptions partielles.','Vérifier les documents de transport et les éventuels blocages douaniers.'],
 'PRODUCTION_OVERDUE':['Vérifier la disponibilité matière, la capacité et les événements machine.','Comparer le planning initial aux dates et quantités réellement enregistrées.'],
 'CUSTOMER_OVERDUE':['Examiner les expéditions partielles et les preuves de livraison.','Vérifier la disponibilité produit et les retards de transport.']
}
class BaseInput(BaseModel):
 model_config=ConfigDict(str_strip_whitespace=True,extra='forbid')
class InvestigationInput(BaseInput):
 version:int=Field(ge=0)
 hypothesis:str=Field(min_length=3,max_length=4000)
 supporting_evidence:str=Field(default='',max_length=8000)
 conclusion:str=Field(default='',max_length=4000)
 status:Literal['DRAFT','CONFIRMED']='DRAFT'
 @model_validator(mode='after')
 def confirmation(self):
  if self.status=='CONFIRMED' and (len(self.supporting_evidence)<10 or len(self.conclusion)<10):raise ValueError('Confirmation : preuves et conclusion de 10 caractères minimum requises.')
  return self
class ActionInput(BaseInput):
 id:UUID
 description:str=Field(min_length=3,max_length=2000)
 owner_label:str=Field(min_length=2,max_length=100)
 due_date:date
class ActionChange(BaseInput):
 version:int=Field(ge=1)
 status:Literal['OPEN','IN_PROGRESS','COMPLETED']
 effectiveness_notes:str=Field(default='',max_length=4000)
 @model_validator(mode='after')
 def completion(self):
  if self.status=='COMPLETED' and len(self.effectiveness_notes)<10:raise ValueError('Décrire le résultat ou la vérification (10 caractères minimum).')
  return self

def require_alert(conn,alert_id,lock=False):
 row=conn.execute('SELECT * FROM ilip.engine_alerts WHERE id=%s'+(' FOR UPDATE' if lock else ''),(alert_id,)).fetchone()
 if not row:raise HTTPException(404,'Alerte moteur introuvable. Enregistrer une détection à l’étape 8.')
 return row

def journal(conn,alert_id,event,payload):
 conn.execute('INSERT INTO ilip.engine_case_history(alert_id,event_type,payload) VALUES (%s,%s,%s)',(alert_id,event,Jsonb(payload)))

@router.get('/{alert_id}')
def case(alert_id:int,conn=Depends(get_connection)):
 alert=require_alert(conn,alert_id)
 return dict(alert=alert,guidance=GUIDANCE.get(alert['rule_code'],[]),guidance_kind='CHECKLIST_NOT_CONFIRMED_CAUSE',
 investigation=conn.execute('SELECT * FROM ilip.engine_investigations WHERE alert_id=%s',(alert_id,)).fetchone(),
 actions=conn.execute('SELECT * FROM ilip.engine_actions WHERE alert_id=%s ORDER BY due_date,id',(alert_id,)).fetchall(),
 history=conn.execute('SELECT * FROM ilip.engine_case_history WHERE alert_id=%s ORDER BY id DESC LIMIT 100',(alert_id,)).fetchall(),history_limit=100)

@router.put('/{alert_id}')
def save_case(alert_id:int,body:InvestigationInput,conn=Depends(write_connection)):
 require_alert(conn,alert_id,True)
 old=conn.execute('SELECT version FROM ilip.engine_investigations WHERE alert_id=%s',(alert_id,)).fetchone()
 if (old['version'] if old else 0)!=body.version:raise HTTPException(409,'Dossier modifié. Recharger avant de sauvegarder.')
 row=conn.execute("""INSERT INTO ilip.engine_investigations(alert_id,hypothesis,supporting_evidence,conclusion,status)
 VALUES(%s,%s,%s,%s,%s) ON CONFLICT(alert_id) DO UPDATE SET hypothesis=excluded.hypothesis,supporting_evidence=excluded.supporting_evidence,
 conclusion=excluded.conclusion,status=excluded.status,version=ilip.engine_investigations.version+1,updated_at=CURRENT_TIMESTAMP RETURNING *""",
 (alert_id,body.hypothesis,body.supporting_evidence,body.conclusion,body.status)).fetchone()
 journal(conn,alert_id,'INVESTIGATION_SAVED',{**body.model_dump(mode='json'),'saved_version':row['version']})
 return row

@router.post('/{alert_id}/actions')
def create_action(alert_id:int,body:ActionInput,conn=Depends(write_connection)):
 require_alert(conn,alert_id,True)
 existing=conn.execute('SELECT * FROM ilip.engine_actions WHERE id=%s',(body.id,)).fetchone()
 if existing:
  if existing['alert_id']!=alert_id or any(existing[k]!=getattr(body,k) for k in ['description','owner_label','due_date']):raise HTTPException(409,'Identifiant d’action déjà utilisé avec un autre contenu.')
  return existing
 row=conn.execute('INSERT INTO ilip.engine_actions(id,alert_id,description,owner_label,due_date) VALUES (%s,%s,%s,%s,%s) RETURNING *',(body.id,alert_id,body.description,body.owner_label,body.due_date)).fetchone()
 journal(conn,alert_id,'ACTION_CREATED',body.model_dump(mode='json'))
 return row

@router.patch('/{alert_id}/actions/{action_id}')
def change_action(alert_id:int,action_id:UUID,body:ActionChange,conn=Depends(write_connection)):
 require_alert(conn,alert_id,True)
 old=conn.execute('SELECT * FROM ilip.engine_actions WHERE id=%s AND alert_id=%s FOR UPDATE',(action_id,alert_id)).fetchone()
 if not old:raise HTTPException(404,'Action introuvable dans ce dossier.')
 if old['version']!=body.version:raise HTTPException(409,'Action modifiée. Recharger le dossier.')
 row=conn.execute('UPDATE ilip.engine_actions SET status=%s,effectiveness_notes=%s,version=version+1,updated_at=CURRENT_TIMESTAMP WHERE id=%s RETURNING *',(body.status,body.effectiveness_notes,action_id)).fetchone()
 journal(conn,alert_id,'ACTION_UPDATED',dict(action_id=str(action_id),old_status=old['status'],**body.model_dump(mode='json')))
 return row
