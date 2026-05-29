# Next.js 16 backoffice — runs `next dev` for the demo.
FROM node:22-alpine

WORKDIR /app
RUN corepack enable

# Install deps first (cached layer). `--ignore-scripts` skips optional native
# build scripts (sharp/msw/unrs-resolver) which pnpm 10 otherwise treats as a
# fatal "ignored builds" error; `next dev` doesn't need them.
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --no-frozen-lockfile --ignore-scripts

COPY . .

EXPOSE 3000
CMD ["pnpm", "dev"]
