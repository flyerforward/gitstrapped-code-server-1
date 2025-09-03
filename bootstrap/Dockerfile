FROM python:3.11-alpine

# git for cloning
RUN apk add --no-cache git

WORKDIR /app
COPY app.py /app/app.py

# no external deps; just Flask
RUN pip install --no-cache-dir flask==3.0.3

EXPOSE 8080
CMD ["python", "/app/app.py"]
