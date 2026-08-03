# Docker Secrets Design

## Goal

ZeroMind loads production credentials from Docker Compose secret files instead
of embedding plaintext values in Compose environment variables or keeping them
in the project `.env` file. Development remains convenient, while production
fails closed when required credentials are absent.

This change improves protection against accidental disclosure through source
control, rendered Compose configuration, process environments, support bundles,
and routine diagnostics. It does not claim to protect secrets after an attacker
has obtained root access to a running application host or arbitrary code
execution inside a credential-bearing container.

## Scope

The first migration covers:

- PostgreSQL password;
- administrator password;
- administrator token signing secret;
- stored-credential encryption secret;
- Provider API keys, including `GLM_API_KEY`;
- webhook signing secrets;
- RSSHub route-provider credentials such as `TWITTER_AUTH_TOKEN`.

Redis authentication, secret rotation without restart, an external KMS, a
hosted secret manager, and multi-host orchestration are outside this change.

## Secret Sources and Compatibility

ZeroMind adopts the conventional `NAME_FILE` interface. A logical secret named
`GLM_API_KEY` is resolved in this order:

1. read the file named by `GLM_API_KEY_FILE` when that variable is present;
2. otherwise read `GLM_API_KEY` from the environment for development and
   backward compatibility;
3. otherwise report the secret as missing.

An explicitly configured file is authoritative. A missing, unreadable, empty,
or invalid file is an error and must not silently fall back to the plaintext
environment variable. Secret values have surrounding line endings removed,
but other whitespace is preserved. Paths are supplied by deployment
configuration rather than derived from user input.

The existing Provider Profile and webhook schemas continue storing logical
names such as `GLM_API_KEY` and `ZEROMIND_WEBHOOK_SECRET`. No database migration
or API compatibility break is required. A shared backend secret resolver is
used by Provider execution, webhook delivery, and application settings so the
rules cannot drift between subsystems.

## Production Compose Layout

Compose declares one secret per independently rotatable credential. Secret
source files live outside the repository, under a root-owned deployment
directory such as `/etc/zeromind/secrets`. The directory is mode `0700` and
individual files are mode `0600` on the host. The deployment documentation
must not prescribe storing secret values in `.env`.

Compose mounts only the secrets each service requires:

- `postgres`: PostgreSQL password through the image-supported
  `POSTGRES_PASSWORD_FILE` interface;
- `api`: database password, administrator password, token secret, and stored-
  credential encryption secret;
- `worker`: database password, stored-credential encryption secret, Provider
  API keys, and webhook secrets required by worker-owned execution paths;
- `scheduler` and `migrate`: database password only, plus another credential
  only if code inspection proves that service directly consumes it;
- `rsshub`: its route-provider credentials;
- `frontend` and `redis`: no application secrets in the current design.

Docker Compose file-backed secrets are mounted read-only under `/run/secrets`.
The Compose file contains only secret names and paths such as
`GLM_API_KEY_FILE=/run/secrets/glm_api_key`; it never interpolates secret
contents into an environment variable.

Because Compose file-backed secrets do not provide Swarm-style secret
management, operators must back up and transfer the host secret directory
separately using encrypted storage. This is an explicit operational boundary,
not an external KMS substitute.

## Database Connection

PostgreSQL and the backend consume the same `postgres_password` secret file.
Non-secret connection fields remain ordinary settings: driver, host, port,
database, and user. The backend constructs its SQLAlchemy URL after reading the
password through the shared resolver and URL-encodes the username and password.
Alembic uses the same construction path, preventing migration and runtime
configuration from diverging.

The existing full `ZEROMIND_DATABASE_URL` remains supported in development and
tests. In production, component fields plus
`ZEROMIND_DATABASE_PASSWORD_FILE` are required. A plaintext full database URL
must not be emitted by logs or validation errors.

## Application Settings

Sensitive settings are represented as secret references rather than eagerly
materialized environment values. Startup resolves secrets required by that
process and validates them before accepting work.

Production requirements are:

- administrator password is non-empty and is not `change-me`;
- token and credential encryption secrets are high-entropy values and are not
  development defaults;
- PostgreSQL password is non-empty;
- a Provider or webhook secret is resolved when its configured profile is used,
  allowing optional integrations to remain unconfigured;
- errors identify only the missing logical name or unreadable path, never the
  secret content.

Development and tests retain current defaults where necessary for fast local
execution. Production mode is selected by `ZEROMIND_ENVIRONMENT=production`
and fails closed.

## Credential Storage and Runtime Flow

Provider Profile creation continues accepting `api_key_env`; the label remains
for API compatibility but semantically identifies a logical secret name. When
an Agent runs, the gateway resolves that logical name, sends the value to the Pi
runner over its existing private child-process channel, and does not persist or
log it.

Webhook endpoints similarly retain `secret_env` and resolve it through the
shared resolver at delivery time.

RSSHub instance Access Keys remain encrypted in PostgreSQL. Their encryption
key is loaded from the `credential_secret` Docker secret instead of plaintext
environment configuration. Existing ciphertext remains decryptable as long as
the deployed secret value is unchanged.

RSSHub route-provider credentials are mounted directly into the RSSHub
container using the provider image's expected environment interface. If an
upstream image does not support `*_FILE`, a small, auditable entrypoint wrapper
may read only those mounted files immediately before starting RSSHub. This
exception is isolated to third-party compatibility and is documented because
the resulting child process may hold the value in its environment.

## Failure Behavior

- Required startup secret missing: the affected service exits before becoming
  ready.
- Configured secret file absent, unreadable, or empty: fail without environment
  fallback and report the logical secret name.
- Optional Provider or webhook secret missing: registration and listing remain
  available; execution or delivery fails with the existing sanitized missing-
  credential error.
- PostgreSQL secret mismatch: PostgreSQL or backend readiness fails visibly;
  no automatic password reset is attempted.
- Credential encryption secret mismatch: stored RSSHub Access Keys fail with a
  sanitized decryption error; data is not overwritten.

Readiness checks must not include secret values. Secret-resolution errors must
not be retried indefinitely when operator action is required.

## Rotation and Recovery

File-backed Compose secrets are refreshed by replacing the host file atomically
and recreating only consumers of that secret. A simple container restart is not
assumed to refresh a mounted secret in every Compose implementation.

Rotation order is credential-specific:

- Provider and webhook keys: update upstream, atomically replace the file,
  recreate consumers, then revoke the old value;
- administrator password and token secret: replace the file and recreate API;
  rotating the token secret intentionally invalidates existing sessions;
- PostgreSQL password: change the database role password in a controlled
  maintenance window, replace the file, then recreate database clients;
- credential encryption secret: decrypt and re-encrypt stored ciphertext in a
  controlled migration before retiring the old key. Merely replacing the file
  is prohibited while ciphertext exists.

Encrypted off-host backups must include PostgreSQL data and the secret source
files as separately protected artifacts. Restore procedures verify that the
credential encryption secret matches stored ciphertext before enabling writes.

## Testing and Verification

Backend unit tests cover file precedence, environment fallback, missing files,
empty files, newline trimming, sanitized errors, and production validation.
Provider and webhook tests prove that logical names resolve through `NAME_FILE`
without persisting secret values. Configuration tests prove runtime and Alembic
produce equivalent database URLs without logging them.

Compose verification renders the final configuration and asserts that secret
values do not appear, required services receive only their declared mounts, and
PostgreSQL uses `POSTGRES_PASSWORD_FILE`. An operational smoke test recreates
the stack from external secret files, verifies readiness, registers and invokes
a test Provider, and confirms that `docker inspect` does not expose its value.

## Migration

1. Create the external secret directory and populate root-owned files from the
   current `.env` values without printing them.
2. Deploy code that supports both `NAME_FILE` and legacy `NAME` sources.
3. Update Compose to mount secret files and set only `*_FILE` references.
4. Recreate services and run readiness plus Provider smoke tests.
5. Remove migrated plaintext values from the server `.env` and shell history.
6. Retain non-secret settings in `.env` and update examples and operations
   documentation.

Rollback restores the previous Compose configuration and the protected legacy
environment file. It must not rotate or alter actual credentials during the
same deployment, so rollback does not require an upstream credential rollback.

## Security Boundary

Docker secrets reduce accidental exposure and limit which containers receive a
credential. They do not protect against host root compromise, Docker daemon
compromise, or arbitrary code execution inside a container that legitimately
mounts the secret. Those threats require an external trust boundary such as a
managed secret service, KMS, TPM, or HSM and are intentionally deferred.
