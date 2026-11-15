from datetime import date
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from .db import get_connection
from .models import Page, Item, InventoryPage, PurchaseOrder, ProductionOrder
from . import repositories as repo

router = APIRouter()
Connection = Annotated[object, Depends(get_connection)]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]
Filter = Annotated[str | None, Query(min_length=1, max_length=100)]


@router.get('/health', tags=['Diagnostic'])
def health():
    return {'status': 'ok', 'service': 'ilip-backend', 'version': '0.1.0'}


@router.get('/ready', tags=['Diagnostic'])
def ready(conn: Connection):
    # Vérifie les objets nécessaires à ce lot, pas seulement SELECT 1.
    conn.execute('SELECT item_id FROM ilip.items LIMIT 0')
    conn.execute('SELECT snapshot_date FROM ilip.inventory_levels LIMIT 0')
    conn.execute('SELECT po_number FROM ilip.purchase_orders LIMIT 0')
    conn.execute('SELECT supplier_id FROM ilip.suppliers LIMIT 0')
    conn.execute('SELECT production_order_id FROM ilip.production_orders LIMIT 0')
    return {'status': 'ready', 'database': 'connected', 'schema': 'ilip'}


@router.get('/items', response_model=Page[Item], tags=['Articles'])
def items(conn: Connection, limit: Limit = 50, offset: Offset = 0,
          q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
          category: Filter = None, active: bool | None = None):
    return repo.list_items(conn, limit, offset, q, category, active)


@router.get('/items/{item_id}', response_model=Item, tags=['Articles'])
def item(item_id: str, conn: Connection):
    result = repo.get_item(conn, item_id)
    if result is None: raise HTTPException(404, 'Article introuvable.')
    return result


@router.get('/inventory', response_model=InventoryPage, tags=['Stocks'])
def inventory(conn: Connection, limit: Limit = 50, offset: Offset = 0,
              snapshot_date: date | None = None, item_id: Filter = None, warehouse_id: Filter = None):
    """Une seule date par réponse : date demandée ou dernière date globale disponible."""
    return repo.list_inventory(conn, limit, offset, snapshot_date, item_id, warehouse_id)


@router.get('/purchase-orders', response_model=Page[PurchaseOrder], tags=['Achats'])
def purchases(conn: Connection, limit: Limit = 50, offset: Offset = 0,
              supplier_id: Filter = None, status: Filter = None):
    return repo.list_purchase_orders(conn, limit, offset, supplier_id, status)


@router.get('/production-orders', response_model=Page[ProductionOrder], tags=['Production'])
def production(conn: Connection, limit: Limit = 50, offset: Offset = 0,
               line_id: Filter = None, status: Filter = None):
    return repo.list_production_orders(conn, limit, offset, line_id, status)
