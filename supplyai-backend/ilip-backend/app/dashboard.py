"""Indicateurs historiques en lecture seule ; paramètres SQL liés, aucun DDL."""
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from .db import get_connection

router = APIRouter(prefix='/dashboard', tags=['Tableau de bord'])

SQL = """
WITH bounds AS (SELECT %s::date AS start_date, %s::date AS end_date),
months AS (
 SELECT m::date AS month, greatest(m::date,b.start_date) AS lo,
 least((m+interval '1 month - 1 day')::date,b.end_date) AS hi
 FROM bounds b, generate_series(date_trunc('month',b.start_date),date_trunc('month',b.end_date),interval '1 month') m
),
stock_dates AS (
 SELECT m.*, (SELECT max(snapshot_date) FROM ilip.inventory_levels WHERE snapshot_date<=m.hi) AS stock_date FROM months m
),
stock_items AS (
 SELECT m.month, s.item_id, sum(s.stock_on_hand) AS physical, sum(s.available_stock) AS available
 FROM stock_dates m JOIN ilip.inventory_levels s ON s.snapshot_date=m.stock_date GROUP BY m.month,s.item_id
),
stock AS (
 SELECT s.month, sum(s.physical*i.standard_unit_cost) AS stock_value_eur,
 count(*) FILTER (WHERE s.physical>0 AND i.standard_unit_cost IS NULL) AS missing_cost_items,
 count(*) FILTER (WHERE i.is_active AND s.available<i.safety_stock) AS below_safety_items,
 count(*) FILTER (WHERE i.is_active AND s.physical>i.max_stock) AS overstock_items,
 count(*) FILTER (WHERE NOT i.is_active AND s.physical>0) AS inactive_stock_items,
 count(*) AS stock_items
 FROM stock_items s JOIN ilip.items i USING(item_id) GROUP BY s.month
),
purchase_lines AS (
 SELECT m.month, l.po_line_id, p.po_number, l.ordered_qty, l.original_promised_delivery_date AS due,
 coalesce(sum(r.received_qty) FILTER (WHERE (r.received_at AT TIME ZONE 'Africa/Casablanca')::date<=m.hi),0) AS received_by_end,
 coalesce(sum(r.received_qty) FILTER (WHERE (r.received_at AT TIME ZONE 'Africa/Casablanca')::date<=l.original_promised_delivery_date),0) AS received_on_time
 FROM months m JOIN ilip.purchase_orders p ON p.order_date<=m.hi AND p.status NOT IN ('CANCELLED','DRAFT')
 JOIN ilip.purchase_order_lines l USING(po_number) LEFT JOIN ilip.purchase_receipts r USING(po_line_id)
 GROUP BY m.month,l.po_line_id,p.po_number
),
purchases AS (
 SELECT m.month, count(DISTINCT p.po_number) FILTER (WHERE p.received_by_end<p.ordered_qty) AS open_purchase_orders,
 count(*) FILTER (WHERE p.due BETWEEN m.lo AND m.hi) AS due_supplier_lines,
 count(*) FILTER (WHERE p.due BETWEEN m.lo AND m.hi AND p.received_on_time<p.ordered_qty) AS late_supplier_lines
 FROM months m LEFT JOIN purchase_lines p USING(month) GROUP BY m.month
),
production AS (
 SELECT m.month, count(p.production_order_id) AS planned_orders,
 coalesce(sum(p.planned_qty),0) AS planned_qty,
 coalesce(sum(p.actual_qty) FILTER (WHERE p.actual_end_date<=b.end_date),0) AS completed_qty,
 count(*) FILTER (WHERE p.actual_end_date<=b.end_date AND p.actual_end_date>p.planned_end_date) AS late_completed_orders,
 count(*) FILTER (WHERE p.planned_end_date<b.end_date AND (p.actual_end_date IS NULL OR p.actual_end_date>b.end_date)) AS overdue_unfinished_orders
 FROM months m CROSS JOIN bounds b LEFT JOIN ilip.production_orders p ON p.planned_end_date BETWEEN m.lo AND m.hi AND p.status NOT IN ('CANCELLED','DRAFT')
 GROUP BY m.month
),
customer_lines AS (
 SELECT m.month,l.customer_order_line_id,l.ordered_qty,
 coalesce(sum(s.delivered_qty) FILTER (WHERE (s.delivered_at AT TIME ZONE 'Africa/Casablanca')::date<=l.promised_delivery_date),0) AS on_time_qty
 FROM months m JOIN ilip.customer_order_lines l ON l.promised_delivery_date BETWEEN m.lo AND m.hi
 JOIN ilip.customer_orders c USING(customer_order_id)
 LEFT JOIN ilip.shipment_lines s USING(customer_order_line_id)
 WHERE c.status NOT IN ('CANCELLED','DRAFT')
 GROUP BY m.month,l.customer_order_line_id
),
logistics AS (
 SELECT month,count(*) AS due_customer_lines,count(*) FILTER (WHERE on_time_qty>=ordered_qty) AS otif_lines FROM customer_lines GROUP BY month
)
SELECT m.month,m.stock_date,s.stock_value_eur,s.missing_cost_items,s.below_safety_items,s.overstock_items,s.inactive_stock_items,s.stock_items,
 p.open_purchase_orders,p.due_supplier_lines,p.late_supplier_lines,
 r.planned_orders,r.planned_qty,r.completed_qty,r.late_completed_orders,r.overdue_unfinished_orders,
 coalesce(l.due_customer_lines,0) AS due_customer_lines,coalesce(l.otif_lines,0) AS otif_lines
FROM stock_dates m LEFT JOIN stock s USING(month) JOIN purchases p USING(month) JOIN production r USING(month) LEFT JOIN logistics l USING(month) ORDER BY m.month
"""

def ratio(numerator, denominator):
    return (Decimal(numerator)*100/Decimal(denominator)).quantize(Decimal('0.01')) if denominator else None

def summarize(rows):
    sums = {k: sum((r[k] or 0) for r in rows) for k in (
        'due_supplier_lines','late_supplier_lines','planned_orders','planned_qty','completed_qty',
        'late_completed_orders','overdue_unfinished_orders','due_customer_lines','otif_lines')}
    last = rows[-1]
    sums.update({k:last[k] for k in ('stock_date','stock_value_eur','missing_cost_items','below_safety_items','overstock_items','inactive_stock_items','stock_items','open_purchase_orders')})
    sums['otif_pct'] = ratio(sums['otif_lines'],sums['due_customer_lines'])
    sums['production_attainment_pct'] = ratio(sums['completed_qty'],sums['planned_qty'])
    for r in rows:
        r['otif_pct'] = ratio(r['otif_lines'],r['due_customer_lines'])
    return sums

@router.get('/overview')
def overview(start_date: date | None = None, end_date: date | None = None, conn=Depends(get_connection)):
    coverage=conn.execute('SELECT min(snapshot_date) AS first_date,max(snapshot_date) AS last_date FROM ilip.inventory_levels').fetchone()
    if not coverage['last_date']:
        raise HTTPException(404,'Aucune photographie de stock disponible pour définir la période.')
    start = start_date or coverage['first_date']
    end = end_date or coverage['last_date']
    if start>end or start<coverage['first_date'] or end>coverage['last_date'] or (end-start).days>366:
        raise HTTPException(422,'Choisir une période chronologique de 367 jours maximum comprise dans les dates de stock disponibles.')
    units=conn.execute("SELECT DISTINCT i.unit_of_measure FROM ilip.production_orders p JOIN ilip.items i USING(item_id) WHERE p.planned_end_date BETWEEN %s AND %s AND p.status NOT IN ('CANCELLED','DRAFT')",(start,end)).fetchall()
    monthly=conn.execute(SQL,(start,end)).fetchall()
    summary=summarize(monthly)
    unit=units[0]['unit_of_measure'] if len(units)==1 else None
    if len(units)>1:
        summary.update(planned_qty=None,completed_qty=None,production_attainment_pct=None)
        for row in monthly: row.update(planned_qty=None,completed_qty=None)
    # Chaînes décimales : préserver la précision de NUMERIC jusqu'au navigateur.
    def encode(v):
        if isinstance(v, Decimal): return str(v)
        if isinstance(v, dict): return {k:encode(x) for k,x in v.items()}
        if isinstance(v, list): return [encode(x) for x in v]
        return v
    return encode({'start_date':start,'end_date':end,'coverage':coverage,'production_unit':unit,
                   'summary':summary,'monthly':monthly,'synthetic_data':True,
                   'warnings':['Seuils, coûts standards, activité et exclusions des commandes annulées/brouillons utilisent le référentiel actuel.',
                               'Quantités réalisées : ordres de la cohorte prévue, terminés au plus tard à la fin de période. Pas de mesure des encours.',
                               'OTIF calculé par ligne client ; une livraison partielle ne compte pas comme complète.'] +
                              (['Plusieurs unités de production : totaux de quantités masqués.'] if len(units)>1 else [])})
