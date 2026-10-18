//go:build windows

package main

import (
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"syscall"
	"unsafe"
)

// These are native wide-character COM interfaces, not the WScript.Shell
// automation wrapper. They preserve non-ASCII installation and user paths.
type shortcutGUID struct {
	Data1        uint32
	Data2, Data3 uint16
	Data4        [8]byte
}

var (
	shellLinkClass = shortcutGUID{0x00021401, 0, 0, [8]byte{0xc0, 0, 0, 0, 0, 0, 0, 0x46}}
	shellLinkWide  = shortcutGUID{0x000214f9, 0, 0, [8]byte{0xc0, 0, 0, 0, 0, 0, 0, 0x46}}
	persistFileID  = shortcutGUID{0x0000010b, 0, 0, [8]byte{0xc0, 0, 0, 0, 0, 0, 0, 0x46}}
)

type shortcutCOM struct{ vtable *[21]uintptr }

//go:uintptrescapes
func (object *shortcutCOM) call(slot int, args ...uintptr) uintptr {
	parameters := append([]uintptr{uintptr(unsafe.Pointer(object))}, args...)
	result, _, _ := syscall.SyscallN(object.vtable[slot], parameters...)
	runtime.KeepAlive(object)
	return result
}

func comResult(result uintptr, operation string) error {
	if int32(uint32(result)) < 0 {
		return fmt.Errorf("%s失败（HRESULT 0x%08X）", operation, uint32(result))
	}
	return nil
}

func newNativeLink() (*shortcutCOM, error) {
	var link *shortcutCOM
	result, _, _ := ole32.NewProc("CoCreateInstance").Call(
		uintptr(unsafe.Pointer(&shellLinkClass)), 0, 1,
		uintptr(unsafe.Pointer(&shellLinkWide)), uintptr(unsafe.Pointer(&link)))
	if err := comResult(result, "创建Unicode快捷方式接口"); err != nil {
		return nil, err
	}
	return link, nil
}

func persistLink(link *shortcutCOM) (*shortcutCOM, error) {
	var persist *shortcutCOM
	result := link.call(0, uintptr(unsafe.Pointer(&persistFileID)), uintptr(unsafe.Pointer(&persist)))
	if err := comResult(result, "取得快捷方式存储接口"); err != nil {
		return nil, err
	}
	return persist, nil
}

func writeNativeShortcut(target, directory string) error {
	if !filepath.IsAbs(target) || !filepath.IsAbs(directory) {
		return errors.New("快捷方式目标和保存目录必须是绝对路径")
	}
	if _, err := os.Stat(target); err != nil {
		return fmt.Errorf("无法找到快捷方式目标：%w", err)
	}
	if err := os.MkdirAll(directory, 0755); err != nil {
		return err
	}
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	result, _, _ := ole32.NewProc("CoInitializeEx").Call(0, 2)
	if err := comResult(result, "初始化快捷方式接口"); err != nil {
		return err
	}
	defer ole32.NewProc("CoUninitialize").Call()
	link, err := newNativeLink()
	if err != nil {
		return err
	}
	defer link.call(2)
	for _, setting := range []struct {
		slot        int
		value, name string
	}{
		{20, target, "设置程序路径"},
		{9, filepath.Dir(target), "设置工作目录"},
		{7, "外贸工作台：客户、产品、报价、邮件与订单", "设置快捷方式说明"},
	} {
		value, err := syscall.UTF16PtrFromString(setting.value)
		if err != nil {
			return err
		}
		if err = comResult(link.call(setting.slot, uintptr(unsafe.Pointer(value))), setting.name); err != nil {
			return err
		}
	}
	icon, err := syscall.UTF16PtrFromString(target)
	if err != nil {
		return err
	}
	if err = comResult(link.call(17, uintptr(unsafe.Pointer(icon)), 0), "设置程序图标"); err != nil {
		return err
	}
	if err = comResult(link.call(15, 1), "设置窗口显示方式"); err != nil {
		return err
	}
	persist, err := persistLink(link)
	if err != nil {
		return err
	}
	defer persist.call(2)
	temporary, err := os.CreateTemp(directory, ".TradeAgent-*.lnk")
	if err != nil {
		return err
	}
	name := temporary.Name()
	if err = temporary.Close(); err != nil {
		os.Remove(name)
		return err
	}
	defer os.Remove(name)
	file, err := syscall.UTF16PtrFromString(name)
	if err != nil {
		return err
	}
	if err = comResult(persist.call(6, uintptr(unsafe.Pointer(file)), 1), "保存Unicode快捷方式"); err != nil {
		return err
	}
	if err = os.Rename(name, filepath.Join(directory, "外贸工作台.lnk")); err != nil {
		return fmt.Errorf("更新快捷方式失败：%w", err)
	}
	return nil
}

// Installer mode runs before GUI/mutex and returns a normal process exit code.
func runShortcutCLI(args []string) (handled bool, exitCode int) {
	if len(args) == 0 || args[0] != "--install-shortcuts" {
		return false, 0
	}
	flags := flag.NewFlagSet("install-shortcuts", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	desktop := flags.String("desktop-dir", "", "Windows desktop directory")
	startMenu := flags.String("start-menu-dir", "", "Windows Start Menu programs directory")
	if err := flags.Parse(args[1:]); err != nil || flags.NArg() != 0 || *desktop == "" || *startMenu == "" {
		fmt.Fprintln(os.Stderr, "创建快捷方式参数无效：须提供 --desktop-dir 和 --start-menu-dir 的完整目录。")
		return true, 2
	}
	target, err := os.Executable()
	if err != nil {
		fmt.Fprintln(os.Stderr, "无法确定程序路径：", err)
		return true, 1
	}
	for _, directory := range []string{*desktop, *startMenu} {
		if err = writeNativeShortcut(target, directory); err != nil {
			fmt.Fprintln(os.Stderr, "创建桌面或开始菜单快捷方式失败：", err)
			return true, 1
		}
	}
	fmt.Fprintln(os.Stdout, "桌面和开始菜单快捷方式已创建。")
	return true, 0
}
