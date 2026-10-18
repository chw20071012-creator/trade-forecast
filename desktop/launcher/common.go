package main

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

const baseURL = "http://127.0.0.1:8765"

var localClient = &http.Client{
	Timeout:       2 * time.Second,
	Transport:     &http.Transport{Proxy: nil},
	CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
}

func newSession() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return hex.EncodeToString(b), nil
}

func sessionHash(token string) string {
	h := sha256.Sum256([]byte(token))
	return hex.EncodeToString(h[:])
}

func healthMatches(body []byte, token string) bool {
	var h struct {
		Status          string `json:"status"`
		Application     string `json:"application"`
		DesktopInstance string `json:"desktop_instance"`
	}
	return json.Unmarshal(body, &h) == nil && h.Status == "ok" && h.Application == "trade_agent" && h.DesktopInstance == sessionHash(token)
}

func ownedHealth(token string) bool {
	r, err := localClient.Get(baseURL + "/health")
	if err != nil {
		return false
	}
	defer r.Body.Close()
	if r.StatusCode != http.StatusOK {
		return false
	}
	body, err := io.ReadAll(io.LimitReader(r.Body, 4096))
	return err == nil && healthMatches(body, token)
}

func requestShutdown(token string) (int, error) {
	req, err := http.NewRequest(http.MethodPost, baseURL+"/local/desktop/shutdown", nil)
	if err != nil {
		return 0, err
	}
	req.Header.Set("X-Desktop-Session", token)
	r, err := localClient.Do(req)
	if err != nil {
		return 0, err
	}
	defer r.Body.Close()
	_, _ = io.Copy(io.Discard, io.LimitReader(r.Body, 4096))
	if r.StatusCode != http.StatusOK {
		return r.StatusCode, fmt.Errorf("shutdown HTTP %d", r.StatusCode)
	}
	return r.StatusCode, nil
}

// Keep the portable application independent of unrelated Python/TradeAgent installs.
// Windows environment names are case insensitive.
func backendEnvironment(inherited []string, data, session string) []string {
	env := make([]string, 0, len(inherited)+8)
	for _, entry := range inherited {
		name := strings.ToUpper(strings.SplitN(entry, "=", 2)[0])
		if strings.HasPrefix(name, "PYTHON") || strings.HasPrefix(name, "TRADE_") || name == "VIRTUAL_ENV" || name == "PLAYWRIGHT_BROWSERS_PATH" {
			continue
		}
		env = append(env, entry)
	}
	return append(env, "TRADE_DATA_DIR="+data, "TRADE_DESKTOP_SESSION="+session,
		"TRADE_HOST=127.0.0.1", "TRADE_PORT=8765")
}
