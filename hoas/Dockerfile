ARG BUILD_FROM
FROM $BUILD_FROM

WORKDIR /app

# Python + pip + bash installieren (HA Base ist Alpine)
RUN apk add --no-cache \
    python3 \
    py3-pip \
    bash

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY run.sh .

RUN chmod +x /app/run.sh

CMD ["/app/run.sh"]
