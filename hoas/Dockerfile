ARG BUILD_FROM=python:3.11-slim
FROM ${BUILD_FROM}

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY run.sh .

RUN chmod +x /app/run.sh

CMD ["/app/run.sh"]
