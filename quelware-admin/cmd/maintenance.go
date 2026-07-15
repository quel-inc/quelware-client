package cmd

import (
	"fmt"
	"sort"
	"strings"
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
	Short: "Run time sync then linkup",
	Long: "Run system-wide time sync then linkup. Each unit is expected to be in\n" +
		"MAINTENANCE before invocation (use `unit drain --all` + `unit maintain --all`\n" +
		"first). --reset-scope selects how much to reset: none (default) preserves\n" +
		"healthy units, control-units re-inits the control units while keeping the\n" +
		"clock distribution, all resets everything.",
	RunE: func(cmd *cobra.Command, args []string) error {
		resetScope, err := resolveResetScope(cmd)
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

		resp, err := client.StartCommission(ctx, &maintenancev1.StartCommissionRequest{
			ResetScope: resetScope,
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

		resp, err := client.GetMaintenanceJob(ctx, &maintenancev1.GetMaintenanceJobRequest{JobId: args[0]})
		if err != nil {
			return fmt.Errorf("GetMaintenanceJob failed: %w", err)
		}
		printJob(resp.Job)
		return nil
	},
}

var maintenanceInspectCmd = &cobra.Command{
	Use:   "inspect",
	Short: "Read per-unit diagnostic measurements",
	RunE: func(cmd *cobra.Command, args []string) error {
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

		resp, err := client.Inspect(ctx, &maintenancev1.InspectRequest{})
		if err != nil {
			return fmt.Errorf("Inspect failed: %w", err)
		}
		printInspection(resp.Units)
		return nil
	},
}

func resolveResetScope(cmd *cobra.Command) (maintenancev1.SyncResetScope, error) {
	if cmd.Flags().Changed("reset-scope") {
		scope, _ := cmd.Flags().GetString("reset-scope")
		switch scope {
		case "none":
			return maintenancev1.SyncResetScope_SYNC_RESET_SCOPE_NONE, nil
		case "control-units":
			return maintenancev1.SyncResetScope_SYNC_RESET_SCOPE_CONTROL_UNITS, nil
		case "all":
			return maintenancev1.SyncResetScope_SYNC_RESET_SCOPE_ALL, nil
		default:
			return 0, fmt.Errorf("invalid --reset-scope %q (want none|control-units|all)", scope)
		}
	}
	if fromScratch, _ := cmd.Flags().GetBool("from-scratch"); fromScratch {
		return maintenancev1.SyncResetScope_SYNC_RESET_SCOPE_ALL, nil
	}
	return maintenancev1.SyncResetScope_SYNC_RESET_SCOPE_NONE, nil
}

func newMaintenanceClient() (maintenancev1.MaintenanceServiceClient, func(), error) {
	conn, err := dial()
	if err != nil {
		return nil, nil, fmt.Errorf("failed to connect: %w", err)
	}
	return maintenancev1.NewMaintenanceServiceClient(conn), func() { conn.Close() }, nil
}

func pollUntilDone(client maintenancev1.MaintenanceServiceClient, jobID string, interval time.Duration) error {
	if interval <= 0 {
		interval = 2 * time.Second
	}
	fmt.Printf("Polling job %s. The job keeps running on the server even if you interrupt.\n", jobID)
	fmt.Printf("Check status later with: quelware-admin maintenance status %s\n", jobID)
	for {
		ctx, cancel, err := contextWithPAT()
		if err != nil {
			fmt.Println()
			return err
		}
		resp, err := client.GetMaintenanceJob(ctx, &maintenancev1.GetMaintenanceJobRequest{JobId: jobID})
		cancel()
		if err != nil {
			fmt.Println()
			return fmt.Errorf("GetMaintenanceJob failed: %w", err)
		}
		job := resp.Job
		switch job.Phase {
		case maintenancev1.JobPhase_JOB_PHASE_DONE:
			fmt.Println()
			printJob(job)
			return nil
		case maintenancev1.JobPhase_JOB_PHASE_FAILED:
			fmt.Println()
			printJob(job)
			return fmt.Errorf("job failed: %s", job.Error)
		}
		fmt.Print(".")
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
	printUnitProgress(job.UnitProgress)
}

var outcomeOrder = []maintenancev1.UnitOutcome{
	maintenancev1.UnitOutcome_UNIT_OUTCOME_OK,
	maintenancev1.UnitOutcome_UNIT_OUTCOME_SKIPPED,
	maintenancev1.UnitOutcome_UNIT_OUTCOME_FAILED,
}

var outcomeLabels = map[maintenancev1.UnitOutcome]string{
	maintenancev1.UnitOutcome_UNIT_OUTCOME_OK:      "OK",
	maintenancev1.UnitOutcome_UNIT_OUTCOME_SKIPPED: "SKIPPED",
	maintenancev1.UnitOutcome_UNIT_OUTCOME_FAILED:  "FAILED",
}

func outcomeLabel(o maintenancev1.UnitOutcome) string {
	if s, ok := outcomeLabels[o]; ok {
		return s
	}
	return o.String()
}

func printUnitProgress(progress []*maintenancev1.UnitProgress) {
	if len(progress) == 0 {
		return
	}
	counts := map[maintenancev1.UnitOutcome]int{}
	for _, p := range progress {
		counts[p.Outcome]++
	}
	parts := make([]string, 0, len(outcomeOrder))
	for _, oc := range outcomeOrder {
		if n := counts[oc]; n > 0 {
			parts = append(parts, fmt.Sprintf("%d %s", n, outcomeLabel(oc)))
		}
	}
	fmt.Printf("units  : %d (%s)\n", len(progress), strings.Join(parts, ", "))

	sorted := append([]*maintenancev1.UnitProgress(nil), progress...)
	sort.Slice(sorted, func(i, j int) bool { return sorted[i].UnitLabel < sorted[j].UnitLabel })
	for _, p := range sorted {
		if p.Detail != "" {
			fmt.Printf("  %s\t%s (%s)\n", p.UnitLabel, outcomeLabel(p.Outcome), p.Detail)
		} else {
			fmt.Printf("  %s\t%s\n", p.UnitLabel, outcomeLabel(p.Outcome))
		}
	}
}

func printInspection(units []*maintenancev1.UnitInspection) {
	if len(units) == 0 {
		fmt.Println("(no units)")
		return
	}
	sorted := append([]*maintenancev1.UnitInspection(nil), units...)
	sort.Slice(sorted, func(i, j int) bool { return sorted[i].UnitLabel < sorted[j].UnitLabel })
	for _, u := range sorted {
		keys := make([]string, 0, len(u.Measurements))
		for k := range u.Measurements {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		parts := make([]string, 0, len(keys))
		for _, k := range keys {
			parts = append(parts, fmt.Sprintf("%s=%s", k, u.Measurements[k]))
		}
		fmt.Printf("  %s\t%s\n", u.UnitLabel, strings.Join(parts, " "))
	}
}

func init() {
	rootCmd.AddCommand(maintenanceCmd)
	maintenanceCmd.AddCommand(maintenanceCommissionCmd, maintenanceStatusCmd, maintenanceInspectCmd)

	maintenanceCommissionCmd.Flags().String("reset-scope", "none", "how much to reset before re-syncing: none|control-units|all")
	maintenanceCommissionCmd.Flags().Bool("from-scratch", false, "deprecated: alias for --reset-scope all")
	_ = maintenanceCommissionCmd.Flags().MarkDeprecated("from-scratch", "use --reset-scope all")
	maintenanceCommissionCmd.Flags().Duration("poll-interval", 2*time.Second, "polling interval while waiting")
}
