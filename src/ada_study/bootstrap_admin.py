"""Bootstrap seguro e idempotente del administrador inicial (FINAL-02).

Problema que resuelve: `docker compose up --build` crea el ESQUEMA (servicio
`migrate`) pero NO crea usuarios: la tabla `users` nace vacía y el login
devuelve 401 genérico hasta que existe una cuenta admin. El CLI interactivo
(`python -m ada_study.cli`) exige consola TTY, lo que no siempre es posible
en despliegues de contenedores.

Mecanismo (activación EXPLÍCITA por entorno, nunca por defecto):

    ADA_ADMIN_EMAIL=admin@ejemplo.com
    ADA_ADMIN_DISPLAY_NAME=Administrador
    ADA_ADMIN_PASSWORD=...   (mínimo 12 caracteres, con dígito y letra)

Garantías (espejan el contrato del CLI interactivo, Spec 06 §37-44):

- Sin las tres variables el paso se OMITE (exit 0): jamás se crean
  credenciales por defecto ni inseguras.
- Configuración parcial → error fail-loud (exit 1): no se adivina nada.
- La contraseña se valida con `validate_password_strength` (mismo criterio
  que el CLI) y NUNCA se registra en logs ni en la auditoría.
- Idempotente: si la cuenta configurada ya es admin activa → no-op (exit 0).
- Sin elevación silenciosa: si el email existe con otro rol o estado →
  error (exit 1) SIN modificar ni duplicar nada.
- Sin administradores duplicados: solo se INSERTA cuando el email no existe.

Uso (lo ejecuta el servicio one-shot `bootstrap` de docker-compose):

    python -m ada_study.bootstrap_admin
"""

import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime

from ada_study.cli import validate_password_strength
from ada_study.contracts.identity import UserRecord
from ada_study.db.repository import CatalogRepository
from ada_study.domain.identity_service import hash_password

# Variables de entorno (todas opcionales COMO CONJUNTO; jamás con defaults)
ADMIN_EMAIL_ENV = "ADA_ADMIN_EMAIL"
ADMIN_DISPLAY_NAME_ENV = "ADA_ADMIN_DISPLAY_NAME"
ADMIN_PASSWORD_ENV = "ADA_ADMIN_PASSWORD"


class AdminBootstrapError(Exception):
    """Configuración o estado incompatible: aborta SIN crear ni modificar."""


async def ensure_initial_admin(
    repo: CatalogRepository, *, email: str, display_name: str, password: str
) -> str:
    """Alta idempotente del admin inicial sobre un repositorio dado.

    Devuelve "created" si insertó la cuenta, "exists" si ya era admin activa.
    Lanza `AdminBootstrapError` si el email existe con otro rol/estado (no
    eleva) o si la contraseña no cumple la política. Nunca duplica.
    """
    existing = await repo.get_user_by_email(email)
    if existing is not None:
        if existing.role == "admin" and existing.account_status == "active":
            return "exists"
        raise AdminBootstrapError(
            f"ya existe una cuenta con el correo {email} "
            f"(rol={existing.role}, estado={existing.account_status}); "
            "no se creó ni elevó ninguna cuenta"
        )
    if message := validate_password_strength(password):
        raise AdminBootstrapError(message)
    now = datetime.now(UTC).isoformat()
    record = UserRecord(
        user_id=f"usr_{uuid.uuid4().hex[:12]}",
        email=email,
        display_name=display_name,
        role="admin",
        account_status="active",
        password_hash=hash_password(password),
        created_at=now,
        updated_at=now,
    )
    await repo.create_user(record)
    return "created"


def _configured_admin(
    env: dict[str, str] | None = None,
) -> tuple[str, str, str] | None:
    """Lee la configuración del bootstrap; None si no se activó.

    Fail-loud: configuración parcial (algunas variables sí y otras no) es un
    error, no una omisión; un email vacío o sin "@" también.
    """
    source = os.environ if env is None else env
    email = (source.get(ADMIN_EMAIL_ENV) or "").strip()
    display_name = (source.get(ADMIN_DISPLAY_NAME_ENV) or "").strip()
    password = source.get(ADMIN_PASSWORD_ENV) or ""
    configured = [bool(email), bool(display_name), bool(password)]
    if not any(configured):
        return None
    if not all(configured):
        raise AdminBootstrapError(
            "configuración parcial: definen las tres variables completas o "
            f"ninguna ({ADMIN_EMAIL_ENV}, {ADMIN_DISPLAY_NAME_ENV}, "
            f"{ADMIN_PASSWORD_ENV})"
        )
    if "@" not in email:
        raise AdminBootstrapError(f"{ADMIN_EMAIL_ENV} no es un email válido")
    return email, display_name, password

async def bootstrap_admin(database_url: str, *, env: dict[str, str] | None = None) -> str:
    """Ejecuta el bootstrap sobre la base configurada.

    Devuelve "created" | "exists" | "skipped" (sin configuración). Lanza
    `AdminBootstrapError` ante configuración inválida o cuenta incompatible.
    """
    config = _configured_admin(env)
    if config is None:
        return "skipped"
    email, display_name, password = config
    # Import diferido: el módulo funciona sin sqlalchemy instalado hasta que
    # se activa el bootstrap (mismo criterio que db/create_schema.py).
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(database_url, echo=False)
    try:
        return await ensure_initial_admin(
            CatalogRepository(engine),
            email=email,
            display_name=display_name,
            password=password,
        )
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada: python -m ada_study.bootstrap_admin (sin argumentos).

    DATABASE_URL llega por entorno (docker-compose la fija por la red
    interna). Exit 0 = creado / ya existía / omitido; exit 1 = error.
    """
    del argv  # el comando no acepta argumentos: nada de secretos por CLI
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        print("ERROR: falta DATABASE_URL en el entorno.", file=sys.stderr)
        return 1
    try:
        result = asyncio.run(bootstrap_admin(database_url))
    except AdminBootstrapError as exc:
        print(f"ERROR de bootstrap del administrador: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI: mensaje claro sin traceback
        print(
            f"ERROR: no se pudo ejecutar el bootstrap: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 1
    if result == "created":
        print("Cuenta admin inicial creada (contraseña: solo por entorno).")
    elif result == "exists":
        print("La cuenta admin configurada ya existe; no se realizaron cambios.")
    else:
        print(
            "Bootstrap del admin omitido: no hay ADA_ADMIN_EMAIL/"
            "ADA_ADMIN_DISPLAY_NAME/ADA_ADMIN_PASSWORD configurados."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())