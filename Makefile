.PHONY: build run stop logs

build:
	sudo docker compose build

run:
	sudo docker compose up -d

stop:
	sudo docker compose down

logs:
	sudo docker compose logs -f

docs-build:
	mkdocs build

docs-serve:
	mkdocs serve