# Gym Server

Backend social de la app [gym-app](../gym-app): perfiles, seguir, copia en la nube de rutinas,
sesiones y ejercicios propios, rutinas destacadas, feed de actividad, bloqueo y reportes.
Diseño en el documento "Backend en la nube para perfiles sociales".

**Stack:** Python 3.13 + FastAPI + Pydantic, SQLAlchemy 2 (async) + Alembic, PostgreSQL en
Supabase, Supabase Auth (la API solo verifica el JWT) y Supabase Storage para las fotos.
Despliegue en Google Cloud Run desde GitHub Actions.

## Comandos

```bash
docker compose up -d              # Postgres local en el puerto 5433 (bases gym y gym_test)
uv sync                           # dependencias (uv descarga Python 3.13 si hace falta)
cp .env.example .env              # y rellenar SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY
uv run alembic upgrade head       # migraciones en la base de desarrollo
uv run uvicorn --factory app.main:create_app --reload   # API en http://localhost:8000 (docs en /docs)

uv run pytest                     # tests (dominio + API contra Postgres real, base gym_test)
uv run ruff check . && uv run ruff format --check . && uv run mypy app tests
uv run alembic revision --autogenerate -m "..."         # nueva migración tras cambiar app/repositories/tables.py
```

## Estructura

Igual que la app: dominio puro, casos de uso detrás de puertos y adaptadores.

```
app/domain/        reglas puras (username, visibilidad, sync last-writer-wins, cursores)
app/services/      casos de uso (ProfileService, FollowService, SyncService, FeedService...) y ports.py
app/repositories/  SQLAlchemy: único sitio que toca SQL (tables.py = esquema)
app/integrations/  Supabase Storage y Auth admin (httpx)
app/routers/       FastAPI: valida con Pydantic (JSON en camelCase) y llama a servicios
app/auth.py        verifica el JWT de Supabase con sus claves públicas (JWKS)
app/container.py   único sitio que elige adaptadores
migrations/        Alembic
tests/             pytest; conftest.py tiene fakes de Storage/Auth y genera tokens de prueba
```

## Reglas que conviene conocer

- **La app solo usa Supabase para iniciar sesión y subir la foto.** Todo lo demás pasa por esta API.
- **Sync:** `PUT /me/{routines|sessions|exercises}/{id}` es idempotente con el UUID del móvil y gana el
  `updatedAt` más reciente. Los borrados se suben como registros con `deletedAt`.
  `GET /me/changes?since=<cursor>` devuelve lo cambiado desde el cursor (`hasMore` = pedir otra vez).
- **Visibilidad:** rutinas y sesiones son `private` / `followers` / `public` (privadas por defecto).
  Un perfil privado solo muestra contenido a sus seguidores aceptados. Un bloqueo, en cualquier sentido,
  hace que cada uno vea al otro como inexistente (404).
- **Actividad:** se crea al compartir una rutina o una sesión (visibilidad distinta de `private`) y al
  empezar a seguir a alguien; desaparece al volver a privado, borrar o dejar de seguir.
- **Foto de perfil:** `POST /me/avatar-upload-url` → subir la imagen (512 px) a la URL firmada →
  `PATCH /me {"avatarUrl": ...}`. La anterior se borra sola.
- **Borrar cuenta:** `DELETE /me` borra todos los datos, las fotos y el usuario de Supabase Auth.
- **Reportes:** se guardan en la tabla `reports` (se revisan a mano en Supabase) y, si hay `RESEND_API_KEY`,
  llega un correo a `REPORTS_EMAIL` por cada uno. Si el correo falla, el reporte se guarda igual.
- **Política de privacidad:** `GET /privacy` (`?lang=es|en`, o según el navegador), en `app/legal/`. Al
  cambiarla, actualizar `PRIVACY_UPDATED` en `app/routers/legal.py`. El responsable sale de `PRIVACY_CONTACT`.
- **Límite de peticiones:** 120 por usuario y minuto (`RATE_LIMIT_PER_MINUTE`), en memoria por instancia.
- **RLS:** todas las tablas tienen Row Level Security activado sin políticas, para que la Data API de
  Supabase (clave anon) no pueda leerlas. La API se conecta como dueña de las tablas y no le afecta.

## Configurar Supabase (una vez)

1. Crear el proyecto en la región más cercana a los usuarios (la misma que Cloud Run).
2. **Authentication → Sign In / Providers:** email, Google y Apple (Apple es obligatorio en iOS si hay Google).
3. **Project Settings → JWT Keys:** usar claves asimétricas (*JWT signing keys*, ES256). La API no acepta
   el secreto compartido antiguo (HS256).
4. **Storage:** bucket público `avatars`, límite 1 MB, tipos `image/jpeg, image/png, image/webp`.
5. **Database → Connection string → Session pooler** (IPv4) como `DATABASE_URL`, cambiando el esquema a
   `postgresql+asyncpg://`.

## Despliegue (una vez)

1. En Google Cloud: proyecto con facturación, **alerta de presupuesto de 1 €**, APIs Cloud Run,
   Artifact Registry y Secret Manager. Repositorio Docker `gym` en Artifact Registry.
2. Secretos en Secret Manager: `gym-database-url`, `gym-supabase-service-role-key` y `gym-resend-api-key`
   (clave de Resend con permiso solo de envío).
3. Cuenta de servicio `gym-deployer` para GitHub con Workload Identity Federation (sin claves JSON, solo
   la rama `main` de este repo), con Cloud Run Admin, Artifact Registry Writer, acceso al secreto
   `gym-database-url` (migraciones) y Service Account User sobre `gym-runtime`.
   Cuenta `gym-runtime` para Cloud Run, con acceso solo a esos tres secretos.
4. Variables del repositorio en GitHub: `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_WORKLOAD_IDENTITY_PROVIDER`,
   `GCP_SERVICE_ACCOUNT`, `GCP_RUNTIME_SERVICE_ACCOUNT`, `SUPABASE_URL` y, tras el primer despliegue, `API_URL`
   (activa el ping de `keepalive.yml` cada 3 días para que Supabase no pause el proyecto).

Proyecto actual: `gym-server-6902`, región `us-east4` (Virginia, junto a Supabase `us-east-1`).

Con eso, cada push a `main` pasa los tests, construye la imagen, aplica las migraciones y despliega
(`max-instances=2`). Hasta que `GCP_PROJECT_ID` exista, el despliegue se salta.
