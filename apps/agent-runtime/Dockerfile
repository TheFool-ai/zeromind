FROM node:22-bookworm-slim AS build
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY tsconfig.json ./
COPY src ./src
RUN pnpm build && pnpm prune --prod

FROM node:22-bookworm-slim
ENV NODE_ENV=production
WORKDIR /app
RUN groupadd --system zeromind && useradd --system --gid zeromind zeromind
COPY --from=build --chown=zeromind:zeromind /app/package.json ./
COPY --from=build --chown=zeromind:zeromind /app/node_modules ./node_modules
COPY --from=build --chown=zeromind:zeromind /app/dist ./dist
USER zeromind
ENTRYPOINT ["node", "dist/main.js"]

