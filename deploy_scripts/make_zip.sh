#!/bin/bash
set -e

ZIP_DIR=$1
ZIP_NAME=$2

if [ ! -f $ZIP_DIR/$ZIP_NAME ]; then

  # remove unnecessary files
  rm -rf fixtures \
    .git \
    .github \
    .coverage \
    .flake8 \
    .gitignore \
    .pre-commit-config.yaml \
    cc-test-reporter \
    coverage.xml \
    docker-compose.yml \
    Dockerfile \
    entrypoint.sh \
    wait-for-it.sh
  find . -type d -name __pycache__ -exec rm -r {} \+

  # create zip file
  zip -r $ZIP_NAME .
  mkdir -p $ZIP_DIR
  mv $ZIP_NAME $ZIP_DIR/$ZIP_NAME

fi
