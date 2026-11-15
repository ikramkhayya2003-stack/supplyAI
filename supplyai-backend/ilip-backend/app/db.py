from collections.abc import Iterator
from fastapi import HTTPException, Request
from psycopg import Connection, Error
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout


def make_pool(dsn: str) -> ConnectionPool | None:
    if not dsn.strip():
        return None
    # Parse sans afficher la chaîne, y compris en cas de mauvaise configuration.
    options = conninfo_to_dict(dsn)
    if not options.get('host'):
        raise ValueError('Hôte PostgreSQL requis.')
    if options['host'] not in ('localhost', '127.0.0.1', '::1'):
        if options.get('sslmode') not in ('require', 'verify-ca', 'verify-full'):
            raise ValueError('TLS requis pour une connexion distante.')
    return ConnectionPool(
        conninfo=dsn, min_size=0, max_size=3, open=False, timeout=8,
        reconnect_timeout=8, max_waiting=10,
        kwargs={'row_factory': dict_row, 'connect_timeout': 5,
                'application_name': 'ilip_backend', 'prepare_threshold': None},
    )


def get_connection(request: Request) -> Iterator[Connection]:
    pool = getattr(request.app.state, 'pool', None)
    if pool is None:
        raise HTTPException(503, 'Connexion non configurée : vérifier DATABASE_URL dans .env, puis redémarrer.')
    try:
        with pool.connection() as conn:
            with conn.transaction():
                # Même instantané pour le total, la date sélectionnée et les lignes.
                conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                conn.execute("SET LOCAL statement_timeout = '8000ms'")
                conn.execute("SET LOCAL TIME ZONE 'Africa/Casablanca'")
                yield conn
    except (Error, PoolTimeout):
        # Aucune chaîne de connexion, requête ou valeur sensible dans la réponse.
        raise HTTPException(503, 'Base indisponible ou schéma ILIP incompatible. Vérifier la connexion et le schéma.') from None
