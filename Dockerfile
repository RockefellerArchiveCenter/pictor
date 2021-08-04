FROM python:3.6

ENV PYTHONUNBUFFERED 1
RUN mkdir /code
RUN apt-get update -y && apt-get install -y ghostscript \
  ocrmypdf
WORKDIR /code
ADD requirements.txt /code/
RUN pip install --upgrade pip && pip install -r requirements.txt
ADD . /code/
