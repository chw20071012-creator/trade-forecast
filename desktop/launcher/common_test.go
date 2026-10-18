package main

import (
	"fmt"
	"io"
	"net/http"
	"strings"
	"testing"
)

type testTransport func(*http.Request) (*http.Response, error)

func (f testTransport) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func TestShutdownPreservesBusyResultAndUsesHeader(t *testing.T) {
	previous := localClient
	defer func() { localClient = previous }()
	localClient = &http.Client{Transport: testTransport(func(r *http.Request) (*http.Response, error) {
		if r.URL.Host != "127.0.0.1:8765" || r.URL.Path != "/local/desktop/shutdown" || r.Method != http.MethodPost {
			t.Errorf("unexpected shutdown destination: %s %s", r.Method, r.URL)
		}
		if r.Header.Get("X-Desktop-Session") != "private-token" || strings.Contains(r.URL.String(), "private-token") {
			t.Error("shutdown token must only be sent in its designated header")
		}
		return &http.Response{StatusCode: 409, Body: io.NopCloser(strings.NewReader(`{"detail":"tasks running"}`)), Header: make(http.Header)}, nil
	})}
	code, err := requestShutdown("private-token")
	if code != 409 || err == nil {
		t.Fatal("busy shutdown must remain distinguishable from success")
	}
}

func TestHealthRejectsUnownedServers(t *testing.T) {
	token := "this-launcher-only"
	good := fmt.Sprintf(`{"status":"ok","application":"trade_agent","desktop_instance":%q}`, sessionHash(token))
	if !healthMatches([]byte(good), token) {
		t.Fatal("own healthy backend was rejected")
	}
	for _, bad := range []string{
		`{"status":"ok","application":"trade_agent"}`,
		`{"status":"ok","application":"other","desktop_instance":"unknown"}`,
		strings.ReplaceAll(good, sessionHash(token), "another-instance"),
		strings.ReplaceAll(good, `"ok"`, `"error"`),
		`<html>unrelated server</html>`,
	} {
		if healthMatches([]byte(bad), token) {
			t.Fatalf("accepted foreign response: %s", bad)
		}
	}
}

func TestEnvironmentIsolation(t *testing.T) {
	env := backendEnvironment([]string{"Path=C:\\Windows", "SystemRoot=C:\\Windows", "trade_api_key=wrong", "TRADE_HOST=0.0.0.0", "PythonPath=other", "VIRTUAL_ENV=other", "PLAYWRIGHT_BROWSERS_PATH=other"}, `C:\用户\data`, "test-session")
	joined := strings.Join(env, "\n")
	for _, bad := range []string{"wrong", "0.0.0.0", "other"} {
		if strings.Contains(joined, bad) {
			t.Errorf("inherited unsafe override %q", bad)
		}
	}
	for _, wanted := range []string{"SystemRoot=C:\\Windows", "TRADE_HOST=127.0.0.1", `TRADE_DATA_DIR=C:\用户\data`} {
		if !strings.Contains(joined, wanted) {
			t.Errorf("missing %s", wanted)
		}
	}
}

func TestSessionRandomness(t *testing.T) {
	a, err := newSession()
	if err != nil {
		t.Fatal(err)
	}
	b, err := newSession()
	if err != nil {
		t.Fatal(err)
	}
	if len(a) != 64 || a == b {
		t.Fatal("session identifier is not unique 256-bit data")
	}
}
