import CryptoKit
import Foundation
import IOKit

/// Append-only JSONL audit writer with AES-256-GCM encryption and HMAC signing.
///
/// Writes to /Library/Application Support/CognitiveIO/audit/{machineIdHash}/
/// Files are daily JSONL, each line encrypted and signed.
final class AuditFileWriter {

    private let auditDir: URL
    private let key: CryptoKit.SymmetricKey
    private let machineIdHash: String

    init(policySeed: String = "") {
        self.key = AuditCrypto.deriveKey(policySeed: policySeed)

        // Machine ID hash for directory naming.
        let serial = Self.getMachineSerial()
        let hashData = serial.data(using: .utf8) ?? Data()
        let digest = CryptoKit.SHA256.hash(data: hashData)
        self.machineIdHash = digest.prefix(8).map { String(format: "%02x", $0) }.joined()

        // Create audit directory.
        let baseDir = URL(fileURLWithPath: "/Library/Application Support/CognitiveIO/audit")
        self.auditDir = baseDir.appendingPathComponent(machineIdHash)

        try? FileManager.default.createDirectory(
            at: auditDir,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o755]
        )
    }

    /// Append an encrypted, HMAC-signed audit event to today's JSONL file.
    func append(eventJSON: String) throws {
        // Validate: reject anything that looks like a secret value.
        guard !containsSecretPattern(eventJSON) else {
            throw AuditWriterError.secretDetected
        }

        // Encrypt the event JSON.
        let encrypted = try AuditCrypto.encrypt(eventJSON, key: key)

        // HMAC sign the encrypted payload.
        let signature = AuditCrypto.hmacSign(encrypted, key: key)

        // Format: {encrypted_base64}\t{hmac_hex}\n
        let line = "\(encrypted)\t\(signature)\n"

        // Append to today's file.
        let filepath = todayFilePath()
        if !FileManager.default.fileExists(atPath: filepath.path) {
            FileManager.default.createFile(atPath: filepath.path, contents: nil)
        }

        let handle = try FileHandle(forWritingTo: filepath)
        defer { handle.closeFile() }
        handle.seekToEndOfFile()
        handle.write(line.data(using: .utf8)!)

        // Update manifest.
        updateManifest(filepath: filepath)
    }

    /// Read and decrypt a JSONL audit file, verifying HMAC signatures.
    func readFile(filename: String) throws -> [String] {
        let filepath = auditDir.appendingPathComponent(filename)
        let content = try String(contentsOf: filepath, encoding: .utf8)
        var events: [String] = []

        for line in content.split(separator: "\n") where !line.isEmpty {
            let parts = line.split(separator: "\t", maxSplits: 1)
            guard parts.count == 2 else { continue }

            let encrypted = String(parts[0])
            let signature = String(parts[1])

            // Verify HMAC.
            guard AuditCrypto.hmacVerify(encrypted, signature: signature, key: key) else {
                throw AuditWriterError.tamperDetected(filename: filename)
            }

            // Decrypt.
            let decrypted = try AuditCrypto.decrypt(encrypted, key: key)
            events.append(decrypted)
        }
        return events
    }

    // MARK: - Private

    private func todayFilePath() -> URL {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.timeZone = TimeZone(identifier: "UTC")
        let filename = formatter.string(from: Date()) + ".jsonl"
        return auditDir.appendingPathComponent(filename)
    }

    private func updateManifest(filepath: URL) {
        let manifestPath = auditDir.appendingPathComponent("manifest.json")
        var manifest: [String: [String: Any]] = [:]

        if let data = try? Data(contentsOf: manifestPath),
           let existing = try? JSONSerialization.jsonObject(with: data) as? [String: [String: Any]] {
            manifest = existing
        }

        if let fileData = try? Data(contentsOf: filepath) {
            let digest = CryptoKit.SHA256.hash(data: fileData)
            let checksum = digest.map { String(format: "%02x", $0) }.joined()

            let formatter = ISO8601DateFormatter()
            manifest[filepath.lastPathComponent] = [
                "checksum": checksum,
                "size": fileData.count,
                "updated_at": formatter.string(from: Date()),
            ]
        }

        if let jsonData = try? JSONSerialization.data(
            withJSONObject: manifest,
            options: [.prettyPrinted, .sortedKeys]
        ) {
            try? jsonData.write(to: manifestPath)
        }
    }

    /// Check if a string contains patterns that look like secret values.
    private func containsSecretPattern(_ text: String) -> Bool {
        let patterns = [
            "sk-[A-Za-z0-9]{20,}",
            "AKIA[0-9A-Z]{16}",
            "-----BEGIN [A-Z ]+PRIVATE KEY-----",
        ]
        for pattern in patterns {
            if let regex = try? NSRegularExpression(pattern: pattern),
               regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)) != nil {
                return true
            }
        }
        return false
    }

    private static func getMachineSerial() -> String {
        #if os(macOS)
        let service = IOServiceGetMatchingService(
            kIOMainPortDefault,
            IOServiceMatching("IOPlatformExpertDevice")
        )
        guard service != 0 else { return "unknown" }
        defer { IOObjectRelease(service) }
        if let ref = IORegistryEntryCreateCFProperty(
            service, "IOPlatformSerialNumber" as CFString, kCFAllocatorDefault, 0
        ) {
            return ref.takeRetainedValue() as? String ?? "unknown"
        }
        #endif
        return "unknown"
    }

    enum AuditWriterError: Error {
        case secretDetected
        case tamperDetected(filename: String)
    }
}
