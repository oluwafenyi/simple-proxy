.PHONY: build run

build:
	docker-compose build

down:
	docker-compose down

run:down build
	docker-compose up proxy_server

test: down
	docker-compose up test