FROM node:22-bookworm-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends python3 make g++ && rm -rf /var/lib/apt/lists/*
COPY package*.json ./
RUN npm install --omit=dev
COPY server.js ./
RUN mkdir -p /app/data
ENV NODE_ENV=production
EXPOSE 8787
CMD ["npm","start"]
