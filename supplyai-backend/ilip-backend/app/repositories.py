"""SQL explicite aligné sur ilip V1. Seules les valeurs viennent de l'utilisateur."""
from datetime import date

ITEM_COLUMNS = 'item_id,name,category,unit_of_measure,standard_unit_cost,lead_time_days,safety_stock,min_stock,max_stock,is_active'


def _page(conn, *, fields, source, conditions, params, order, limit, offset):
    # fields/source/order/conditions sont exclusivement des constantes internes.
    where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
    total = conn.execute('SELECT count(*) AS total FROM ' + source + where, params).fetchone()['total']
    rows = conn.execute('SELECT ' + fields + ' FROM ' + source + where + ' ORDER BY ' + order + ' LIMIT %s OFFSET %s', [*params, limit, offset]).fetchall()
    return {'total': total, 'limit': limit, 'offset': offset, 'data': rows}


def list_items(conn, limit=50, offset=0, q=None, category=None, active=None):
    conditions, params = [], []
    if q is not None:
        # Recherche littérale : %, _ et le caractère d'échappement ne deviennent pas des jokers.
        pattern = '%' + q.replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'
        conditions.append("(item_id ILIKE %s ESCAPE '!' OR name ILIKE %s ESCAPE '!')")
        params.extend([pattern, pattern])
    if category is not None:
        conditions.append('category = %s'); params.append(category)
    if active is not None:
        conditions.append('is_active = %s'); params.append(active)
    return _page(conn, fields=ITEM_COLUMNS, source='ilip.items', conditions=conditions, params=params, order='item_id', limit=limit, offset=offset)


def get_item(conn, item_id):
    return conn.execute('SELECT ' + ITEM_COLUMNS + ' FROM ilip.items WHERE item_id = %s', [item_id]).fetchone()


def list_inventory(conn, limit=50, offset=0, snapshot_date=None, item_id=None, warehouse_id=None):
    selected = snapshot_date
    if selected is None:
        selected = conn.execute('SELECT max(snapshot_date) AS snapshot_date FROM ilip.inventory_levels').fetchone()['snapshot_date']
    if selected is None:
        return {'total': 0, 'limit': limit, 'offset': offset, 'snapshot_date': None, 'data': []}
    conditions, params = ['s.snapshot_date = %s'], [selected]
    if item_id is not None: conditions.append('s.item_id = %s'); params.append(item_id)
    if warehouse_id is not None: conditions.append('s.warehouse_id = %s'); params.append(warehouse_id)
    result = _page(conn, fields='s.inventory_id,s.item_id,i.name AS item_name,i.unit_of_measure,s.warehouse_id,s.snapshot_date,s.stock_on_hand,s.reserved_stock,s.available_stock', source='ilip.inventory_levels s JOIN ilip.items i ON i.item_id=s.item_id', conditions=conditions, params=params, order='s.item_id,s.warehouse_id', limit=limit, offset=offset)
    return {**result, 'snapshot_date': selected}


def list_purchase_orders(conn, limit=50, offset=0, supplier_id=None, status=None):
    conditions, params = [], []
    if supplier_id is not None: conditions.append('p.supplier_id = %s'); params.append(supplier_id)
    if status is not None: conditions.append('p.status = %s'); params.append(status)
    return _page(conn, fields='p.po_number,p.supplier_id,s.name AS supplier_name,p.order_date,p.status,p.is_emergency_purchase', source='ilip.purchase_orders p JOIN ilip.suppliers s ON s.supplier_id=p.supplier_id', conditions=conditions, params=params, order='p.order_date DESC,p.po_number', limit=limit, offset=offset)


def list_production_orders(conn, limit=50, offset=0, line_id=None, status=None):
    conditions, params = [], []
    if line_id is not None: conditions.append('line_id = %s'); params.append(line_id)
    if status is not None: conditions.append('status = %s'); params.append(status)
    fields = 'production_order_id,item_id,line_id,planned_qty,actual_qty,planned_start_date,planned_end_date,actual_start_date,actual_end_date,material_availability_status,status'
    return _page(conn, fields=fields, source='ilip.production_orders', conditions=conditions, params=params, order='planned_start_date DESC,production_order_id', limit=limit, offset=offset)
