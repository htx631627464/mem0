FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir .

EXPOSE 8765

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "mem0_agent_gateway.app:create_app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8765"]
