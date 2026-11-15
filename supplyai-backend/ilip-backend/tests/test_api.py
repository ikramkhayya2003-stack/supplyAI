from datetime import date
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from psycopg import OperationalError
from app.main import app
from app.db import get_connection, make_pool
from app import repositories

ITEM = dict(item_id='WH-001', name='Faisceau', category='FINISHED_GOOD', unit_of_measure='EA',
            standard_unit_cost=Decimal('18.000000'), lead_time_days=3, safety_stock=Decimal('80'),
            min_stock=Decimal('80'), max_stock=Decimal('1500'), is_active=True)


class FakeConnection:
    def __init__(self, responses): self.responses = iter(responses); self.calls = []
    def execute(self, sql, params=None):
        self.calls.append((sql, params)); return self
    def fetchone(self): return next(self.responses)
    def fetchall(self): return next(self.responses)


@pytest.fixture
def client():
    # Ne démarre aucune connexion externe. Surcharge explicite de la dépendance.
    app.dependency_overrides[get_connection] = lambda: FakeConnection([])
    yield TestClient(app)
    app.dependency_overrides.clear()


def inject(fake): app.dependency_overrides[get_connection] = lambda: fake


def test_health_without_database(client):
    assert client.get('/health').json()['status'] == 'ok'


def test_items_and_decimal_precision(client):
    fake = FakeConnection([{'total': 37}, [ITEM]]); inject(fake)
    r = client.get('/items?limit=1')
    assert r.status_code == 200
    assert r.json()['total'] == 37
    assert r.json()['data'][0]['standard_unit_cost'] == '18.000000'
    assert fake.calls[1][1][-2:] == [1, 0]


@pytest.mark.parametrize('query', ['limit=0','limit=201','offset=-1','active=invalid','q='])
def test_invalid_parameters(client, query):
    assert client.get('/items?'+query).status_code == 422


def test_missing_item(client):
    inject(FakeConnection([None])); assert client.get('/items/UNKNOWN').status_code == 404


def test_search_is_parameterized(client):
    fake=FakeConnection([{'total':0},[]]);inject(fake)
    attack="x'; DROP TABLE ilip.items; --"
    assert client.get('/items',params={'q':attack}).status_code==200
    assert attack not in fake.calls[0][0]
    assert attack in fake.calls[0][1][0]


def test_literal_wildcards():
    fake=FakeConnection([{'total':0},[]]);repositories.list_items(fake,q='a_%!')
    assert fake.calls[0][1]==['%a!_!%!!%','%a!_!%!!%']


def test_inventory_empty_database(client):
    inject(FakeConnection([{'snapshot_date':None}]))
    assert client.get('/inventory').json()=={'total':0,'limit':50,'offset':0,'data':[],'snapshot_date':None}


def test_inventory_latest_date(client):
    row=dict(inventory_id='I1',item_id='WH-001',item_name='Faisceau',unit_of_measure='EA',warehouse_id='FG',snapshot_date=date(2025,12,31),stock_on_hand=Decimal('1'),reserved_stock=Decimal('0'),available_stock=Decimal('1'))
    fake=FakeConnection([{'snapshot_date':date(2025,12,31)},{'total':1},[row]]);inject(fake)
    r=client.get('/inventory');assert r.status_code==200
    assert r.json()['snapshot_date']=='2025-12-31'
    assert fake.calls[1][1]==[date(2025,12,31)]


def test_inventory_explicit_date_no_fallback(client):
    fake=FakeConnection([{'total':0},[]]);inject(fake)
    r=client.get('/inventory?snapshot_date=2030-01-01');assert r.status_code==200
    assert r.json()['snapshot_date']=='2030-01-01'
    assert len(fake.calls)==2


def test_bad_date(client):
    assert client.get('/inventory?snapshot_date=oops').status_code==422


def test_database_error_no_secret(client):
    class Broken:
        def execute(self,*a):raise OperationalError('postgresql://USER:SECRET@host/db')
    inject(Broken());r=client.get('/ready')
    assert r.status_code==503 and 'SECRET' not in r.text and 'postgresql://' not in r.text


def test_no_implicit_mock_mode():
    app.dependency_overrides.clear()
    app.state.pool=None
    r=TestClient(app).get('/items')
    assert r.status_code==503


def test_remote_tls_required():
    with pytest.raises(ValueError):make_pool('postgresql://u:p@example.com/db?sslmode=disable')


@pytest.mark.parametrize('path',['/items','/inventory','/purchase-orders','/production-orders'])
def test_no_write_routes(client,path):
    assert client.post(path,json={}).status_code==405


def test_documentation(client):
    assert client.get('/docs').status_code==200
    spec=client.get('/openapi.json').json()
    assert '/items/{item_id}' in spec['paths']
