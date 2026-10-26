import Foundation

/// Realtime session stream over URLSessionWebSocketTask. Resumes from the last processed sequence after any
/// disconnect, drops duplicate replays, ACKs processed events. The access token is sent in-band, never in the URL.
public final class RealtimeClient: @unchecked Sendable {
    private let api: APIClient
    private let sessionId: String
    private var task: URLSessionWebSocketTask?
    private var loop: Task<Void, Never>?
    public private(set) var cursor: Int64
    public var onEvent: (@Sendable (EventEnvelope) -> Void)?
    public var onConnection: (@Sendable (Bool) -> Void)?

    public init(api: APIClient, sessionId: String, cursor: Int64) {
        self.api = api; self.sessionId = sessionId; self.cursor = cursor
    }

    public func start() {
        loop?.cancel()
        loop = Task { [weak self] in
            var backoff: UInt64 = 1_000_000_000
            while !Task.isCancelled, let self {
                await self.runOnce()
                self.onConnection?(false)
                try? await Task.sleep(nanoseconds: backoff)
                backoff = min(backoff * 2, 30_000_000_000)
            }
        }
    }

    private func runOnce() async {
        // Refresh expired access credentials before every reconnect, including long pocket sessions.
        guard (try? await api.raw("GET", "/v1/me")) != nil, !Task.isCancelled else { return }
        var comps = URLComponents(url: api.baseURL, resolvingAgainstBaseURL: false)!
        comps.scheme = comps.scheme == "https" ? "wss" : "ws"
        comps.path = "/v1/sessions/\(sessionId)/realtime"
        guard let url = comps.url else { return }
        let ws = api.session.webSocketTask(with: url)
        task = ws
        ws.resume()
        let auth: [String: Any] = ["type": "auth", "access_token": api.accessToken ?? "", "cursor": cursor]
        guard let authData = try? JSONSerialization.data(withJSONObject: auth), let s = String(data: authData, encoding: .utf8) else { return }
        do { try await ws.send(.string(s)) } catch { return }
        onConnection?(true)
        while !Task.isCancelled {
            guard let msg = try? await ws.receive() else { break }
            guard case .string(let text) = msg, let data = text.data(using: .utf8),
                  let ev = try? Wire.decoder.decode(EventEnvelope.self, from: data) else { continue }
            if ev.type == "ping" { continue }
            if ev.type == "error" { ws.cancel(with: .normalClosure, reason: nil); break }
            guard let seq = ev.sequence, seq > cursor else { continue } // duplicate after reconnect
            cursor = seq
            onEvent?(ev)
            send(["type": "ack", "sequence": seq])
        }
    }

    private func send(_ obj: [String: Any]) {
        guard let d = try? JSONSerialization.data(withJSONObject: obj), let s = String(data: d, encoding: .utf8) else { return }
        task?.send(.string(s)) { _ in }
    }

    public func signalUserSpeaking(_ speaking: Bool) { send(["type": "signal", "user_speaking": speaking]) }
    public func reportRouteLost() { send(["type": "voice.route_lost"]) }

    public func stop() {
        loop?.cancel()
        task?.cancel(with: .normalClosure, reason: nil)
    }
}
