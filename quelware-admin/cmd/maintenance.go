package cmd

import (
	"context"
	"fmt"
	"time"

	"github.com/spf13/cobra"

	maintenancev1 "quelware-core-go/quelware/maintenance/v1"
)

var maintenanceCmd = &cobra.Command{
	Use:   "maintenance",
	Short: "Trigger and observe maintenance jobs (commission)",
}

var maintenanceCommissionCmd = &cobra.Command{
	Use:   "commission",
	Short: "Drain all units, run time sync, then linkup",
	Long: "Drain all units, run system-wide time sync, then linkup each unit\n" +
		"in parallel. By default any unit whose link status reports healthy\n" +
		"is preserved; pass --from-scratch to fully reset.",
	RunE: func(cmd *cobra.Command, args []string) error {
		client, ctx, cleanup, err := newMaintenanceClient()
		if err != nil {
			return err
		}
		defer cleanup()

		fromScratch, _ := cmd.Flags().GetBool("from-scratch")
		resp, err := client.StartCommission(ctx, &maintenancev1.StartCommissionRequest{
			PreserveHealthy: !fromScratch,
		})
		if err != nil {
			return fmt.Errorf("StartCommission failed: %w", err)
		}
		fmt.Printf("Started commission job: %s\n", resp.JobId)

		pollInterval, _ := cmd.Flags().GetDuration("poll-interval")
		return pollUntilDone(client, resp.JobId, pollInterval)
	},
}

var maintenanceStatusCmd = &cobra.Command{
	Use:   "status <job_id>",
	Short: "Print the state of a maintenance job",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		client, ctx, cleanup, err := newMaintenanceClient()
		if err != nil {
			return err
		}
		defer cleanup()

		resp, err := client.GetMaintenanceJob(ctx, &maintenancev1.GetMaintenanceJobRequest{JobId: args[0]})
		if err != nil {
			return fmt.Errorf("GetMaintenanceJob failed: %w", err)
		}
		printJob(resp.Job)
		return nil
	},
}

func newMaintenanceClient() (maintenancev1.MaintenanceServiceClient, context.Context, func(), error) {
	conn, err := dial()
	if err != nil {
		return nil, nil, nil, fmt.Errorf("failed to connect: %w", err)
	}
	ctx, err := contextWithPAT()
	if err != nil {
		conn.Close()
		return nil, nil, nil, err
	}
	return maintenancev1.NewMaintenanceServiceClient(conn), ctx, func() { conn.Close() }, nil
}

func pollUntilDone(client maintenancev1.MaintenanceServiceClient, jobID string, interval time.Duration) error {
	if interval <= 0 {
		interval = 2 * time.Second
	}
	for {
		ctx, err := contextWithPAT()
		if err != nil {
			return err
		}
		resp, err := client.GetMaintenanceJob(ctx, &maintenancev1.GetMaintenanceJobRequest{JobId: jobID})
		if err != nil {
			return fmt.Errorf("GetMaintenanceJob failed: %w", err)
		}
		job := resp.Job
		fmt.Printf("  phase=%s\n", job.Phase)
		switch job.Phase {
		case maintenancev1.JobPhase_JOB_PHASE_DONE:
			printJob(job)
			return nil
		case maintenancev1.JobPhase_JOB_PHASE_FAILED:
			printJob(job)
			return fmt.Errorf("job failed: %s", job.Error)
		}
		time.Sleep(interval)
	}
}

func printJob(job *maintenancev1.MaintenanceJob) {
	if job == nil {
		fmt.Println("(no job)")
		return
	}
	fmt.Printf("job_id : %s\n", job.JobId)
	fmt.Printf("kind   : %s\n", job.Kind)
	fmt.Printf("phase  : %s\n", job.Phase)
	if job.StartedAt != nil {
		fmt.Printf("started: %s\n", job.StartedAt.AsTime().Format(time.RFC3339))
	}
	if job.FinishedAt != nil {
		fmt.Printf("ended  : %s\n", job.FinishedAt.AsTime().Format(time.RFC3339))
	}
	if job.Error != "" {
		fmt.Printf("error  : %s\n", job.Error)
	}
	for _, p := range job.UnitProgress {
		fmt.Printf("  unit=%s phase=%s outcome=%s detail=%s\n",
			p.UnitLabel, p.Phase, p.Outcome, p.Detail)
	}
}

func init() {
	rootCmd.AddCommand(maintenanceCmd)
	maintenanceCmd.AddCommand(maintenanceCommissionCmd, maintenanceStatusCmd)

	maintenanceCommissionCmd.Flags().Bool("from-scratch", false, "fully reset all state instead of preserving units with healthy link status")
	maintenanceCommissionCmd.Flags().Duration("poll-interval", 2*time.Second, "polling interval while waiting")
}
