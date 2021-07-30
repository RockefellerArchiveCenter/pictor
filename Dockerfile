FROM python:3.6

ENV PYTHONUNBUFFERED 1
RUN mkdir /code
RUN apt-get update -y && apt-get install -y wget \
  build-essential \
  git \
  unzip \
  cmake \
  make \
  pkg-config \
  libtiff-dev \
  libqpdf-dev \
  libmagic-dev \
  ghostscript \
  ocrmypdf
WORKDIR /code
ADD requirements.txt /code/
RUN pip install --upgrade pip setuptools wheel && pip install -r requirements.txt
ADD . /code/
