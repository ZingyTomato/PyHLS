FROM python:alpine

WORKDIR /PyHLS

COPY database.py database.py
COPY main.py main.py
COPY utils.py utils.py
COPY env.py env.py
COPY requirements.txt requirements.txt

EXPOSE 8000

RUN apk add ffmpeg --no-cache

RUN pip3 install -r requirements.txt

CMD ["python", "-m", "uvicorn", "app:app" , "--host", "0.0.0.0", "--port", "8000"]