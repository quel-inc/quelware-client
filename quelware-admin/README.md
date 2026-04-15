# quelware-admin

A command-line tool for managing users on a QuEL system.
This tool is intended for administrators only.

## Build

```sh
go build -o quelware-admin .
```

## Setup

Place your Personal Access Token (PAT) at `~/.config/quelware-admin/pat`:

```sh
mkdir -p ~/.config/quelware-admin
echo "your-pat-here" > ~/.config/quelware-admin/pat
```

## Usage

```sh
quelware-admin --address <host:port> user <command> [flags]
```

### Commands

```sh
# List all users
quelware-admin --address localhost:50051 user list

# Add a user
quelware-admin --address localhost:50051 user add --user-id alice --role admin

# Update a user's role
quelware-admin --address localhost:50051 user update-role --user-id alice --role normal_user

# Revoke a user
quelware-admin --address localhost:50051 user revoke --user-id alice
```

### Roles

- `normal_user` (or `normal`)
- `privileged_user` (or `privileged`)
- `admin`

## License

This project is licensed under the Apache License 2.0.
