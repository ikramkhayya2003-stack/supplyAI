"""Postes datés : volumes, files, capacité théorique, pas de télémétrie implicite."""
from datetime import date
from fastapi import APIRouter,Depends,HTTPException
from .db import get_connection
from .departments import encode
router=APIRouter(prefix='/dashboard',tags=['Line stations'])
SQL="""SELECT s.station_id,s.line_id,s.station_name,s.sequence_no,s.ideal_cycle_minutes AS configured_cycle_minutes,
 s.is_synthetic AS configuration_synthetic,m.work_date,m.planned_minutes,m.run_minutes,m.ideal_cycle_minutes,
 m.opening_wip,m.received_units,m.completed_units,m.good_units,m.closing_wip,m.stop_reason,m.is_synthetic AS measurement_synthetic,m.source_reference,
 round(100*m.run_minutes/nullif(m.planned_minutes,0),2) AS availability_pct,
 round(m.run_minutes/nullif(m.completed_units,0),3) AS observed_minutes_per_unit,
 round(m.run_minutes/m.ideal_cycle_minutes,2) AS theoretical_capacity_units,
 round(100*(m.opening_wip+m.received_units)*m.ideal_cycle_minutes/nullif(m.run_minutes,0),2) AS load_pct
FROM ilip.line_stations s LEFT JOIN ilip.station_daily_measurements m ON m.station_id=s.station_id AND m.work_date=%s
WHERE s.line_id=%s ORDER BY s.sequence_no,s.station_id"""

def classify(row):
    if row['work_date'] is None:return 'NO_DATA'
    if row['run_minutes']==0:return 'NO_RUN'
    if row['closing_wip']>row['opening_wip'] and row['load_pct'] is not None and row['load_pct']>100:return 'BOTTLENECK_CANDIDATE'
    if row['closing_wip']>row['opening_wip']:return 'QUEUE_GROWTH'
    return 'NO_SIGNAL'

@router.get('/line-stations')
def line_stations(line_id:str,as_of:date,conn=Depends(get_connection)):
    line=conn.execute('SELECT line_id,plant_id FROM ilip.production_lines WHERE line_id=%s',(line_id,)).fetchone()
    if not line:raise HTTPException(404,'Ligne inconnue.')
    rows=conn.execute(SQL,(as_of,line_id)).fetchall()
    for row in rows:row['signal']=classify(row)
    days=conn.execute('SELECT DISTINCT m.work_date FROM ilip.station_daily_measurements m JOIN ilip.line_stations s USING(station_id) WHERE s.line_id=%s ORDER BY m.work_date DESC LIMIT 400',(line_id,)).fetchall()
    return encode(dict(line=line,as_of=as_of,stations=rows,available_dates=[r['work_date'] for r in days],
      definitions=[
        'Vue logique en perspective, non maquette physique : ordre des postes du référentiel actuel. Les mesures sont celles du jour choisi, sans report automatique du dernier jour.',
        'Goulot potentiel : file de fin supérieure à la file initiale ET charge théorique >100 % du temps de marche. Il faut vérifier mix produit, alimentation, équipe et temps standard avant de confirmer.',
        'Capacité théorique = minutes de marche / cycle idéal historisé. Ce n’est pas une prévision garantie ni une cadence mesurée.',
        'Volumes en pièces EA par poste : ne pas les additionner entre postes pour obtenir la production de la ligne.',
        'Les files sont des instantanés ouverture/fermeture. Le temps moyen de passage ne peut pas être déduit de ces seuls comptages. Absence de mesure = inconnue, pas zéro.',
        'Le modèle suppose un flux linéaire. Les transferts inter-postes réels nécessitent leur propre journal ; les flèches indiquent uniquement la séquence configurée.'
      ]))
