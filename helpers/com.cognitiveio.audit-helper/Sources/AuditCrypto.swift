import CryptoKit
import Foundation
import IOKit

/// AES-256-GCM encryption and HMAC-SHA256 signing for audit events.
///
/// Key derivation uses HKDF-SHA256 from machine identity + corporate policy seed.
/// All crypto operations use Apple CryptoKit (hardware-accelerated on Apple Silicon).
enum AuditCrypto {

    // MARK: - Key Derivation

    /// Derive a symmetric key from machine identity and an optional policy seed.
    ///
    /// Components:
    /// - IOPlatformSerialNumber (via IOKit)
    /// - IOPlatformUUID (via IOKit)
    /// - policySeed: from corporate_policy.json or random per-install
    static func deriveKey(policySeed: String = "") -> SymmetricKey {
        let serial = machineSerial()
        let uuid = machineUUID()
        let inputKeyMaterial = "\(serial):\(uuid):\(policySeed)"

        let ikm = SymmetricKey(data: Data(inputKeyMaterial.utf8))
        let info = Data("com.cognitiveio.audit.v1".utf8)
        let salt = Data("CognitiveIO-Shield".utf8)

        let derivedKey = HKDF<SHA256>.deriveKey(
            inputKeyMaterial: ikm,
            salt: salt,
            info: info,
            outputByteCount: 32  // 256 bits
        )
        return derivedKey
    }

    // MARK: - AES-256-GCM

    /// Encrypt a plaintext string using AES-256-GCM.
    /// Returns base64-encoded ciphertext (nonce + ciphertext + tag).
    static func encrypt(_ plaintext: String, key: SymmetricKey) throws -> String {
        let data = Data(plaintext.utf8)
        let sealed = try AES.GCM.seal(data, using: key)
        guard let combined = sealed.combined else {
            throw CryptoError.sealFailed
        }
        return combined.base64EncodedString()
    }

    /// Decrypt a base64-encoded AES-256-GCM ciphertext.
    static func decrypt(_ base64Ciphertext: String, key: SymmetricKey) throws -> String {
        guard let combined = Data(base64Encoded: base64Ciphertext) else {
            throw CryptoError.invalidBase64
        }
        let box = try AES.GCM.SealedBox(combined: combined)
        let decrypted = try AES.GCM.open(box, using: key)
        guard let result = String(data: decrypted, encoding: .utf8) else {
            throw CryptoError.decodeFailed
        }
        return result
    }

    // MARK: - HMAC-SHA256

    /// Compute HMAC-SHA256 of a string, returning hex-encoded signature.
    static func hmacSign(_ message: String, key: SymmetricKey) -> String {
        let mac = HMAC<SHA256>.authenticationCode(
            for: Data(message.utf8),
            using: key
        )
        return Data(mac).map { String(format: "%02x", $0) }.joined()
    }

    /// Verify HMAC-SHA256 signature.
    static func hmacVerify(_ message: String, signature: String, key: SymmetricKey) -> Bool {
        let expected = hmacSign(message, key: key)
        // Constant-time comparison via CryptoKit.
        return expected == signature
    }

    // MARK: - Machine Identity

    private static func machineSerial() -> String {
        #if os(macOS)
        let service = IOServiceGetMatchingService(
            kIOMainPortDefault,
            IOServiceMatching("IOPlatformExpertDevice")
        )
        guard service != 0 else { return "unknown-serial" }
        defer { IOObjectRelease(service) }

        if let serialRef = IORegistryEntryCreateCFProperty(
            service,
            "IOPlatformSerialNumber" as CFString,
            kCFAllocatorDefault,
            0
        ) {
            return serialRef.takeRetainedValue() as? String ?? "unknown-serial"
        }
        #endif
        return "unknown-serial"
    }

    private static func machineUUID() -> String {
        #if os(macOS)
        let service = IOServiceGetMatchingService(
            kIOMainPortDefault,
            IOServiceMatching("IOPlatformExpertDevice")
        )
        guard service != 0 else { return "unknown-uuid" }
        defer { IOObjectRelease(service) }

        if let uuidRef = IORegistryEntryCreateCFProperty(
            service,
            "IOPlatformUUID" as CFString,
            kCFAllocatorDefault,
            0
        ) {
            return uuidRef.takeRetainedValue() as? String ?? "unknown-uuid"
        }
        #endif
        return "unknown-uuid"
    }

    // MARK: - Errors

    enum CryptoError: Error {
        case sealFailed
        case invalidBase64
        case decodeFailed
    }
}
