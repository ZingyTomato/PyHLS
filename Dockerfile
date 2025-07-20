FROM python:alpine

WORKDIR /PyHLS

COPY PyHLS/database.py database.py
COPY PyHLS/main.py main.py
COPY PyHLS/utils.py utils.py
COPY PyHLS/env.py env.py
COPY requirements.txt requirements.txt

EXPOSE 8000

RUN apk add ffmpeg --no-cache

RUN pip3 install -r requirements.txt

CMD ["python", "-m", "uvicorn", "main:app" , "--host", "0.0.0.0", "--port", "8000"]