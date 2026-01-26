ARG BUILD_FROM
FROM ${BUILD_FROM}

WORKDIR /app

RUN apk add --no-cache python3 py3-pip bash

COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY run.sh /app/run.sh

RUN chmod +x /app/run.sh

CMD ["/app/run.sh"]
