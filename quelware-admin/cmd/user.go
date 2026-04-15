package cmd

import (
	"fmt"
	"strings"

	"github.com/spf13/cobra"

	modelsv1 "quelware-core-go/quelware/models/v1"
	userv1 "quelware-core-go/quelware/user/v1"
)

var userCmd = &cobra.Command{
	Use:   "user",
	Short: "Manage users",
}

var addUserCmd = &cobra.Command{
	Use:   "add",
	Short: "Add a new user",
	RunE: func(cmd *cobra.Command, args []string) error {
		userID, _ := cmd.Flags().GetString("user-id")
		roleStr, _ := cmd.Flags().GetString("role")

		role, err := parseRole(roleStr)
		if err != nil {
			return err
		}

		conn, err := dial()
		if err != nil {
			return fmt.Errorf("failed to connect: %w", err)
		}
		defer conn.Close()

		ctx, err := contextWithPAT()
		if err != nil {
			return err
		}

		client := userv1.NewUserServiceClient(conn)
		resp, err := client.AddUser(ctx, &userv1.AddUserRequest{
			UserId: userID,
			Role:   role,
		})
		if err != nil {
			return fmt.Errorf("AddUser failed: %w", err)
		}

		fmt.Printf("User added: %s\n", resp.UserId)
		fmt.Printf("Generated PAT: %s\n", resp.GeneratedPat)
		return nil
	},
}

var updateUserRoleCmd = &cobra.Command{
	Use:   "update-role",
	Short: "Update a user's role",
	RunE: func(cmd *cobra.Command, args []string) error {
		userID, _ := cmd.Flags().GetString("user-id")
		roleStr, _ := cmd.Flags().GetString("role")

		role, err := parseRole(roleStr)
		if err != nil {
			return err
		}

		conn, err := dial()
		if err != nil {
			return fmt.Errorf("failed to connect: %w", err)
		}
		defer conn.Close()

		ctx, err := contextWithPAT()
		if err != nil {
			return err
		}

		client := userv1.NewUserServiceClient(conn)
		resp, err := client.UpdateUserRole(ctx, &userv1.UpdateUserRoleRequest{
			UserId:  userID,
			NewRole: role,
		})
		if err != nil {
			return fmt.Errorf("UpdateUserRole failed: %w", err)
		}

		fmt.Printf("Success: %v\n", resp.Success)
		if resp.Message != "" {
			fmt.Printf("Message: %s\n", resp.Message)
		}
		return nil
	},
}

var revokeUserCmd = &cobra.Command{
	Use:   "revoke",
	Short: "Revoke a user",
	RunE: func(cmd *cobra.Command, args []string) error {
		userID, _ := cmd.Flags().GetString("user-id")

		conn, err := dial()
		if err != nil {
			return fmt.Errorf("failed to connect: %w", err)
		}
		defer conn.Close()

		ctx, err := contextWithPAT()
		if err != nil {
			return err
		}

		client := userv1.NewUserServiceClient(conn)
		resp, err := client.RevokeUser(ctx, &userv1.RevokeUserRequest{
			UserId: userID,
		})
		if err != nil {
			return fmt.Errorf("RevokeUser failed: %w", err)
		}

		fmt.Printf("Success: %v\n", resp.Success)
		if resp.Message != "" {
			fmt.Printf("Message: %s\n", resp.Message)
		}
		return nil
	},
}

var listUsersCmd = &cobra.Command{
	Use:   "list",
	Short: "List all users",
	RunE: func(cmd *cobra.Command, args []string) error {
		conn, err := dial()
		if err != nil {
			return fmt.Errorf("failed to connect: %w", err)
		}
		defer conn.Close()

		ctx, err := contextWithPAT()
		if err != nil {
			return err
		}

		client := userv1.NewUserServiceClient(conn)
		resp, err := client.ListUsers(ctx, &userv1.ListUsersRequest{})
		if err != nil {
			return fmt.Errorf("ListUsers failed: %w", err)
		}

		if len(resp.Users) == 0 {
			fmt.Println("No users found.")
			return nil
		}

		for _, u := range resp.Users {
			fmt.Printf("%s\t%s\n", u.UserId, u.Role)
		}
		return nil
	},
}

func init() {
	rootCmd.AddCommand(userCmd)
	userCmd.AddCommand(addUserCmd, updateUserRoleCmd, revokeUserCmd, listUsersCmd)

	addUserCmd.Flags().String("user-id", "", "User ID")
	addUserCmd.Flags().String("role", "", "Role (normal_user, privileged_user, admin)")
	addUserCmd.MarkFlagRequired("user-id")
	addUserCmd.MarkFlagRequired("role")

	updateUserRoleCmd.Flags().String("user-id", "", "User ID")
	updateUserRoleCmd.Flags().String("role", "", "New role (normal_user, privileged_user, admin)")
	updateUserRoleCmd.MarkFlagRequired("user-id")
	updateUserRoleCmd.MarkFlagRequired("role")

	revokeUserCmd.Flags().String("user-id", "", "User ID")
	revokeUserCmd.MarkFlagRequired("user-id")
}

func parseRole(s string) (modelsv1.UserRole, error) {
	switch strings.ToLower(s) {
	case "normal_user", "normal":
		return modelsv1.UserRole_USER_ROLE_NORMAL_USER, nil
	case "privileged_user", "privileged":
		return modelsv1.UserRole_USER_ROLE_PRIVILEGED_USER, nil
	case "admin":
		return modelsv1.UserRole_USER_ROLE_ADMIN, nil
	default:
		return 0, fmt.Errorf("unknown role %q (valid: normal_user, privileged_user, admin)", s)
	}
}
