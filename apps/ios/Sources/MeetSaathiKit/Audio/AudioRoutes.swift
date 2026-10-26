import AVFoundation
import Foundation

public struct AudioRoute: Equatable, Sendable {
    public var input: String            // phone_mic | headset_mic | bluetooth_mic | usb_mic | none
    public var output: String           // receiver | phone_speaker | bluetooth_a2dp | bluetooth_hfp | bluetooth_le | wired_headphones | airplay | other
    public var outputDeviceName: String?
    public var privateOutputPresent: Bool
    public var couplesInputAndOutput: Bool // HFP: the headset becomes the microphone too
}

/// Observes REAL routes (master 5.4, 8.1). On iOS this is AVAudioSession; HFP may couple input and output, so the
/// session is configured with A2DP (output-only) by default and the actual route is always re-read, never assumed.
public final class AudioRoutes: @unchecked Sendable {
    public private(set) var route = AudioRoute(input: "none", output: "none", outputDeviceName: nil, privateOutputPresent: false, couplesInputAndOutput: false)
    private var verifiedDevice: String?
    public private(set) var userVerified = false
    public var onChange: ((_ old: AudioRoute, _ new: AudioRoute, _ deviceLost: Bool) -> Void)?
    public var onInterruption: ((_ began: Bool) -> Void)?
    private var observers: [NSObjectProtocol] = []

    public init() {}

    public var privateRouteVerified: Bool { userVerified && route.privateOutputPresent && route.outputDeviceName == verifiedDevice }

    public func confirmPrivateRoute() {
        guard route.privateOutputPresent else { return }
        userVerified = true
        verifiedDevice = route.outputDeviceName
    }

    #if os(iOS)
    public func configureForCapture() throws {
        let s = AVAudioSession.sharedInstance()
        // No .defaultToSpeaker: private advice must never be routed to the loudspeaker.
        try s.setCategory(.playAndRecord, mode: .default, options: [.allowBluetoothA2DP])
        try s.setActive(true)
        refresh(deviceLost: false)
    }

    public func deactivate() {
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    public func start() {
        let nc = NotificationCenter.default
        observers.append(nc.addObserver(forName: AVAudioSession.routeChangeNotification, object: nil, queue: .main) { [weak self] n in
            let reason = (n.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt).flatMap(AVAudioSession.RouteChangeReason.init(rawValue:))
            self?.refresh(deviceLost: reason == .oldDeviceUnavailable)
        })
        observers.append(nc.addObserver(forName: AVAudioSession.interruptionNotification, object: nil, queue: .main) { [weak self] n in
            let type = (n.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt).flatMap(AVAudioSession.InterruptionType.init(rawValue:))
            self?.onInterruption?(type == .began) // resume is always an explicit user action
        })
        observers.append(nc.addObserver(forName: AVAudioSession.mediaServicesWereResetNotification, object: nil, queue: .main) { [weak self] _ in
            self?.onInterruption?(true)
        })
        refresh(deviceLost: false)
    }

    public func refresh(deviceLost: Bool) {
        let old = route
        let r = AVAudioSession.sharedInstance().currentRoute
        let inPort = r.inputs.first?.portType
        let outPort = r.outputs.first
        let input: String = {
            switch inPort {
            case .builtInMic?: return "phone_mic"
            case .headsetMic?: return "headset_mic"
            case .bluetoothHFP?: return "bluetooth_mic"
            case .usbAudio?: return "usb_mic"
            case nil: return "none"
            default: return "other"
            }
        }()
        let (output, isPrivate): (String, Bool) = {
            switch outPort?.portType {
            case .bluetoothA2DP?: return ("bluetooth_a2dp", true)
            case .bluetoothHFP?: return ("bluetooth_hfp", true)
            case .bluetoothLE?: return ("bluetooth_le", true)
            case .headphones?: return ("wired_headphones", true)
            case .builtInReceiver?: return ("receiver", false)
            case .builtInSpeaker?: return ("phone_speaker", false)
            case .airPlay?: return ("airplay", false) // a room speaker is never private
            case nil: return ("none", false)
            default: return ("other", false)
            }
        }()
        route = AudioRoute(input: input, output: output, outputDeviceName: isPrivate ? outPort?.portName : nil,
                           privateOutputPresent: isPrivate, couplesInputAndOutput: inPort == .bluetoothHFP)
        if deviceLost || !route.privateOutputPresent || route.outputDeviceName != verifiedDevice { userVerified = false } // fresh check required
        if old != route || deviceLost { onChange?(old, route, deviceLost) }
    }

    public static func requestRecordPermission() async -> Bool { await AVAudioApplication.requestRecordPermission() }
    public static var recordPermissionGranted: Bool { AVAudioApplication.shared.recordPermission == .granted }
    #else
    // macOS is not a product target; these keep the shared package compilable for `swift test`.
    public func configureForCapture() throws {}
    public func deactivate() {}
    public func start() {}
    public func refresh(deviceLost: Bool) {}
    public static func requestRecordPermission() async -> Bool { false }
    public static var recordPermissionGranted: Bool { false }
    #endif

    /// Test hook: inject an observed route (used by unit tests to exercise fail-closed behaviour).
    public func _simulate(_ r: AudioRoute, deviceLost: Bool) {
        let old = route
        route = r
        if deviceLost || !r.privateOutputPresent || r.outputDeviceName != verifiedDevice { userVerified = false }
        onChange?(old, r, deviceLost)
    }
}

/// Private earbud voice (ADR-014): checks the verified private route immediately before every utterance, stops on
/// route loss or barge-in, and never falls back to the loudspeaker. Reports its own playback windows so ASR never
/// attributes MeetSaathi's voice to a participant.
public final class PrivateVoice: NSObject, AVSpeechSynthesizerDelegate, @unchecked Sendable {
    private let synth = AVSpeechSynthesizer()
    private let routes: AudioRoutes
    private let clockMs: () -> Int64
    private var startedAt: Int64?
    public var onPlayback: ((Int64, Int64) -> Void)?

    public init(routes: AudioRoutes, clockMs: @escaping () -> Int64) {
        self.routes = routes; self.clockMs = clockMs
        super.init()
        synth.delegate = self
    }

    public var isSpeaking: Bool { synth.isSpeaking }

    @discardableResult
    public func speak(_ text: String, maxSeconds: Int = 7) -> Bool {
        guard routes.privateRouteVerified else { return false }
        let words = text.split(whereSeparator: \.isWhitespace).prefix(maxSeconds * 5 / 2).joined(separator: " ")
        synth.stopSpeaking(at: .immediate)
        synth.speak(AVSpeechUtterance(string: words))
        return true
    }

    @discardableResult
    public func playTestSample() -> Bool {
        guard routes.route.privateOutputPresent else { return false }
        synth.speak(AVSpeechUtterance(string: routes.route.outputDeviceName.map { L("voice_test_sample_named", $0) } ?? L("voice_test_sample")))
        return true
    }

    public func hardMute() { if synth.isSpeaking { synth.stopSpeaking(at: .immediate) } }

    public func speechSynthesizer(_ s: AVSpeechSynthesizer, didStart u: AVSpeechUtterance) { startedAt = clockMs() }
    public func speechSynthesizer(_ s: AVSpeechSynthesizer, didFinish u: AVSpeechUtterance) { finished() }
    public func speechSynthesizer(_ s: AVSpeechSynthesizer, didCancel u: AVSpeechUtterance) { finished() }
    private func finished() {
        if let s = startedAt { onPlayback?(s, clockMs()) }
        startedAt = nil
    }
}
