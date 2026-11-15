from datetime import date
from decimal import Decimal
from typing import Generic, TypeVar
from pydantic import BaseModel, ConfigDict

T = TypeVar('T')


class Page(BaseModel, Generic[T]):
    total: int
    limit: int
    offset: int
    data: list[T]


class Item(BaseModel):
    item_id: str
    name: str
    category: str
    unit_of_measure: str
    standard_unit_cost: Decimal | None
    lead_time_days: int | None
    safety_stock: Decimal | None
    min_stock: Decimal | None
    max_stock: Decimal | None
    is_active: bool


class InventoryRow(BaseModel):
    inventory_id: str
    item_id: str
    item_name: str
    unit_of_measure: str
    warehouse_id: str
    snapshot_date: date
    stock_on_hand: Decimal
    reserved_stock: Decimal
    available_stock: Decimal


class InventoryPage(Page[InventoryRow]):
    snapshot_date: date | None


class PurchaseOrder(BaseModel):
    po_number: str
    supplier_id: str
    supplier_name: str
    order_date: date
    status: str
    is_emergency_purchase: bool


class ProductionOrder(BaseModel):
    production_order_id: str
    item_id: str
    line_id: str
    planned_qty: Decimal
    actual_qty: Decimal | None
    planned_start_date: date
    planned_end_date: date
    actual_start_date: date | None
    actual_end_date: date | None
    material_availability_status: str | None
    status: str
