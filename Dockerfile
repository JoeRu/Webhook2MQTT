FROM tiangolo/meinheld-gunicorn-flask:latest

RUN apt-get update && apt-get install -y \
    python3-pip 

RUN /usr/local/bin/python -m pip install --upgrade pip
RUN pip3 install --upgrade Flask
RUN pip3 install paho-mqtt

COPY ./app /app
