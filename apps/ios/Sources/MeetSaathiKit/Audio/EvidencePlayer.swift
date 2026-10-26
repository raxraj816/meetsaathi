import AVFoundation
import Foundation

/// Evidence player (U07/S14): plays exactly the permitted audio for one cited utterance, fetched from the server span
/// endpoint - never a neighbouring segment. The clip is held in memory only for playback; nothing is written to disk.
@MainActor
public final class EvidencePlayer: NSObject, ObservableObject, AVAudioPlayerDelegate {
    public enum State: Equatable {
        case idle
        case loading(String)
        case playing(String)
        /// `code` is the API error code (AUDIO_DELETED, CLIP_UNAVAILABLE, OFFLINE, …); `message` is server copy if any.
        case failed(String, code: String, message: String)

        var utteranceId: String? {
            switch self { case .idle: nil; case .loading(let u), .playing(let u): u; case .failed(let u, _, _): u }
        }
    }

    @Published public private(set) var state: State = .idle
    private let api: APIClient
    private var player: AVAudioPlayer?
    private var task: Task<Void, Never>?

    public init(api: APIClient) { self.api = api }

    public func toggle(sessionId: String, utteranceId: String) {
        switch state {
        case .loading(let u) where u == utteranceId, .playing(let u) where u == utteranceId: stop()
        default: play(sessionId: sessionId, utteranceId: utteranceId)
        }
    }

    public func play(sessionId: String, utteranceId: String) {
        stop()
        state = .loading(utteranceId)
        task = Task {
            do {
                let data = try await api.bytes("/v1/sessions/\(sessionId)/utterances/\(utteranceId)/audio")
                guard !Task.isCancelled else { return }
                #if os(iOS)
                try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .spokenAudio)
                try? AVAudioSession.sharedInstance().setActive(true)
                #endif
                let p = try AVAudioPlayer(data: data)
                p.delegate = self
                guard p.play() else { state = .failed(utteranceId, code: "PLAYBACK_FAILED", message: ""); return }
                player = p
                state = .playing(utteranceId)
            } catch let e as APIError {
                if case .offline = e { state = .failed(utteranceId, code: "OFFLINE", message: "") }
                else { state = .failed(utteranceId, code: e.code ?? "PLAYBACK_FAILED", message: e.userMessage) }
            } catch {
                state = .failed(utteranceId, code: "PLAYBACK_FAILED", message: "")
            }
        }
    }

    public func stop() {
        task?.cancel(); task = nil
        player?.stop(); player = nil
        state = .idle
    }

    nonisolated public func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in self.stop() }
    }
}
