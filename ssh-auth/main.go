package main

import (
	"context"
	"fmt"
	"net"
	"os"
	"strconv"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"google.golang.org/grpc"
)

func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envInt(key string, fallback int) (int, error) {
	v := os.Getenv(key)
	if v == "" {
		return fallback, nil
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return 0, fmt.Errorf("%s: %w", key, err)
	}
	return n, nil
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "ssh-auth:", err)
		os.Exit(1)
	}
}

func run() error {
	log := newLogger()

	listen := env("CAELUS_SSH_RESOLVER_LISTEN", "127.0.0.1:50051")
	keyPath := env("CAELUS_SSH_RESOLVER_UPSTREAM_KEY_PATH", "/upstreamkey/ssh_upstream_key")
	dsn := os.Getenv("CAELUS_SSH_RESOLVER_DATABASE_URL")
	if dsn == "" {
		return fmt.Errorf("CAELUS_SSH_RESOLVER_DATABASE_URL is not set")
	}
	sidecarPort, err := envInt("CAELUS_SFTP_SIDECAR_PORT", 2222)
	if err != nil {
		return err
	}
	poolSize, err := envInt("CAELUS_SSH_RESOLVER_POOL_SIZE", 4)
	if err != nil {
		return err
	}
	timeoutMs, err := envInt("CAELUS_SSH_RESOLVER_STATEMENT_TIMEOUT_MS", 2000)
	if err != nil {
		return err
	}

	// Read once at startup, so a missing or unreadable key stops the process
	// instead of turning every SSH connection into a puzzle.
	upstreamKey, err := os.ReadFile(keyPath)
	if err != nil {
		return fmt.Errorf("upstream key: %w", err)
	}
	if len(upstreamKey) == 0 {
		return fmt.Errorf("upstream key %s is empty", keyPath)
	}

	db, err := openPool(context.Background(), dsn, poolSize, timeoutMs)
	if err != nil {
		return err
	}
	defer db.Close()

	listener, err := net.Listen("tcp", listen)
	if err != nil {
		return err
	}

	s := grpc.NewServer()
	register(s,
		&resolver{db: db, upstreamKey: upstreamKey, sidecarPort: sidecarPort, log: log},
		&health{db: db, log: log},
	)

	log.Info("ssh resolver listening",
		"addr", listen, "upstream_key", keyPath, "sidecar_port", sidecarPort)
	return s.Serve(listener)
}

// openPool bounds the database dependency: a small pool and a short statement
// timeout, so a slow database refuses connections quickly rather than hanging
// the edge. The client retries; the edge does not.
func openPool(ctx context.Context, dsn string, poolSize, timeoutMs int) (*pgxpool.Pool, error) {
	cfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		return nil, fmt.Errorf("database url: %w", err)
	}
	cfg.MaxConns = int32(poolSize)
	cfg.ConnConfig.RuntimeParams["statement_timeout"] = strconv.Itoa(timeoutMs)

	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, err
	}
	pingCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	if err := pool.Ping(pingCtx); err != nil {
		// Not fatal in principle -- the resolver fails closed and would
		// recover -- but a resolver that cannot reach the database at startup
		// is a misconfiguration far more often than an outage, and saying so
		// here beats discovering it as refused logins.
		return nil, fmt.Errorf("database: %w", err)
	}
	return pool, nil
}
