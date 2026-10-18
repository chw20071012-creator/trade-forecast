//go:build windows

package main

import (
	"os"
	"path/filepath"
	"runtime"
	"syscall"
	"testing"
	"unsafe"
)

func assertShortcutFileIdentity(t *testing.T, label, got, expected string) {
	t.Helper()
	actualInfo, err := os.Stat(got)
	if err != nil {
		t.Fatalf("%s target is not accessible: %q: %v", label, got, err)
	}
	expectedInfo, err := os.Stat(expected)
	if err != nil {
		t.Fatal(err)
	}
	// Windows CI returned runneradmin where TempDir used the RUNNER~1 8.3
	// alias. Compare actual file identity while preserving the Unicode test.
	if !os.SameFile(actualInfo, expectedInfo) {
		t.Fatalf("%s points to a different file: %q != %q", label, got, expected)
	}
}

func TestNativeShortcutUnicodePaths(t *testing.T) {
	root := filepath.Join(t.TempDir(), "中文 资料")
	if err := os.MkdirAll(root, 0700); err != nil {
		t.Fatal(err)
	}
	target := filepath.Join(root, "外贸 TradeAgent.exe")
	if err := os.WriteFile(target, []byte("synthetic shortcut target; never executed"), 0600); err != nil {
		t.Fatal(err)
	}
	directory := filepath.Join(root, "桌面 开始菜单")
	if err := writeNativeShortcut(target, directory); err != nil {
		t.Fatal(err)
	}
	file := filepath.Join(directory, "外贸工作台.lnk")
	if info, err := os.Stat(file); err != nil || info.Size() == 0 {
		t.Fatalf("shortcut was not saved: %v", err)
	}

	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	hr, _, _ := ole32.NewProc("CoInitializeEx").Call(0, 2)
	if err := comResult(hr, "test COM initialization"); err != nil {
		t.Fatal(err)
	}
	defer ole32.NewProc("CoUninitialize").Call()
	link, err := newNativeLink()
	if err != nil {
		t.Fatal(err)
	}
	defer link.call(2)
	persist, err := persistLink(link)
	if err != nil {
		t.Fatal(err)
	}
	defer persist.call(2)
	name, err := syscall.UTF16PtrFromString(file)
	if err != nil {
		t.Fatal(err)
	}
	if err = comResult(persist.call(5, uintptr(unsafe.Pointer(name)), 0), "Load Unicode .lnk"); err != nil {
		t.Fatal(err)
	}
	path := make([]uint16, 32768)
	if err = comResult(link.call(3, uintptr(unsafe.Pointer(&path[0])), uintptr(len(path)), 0, 4), "Read Unicode target"); err != nil {
		t.Fatal(err)
	}
	assertShortcutFileIdentity(t, "target", syscall.UTF16ToString(path), target)
	working := make([]uint16, 32768)
	if err = comResult(link.call(8, uintptr(unsafe.Pointer(&working[0])), uintptr(len(working))), "Read Unicode working directory"); err != nil {
		t.Fatal(err)
	}
	assertShortcutFileIdentity(t, "working directory", syscall.UTF16ToString(working), root)
}
