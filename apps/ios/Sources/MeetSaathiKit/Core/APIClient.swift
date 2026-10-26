import Foundation

public enum APIError: Error, Sendable {
    case server(status: Int, body: APIErrorBody)
    case offline
    case decoding

    public var userMessage: String {
        switch self {
        case .server(_, let b): return b.userMessage.isEmpty ? L("error_generic") : b.userMessage
        case .offline: return L("error_offline")
        case .decoding: return L("error_generic")
        }
    }
    public var code: String? { if case .server(_, let b) = self { return b.code }; return nil }
}

/// REST client. Every mutation carries an Idempotency-Key so retries after a network flap never double-apply.
public final class APIClient: @unchecked Sendable {
    public let baseURL: URL
    public let session: URLSession
    let tokens: TokenStore
    private let refreshGate = RefreshGate()
    public var onSignedOut: (@Sendable () -> Void)?

    public init(baseURL: URL, tokens: TokenStore, session: URLSession = .shared) {
        self.baseURL = baseURL; self.tokens = tokens; self.session = session
    }

    public var isSignedIn: Bool { tokens.accessToken != nil }
    public var accessToken: String? { tokens.accessToken }
    public var deviceId: String? { tokens.deviceId }

    public func send<T: Decodable>(_ method: String, _ path: String, body: Encodable? = nil, idempotencyKey: String? = nil,
                                   auth: Bool = true, as: T.Type = T.self) async throws -> T {
        let data = try await raw(method, path, body: body, idempotencyKey: idempotencyKey, auth: auth)
        do { return try Wire.decoder.decode(T.self, from: data) } catch { throw APIError.decoding }
    }

    @discardableResult
    public func raw(_ method: String, _ path: String, body: Encodable? = nil, idempotencyKey: String? = nil, auth: Bool = true) async throws -> Data {
        let payload = try body.map { try Wire.encoder.encode(AnyEncodable($0)) }
        var (data, status) = try await perform(method, path, payload, idempotencyKey, auth)
        if status == 401 && auth, await refreshGate.run({ try await self.refresh() }) {
            (data, status) = try await perform(method, path, payload, idempotencyKey, auth) // same key: safe replay
        }
        guard (200..<300).contains(status) else {
            let err = (try? Wire.decoder.decode(APIErrorBody.self, from: data)) ?? APIErrorBody(code: "HTTP_\(status)", userMessage: "")
            if status == 401 && auth { tokens.accessToken = nil; tokens.refreshToken = nil; onSignedOut?() }
            throw APIError.server(status: status, body: err)
        }
        return data
    }

    /// Authenticated binary GET (evidence audio, export download) with the same refresh / sign-out semantics.
    public func bytes(_ path: String) async throws -> Data { try await raw("GET", path) }

    private func perform(_ method: String, _ path: String, _ body: Data?, _ key: String?, _ auth: Bool) async throws -> (Data, Int) {
        var req = URLRequest(url: URL(string: path, relativeTo: baseURL)!)
        req.httpMethod = method
        req.timeoutInterval = 60
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if auth, let t = tokens.accessToken { req.setValue("Bearer \(t)", forHTTPHeaderField: "Authorization") }
        if let key { req.setValue(key, forHTTPHeaderField: "Idempotency-Key") }
        req.httpBody = body ?? ((method == "POST" || method == "PATCH" || method == "PUT") ? Data("{}".utf8) : nil)
        do {
            let (data, resp) = try await session.data(for: req)
            return (data, (resp as? HTTPURLResponse)?.statusCode ?? 0)
        } catch {
            throw APIError.offline
        }
    }

    private func refresh() async throws -> Bool {
        guard let rt = tokens.refreshToken else { return false }
        let (data, status) = try await perform("POST", "/v1/auth/refresh", try Wire.encoder.encode(["refresh_token": rt]), nil, false)
        guard status == 200, let t = try? Wire.decoder.decode(Tokens.self, from: data) else { return false }
        tokens.accessToken = t.accessToken
        tokens.refreshToken = t.refreshToken
        return true
    }

    // ---- identity --------------------------------------------------------------------------------------------
    struct DeviceIn: Encodable { var platform = "IOS"; var name: String; var deviceId: String? }
    struct RegisterIn: Encodable { var email: String; var password: String; var displayName: String?; var device: DeviceIn; var ageConfirmed: Bool }
    struct LoginIn: Encodable { var email: String; var password: String; var device: DeviceIn }

    public func register(email: String, password: String, name: String?, deviceName: String, ageConfirmed: Bool) async throws {
        let t: Tokens = try await send("POST", "/v1/auth/register", body: RegisterIn(email: email, password: password, displayName: name,
                                                                                         device: DeviceIn(name: deviceName), ageConfirmed: ageConfirmed), auth: false)
        store(t)
    }

    public func login(email: String, password: String, deviceName: String) async throws {
        let t: Tokens = try await send("POST", "/v1/auth/login", body: LoginIn(email: email, password: password,
                                                                                  device: DeviceIn(name: deviceName, deviceId: tokens.deviceId)), auth: false)
        store(t)
    }

    public func reauth(password: String) async throws {
        let t: Tokens = try await send("POST", "/v1/auth/reauth", body: ["password": password])
        tokens.accessToken = t.accessToken
    }

    public func logout() async {
        _ = try? await raw("POST", "/v1/auth/logout")
        tokens.accessToken = nil; tokens.refreshToken = nil
    }

    private func store(_ t: Tokens) {
        tokens.accessToken = t.accessToken
        tokens.refreshToken = t.refreshToken
        if let d = t.deviceId { tokens.deviceId = d }
    }

    public static func newKey() -> String { "ios-" + UUID().uuidString.lowercased() }
}

/// Serializes concurrent refreshes (only one refresh request in flight).
actor RefreshGate {
    private var task: Task<Bool, Error>?
    func run(_ op: @escaping @Sendable () async throws -> Bool) async -> Bool {
        if let task { return (try? await task.value) ?? false }
        let t = Task { try await op() }
        task = t
        let r = (try? await t.value) ?? false
        task = nil
        return r
    }
}

struct AnyEncodable: Encodable {
    let value: Encodable
    init(_ v: Encodable) { value = v }
    func encode(to encoder: Encoder) throws { try value.encode(to: encoder) }
}
