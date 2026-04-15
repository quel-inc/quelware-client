package cmd

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
)

var address string

var rootCmd = &cobra.Command{
	Use:   "quelware-admin",
	Short: "Admin CLI for quelware",
}

func init() {
	rootCmd.PersistentFlags().StringVar(&address, "address", "localhost:50051", "gRPC server address (host:port)")
}

func Execute() error {
	return rootCmd.Execute()
}

func dial() (*grpc.ClientConn, error) {
	return grpc.NewClient(address, grpc.WithTransportCredentials(insecure.NewCredentials()))
}

func contextWithPAT() (context.Context, error) {
	pat, err := loadPAT()
	if err != nil {
		return nil, err
	}
	md := metadata.Pairs("x-pat", pat)
	return metadata.NewOutgoingContext(context.Background(), md), nil
}

func loadPAT() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("failed to get home directory: %w", err)
	}
	path := filepath.Join(home, ".config", "quelware-admin", "pat")
	data, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("failed to read PAT from %s: %w", path, err)
	}
	pat := strings.TrimSpace(string(data))
	if pat == "" {
		return "", fmt.Errorf("PAT file is empty: %s", path)
	}
	return pat, nil
}
