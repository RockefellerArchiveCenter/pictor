FROM python:3.6-buster

ENV PYTHONUNBUFFERED 1
RUN mkdir /code
RUN apt-get update -y && apt-get install -y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confnew ghostscript \ ocrmypdf
WORKDIR /code
ADD requirements.txt /code/
RUN pip install --upgrade pip && pip install -r requirements.txt
ADD . /code/
