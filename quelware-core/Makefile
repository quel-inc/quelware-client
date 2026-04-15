generate: generate-python generate-go

generate-python:
	@buf generate --template buf.gen.python.yaml

generate-go:
	@buf generate --template buf.gen.go.yaml --path proto/quelware/models/v1/user.proto --path proto/quelware/user/v1/user.proto

build:
	@buf build -o quelware.protoset

format:
	@buf format -w

lint:
	@buf lint
