# CRM Vocal — Next.js dev image (fallback dashboard).

FROM node:20-alpine

WORKDIR /app

# Install deps first for layer caching; source is bind-mounted at runtime.
COPY package.json package-lock.json ./
RUN npm install

EXPOSE 3000
CMD ["npm", "run", "dev"]
