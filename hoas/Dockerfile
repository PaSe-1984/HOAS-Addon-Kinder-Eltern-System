FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY run.sh .

RUN chmod +x /app/run.sh

CMD ["/app/run.sh"]
