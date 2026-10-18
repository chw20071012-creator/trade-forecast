//go:build windows

package main

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"testing"
	"unsafe"
)

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
	if got := syscall.UTF16ToString(path); !strings.EqualFold(filepath.Clean(got), filepath.Clean(target)) {
		t.Fatalf("target differs: %q != %q", got, target)
	}
	working := make([]uint16, 32768)
	if err = comResult(link.call(8, uintptr(unsafe.Pointer(&working[0])), uintptr(len(working))), "Read Unicode working directory"); err != nil {
		t.Fatal(err)
	}
	if got := syscall.UTF16ToString(working); !strings.EqualFold(filepath.Clean(got), filepath.Clean(root)) {
		t.Fatalf("working directory differs: %q != %q", got, root)
	}
}
