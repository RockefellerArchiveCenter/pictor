# pictor

A microservice to create image derivatives (JPG2000 and PDF files) and IIIF Manifests from digital content (TIFF files).

pictor is part of [Project Electron](https://github.com/RockefellerArchiveCenter/project_electron), an initiative to build sustainable, open and user-centered infrastructure for the archival management of digital records at the [Rockefeller Archive Center](http://rockarch.org/).

[![Build Status](https://travis-ci.org/RockefellerArchiveCenter/pictor.svg?branch=base)](https://travis-ci.org/RockefellerArchiveCenter/pictor)

## Setup

Install [git](https://git-scm.com/) and clone the repository

    $ git clone https://github.com/RockefellerArchiveCenter/aquila.git

Install [Docker](https://store.docker.com/search?type=edition&offering=community) and run docker-compose from the root directory

    $ cd pictor
    $ docker-compose up

Once the application starts successfully, you should be able to access the application in your browser at `http://localhost:8000`.

When you're done, shut down docker-compose

    $ docker-compose down

Or, if you want to remove all data

    $ docker-compose down -v

### Running Container on Docker for Apple silicon

Note that for some packages to install correctly in the Docker image, an Intel image needs to be run under emulation. Use the `docker-compose.m1.yml` instead of the default Docker compose file:

```
docker-compose -f docker-compose.m1.yml up
```

## Configuring
pictor configurations are stored in `/pictor/config.py`. This file is excluded from version control, and you will need to update this file with values for your local instance.

The first time the container is started, the example config file (`/pictor/config.py.example`) will be copied to create the config file if it doesn't already exist.
## Requirements

Using this repo requires having [Docker](https://store.docker.com/search?type=edition&offering=community) installed.

## Services
pictor receives content from an external service. It expects TIFF files that are in bags that
contain their ArchivesSpace RefID in the bag-info.txt file. For an example of what pictor expects to receive, see the `fixtures/` directory.

pictor has 6 services:
1. Prepare Bag: unpacks bags and adds all necessary data to the object.
2. Make JPG2000: creates JPG2000 derivatives from TIFF files.
3. Make PDF: creates concatenated PDF file from JPG2000 derivatives.
4. Make Manifest: creates a IIIF presentation manifest from JPG2000 files.
5. AWS Upload: uploads bags with derivatives and Manifest to Amazon Web Services (AWS).
6. Cleanup: removes bag files that have been processed.

### Routes

| Method | URL | Parameters | Response  | Behavior  |
|--------|-----|---|---|---|
|GET|/bags| |200|Return a list of bags|


## License

Code is released under an MIT License. See [LICENSE](LICENSE) for details.
