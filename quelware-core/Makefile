generate: generate-python generate-go

generate-python:
	@buf generate --template buf.gen.python.yaml

generate-go:
	@buf generate --template buf.gen.go.yaml --path proto/quelware/models/v1/user.proto --path proto/quelware/user/v1/user.proto --path proto/quelware/maintenance/v1/maintenance.proto --path proto/quelware/models/v1/configuration.proto --path proto/quelware/system_configuration/v1/system_configuration.proto

build:
	@buf build -o quelware.protoset

format:
	@buf format -w

lint:
	@buf lint
