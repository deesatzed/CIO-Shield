import CryptoKit
import Foundation

/// CIO-II Shield Privileged Audit Helper
///
/// This is a privileged helper daemon installed via SMJobBless.
/// It receives categorical audit events from the CIO-II Python process via
/// stdin (JSON line protocol), encrypts them with AES-256-GCM, signs with
/// HMAC-SHA256, and appends to root-owned JSONL files.
///
/// Communication: One JSON object per line on stdin.
/// Response: "ok\n" or "error:{message}\n" on stdout.
///
/// The helper NEVER receives secret values, clipboard contents, or raw text.
/// It validates incoming events and rejects anything that matches secret patterns.

// Read policy seed from corporate policy file if available.
func loadPolicySeed() -> String {
    let policyPaths = [
        "/Library/Application Support/CognitiveIO/corporate_policy.json",
    ]
    for path in policyPaths {
        guard let data = FileManager.default.contents(atPath: path),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let orgId = json["organization_id"] as? String else {
            continue
        }
        return orgId
    }
    return ""
}

// MARK: - Main

let policySeed = loadPolicySeed()
let writer = AuditFileWriter(policySeed: policySeed)

// Process stdin line by line (JSON line protocol).
while let line = readLine(strippingNewline: true) {
    guard !line.isEmpty else { continue }

    // Validate JSON structure.
    guard let data = line.data(using: .utf8),
          let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          json["event"] != nil else {
        print("error:invalid_json")
        fflush(stdout)
        continue
    }

    do {
        try writer.append(eventJSON: line)
        print("ok")
    } catch AuditFileWriter.AuditWriterError.secretDetected {
        print("error:secret_detected")
    } catch {
        print("error:\(error.localizedDescription)")
    }
    fflush(stdout)
}
