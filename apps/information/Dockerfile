FROM node:22-bookworm-slim AS pi-build
WORKDIR /work/pi-runner
RUN corepack enable
COPY apps/agent-runtime/package.json apps/agent-runtime/pnpm-lock.yaml apps/agent-runtime/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/agent-runtime/tsconfig.json ./
COPY apps/agent-runtime/src ./src
RUN pnpm build && pnpm prune --prod

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/zeromind/.local/bin:${PATH}"
WORKDIR /app/information
RUN addgroup --system zeromind && adduser --system --ingroup zeromind zeromind
COPY apps/information/pyproject.toml ./
COPY apps/information/src ./src
RUN pip install --no-cache-dir .
COPY apps/information/alembic.ini ./
COPY apps/information/migrations ./migrations
COPY apps/information/scripts ./scripts
COPY apps/information/docs/examples /app/docs/examples
COPY --from=pi-build /usr/local/bin/node /usr/local/bin/node
COPY --from=pi-build /work/pi-runner/dist /app/pi-runner/dist
COPY --from=pi-build /work/pi-runner/node_modules /app/pi-runner/node_modules
COPY --from=pi-build /work/pi-runner/package.json /app/pi-runner/package.json
RUN mkdir -p /app/information/data && chown -R zeromind:zeromind /app
USER zeromind
EXPOSE 8000
CMD ["uvicorn", "zeromind.bootstrap.app:app", "--host", "0.0.0.0", "--port", "8000"]
