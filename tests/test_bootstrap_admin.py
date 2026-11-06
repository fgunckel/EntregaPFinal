"""Pruebas del bootstrap del administrador inicial (FINAL-02).

Unitarias con fake de repositorio (sin PostgreSQL real): verifican el
contrato de seguridad del mecanismo —idempotencia, sin credenciales por
defecto, fail-loud ante configuración parcial, sin elevación silenciosa y
sin duplicados—. La integración con PostgreSQL real vive en
tests/test_bootstrap_admin_integration.py.
"""

import pytest

from ada_study.bootstrap_admin import (
    AdminBootstrapError,
    bootstrap_admin,
    ensure_initial_admin,
    main,
)
from ada_study.contracts.identity import AuditEvent, SessionRecord, UserRecord
from ada_study.domain.identity_service import (
    IdentityService,
    InvalidCredentialsError,
    hash_password,
    verify_password,
)

URL_FALSA = "postgresql+asyncpg://usuario:clave@localhost:5432/test"
ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORD = "Contrasena123"
ENV_COMPLETO = {
    "ADA_ADMIN_EMAIL": ADMIN_EMAIL,
    "ADA_ADMIN_DISPLAY_NAME": "Administrador",
    "ADA_ADMIN_PASSWORD": ADMIN_PASSWORD,
}


class FakeRepository:
    """Fake mínimo del contrato de identidad usado por el bootstrap/login."""

    def __init__(self) -> None:
        self.users: dict[str, UserRecord] = {}
        self.sessions: dict[str, SessionRecord] = {}
        self.audit: list[AuditEvent] = []

    async def create_user(self, record: UserRecord) -> None:
        self.users[record.user_id] = record

    async def get_user_by_email(self, email: str) -> UserRecord | None:
        return next((u for u in self.users.values() if u.email == email), None)

    async def get_user(self, user_id: str) -> UserRecord | None:
        return self.users.get(user_id)

    async def create_session(self, session: SessionRecord) -> None:
        self.sessions[session.session_id] = session

    async def get_session_by_token_hash(self, token_hash: str) -> SessionRecord | None:
        return next((s for s in self.sessions.values() if s.token_hash == token_hash), None)

    async def append_audit_event(self, event: AuditEvent) -> None:
        self.audit.append(event)


# ---------------------------------------------------------------------------
# Configuración por entorno (sin defaults, fail-loud)
# ---------------------------------------------------------------------------


async def test_sin_configuracion_se_omite():
    """Sin las tres variables: el paso se omite; jamás se crea nada."""
    assert await bootstrap_admin(URL_FALSA, env={}) == "skipped"


async def test_configuracion_parcial_falla():
    """Algunas variables sí y otras no: error explícito, sin adivinar."""
    for parcial in (
        {"ADA_ADMIN_EMAIL": ADMIN_EMAIL},
        {"ADA_ADMIN_EMAIL": ADMIN_EMAIL, "ADA_ADMIN_DISPLAY_NAME": "X"},
    ):
        with pytest.raises(AdminBootstrapError) as exc:
            await bootstrap_admin(URL_FALSA, env=parcial)
        assert "configuración parcial" in str(exc.value)


async def test_email_invalido_falla():
    env = dict(ENV_COMPLETO, ADA_ADMIN_EMAIL="sin-arroba")
    with pytest.raises(AdminBootstrapError):
        await bootstrap_admin(URL_FALSA, env=env)


# ---------------------------------------------------------------------------
# Alta, formato del hash y rol/estado
# ---------------------------------------------------------------------------


async def test_crea_admin_activo_con_hash_pbkdf2():
    repo = FakeRepository()
    assert await ensure_initial_admin(
        repo, email=ADMIN_EMAIL, display_name="Admin", password=ADMIN_PASSWORD
    ) == "created"
    user = repo.users[next(iter(repo.users))]
    assert user.role == "admin"
    assert user.account_status == "active"
    assert user.password_hash.startswith("pbkdf2_sha256$600000$")
    assert verify_password(ADMIN_PASSWORD, user.password_hash)


async def test_contraseña_debil_rechazada_sin_crear_nada():
    repo = FakeRepository()
    with pytest.raises(AdminBootstrapError):
        await ensure_initial_admin(
            repo, email=ADMIN_EMAIL, display_name="Admin", password="corta1"
        )
    assert repo.users == {}  # sin cuenta parcial ni hash residual

# ---------------------------------------------------------------------------
# Idempotencia y no duplicación
# ---------------------------------------------------------------------------


async def test_segunda_ejecucion_es_no_op_sin_duplicar():
    repo = FakeRepository()
    primero = await ensure_initial_admin(
        repo, email=ADMIN_EMAIL, display_name="Admin", password=ADMIN_PASSWORD
    )
    segundo = await ensure_initial_admin(
        repo, email=ADMIN_EMAIL, display_name="Admin", password=ADMIN_PASSWORD
    )
    assert (primero, segundo) == ("created", "exists")
    assert len(repo.users) == 1  # sin administradores duplicados


async def test_email_existente_no_admin_no_se_eleva():
    """Un email ya registrado con otro rol: error, sin modificar ni duplicar."""
    repo = FakeRepository()
    await repo.create_user(
        UserRecord(
            user_id="usr_student",
            email=ADMIN_EMAIL,
            display_name="Estudiante",
            role="student",
            account_status="active",
            password_hash=hash_password("OtraClave123"),
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
    )
    with pytest.raises(AdminBootstrapError) as exc:
        await ensure_initial_admin(
            repo, email=ADMIN_EMAIL, display_name="Admin", password=ADMIN_PASSWORD
        )
    assert "no se creó ni elevó" in str(exc.value)
    assert len(repo.users) == 1
    assert next(iter(repo.users.values())).role == "student"  # intacto


async def test_admin_suspendido_no_reactiva():
    """Admin existente pero suspendido: error (no reactiva ni duplica)."""
    repo = FakeRepository()
    await repo.create_user(
        UserRecord(
            user_id="usr_susp",
            email=ADMIN_EMAIL,
            display_name="Admin",
            role="admin",
            account_status="suspended",
            password_hash=hash_password(ADMIN_PASSWORD),
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
    )
    with pytest.raises(AdminBootstrapError):
        await ensure_initial_admin(
            repo, email=ADMIN_EMAIL, display_name="Admin", password=ADMIN_PASSWORD
        )
    assert next(iter(repo.users.values())).account_status == "suspended"


# ---------------------------------------------------------------------------
# Login real tras el bootstrap (IdentityService real)
# ---------------------------------------------------------------------------


async def test_login_del_admin_creado_funciona():
    repo = FakeRepository()
    await ensure_initial_admin(
        repo, email=ADMIN_EMAIL, display_name="Admin", password=ADMIN_PASSWORD
    )
    service = IdentityService(repo)
    token = await service.login(email=ADMIN_EMAIL, password=ADMIN_PASSWORD)
    assert token  # token opaco emitido
    validated = await service.validate_session(token)
    assert validated.role == "admin"
    assert validated.email == ADMIN_EMAIL


async def test_login_con_contraseña_incorrecta_rechazado():
    repo = FakeRepository()
    await ensure_initial_admin(
        repo, email=ADMIN_EMAIL, display_name="Admin", password=ADMIN_PASSWORD
    )
    service = IdentityService(repo)
    with pytest.raises(InvalidCredentialsError):
        await service.login(email=ADMIN_EMAIL, password="Incorrecta1")
    with pytest.raises(InvalidCredentialsError):
        await service.login(email="nadie@test.local", password=ADMIN_PASSWORD)


# ---------------------------------------------------------------------------
# CLI (python -m ada_study.bootstrap_admin): códigos de salida
# ---------------------------------------------------------------------------


def test_main_sin_configuracion_exit_0(monkeypatch):
    monkeypatch.delenv("ADA_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADA_ADMIN_DISPLAY_NAME", raising=False)
    monkeypatch.delenv("ADA_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("DATABASE_URL", URL_FALSA)
    assert main([]) == 0  # omitido, no es error


def test_main_con_configuracion_parcial_exit_1(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL_FALSA)
    monkeypatch.setenv("ADA_ADMIN_EMAIL", ADMIN_EMAIL)
    # display_name y password ausentes → fail-loud
    monkeypatch.delenv("ADA_ADMIN_DISPLAY_NAME", raising=False)
    monkeypatch.delenv("ADA_ADMIN_PASSWORD", raising=False)
    assert main([]) == 1


def test_main_sin_database_url_exit_1(monkeypatch):
    for var in ("ADA_ADMIN_EMAIL", "ADA_ADMIN_DISPLAY_NAME", "ADA_ADMIN_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert main([]) == 1