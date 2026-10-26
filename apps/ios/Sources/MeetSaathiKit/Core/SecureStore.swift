import CryptoKit
import Foundation
import Security

/// Keychain-backed secrets (tokens, device id, spool key). Items are device-only and unavailable until first unlock.
public final class Keychain: @unchecked Sendable {
    private let service: String
    public init(service: String = "app.meetsaathi") { self.service = service }

    public func set(_ name: String, _ value: Data?) {
        let base: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: name]
        SecItemDelete(base as CFDictionary)
        guard let value else { return }
        var add = base
        add[kSecValueData as String] = value
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        SecItemAdd(add as CFDictionary, nil)
    }

    public func get(_ name: String) -> Data? {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                kSecAttrAccount as String: name, kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var out: AnyObject?
        return SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess ? out as? Data : nil
    }

    public func string(_ name: String) -> String? { get(name).flatMap { String(data: $0, encoding: .utf8) } }
    public func setString(_ name: String, _ v: String?) { set(name, v?.data(using: .utf8)) }

    /// 256-bit symmetric key generated on first use and kept only in the Keychain (encrypted local spool, master 7.2).
    public func symmetricKey(_ name: String) -> SymmetricKey {
        if let d = get(name), d.count == 32 { return SymmetricKey(data: d) }
        let k = SymmetricKey(size: .bits256)
        set(name, k.withUnsafeBytes { Data($0) })
        return k
    }
}

/// AES-256-GCM sealing; AAD binds the blob to its session + sequence so files can't be swapped.
public struct Sealer: Sendable {
    let key: SymmetricKey
    public init(key: SymmetricKey) { self.key = key }

    public func seal(_ plain: Data, aad: Data) throws -> Data {
        guard let combined = try AES.GCM.seal(plain, using: key, authenticating: aad).combined else { throw CocoaError(.coderInvalidValue) }
        return combined
    }

    public func open(_ sealed: Data, aad: Data) throws -> Data {
        try AES.GCM.open(try AES.GCM.SealedBox(combined: sealed), using: key, authenticating: aad)
    }
}

public protocol TokenStore: AnyObject, Sendable {
    var accessToken: String? { get set }
    var refreshToken: String? { get set }
    var deviceId: String? { get set }
}

public final class KeychainTokenStore: TokenStore, @unchecked Sendable {
    private let kc: Keychain
    public init(_ kc: Keychain) { self.kc = kc }
    public var accessToken: String? { get { kc.string("access") } set { kc.setString("access", newValue) } }
    public var refreshToken: String? { get { kc.string("refresh") } set { kc.setString("refresh", newValue) } }
    public var deviceId: String? { get { kc.string("device") } set { kc.setString("device", newValue) } }
}
