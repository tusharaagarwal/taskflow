FROM node:18-slim as builder
WORKDIR /app
COPY package*.json ./
RUN npm install --legacy-peer-deps
COPY . .

# Accept build-time API URL — Railway injects VITE_API_BASE as a build arg
ARG VITE_API_BASE=https://backend-production-701b.up.railway.app/api/v1
ENV VITE_API_BASE=$VITE_API_BASE

RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/templates/default.conf.template
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
