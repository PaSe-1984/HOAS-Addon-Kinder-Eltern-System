ARG BUILD_FROM
FROM ${BUILD_FROM}

WORKDIR /app

# Python + venv + bash
RUN apk add --no-cache python3 py3-pip py3-virtualenv bash

# Create virtualenv and upgrade pip inside it
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
 && pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY run.sh /app/run.sh

RUN chmod +x /app/run.sh

CMD ["/app/run.sh"]
