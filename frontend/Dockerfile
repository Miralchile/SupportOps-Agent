FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

EXPOSE 5181

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
