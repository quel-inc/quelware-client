# quelware-admin

A command-line tool for administering a QuEL system — managing users, units, and maintenance jobs.
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

## Documentation

For the full command reference, see the [admin documentation](https://quel-inc.github.io/quelware-client/admin/).

## License

This project is licensed under the Apache License 2.0.
