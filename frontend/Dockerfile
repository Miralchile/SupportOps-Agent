FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
# npm install (not ci) keeps the build working even if the lockfile lags package.json.
RUN npm install

COPY . .

EXPOSE 5181

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
