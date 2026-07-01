# Admin

`quelware-admin` is a command-line tool for administrators of a QuEL system. It
manages users, inspects and transitions units, and drives maintenance jobs.

See [Access control](../concepts/access-control.md) for the roles, capabilities,
and unit statuses these commands operate on.

## Build

```sh
go build -o quelware-admin .
```

## Authentication

A Personal Access Token (PAT) with administrator privileges is required. Provide
it in one of the following ways:

- Place it at `~/.config/quelware-admin/pat`:

    ```sh
    mkdir -p ~/.config/quelware-admin
    echo "your-pat-here" > ~/.config/quelware-admin/pat
    ```

- Or set the `QUELWARE_ADMIN_PAT` environment variable (takes precedence over
  the file):

    ```sh
    export QUELWARE_ADMIN_PAT="your-pat-here"
    ```

## Global flags

These persistent flags apply to every command:

| Flag                    | Default            | Description                                                                                             |
| ----------------------- | ------------------ | ------------------------------------------------------------------------------------------------------- |
| `--address <host:port>` | `localhost:50051`  | gRPC server address. Set this to your control server; the default is only a placeholder for local use.  |
| `--unit-label <label>`  | `central-server`   | Value sent as the `x-unit-label` metadata.                                                              |

```sh
quelware-admin --address <host:port> <command> [flags]
```

The `--address` values shown throughout this page are placeholders. Use the
control-server address for your deployment (for example `192.0.2.1:50051`).

## `user` — user management

```sh
# List all users
quelware-admin --address <host:port> user list

# Add a user (prints a generated PAT for the new user)
quelware-admin --address <host:port> user add --user-id alice --role admin

# Update a user's role
quelware-admin --address <host:port> user update-role --user-id alice --role normal_user

# Revoke a user
quelware-admin --address <host:port> user revoke --user-id alice
```

`user add` prints a freshly generated PAT for the new user — share it with them
securely. `--user-id` and `--role` are required for `add` and `update-role`;
`revoke` requires `--user-id`.

### Roles

| Role              | Aliases      |
| ----------------- | ------------ |
| `normal_user`     | `normal`     |
| `privileged_user` | `privileged` |
| `admin`           | —            |

## `unit` — inspect and manage units

Units move through the lifecycle states `ACTIVE`, `DRAINING`, `MAINTENANCE`, and
`RELEASED`. The `unit` commands report and transition those states.

```sh
# List all units and their statuses
quelware-admin --address <host:port> unit list

# Print the status of a single unit
quelware-admin --address <host:port> unit status <label>

# Drive a unit toward ACTIVE (resumes from MAINTENANCE)
quelware-admin --address <host:port> unit activate <label>

# Transition a unit to DRAINING
quelware-admin --address <host:port> unit drain <label>

# Transition a unit to MAINTENANCE (the unit must be RELEASED)
quelware-admin --address <host:port> unit maintain <label>
```

`activate`, `drain`, and `maintain` accept either an explicit unit `<label>` or
the `--all` flag, which applies the transition to every unit in parallel. The
two are mutually exclusive.

```sh
# Transition every unit at once
quelware-admin --address <host:port> unit drain --all
quelware-admin --address <host:port> unit maintain --all
```

## `maintenance` — commissioning jobs

You typically commission the system when bringing it up for the first time (for
example, after power-on) or after adding a new control device.

`maintenance commission` runs the commissioning operation defined for the
system — for example, a system-wide time synchronization followed by linkup.
Every unit must be in `MAINTENANCE` before you start, so drain and maintain all
units first. Afterwards, bring the units back into service with
`unit activate --all` (required in some setups):

```sh
quelware-admin --address <host:port> unit drain --all
quelware-admin --address <host:port> unit maintain --all
quelware-admin --address <host:port> maintenance commission
quelware-admin --address <host:port> unit activate --all
```

By default, units whose link status is already healthy are preserved. Pass
`--from-scratch` to fully reset all state instead.

| Flag                         | Default | Description                                                            |
| ---------------------------- | ------- | ---------------------------------------------------------------------- |
| `--from-scratch`             | `false` | Fully reset all state instead of preserving units with a healthy link. |
| `--poll-interval <duration>` | `2s`    | Polling interval while waiting for the job to finish.                  |

`commission` starts a job and polls until it finishes. The job keeps running on
the server even if you interrupt the command; check on it later with its job ID:

```sh
quelware-admin --address <host:port> maintenance status <job_id>
```
