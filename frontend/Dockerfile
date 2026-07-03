# 1. Aşama: Projeyi derleme (Build)
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# 2. Aşama: Derlenen dosyaları hafif bir Node sunucusu ile servis etme
FROM node:20-alpine
WORKDIR /app
RUN npm install -g serve
# Üst aşamada oluşan 'dist' klasörünü buraya taşıyoruz
COPY --from=builder /app/dist ./dist

EXPOSE 3000

# Port 3000 üzerinden siteyi yayına alıyoruz
CMD ["serve", "-s", "dist", "-l", "3000"]
