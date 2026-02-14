### Makefile --- 

## Author: shell@mpb21
## Version: $Id: Makefile,v 0.0 2024/01/24 05:22:23 shell Exp $
## Keywords: 
## X-URL: 

all: clean build

clean:
	-docker rmi -f dkai:latest

update:
	docker pull debian:13-slim

build: update
	docker build -t dkai . -f Dockerfile

### Makefile ends here
