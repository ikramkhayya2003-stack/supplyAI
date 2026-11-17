"""Analyses de département : lecture seule, même convention de période que l'overview."""
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from .db import get_connection
router=APIRouter(prefix='/dashboard/departments',tags=['Analyses départementales'])
QUERIES={
'inventory':"""WITH d AS (SELECT max(snapshot_date) AS dt FROM ilip.inventory_levels WHERE snapshot_date<=%s),
s AS (SELECT item_id,sum(stock_on_hand) physical,sum(available_stock) available,sum(reserved_stock) reserved FROM ilip.inventory_levels,d WHERE snapshot_date=d.dt GROUP BY item_id)
SELECT i.item_id,i.name,i.unit_of_measure,i.is_active,s.physical,s.reserved,s.available,i.safety_stock,i.max_stock,
s.physical*i.standard_unit_cost AS value_eur,
CASE WHEN NOT i.is_active AND s.physical>0 THEN 'INACTIF_AVEC_STOCK'
WHEN i.is_active AND s.available<i.safety_stock THEN 'SOUS_SECURITE'
WHEN i.is_active AND s.physical>i.max_stock THEN 'SURSTOCK'
WHEN i.safety_stock IS NULL OR i.max_stock IS NULL THEN 'SEUIL_INCOMPLET' ELSE 'NORMAL' END AS signal,
(i.is_active AND s.available<i.safety_stock) AS below_safety,
(i.is_active AND s.physical>i.max_stock) AS overstock
FROM s JOIN ilip.items i USING(item_id) ORDER BY i.item_id""",
'procurement':"""WITH lines AS (
SELECT p.supplier_id,l.po_line_id,l.ordered_qty,
coalesce(sum(r.received_qty) FILTER(WHERE (r.received_at AT TIME ZONE 'Africa/Casablanca')::date<=l.original_promised_delivery_date),0) AS on_time_qty
FROM ilip.purchase_order_lines l JOIN ilip.purchase_orders p USING(po_number)
LEFT JOIN ilip.purchase_receipts r USING(po_line_id)
WHERE l.original_promised_delivery_date BETWEEN %s AND %s AND p.status NOT IN ('DRAFT','CANCELLED')
GROUP BY p.supplier_id,l.po_line_id)
SELECT s.supplier_id,s.name,count(*) AS due_lines,
count(*) FILTER(WHERE on_time_qty>=ordered_qty) AS on_time_lines,
count(*) FILTER(WHERE on_time_qty<ordered_qty) AS late_lines,
round(100.0*count(*) FILTER(WHERE on_time_qty>=ordered_qty)/nullif(count(*),0),2) AS on_time_pct
FROM lines l JOIN ilip.suppliers s USING(supplier_id) GROUP BY s.supplier_id ORDER BY late_lines DESC,s.supplier_id""",
'production':"""SELECT p.line_id,i.unit_of_measure,count(*) AS planned_orders,sum(p.planned_qty) AS planned_qty,
coalesce(sum(p.actual_qty) FILTER(WHERE p.actual_end_date<=%s),0) AS completed_qty,
count(*) FILTER(WHERE p.actual_end_date<=%s AND p.actual_end_date>p.planned_end_date) AS late_completed_orders,
count(*) FILTER(WHERE p.planned_end_date<%s AND (p.actual_end_date IS NULL OR p.actual_end_date>%s)) AS overdue_unfinished_orders
FROM ilip.production_orders p JOIN ilip.items i USING(item_id)
WHERE p.planned_end_date BETWEEN %s AND %s AND p.status NOT IN ('CANCELLED','DRAFT')
GROUP BY p.line_id,i.unit_of_measure ORDER BY p.line_id,i.unit_of_measure""",
'logistics':"""WITH lines AS (
SELECT c.customer_id,l.customer_order_line_id,l.ordered_qty,
coalesce(sum(s.delivered_qty) FILTER(WHERE (s.delivered_at AT TIME ZONE 'Africa/Casablanca')::date<=l.promised_delivery_date),0) AS on_time_qty
FROM ilip.customer_order_lines l JOIN ilip.customer_orders c USING(customer_order_id)
LEFT JOIN ilip.shipment_lines s USING(customer_order_line_id)
WHERE l.promised_delivery_date BETWEEN %s AND %s AND c.status NOT IN ('CANCELLED','DRAFT')
GROUP BY c.customer_id,l.customer_order_line_id)
SELECT c.customer_id,c.name,count(*) AS due_lines,
count(*) FILTER(WHERE on_time_qty>=ordered_qty) AS otif_lines,
count(*) FILTER(WHERE on_time_qty<ordered_qty) AS failed_lines,
round(100.0*count(*) FILTER(WHERE on_time_qty>=ordered_qty)/nullif(count(*),0),2) AS otif_pct
FROM lines l JOIN ilip.customers c USING(customer_id) GROUP BY c.customer_id ORDER BY failed_lines DESC,c.customer_id"""
}
def parameters(department,start,end):
    if department=='inventory':return (end,)
    if department=='production':return (end,end,end,end,start,end)
    return (start,end)

def encode(v):
    if isinstance(v,Decimal):return str(v)
    if isinstance(v,dict):return {k:encode(x) for k,x in v.items()}
    if isinstance(v,list):return [encode(x) for x in v]
    return v

@router.get('/{department}')
def department_report(department:str,start_date:date|None=None,end_date:date|None=None,conn=Depends(get_connection)):
    if department not in QUERIES:raise HTTPException(404,'Département inconnu.')
    coverage=conn.execute('SELECT min(snapshot_date) AS first_date,max(snapshot_date) AS last_date FROM ilip.inventory_levels').fetchone()
    if not coverage['last_date']:raise HTTPException(404,'Aucune photographie de stock disponible.')
    start=start_date or coverage['first_date'];end=end_date or coverage['last_date']
    if start>end or start<coverage['first_date'] or end>coverage['last_date'] or (end-start).days>366:
        raise HTTPException(422,'Période invalide ou hors couverture du dataset ; 367 jours maximum.')
    rows=conn.execute(QUERIES[department],parameters(department,start,end)).fetchall()
    snapshot=None
    if department=='inventory':snapshot=conn.execute('SELECT max(snapshot_date) AS dt FROM ilip.inventory_levels WHERE snapshot_date<=%s',(end,)).fetchone()['dt']
    return encode(dict(department=department,start_date=start,end_date=end,coverage=coverage,snapshot_date=snapshot,data=rows,total=len(rows),synthetic_data=True))
