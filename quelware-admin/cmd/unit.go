package cmd

import (
	"context"
	"fmt"
	"sync"

	"github.com/spf13/cobra"

	modelsv1 "quelware-core-go/quelware/models/v1"
	sysconfv1 "quelware-core-go/quelware/system_configuration/v1"
)

var unitCmd = &cobra.Command{
	Use:   "unit",
	Short: "Inspect and manage units",
}

var unitListCmd = &cobra.Command{
	Use:   "list",
	Short: "List all units and their statuses",
	RunE: func(cmd *cobra.Command, args []string) error {
		client, cleanup, err := newSysconfClient()
		if err != nil {
			return err
		}
		defer cleanup()

		ctx, cancel, err := contextWithPAT()
		if err != nil {
			return err
		}
		defer cancel()

		resp, err := client.ListUnits(ctx, &sysconfv1.ListUnitsRequest{})
		if err != nil {
			return fmt.Errorf("ListUnits failed: %w", err)
		}
		if len(resp.Units) == 0 {
			fmt.Println("(no units)")
			return nil
		}
		for _, u := range resp.Units {
			fmt.Printf("%s\t%s\n", u.Label, u.Status)
		}
		return nil
	},
}

var unitStatusCmd = &cobra.Command{
	Use:   "status <label>",
	Short: "Print the status of a single unit",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		client, cleanup, err := newSysconfClient()
		if err != nil {
			return err
		}
		defer cleanup()

		ctx, cancel, err := contextWithPAT()
		if err != nil {
			return err
		}
		defer cancel()

		resp, err := client.GetUnitStatus(ctx, &sysconfv1.GetUnitStatusRequest{Label: args[0]})
		if err != nil {
			return fmt.Errorf("GetUnitStatus failed: %w", err)
		}
		fmt.Println(resp.Status)
		return nil
	},
}

type unitTransitionFn func(c sysconfv1.SystemConfigurationServiceClient, ctx context.Context, label string) (*modelsv1.Unit, error)

var unitActivateCmd = &cobra.Command{
	Use:   "activate [<label>]",
	Short: "Drive a unit toward ACTIVE (resumes from MAINTENANCE)",
	Args:  cobra.MaximumNArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		return dispatchUnitTransition(cmd, args, func(c sysconfv1.SystemConfigurationServiceClient, ctx context.Context, label string) (*modelsv1.Unit, error) {
			resp, err := c.ActivateUnit(ctx, &sysconfv1.ActivateUnitRequest{Label: label})
			if err != nil {
				return nil, err
			}
			return resp.Unit, nil
		})
	},
}

var unitDrainCmd = &cobra.Command{
	Use:   "drain [<label>]",
	Short: "Transition a unit to DRAINING",
	Args:  cobra.MaximumNArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		return dispatchUnitTransition(cmd, args, func(c sysconfv1.SystemConfigurationServiceClient, ctx context.Context, label string) (*modelsv1.Unit, error) {
			resp, err := c.DrainUnit(ctx, &sysconfv1.DrainUnitRequest{Label: label})
			if err != nil {
				return nil, err
			}
			return resp.Unit, nil
		})
	},
}

var unitMaintainCmd = &cobra.Command{
	Use:   "maintain [<label>]",
	Short: "Transition a unit to MAINTENANCE (must be RELEASED)",
	Args:  cobra.MaximumNArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		return dispatchUnitTransition(cmd, args, func(c sysconfv1.SystemConfigurationServiceClient, ctx context.Context, label string) (*modelsv1.Unit, error) {
			resp, err := c.MaintainUnit(ctx, &sysconfv1.MaintainUnitRequest{Label: label})
			if err != nil {
				return nil, err
			}
			return resp.Unit, nil
		})
	},
}

func newSysconfClient() (sysconfv1.SystemConfigurationServiceClient, func(), error) {
	conn, err := dial()
	if err != nil {
		return nil, nil, fmt.Errorf("failed to connect: %w", err)
	}
	return sysconfv1.NewSystemConfigurationServiceClient(conn), func() { conn.Close() }, nil
}

func dispatchUnitTransition(cmd *cobra.Command, args []string, fn unitTransitionFn) error {
	all, _ := cmd.Flags().GetBool("all")
	if all && len(args) > 0 {
		return fmt.Errorf("--all and explicit label are mutually exclusive")
	}
	if !all && len(args) == 0 {
		return fmt.Errorf("must specify <label> or --all")
	}
	if all {
		return runUnitTransitionAll(fn)
	}
	return runUnitTransition(args[0], fn)
}

func runUnitTransition(label string, fn unitTransitionFn) error {
	client, cleanup, err := newSysconfClient()
	if err != nil {
		return err
	}
	defer cleanup()
	ctx, cancel, err := contextWithPAT()
	if err != nil {
		return err
	}
	defer cancel()
	unit, err := fn(client, ctx, label)
	if err != nil {
		return fmt.Errorf("transition failed: %w", err)
	}
	fmt.Printf("%s\t%s\n", unit.Label, unit.Status)
	return nil
}

func runUnitTransitionAll(fn unitTransitionFn) error {
	client, cleanup, err := newSysconfClient()
	if err != nil {
		return err
	}
	defer cleanup()

	listCtx, listCancel, err := contextWithPAT()
	if err != nil {
		return err
	}
	defer listCancel()
	listResp, err := client.ListUnits(listCtx, &sysconfv1.ListUnitsRequest{})
	if err != nil {
		return fmt.Errorf("ListUnits failed: %w", err)
	}

	type result struct {
		label  string
		status string
		err    error
	}
	results := make([]result, len(listResp.Units))
	var wg sync.WaitGroup
	for i, u := range listResp.Units {
		i, label := i, u.Label
		wg.Add(1)
		go func() {
			defer wg.Done()
			r := result{label: label}
			ctx, cancel, err := contextWithPAT()
			if err != nil {
				r.err = err
				results[i] = r
				return
			}
			defer cancel()
			unit, err := fn(client, ctx, label)
			if err != nil {
				r.err = err
			} else {
				r.status = string(unit.Status)
			}
			results[i] = r
		}()
	}
	wg.Wait()

	fails := 0
	for _, r := range results {
		if r.err != nil {
			fmt.Printf("%s\tERROR: %v\n", r.label, r.err)
			fails++
		} else {
			fmt.Printf("%s\t%s\n", r.label, r.status)
		}
	}
	if fails > 0 {
		return fmt.Errorf("%d unit(s) failed", fails)
	}
	return nil
}

func init() {
	rootCmd.AddCommand(unitCmd)
	unitCmd.AddCommand(unitListCmd, unitStatusCmd, unitActivateCmd, unitDrainCmd, unitMaintainCmd)

	for _, c := range []*cobra.Command{unitActivateCmd, unitDrainCmd, unitMaintainCmd} {
		c.Flags().Bool("all", false, "apply to all units in parallel")
	}
}
