FROM python:3.10-buster

ENV PYTHONUNBUFFERED 1
RUN mkdir /code
RUN apt-get update -y && apt-get install -y ghostscript \
  cmake \
  make \
  libtiff-dev \
  libtiff-tools \
  libzstd-dev \
  tesseract-ocr

# Download and compile openjpeg2.5
WORKDIR /tmp/openjpeg
RUN git clone https://github.com/uclouvain/openjpeg.git ./
RUN git checkout tags/v2.5.0
RUN cmake . && make && make install

WORKDIR /code
ADD requirements.txt /code/
RUN pip install --upgrade pip && pip install -r requirements.txt
ADD . /code/
