package cmd

import (
	"context"
	"fmt"

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
		client, ctx, cleanup, err := newSysconfClient()
		if err != nil {
			return err
		}
		defer cleanup()

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
		client, ctx, cleanup, err := newSysconfClient()
		if err != nil {
			return err
		}
		defer cleanup()

		resp, err := client.GetUnitStatus(ctx, &sysconfv1.GetUnitStatusRequest{Label: args[0]})
		if err != nil {
			return fmt.Errorf("GetUnitStatus failed: %w", err)
		}
		fmt.Println(resp.Status)
		return nil
	},
}

var unitActivateCmd = &cobra.Command{
	Use:   "activate <label>",
	Short: "Drive a unit toward ACTIVE (resumes from MAINTENANCE)",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		return runUnitTransition(args[0], func(c sysconfv1.SystemConfigurationServiceClient, ctx context.Context, label string) (*modelsv1.Unit, error) {
			resp, err := c.ActivateUnit(ctx, &sysconfv1.ActivateUnitRequest{Label: label})
			if err != nil {
				return nil, err
			}
			return resp.Unit, nil
		})
	},
}

var unitDrainCmd = &cobra.Command{
	Use:   "drain <label>",
	Short: "Transition a unit to DRAINING",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		return runUnitTransition(args[0], func(c sysconfv1.SystemConfigurationServiceClient, ctx context.Context, label string) (*modelsv1.Unit, error) {
			resp, err := c.DrainUnit(ctx, &sysconfv1.DrainUnitRequest{Label: label})
			if err != nil {
				return nil, err
			}
			return resp.Unit, nil
		})
	},
}

var unitMaintainCmd = &cobra.Command{
	Use:   "maintain <label>",
	Short: "Transition a unit to MAINTENANCE (must be RELEASED)",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		return runUnitTransition(args[0], func(c sysconfv1.SystemConfigurationServiceClient, ctx context.Context, label string) (*modelsv1.Unit, error) {
			resp, err := c.MaintainUnit(ctx, &sysconfv1.MaintainUnitRequest{Label: label})
			if err != nil {
				return nil, err
			}
			return resp.Unit, nil
		})
	},
}

func newSysconfClient() (sysconfv1.SystemConfigurationServiceClient, context.Context, func(), error) {
	conn, err := dial()
	if err != nil {
		return nil, nil, nil, fmt.Errorf("failed to connect: %w", err)
	}
	ctx, err := contextWithPAT()
	if err != nil {
		conn.Close()
		return nil, nil, nil, err
	}
	return sysconfv1.NewSystemConfigurationServiceClient(conn), ctx, func() { conn.Close() }, nil
}

func runUnitTransition(label string, fn func(c sysconfv1.SystemConfigurationServiceClient, ctx context.Context, label string) (*modelsv1.Unit, error)) error {
	client, ctx, cleanup, err := newSysconfClient()
	if err != nil {
		return err
	}
	defer cleanup()
	unit, err := fn(client, ctx, label)
	if err != nil {
		return fmt.Errorf("transition failed: %w", err)
	}
	fmt.Printf("%s\t%s\n", unit.Label, unit.Status)
	return nil
}

func init() {
	rootCmd.AddCommand(unitCmd)
	unitCmd.AddCommand(unitListCmd, unitStatusCmd, unitActivateCmd, unitDrainCmd, unitMaintainCmd)
}
