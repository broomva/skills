FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

# SQLite lives on a mounted volume in production so facts survive redeploys.
ENV SWAPIT_COMMONS_DB=/data/commons.db
VOLUME ["/data"]
EXPOSE 8080

# Run as a non-root user; give it ownership of the data volume mount point.
RUN useradd --system --uid 10001 swapit && mkdir -p /data && chown -R swapit:swapit /data /app
USER swapit

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
