FROM node:22-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ARG VITE_GA_MEASUREMENT_ID=
ENV VITE_GA_MEASUREMENT_ID=$VITE_GA_MEASUREMENT_ID

RUN npm run build

FROM node:22-alpine AS runtime

WORKDIR /app

ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=3000

COPY package*.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=build /app/build ./build

EXPOSE 3000

CMD ["npm", "run", "start"]
