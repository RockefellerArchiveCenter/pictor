# Pictor

IIIF derivative generation microservice 

## Requirements

Using this repo requires having [Docker](https://store.docker.com/search?type=edition&offering=community) installed.


    $ docker-compose down


### Running Container on Docker for Apple silicon

Note that for some packages to install correctly in the Docker image, an Intel image needs to be run under emulation. Use the `docker-compose.m1.yml` instead of the default Docker compose file, e.g.,:

```
docker-compose -f docker-compose.m1.yml up
```

## License

Code is released under an MIT License. See [LICENSE](LICENSE) for details.
