import Foundation
import IOBluetooth

/// Keeps the Cursor→MiniToo bridge always running, and only starts the
/// RFCOMM daemon when the paired MiniToo appears connected over Bluetooth.
final class Supervisor {
    let projectRoot: URL
    let macAddress: String
    let rfcommChannel: UInt8
    let daemonPort: UInt16
    let pollSeconds: TimeInterval
    let logURL: URL

    private var daemonProcess: Process?
    private var bridgeProcess: Process?
    private var lastDeviceConnected: Bool?
    private var lastDaemonStartAttempt = Date.distantPast
    /// Daemon briefly releases the macOS audio profile while opening RFCOMM,
    /// which makes isConnected() flicker false. Require sustained disconnect.
    private var consecutiveDisconnectTicks = 0
    private let disconnectTicksBeforeStop = 4  // ~12s at 3s poll
    private let postStartGraceSeconds: TimeInterval = 20

    init(
        projectRoot: URL,
        macAddress: String,
        rfcommChannel: UInt8 = 1,
        daemonPort: UInt16 = 40583,
        pollSeconds: TimeInterval = 3.0
    ) {
        self.projectRoot = projectRoot
        self.macAddress = macAddress
        self.rfcommChannel = rfcommChannel
        self.daemonPort = daemonPort
        self.pollSeconds = pollSeconds
        self.logURL = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".minitoo/supervisor.log")
    }

    private var daemonURL: URL {
        projectRoot.appendingPathComponent("divoom-minitoo-osx/tools/divoom-daemon")
    }

    private var pythonURL: URL {
        projectRoot.appendingPathComponent("divoom-minitoo-osx/.venv/bin/python")
    }

    private var bridgeURL: URL {
        projectRoot.appendingPathComponent("minitoo-cursor-bridge/cursor_minitoo_bridge.py")
    }

    private var senderURL: URL {
        projectRoot.appendingPathComponent("divoom-minitoo-osx/tools/divoom_send.py")
    }

    private var spritesURL: URL {
        projectRoot.appendingPathComponent("sprites")
    }

    func log(_ message: String) {
        let line = "\(isoNow()) \(message)\n"
        try? FileManager.default.createDirectory(
            at: logURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        if let data = line.data(using: .utf8) {
            if FileManager.default.fileExists(atPath: logURL.path) {
                if let handle = try? FileHandle(forWritingTo: logURL) {
                    defer { try? handle.close() }
                    _ = try? handle.seekToEnd()
                    try? handle.write(contentsOf: data)
                }
            } else {
                try? data.write(to: logURL, options: .atomic)
            }
        }
        fputs(line, stderr)
    }

    private func isoNow() -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.string(from: Date())
    }

    func isMiniTooConnected() -> Bool {
        guard let device = IOBluetoothDevice(addressString: macAddress) else {
            return false
        }
        return device.isConnected()
    }

    func isPortListening(_ port: UInt16) -> Bool {
        let sock = socket(AF_INET, SOCK_STREAM, 0)
        guard sock >= 0 else { return false }
        defer { close(sock) }
        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = port.bigEndian
        addr.sin_addr = in_addr(s_addr: inet_addr("127.0.0.1"))
        let result = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                connect(sock, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        return result == 0
    }

    func ensureBridgeRunning() {
        if let p = bridgeProcess, p.isRunning { return }
        guard FileManager.default.isExecutableFile(atPath: pythonURL.path) else {
            log("bridge python missing: \(pythonURL.path)")
            return
        }
        guard FileManager.default.fileExists(atPath: bridgeURL.path) else {
            log("bridge script missing: \(bridgeURL.path)")
            return
        }
        let process = Process()
        process.executableURL = pythonURL
        process.arguments = [
            bridgeURL.path,
            "--sender", senderURL.path,
            "--sprites-dir", spritesURL.path,
            "--interval", "0.75",
        ]
        process.currentDirectoryURL = projectRoot
        var env = ProcessInfo.processInfo.environment
        env["PYTHONUNBUFFERED"] = "1"
        process.environment = env
        let logFile = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".minitoo/bridge.log")
        if !FileManager.default.fileExists(atPath: logFile.path) {
            FileManager.default.createFile(atPath: logFile.path, contents: Data())
        }
        if let handle = try? FileHandle(forWritingTo: logFile) {
            _ = try? handle.seekToEnd()
            process.standardOutput = handle
            process.standardError = handle
        }
        do {
            try process.run()
            bridgeProcess = process
            log("started bridge pid=\(process.processIdentifier)")
        } catch {
            log("failed to start bridge: \(error)")
        }
    }

    func startDaemon() {
        if isPortListening(daemonPort) { return }
        if let p = daemonProcess, p.isRunning { return }
        // Avoid restart storms when RFCOMM fails repeatedly.
        if Date().timeIntervalSince(lastDaemonStartAttempt) < 8 {
            return
        }
        lastDaemonStartAttempt = Date()
        guard FileManager.default.isExecutableFile(atPath: daemonURL.path) else {
            log("daemon binary missing: \(daemonURL.path)")
            return
        }
        let process = Process()
        process.executableURL = daemonURL
        process.arguments = [macAddress, String(rfcommChannel), String(daemonPort)]
        process.currentDirectoryURL = projectRoot
        let logFile = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".minitoo/daemon.log")
        if !FileManager.default.fileExists(atPath: logFile.path) {
            FileManager.default.createFile(atPath: logFile.path, contents: Data())
        }
        if let handle = try? FileHandle(forWritingTo: logFile) {
            _ = try? handle.seekToEnd()
            process.standardOutput = handle
            process.standardError = handle
        }
        do {
            try process.run()
            daemonProcess = process
            log("started daemon pid=\(process.processIdentifier)")
        } catch {
            log("failed to start daemon: \(error)")
        }
    }

    func stopDaemon(reason: String) {
        if let p = daemonProcess, p.isRunning {
            p.terminate()
            daemonProcess = nil
            log("stopped managed daemon (\(reason))")
        }
        // Also clear any stray daemon on our port from older sessions.
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/bin/pkill")
        task.arguments = ["-f", "divoom-daemon \(macAddress)"]
        try? task.run()
        task.waitUntilExit()
        if isPortListening(daemonPort) {
            let killPort = Process()
            killPort.executableURL = URL(fileURLWithPath: "/bin/bash")
            killPort.arguments = [
                "-c",
                "pids=$(lsof -tiTCP:\(daemonPort) -sTCP:LISTEN); [ -n \"$pids\" ] && kill $pids || true",
            ]
            try? killPort.run()
            killPort.waitUntilExit()
            log("cleared listener on \(daemonPort) (\(reason))")
        }
        daemonProcess = nil
    }

    func tick() {
        ensureBridgeRunning()
        let connected = isMiniTooConnected()
        let portUp = isPortListening(daemonPort)
        let withinGrace = Date().timeIntervalSince(lastDaemonStartAttempt) < postStartGraceSeconds

        if connected {
            consecutiveDisconnectTicks = 0
            if lastDeviceConnected != true {
                log("MiniToo connected (\(macAddress))")
                lastDeviceConnected = true
            }
            if !portUp {
                if let p = daemonProcess, !p.isRunning {
                    daemonProcess = nil
                }
                startDaemon()
            }
            return
        }

        consecutiveDisconnectTicks += 1
        if lastDeviceConnected != false && consecutiveDisconnectTicks >= disconnectTicksBeforeStop {
            log("MiniToo disconnected (\(macAddress))")
            lastDeviceConnected = false
        }

        // Keep daemon during RFCOMM bring-up even if Classic link briefly drops.
        if portUp && (withinGrace || consecutiveDisconnectTicks < disconnectTicksBeforeStop) {
            return
        }

        if consecutiveDisconnectTicks >= disconnectTicksBeforeStop {
            stopDaemon(reason: "device not connected")
        }
    }

    func run() {
        try? FileManager.default.createDirectory(
            at: logURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        log("supervisor starting projectRoot=\(projectRoot.path)")
        // Strong capture keeps the supervisor alive for the lifetime of the timer.
        let timer = Timer.scheduledTimer(withTimeInterval: pollSeconds, repeats: true) { _ in
            self.tick()
        }
        timer.tolerance = 0.5
        tick()
        RunLoop.main.run()
    }
}

let args = CommandLine.arguments
let projectRoot: URL
if args.count > 1 {
    projectRoot = URL(fileURLWithPath: args[1]).standardizedFileURL
} else {
    // Binary lives at <root>/divoom-minitoo-osx/tools/minitoo-supervisor
    projectRoot = URL(fileURLWithPath: CommandLine.arguments[0])
        .deletingLastPathComponent() // tools
        .deletingLastPathComponent() // divoom-minitoo-osx
        .deletingLastPathComponent() // project root
        .standardizedFileURL
}
let mac = args.count > 2 ? args[2] : "B1:21:81:91:DE:0A"
let supervisor = Supervisor(projectRoot: projectRoot, macAddress: mac)
supervisor.run()
