"""Logical factory map based on master data and dated operational aggregates."""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from .db import get_connection
from .departments import QUERIES, parameters, encode
router=APIRouter(prefix='/dashboard',tags=['Factory overview'])
LINES_SQL="""SELECT l.line_id,l.plant_id,count(m.machine_id) AS machine_count
FROM ilip.production_lines l LEFT JOIN ilip.machines m USING(line_id)
GROUP BY l.line_id,l.plant_id ORDER BY l.plant_id,l.line_id"""
WAREHOUSES_SQL="""WITH d AS (
 SELECT max(snapshot_date) AS dt FROM ilip.inventory_levels WHERE snapshot_date<=%s
), stock AS (
 SELECT s.warehouse_id,count(*) AS reference_count,
 count(*) FILTER(WHERE i.is_active AND s.available_stock=0) AS zero_available_references,
 count(*) FILTER(WHERE NOT i.is_active AND s.stock_on_hand>0) AS inactive_stock_references,
 count(*) FILTER(WHERE s.stock_on_hand>0 AND i.standard_unit_cost IS NULL) AS missing_cost_references,
 coalesce(sum(s.stock_on_hand*i.standard_unit_cost),0) AS stock_value_eur
 FROM ilip.inventory_levels s JOIN ilip.items i USING(item_id) CROSS JOIN d
 WHERE s.snapshot_date=d.dt GROUP BY s.warehouse_id
)
SELECT w.warehouse_id,w.warehouse_name,w.plant_id,w.location_type,d.dt AS snapshot_date,
 s.reference_count,s.zero_available_references,s.inactive_stock_references,s.missing_cost_references,
 CASE WHEN s.missing_cost_references=0 THEN s.stock_value_eur END AS stock_value_eur
FROM ilip.warehouses w CROSS JOIN d LEFT JOIN stock s USING(warehouse_id)
ORDER BY w.plant_id,w.warehouse_id"""

@router.get('/factory-overview')
def factory_overview(start_date:date|None=None,end_date:date|None=None,conn=Depends(get_connection)):
    coverage=conn.execute('SELECT min(snapshot_date) AS first_date,max(snapshot_date) AS last_date FROM ilip.inventory_levels').fetchone()
    if not coverage['first_date'] or not coverage['last_date']:
        raise HTTPException(404,'Aucune photographie de stock pour définir la période.')
    start=start_date or coverage['first_date'];end=end_date or coverage['last_date']
    if start>end or start<coverage['first_date'] or end>coverage['last_date'] or (end-start).days>366:
        raise HTTPException(422,'Période invalide ou hors couverture ; maximum 367 jours.')
    plants=conn.execute('SELECT plant_id FROM ilip.plants ORDER BY plant_id').fetchall()
    lines=conn.execute(LINES_SQL).fetchall()
    production=conn.execute(QUERIES['production'],parameters('production',start,end)).fetchall()
    by_line={}
    for row in production: by_line.setdefault(row['line_id'],[]).append(row)
    for line in lines:
        groups=by_line.get(line['line_id'],[])
        line['quantities_by_unit']=groups
        for key in ['planned_orders','late_completed_orders','overdue_unfinished_orders']:
            line[key]=sum(row[key] for row in groups)
        line['period_status']=('NO_ACTIVITY' if line['planned_orders']==0 else 'OVERDUE' if line['overdue_unfinished_orders']>0 else 'HISTORICAL_DELAY' if line['late_completed_orders']>0 else 'NO_RECORDED_DELAY')
    warehouses=conn.execute(WAREHOUSES_SQL,(end,)).fetchall()
    return encode(dict(start_date=start,end_date=end,coverage=coverage,plants=plants,lines=lines,warehouses=warehouses,
        definitions={
          'map':'Organisation logique issue des identifiants de la base, pas implantation physique ni télémétrie.',
          'production':'OF dont la fin prévue appartient à la période. Quantités réalisées des OF terminés avant la fin sélectionnée. Les quantités restent séparées par unité.',
          'status':'Statut historique calculé depuis les retards de ces OF. Aucun état machine temps réel n’est déduit.',
          'warehouses':'Dernière photographie globale de stock disponible avant la fin. Aucune ligne à cette date signifie données absentes, pas entrepôt vide.',
          'zero_available':'Références actives avec disponible nul ; ne prouve pas une rupture par rapport à une demande.',
          'master_data':'Sites, lignes, machines et entrepôts du référentiel actuel. Nombre de machines enregistrées, pas nombre de machines en marche.'}))
