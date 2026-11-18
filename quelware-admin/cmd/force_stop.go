package cmd

import (
	"fmt"
	"strings"

	"github.com/spf13/cobra"

	maintenancev1 "quelware-core-go/quelware/maintenance/v1"
)

var maintenanceForceStopCmd = &cobra.Command{
	Use:   "force-stop <unit>",
	Short: "Stop the wave units of a unit's ports, whichever session runs them",
	Long: "Stop the wave units of the given ports of a unit now, or of all its ports\n" +
		"without --port. The execution that runs on them fails; its session keeps\n" +
		"its lock and can arm again.",
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		unit := args[0]
		names, _ := cmd.Flags().GetStringSlice("port")
		req, err := forceStopRequest(unit, names)
		if err != nil {
			return err
		}

		client, cleanup, err := newMaintenanceClient()
		if err != nil {
			return err
		}
		defer cleanup()

		ctx, cancel, err := contextWithPAT()
		if err != nil {
			return err
		}
		defer cancel()

		resp, err := client.ForceStop(ctx, req)
		if err != nil {
			return fmt.Errorf("ForceStop failed: %w", err)
		}
		return printForceStop(req, resp.NotStoppedPortIds)
	},
}

func forceStopRequest(unit string, names []string) (*maintenancev1.ForceStopRequest, error) {
	if len(names) == 0 {
		return &maintenancev1.ForceStopRequest{UnitLabel: unit, AllPorts: true}, nil
	}
	ids := make([]string, 0, len(names))
	for _, name := range names {
		if !strings.Contains(name, ":") {
			name = unit + ":" + name
		} else if !strings.HasPrefix(name, unit+":") {
			return nil, fmt.Errorf("port %q is not of unit %q", name, unit)
		}
		ids = append(ids, name)
	}
	return &maintenancev1.ForceStopRequest{UnitLabel: unit, PortIds: ids}, nil
}

func printForceStop(req *maintenancev1.ForceStopRequest, notStopped []string) error {
	running := map[string]bool{}
	for _, id := range notStopped {
		running[id] = true
	}
	if req.AllPorts {
		for _, id := range notStopped {
			fmt.Printf("%s\tSTILL RUNNING\n", id)
		}
		if len(notStopped) == 0 {
			fmt.Printf("%s\tSTOPPED (all ports)\n", req.UnitLabel)
		}
	} else {
		for _, id := range req.PortIds {
			if running[id] {
				fmt.Printf("%s\tSTILL RUNNING\n", id)
			} else {
				fmt.Printf("%s\tSTOPPED\n", id)
			}
		}
	}
	if len(notStopped) > 0 {
		return fmt.Errorf("%d port(s) not stopped", len(notStopped))
	}
	return nil
}

func init() {
	maintenanceCmd.AddCommand(maintenanceForceStopCmd)
	maintenanceForceStopCmd.Flags().StringSlice("port", nil, "ports to stop, by name or id (default: all ports of the unit)")
}
