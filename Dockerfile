FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN echo '#!/bin/bash\n\
echo "Waiting for database..."\n\
sleep 5\n\
echo "Applying migrations..."\n\
alembic upgrade head\n\
echo "Starting bot..."\n\
python main.py' > /app/entrypoint.sh && \
chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]