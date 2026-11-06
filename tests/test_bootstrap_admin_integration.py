"""Bootstrap del admin contra PostgreSQL REAL (FINAL-02).

Cubre el ciclo completo del mecanismo sobre la base efímera de test:
esquema rev. 3 → bootstrap crea el admin → idempotencia real (segunda
ejecución no-op) → login correcto → contraseña incorrecta rechazada →
persistencia del usuario tras "reiniciar" (engine nuevo, como al reiniciar
los contenedores). Se crea una base EFÍMERA (`ada_study_test_<hex>`) y
NUNCA se toca la base configurada en DATABASE_URL.
"""

import secrets
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from ada_study.bootstrap_admin import AdminBootstrapError, bootstrap_admin
from ada_study.db.create_schema import create_schema
from ada_study.db.repository import CatalogRepository
from ada_study.domain.identity_service import (
    IdentityService,
    InvalidCredentialsError,
)

pytest.importorskip("sqlalchemy")
pytest.importorskip("asyncpg")

pytestmark = pytest.mark.integration

ADMIN_PASSWORD = "Contrasena123"


def _env(email: str) -> dict[str, str]:
    """Entorno completo de bootstrap con email único por test."""
    return {
        "ADA_ADMIN_EMAIL": email,
        "ADA_ADMIN_DISPLAY_NAME": "Administrador",
        "ADA_ADMIN_PASSWORD": ADMIN_PASSWORD,
    }


def _database_url_from_project_config() -> str:
    """Resuelve la URL desde la configuración del repo (.env), no ambiental."""
    import os

    from ada_study.config import Settings

    saved = os.environ.pop("DATABASE_URL", None)
    try:
        return Settings().database_url.strip()
    finally:
        if saved is not None:
            os.environ["DATABASE_URL"] = saved


DATABASE_URL = _database_url_from_project_config()


@pytest.fixture(scope="module")
async def test_database_url():
    """Base EFÍMERA por módulo; nunca se toca la base configurada."""
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL no definida: se requiere PostgreSQL real")
    from sqlalchemy.engine import make_url

    url = make_url(DATABASE_URL)
    dbname = f"ada_study_test_{secrets.token_hex(4)}"
    admin_url = url.set(database="postgres")
    admin = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    finally:
        await admin.dispose()
    yield url.set(database=dbname).render_as_string(hide_password=False)
    drop = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with drop.connect() as conn:
            await conn.execute(text(f'DROP DATABASE "{dbname}" WITH (FORCE)'))
    finally:
        await drop.dispose()


@pytest.fixture()
async def schema_url(test_database_url):
    """Base efímera con el esquema rev. 3 aplicado (como el servicio migrate)."""
    assert await create_schema(test_database_url) == 0
    return test_database_url


async def _count_users(database_url: str) -> int:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            return (await conn.execute(text("SELECT count(*) FROM users"))).scalar_one()
    finally:
        await engine.dispose()


async def test_bootstrap_crea_admin_y_es_idempotente(schema_url):
    """Primera ejecución crea; segunda es no-op; un solo usuario en la base."""
    email = f"admin-{uuid.uuid4().hex[:8]}@test.local"
    assert await bootstrap_admin(schema_url, env=_env(email)) == "created"
    assert await _count_users(schema_url) == 1
    # Idempotencia REAL (servicio one-shot re-ejecutado en cada arranque):
    assert await bootstrap_admin(schema_url, env=_env(email)) == "exists"
    assert await _count_users(schema_url) == 1  # sin duplicados


async def test_login_y_persistencia_tras_reinicio(schema_url):
    """Login correcto; contraseña incorrecta rechazada; usuario persiste."""
    email = f"admin-{uuid.uuid4().hex[:8]}@test.local"
    assert await bootstrap_admin(schema_url, env=_env(email)) == "created"
    # "Reinicio": engine nuevo contra la misma base (como al reiniciar compose).
    engine = create_async_engine(schema_url)
    try:
        service = IdentityService(CatalogRepository(engine))
        token = await service.login(email=email, password=ADMIN_PASSWORD)
        validated = await service.validate_session(token)
        assert validated.role == "admin"
        assert validated.account_status == "active"
        with pytest.raises(InvalidCredentialsError):
            await service.login(email=email, password="Incorrecta1")
        with pytest.raises(InvalidCredentialsError):
            await service.login(email="nadie@test.local", password=ADMIN_PASSWORD)
    finally:
        await engine.dispose()


async def test_email_existente_con_otro_rol_no_se_eleva(schema_url):
    """Cuenta preexistente no admin: el bootstrap aborta sin modificar datos."""
    from datetime import UTC, datetime

    from ada_study.contracts.identity import UserRecord
    from ada_study.domain.identity_service import hash_password

    student_email = f"previo-{uuid.uuid4().hex[:8]}@test.local"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@test.local"
    assert await bootstrap_admin(schema_url, env=_env(admin_email)) == "created"
    engine = create_async_engine(schema_url)
    repo = CatalogRepository(engine)
    now = datetime.now(UTC).isoformat()
    await repo.create_user(
        UserRecord(
            user_id="usr_previo",
            email=student_email,
            display_name="Previo",
            role="student",
            account_status="active",
            password_hash=hash_password("ClavePrevia1"),
            created_at=now,
            updated_at=now,
        )
    )
    await engine.dispose()
    env = dict(_env(student_email))
    with pytest.raises(AdminBootstrapError):
        await bootstrap_admin(schema_url, env=env)
    # El estudiante sigue intacto (rol student) y el admin original no cambió:
    engine = create_async_engine(schema_url)
    try:
        async with engine.connect() as conn:
            student_role = (
                await conn.execute(
                    text("SELECT role FROM users WHERE email = :email"),
                    {"email": student_email},
                )
            ).scalar_one()
            rows_con_nuestros_emails = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM users "
                        "WHERE email IN (:student, :admin)"
                    ),
                    {"student": student_email, "admin": admin_email},
                )
            ).scalar_one()
    finally:
        await engine.dispose()
    assert student_role == "student"  # jamás elevado
    assert rows_con_nuestros_emails == 2  # sin duplicados ni filas extra