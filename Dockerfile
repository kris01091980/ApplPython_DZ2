FROM python:3.10-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]