//go:build windows

package main

import (
	"errors"
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sync"
	"syscall"
	"time"
	"unsafe"
)

var (
	user32         = syscall.NewLazyDLL("user32.dll")
	kernel32       = syscall.NewLazyDLL("kernel32.dll")
	shell32        = syscall.NewLazyDLL("shell32.dll")
	ole32          = syscall.NewLazyDLL("ole32.dll")
	gdi32          = syscall.NewLazyDLL("gdi32.dll")
	pMessageBox    = user32.NewProc("MessageBoxW")
	pDefWindowProc = user32.NewProc("DefWindowProcW")
	pPostMessage   = user32.NewProc("PostMessageW")
	pSendMessage   = user32.NewProc("SendMessageW")
	pSetWindowText = user32.NewProc("SetWindowTextW")
	pEnableWindow  = user32.NewProc("EnableWindow")
	pShowWindow    = user32.NewProc("ShowWindow")
	pDestroyWindow = user32.NewProc("DestroyWindow")
	pShellExecute  = shell32.NewProc("ShellExecuteW")
)

const (
	windowClass = "TradeAgentDesktopControllerV1"
	windowTitle = "外贸工作台 · 桌面控制台"
	wmCommand   = 0x0111
	wmClose     = 0x0010
	wmDestroy   = 0x0002
	wmNotify    = 0x8001
	wmImport    = 0x8002
	wmReopen    = 0x8003
	wmFinished  = 0x8004
	buttonOpen  = 101
	buttonData  = 102
	buttonLogs  = 103
	buttonExit  = 104
)

type point struct{ X, Y int32 }
type msg struct {
	Hwnd           uintptr
	Message        uint32
	WParam, LParam uintptr
	Time           uint32
	Pt             point
	LPrivate       uint32
}
type wndClassEx struct {
	Size, Style                        uint32
	Proc                               uintptr
	ClsExtra, WndExtra                 int32
	Instance, Icon, Cursor, Background uintptr
	MenuName, ClassName                *uint16
	IconSmall                          uintptr
}
type browseInfo struct {
	Owner, Root        uintptr
	DisplayName, Title *uint16
	Flags              uint32
	Callback, Param    uintptr
	Image              int32
}

type controller struct {
	mu                                         sync.Mutex
	hwnd, label, openButton, exitButton        uintptr
	root, data, logDir, python, browser, token string
	status, alert                              string
	ready, stopping, exited, starting          bool
	cmd                                        *exec.Cmd
	done                                       chan struct{}
	processErr                                 error
	importSelection                            chan string
}

var app controller

func u16(s string) *uint16 { return syscall.StringToUTF16Ptr(s) }
func message(owner uintptr, text string, flags uintptr) uintptr {
	result, _, _ := pMessageBox.Call(owner, uintptr(unsafe.Pointer(u16(text))), uintptr(unsafe.Pointer(u16("外贸工作台"))), flags)
	return result
}

func main() {
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	defer func() {
		if recover() != nil {
			message(0, "桌面启动器发生异常。请重新打开；若仍失败，请提供数据目录 logs 中的日志。", 0x10)
		}
	}()
	mutex, _, mutexErr := kernel32.NewProc("CreateMutexW").Call(0, 0, uintptr(unsafe.Pointer(u16("Local\\TradeAgent.Desktop.Controller.v1"))))
	if mutex == 0 {
		message(0, "无法创建桌面程序运行锁，请重启电脑后再试。", 0x10)
		return
	}
	defer syscall.CloseHandle(syscall.Handle(mutex))
	if mutexErr == syscall.Errno(183) {
		existing, _, _ := user32.NewProc("FindWindowW").Call(uintptr(unsafe.Pointer(u16(windowClass))), 0)
		if existing != 0 {
			pShowWindow.Call(existing, 9)
			user32.NewProc("SetForegroundWindow").Call(existing)
			pPostMessage.Call(existing, wmReopen, 0, 0)
		} else {
			message(0, "外贸工作台已在启动，请稍等。", 0x40)
		}
		return
	}

	exe, err := os.Executable()
	if err != nil {
		message(0, "无法确定程序所在文件夹，请重新解压完整软件包。", 0x10)
		return
	}
	app.root = filepath.Dir(exe)
	local := os.Getenv("LOCALAPPDATA")
	if local == "" {
		message(0, "Windows 的 LOCALAPPDATA 用户目录不可用，请用正常 Windows 用户登录后重试。", 0x10)
		return
	}
	app.data = filepath.Join(local, "TradeAgent", "data")
	app.logDir = filepath.Join(local, "TradeAgent", "logs")
	app.python = filepath.Join(app.root, "runtime", "python.exe")
	app.importSelection = make(chan string, 1)
	app.starting = true
	app.status = "正在准备本机运行环境，请稍候……"
	app.token, err = newSession()
	if err != nil {
		message(0, "无法生成安全启动标识，请重试。", 0x10)
		return
	}
	if err = os.MkdirAll(app.logDir, 0700); err != nil {
		message(0, "无法写入用户数据目录。请检查磁盘空间和文件夹权限。", 0x10)
		return
	}

	ole32.NewProc("CoInitializeEx").Call(0, 2)
	defer ole32.NewProc("CoUninitialize").Call()
	if err = createWindow(); err != nil {
		message(0, err.Error(), 0x10)
		return
	}
	go startBackend()
	var m msg
	for {
		result, _, _ := user32.NewProc("GetMessageW").Call(uintptr(unsafe.Pointer(&m)), 0, 0, 0)
		if int32(result) <= 0 {
			break
		}
		user32.NewProc("TranslateMessage").Call(uintptr(unsafe.Pointer(&m)))
		user32.NewProc("DispatchMessageW").Call(uintptr(unsafe.Pointer(&m)))
	}
}

func createWindow() error {
	instance, _, _ := kernel32.NewProc("GetModuleHandleW").Call(0)
	cursor, _, _ := user32.NewProc("LoadCursorW").Call(0, 32512)
	icon, _, _ := user32.NewProc("LoadIconW").Call(instance, 1)
	if icon == 0 {
		icon, _, _ = user32.NewProc("LoadIconW").Call(0, 32512)
	}
	wc := wndClassEx{Proc: syscall.NewCallback(windowProc), Instance: instance, Icon: icon, IconSmall: icon, Cursor: cursor, Background: 6, ClassName: u16(windowClass)}
	wc.Size = uint32(unsafe.Sizeof(wc))
	if ok, _, _ := user32.NewProc("RegisterClassExW").Call(uintptr(unsafe.Pointer(&wc))); ok == 0 {
		return errors.New("无法创建程序窗口。")
	}
	w, _, _ := user32.NewProc("GetSystemMetrics").Call(0)
	h, _, _ := user32.NewProc("GetSystemMetrics").Call(1)
	app.hwnd, _, _ = user32.NewProc("CreateWindowExW").Call(0, uintptr(unsafe.Pointer(u16(windowClass))), uintptr(unsafe.Pointer(u16(windowTitle))), 0x00C80000|0x00020000, (w-660)/2, (h-355)/2, 660, 355, 0, 0, instance, 0)
	if app.hwnd == 0 {
		return errors.New("无法创建程序窗口。")
	}
	font, _, _ := gdi32.NewProc("GetStockObject").Call(17)
	child := func(class, text string, x, y, width, height int, id int) uintptr {
		handle, _, _ := user32.NewProc("CreateWindowExW").Call(0, uintptr(unsafe.Pointer(u16(class))), uintptr(unsafe.Pointer(u16(text))), 0x50000000|0x00010000, uintptr(x), uintptr(y), uintptr(width), uintptr(height), app.hwnd, uintptr(id), instance, 0)
		pSendMessage.Call(handle, 0x0030, font, 1)
		return handle
	}
	child("STATIC", "外贸工作台  Trade Agent", 26, 22, 600, 25, 0)
	app.label = child("STATIC", app.status, 26, 60, 600, 72, 0)
	child("STATIC", "客户、产品、报价和附件保存在本机。\r\n关闭业务窗口后仍可继续运行；结束使用请点击“退出工作台”。", 26, 144, 600, 50, 0)
	app.openButton = child("BUTTON", "打开工作台", 26, 211, 142, 38, buttonOpen)
	child("BUTTON", "数据文件夹", 179, 211, 132, 38, buttonData)
	child("BUTTON", "查看日志", 322, 211, 132, 38, buttonLogs)
	app.exitButton = child("BUTTON", "退出工作台", 465, 211, 150, 38, buttonExit)
	child("STATIC", "本机入口：http://127.0.0.1:8765", 26, 273, 600, 22, 0)
	pEnableWindow.Call(app.openButton, 0)
	pShowWindow.Call(app.hwnd, 1)
	user32.NewProc("UpdateWindow").Call(app.hwnd)
	return nil
}

func windowProc(hwnd uintptr, messageID uint32, wParam, lParam uintptr) uintptr {
	switch messageID {
	case wmNotify:
		app.mu.Lock()
		status, alert, ready, stopping := app.status, app.alert, app.ready, app.stopping
		app.alert = ""
		app.mu.Unlock()
		pSetWindowText.Call(app.label, uintptr(unsafe.Pointer(u16(status))))
		var enabled uintptr
		if ready && !stopping {
			enabled = 1
		}
		pEnableWindow.Call(app.openButton, enabled)
		if stopping {
			pEnableWindow.Call(app.exitButton, 0)
		} else {
			pEnableWindow.Call(app.exitButton, 1)
		}
		if alert != "" {
			message(hwnd, alert, 0x30)
		}
		return 0
	case wmImport:
		choice := message(hwnd, "第一次使用桌面版。\r\n\r\n是否导入旧版外贸工作台的客户、产品和设置？\r\n请先用旧版 stop.cmd 完全停止旧程序。\r\n\r\n“是”：选择旧版程序文件夹并复制原有资料。\r\n“否”：从空白资料开始。\r\n“取消”：退出，稍后再设置。\r\n\r\n旧版文件不会被删除。", 0x23)
		switch choice {
		case 6:
			path := selectFolder(hwnd)
			if path == "" {
				app.importSelection <- "cancel"
			} else {
				app.importSelection <- path
			}
		case 7:
			app.importSelection <- "new"
		default:
			app.importSelection <- "cancel"
		}
		return 0
	case wmReopen:
		app.mu.Lock()
		ready := app.ready
		app.mu.Unlock()
		if ready {
			go openWorkspace()
		}
		return 0
	case wmCommand:
		switch int(wParam & 0xffff) {
		case buttonOpen:
			go openWorkspace()
		case buttonData:
			openPath(app.data)
		case buttonLogs:
			openPath(app.logDir)
		case buttonExit:
			askExit(hwnd)
		}
		return 0
	case wmClose:
		askExit(hwnd)
		return 0
	case wmFinished:
		pDestroyWindow.Call(hwnd)
		return 0
	case wmDestroy:
		user32.NewProc("PostQuitMessage").Call(0)
		return 0
	}
	r, _, _ := pDefWindowProc.Call(hwnd, uintptr(messageID), wParam, lParam)
	return r
}

func selectFolder(owner uintptr) string {
	buf := make([]uint16, 32768)
	display := make([]uint16, 32768)
	bi := browseInfo{Owner: owner, DisplayName: &display[0], Title: u16("请选择旧版外贸工作台根文件夹（能看到 start.cmd 和 trade_agent 的文件夹）"), Flags: 0x0041 | 0x0010}
	id, _, _ := shell32.NewProc("SHBrowseForFolderW").Call(uintptr(unsafe.Pointer(&bi)))
	if id == 0 {
		return ""
	}
	defer ole32.NewProc("CoTaskMemFree").Call(id)
	ok, _, _ := shell32.NewProc("SHGetPathFromIDListW").Call(id, uintptr(unsafe.Pointer(&buf[0])))
	if ok == 0 {
		return ""
	}
	return syscall.UTF16ToString(buf)
}

func update(status, alert string) {
	app.mu.Lock()
	app.status = status
	if alert != "" {
		app.alert = alert
	}
	app.mu.Unlock()
	pPostMessage.Call(app.hwnd, wmNotify, 0, 0)
}

func startBackend() {
	defer func() { app.mu.Lock(); app.starting = false; app.mu.Unlock() }()
	for _, path := range []string{app.python, filepath.Join(app.root, "app", "trade_agent", "desktop_server.py")} {
		if _, err := os.Stat(path); err != nil {
			update("软件包不完整，尚未启动。", "请先将整个 ZIP 解压到一个文件夹，再双击 TradeAgent.exe。\r\n不要只复制 EXE，也不要在压缩包内直接运行。")
			return
		}
	}
	listener, err := net.Listen("tcp4", "127.0.0.1:8765")
	if err != nil {
		update("本机 8765 端口已被占用，尚未启动。", "旧版外贸工作台或其他程序正在占用端口 8765。\r\n请先双击旧版 stop.cmd 停止旧程序，再重新打开桌面版。\r\n本程序不会结束其他程序或切换到另一套资料。")
		return
	}
	listener.Close()
	if _, err = os.Stat(filepath.Join(app.data, "trade.sqlite3")); os.IsNotExist(err) {
		update("请选择是否导入旧版资料……", "")
		pPostMessage.Call(app.hwnd, wmImport, 0, 0)
		selection := <-app.importSelection
		if selection == "cancel" {
			pPostMessage.Call(app.hwnd, wmFinished, 0, 0)
			return
		}
		if selection != "new" {
			update("正在复制旧版资料；请勿关闭电脑或移动原文件夹……", "")
			report := filepath.Join(app.logDir, "migration-report.json")
			cmd := pythonCommand("-m", "trade_agent.desktop_migrate", "--source", selection, "--target", app.data, "--report", report)
			log, err := os.OpenFile(filepath.Join(app.logDir, "migration.log"), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0600)
			if err != nil {
				update("无法写入迁移日志。", "请检查数据目录权限，再重新启动。")
				return
			}
			cmd.Stdout, cmd.Stderr = log, log
			err = cmd.Run()
			log.Close()
			if err != nil {
				update("旧版资料未导入；工作台尚未启动。", "请点击“查看日志”，查看 migration-report.json 或 migration.log。\r\n确认选择的是旧版程序根文件夹，并已停止旧程序，然后退出桌面版后重试。\r\n没有自动改为空白资料启动。")
				return
			}
		}
	}
	if err = os.MkdirAll(app.data, 0700); err != nil {
		update("无法创建数据目录。", "请检查本机磁盘空间和文件夹权限。")
		return
	}
	app.browser = findBrowser()
	if app.browser == "" {
		update("缺少可用的桌面显示浏览器。", "请安装或修复 Microsoft Edge（Windows 10/11 通常自带）或 Google Chrome，然后重新打开桌面版。\r\n你的业务数据会保留。")
		return
	}
	update("正在启动外贸工作台，首次启动可能需要约一分钟……", "")
	log, err := os.OpenFile(filepath.Join(app.logDir, "server.log"), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0600)
	if err != nil {
		update("无法创建运行日志。", "请检查用户数据目录权限。")
		return
	}
	fmt.Fprintln(log, "\n--- Desktop start", time.Now().Format(time.RFC3339), "---")
	cmd := pythonCommand("-m", "trade_agent.desktop_server", "--host", "127.0.0.1", "--port", "8765")
	cmd.Stdout, cmd.Stderr = log, log
	if err = cmd.Start(); err != nil {
		log.Close()
		update("本机服务启动失败。", "请确认整个软件包已经解压，杀毒软件没有隔离 runtime 中的文件。\r\n点击“查看日志”获取详情。")
		return
	}
	app.mu.Lock()
	app.cmd = cmd
	app.done = make(chan struct{})
	done := app.done
	app.mu.Unlock()
	go func() {
		err := cmd.Wait()
		log.Close()
		app.mu.Lock()
		app.processErr = err
		app.exited = true
		wasReady, stopping := app.ready, app.stopping
		app.ready = false
		close(done)
		app.mu.Unlock()
		if wasReady && !stopping {
			update("本机服务已经停止。", "请退出桌面控制台后重新打开。若再次停止，请检查 logs/server.log。")
		}
	}()
	timeout := time.NewTimer(75 * time.Second)
	defer timeout.Stop()
	tick := time.NewTicker(350 * time.Millisecond)
	defer tick.Stop()
	for {
		select {
		case <-done:
			update("本机服务未能启动。", "点击“查看日志”查看 server.log。\r\n请不要删除 data 文件夹；修复软件后可继续使用原有资料。")
			return
		case <-timeout.C:
			// This process handle belongs only to the Python child started above.
			_ = cmd.Process.Kill()
			update("启动等待超时，本次启动已停止。", "请点击“查看日志”查看 server.log，检查磁盘空间和安全软件后重试。\r\n没有结束旧版或其他程序。")
			return
		case <-tick.C:
			if ownedHealth(app.token) {
				app.mu.Lock()
				if app.exited {
					app.mu.Unlock()
					continue
				}
				app.ready = true
				app.mu.Unlock()
				update("正在运行 · 数据保存在你的 Windows 用户目录。\r\n业务窗口关闭后，可点击“打开工作台”继续使用。", "")
				openWorkspace()
				return
			}
		}
	}
}

func pythonCommand(args ...string) *exec.Cmd {
	args = append([]string{"-E", "-s", "-X", "utf8"}, args...)
	cmd := exec.Command(app.python, args...)
	cmd.Dir = filepath.Join(app.root, "app")
	cmd.Env = append(backendEnvironment(os.Environ(), app.data, app.token), "TRADE_API_KEY_FILE="+filepath.Join(app.data, "secrets", "api-key.txt"))
	cmd.Env = append(cmd.Env, "PLAYWRIGHT_BROWSERS_PATH="+filepath.Join(filepath.Dir(app.data), "browsers"))
	if app.browser != "" {
		cmd.Env = append(cmd.Env, "TRADE_BROWSER_EXECUTABLE="+app.browser)
	}
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: 0x08000000}
	return cmd
}

func findBrowser() string {
	for _, base := range []string{os.Getenv("ProgramFiles(x86)"), os.Getenv("ProgramFiles"), os.Getenv("LOCALAPPDATA")} {
		if base == "" {
			continue
		}
		for _, path := range []string{filepath.Join(base, "Microsoft", "Edge", "Application", "msedge.exe"), filepath.Join(base, "Google", "Chrome", "Application", "chrome.exe")} {
			if info, err := os.Stat(path); err == nil && !info.IsDir() {
				return path
			}
		}
	}
	return ""
}

func openWorkspace() {
	app.mu.Lock()
	ready, stopping, browser := app.ready, app.stopping, app.browser
	app.mu.Unlock()
	if !ready || stopping {
		return
	}
	if !ownedHealth(app.token) {
		update("本机服务暂时无法访问。", "请稍后重试；若持续出现，请查看运行日志。")
		return
	}
	profile := filepath.Join(filepath.Dir(app.data), "browser-profile")
	cmd := exec.Command(browser, "--app="+baseURL, "--new-window", "--window-size=1400,900", "--user-data-dir="+profile, "--no-first-run")
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	if err := cmd.Start(); err != nil {
		update("工作台运行中，独立窗口未能打开。", "请在 Edge 或 Chrome 地址栏输入 http://127.0.0.1:8765 访问。\r\n结束使用时仍请从桌面控制台退出。")
		return
	}
	go func() { _ = cmd.Wait() }() // Browser handoff/exit is not evidence that the app is closed.
}

func openPath(path string) {
	_ = os.MkdirAll(path, 0700)
	pShellExecute.Call(app.hwnd, uintptr(unsafe.Pointer(u16("open"))), uintptr(unsafe.Pointer(u16(path))), 0, 0, 1)
}

func askExit(hwnd uintptr) {
	app.mu.Lock()
	stopping, cmd, exited, ready := app.stopping, app.cmd, app.exited, app.ready
	app.mu.Unlock()
	if stopping {
		return
	}
	if cmd == nil && !ready {
		app.mu.Lock()
		starting := app.starting
		app.mu.Unlock()
		if starting {
			message(hwnd, "正在准备或迁移资料，请等待此步骤完成后再退出。", 0x40)
			return
		}
		pDestroyWindow.Call(hwnd)
		return
	}
	if exited {
		pDestroyWindow.Call(hwnd)
		return
	}
	if !ready {
		message(hwnd, "程序正在启动，请稍候。启动完成或出现错误后可退出。", 0x40)
		return
	}
	if message(hwnd, "是否退出外贸工作台？\r\n\r\n退出后本机后台服务会停止，客户和产品资料会保留。\r\n如有正在执行的任务，程序会提示你先完成或暂停任务。", 0x24) != 6 {
		return
	}
	app.mu.Lock()
	app.stopping = true
	app.mu.Unlock()
	update("正在停止本机服务，请稍候……", "")
	go func() {
		code, err := requestShutdown(app.token)
		if err != nil {
			app.mu.Lock()
			app.stopping = false
			exited := app.exited
			app.mu.Unlock()
			if exited {
				pPostMessage.Call(app.hwnd, wmFinished, 0, 0)
				return
			}
			if code == 409 {
				update("仍有任务在执行，工作台继续运行。", "请先在“邮件与询盘”或“任务记录”页面暂停待执行任务，并等待本次操作结束，然后再退出。\r\n程序没有强行结束任务。")
			} else {
				update("暂时无法安全停止，工作台继续运行。", "请稍后再点击“退出工作台”。若持续失败，请查看运行日志。")
			}
			return
		}
		select {
		case <-app.done:
			pPostMessage.Call(app.hwnd, wmFinished, 0, 0)
		case <-time.After(20 * time.Second):
			app.mu.Lock()
			app.stopping = false
			app.mu.Unlock()
			update("本机服务尚未完全停止。", "请稍后再点击“退出工作台”。程序没有强行结束后台操作。")
		}
	}()
}
