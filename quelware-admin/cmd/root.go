package cmd

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/spf13/cobra"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
)

const rpcTimeout = 15 * time.Second

var (
	address   string
	unitLabel string
	version   = "dev"
)

var rootCmd = &cobra.Command{
	Use:   "quelware-admin",
	Short: "Admin CLI for quelware",
}

func init() {
	rootCmd.Version = version
	rootCmd.PersistentFlags().StringVar(&address, "address", "localhost:50051", "gRPC server address (host:port)")
	rootCmd.PersistentFlags().StringVar(&unitLabel, "unit-label", "central-server", "Unit label for x-unit-label metadata")
}

func Execute() error {
	return rootCmd.Execute()
}

func dial() (*grpc.ClientConn, error) {
	return grpc.NewClient(address, grpc.WithTransportCredentials(insecure.NewCredentials()))
}

func contextWithPAT() (context.Context, context.CancelFunc, error) {
	pat, err := loadPAT()
	if err != nil {
		return nil, nil, err
	}
	md := metadata.Pairs("x-pat", pat, "x-unit-label", unitLabel)
	base := metadata.NewOutgoingContext(context.Background(), md)
	ctx, cancel := context.WithTimeout(base, rpcTimeout)
	return ctx, cancel, nil
}

func loadPAT() (string, error) {
	if pat := os.Getenv("QUELWARE_ADMIN_PAT"); pat != "" {
		return pat, nil
	}

	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("failed to get home directory: %w", err)
	}
	path := filepath.Join(home, ".config", "quelware-admin", "pat")
	data, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("failed to read PAT from %s (or set QUELWARE_ADMIN_PAT): %w", path, err)
	}
	pat := strings.TrimSpace(string(data))
	if pat == "" {
		return "", fmt.Errorf("PAT file is empty: %s", path)
	}
	return pat, nil
}
