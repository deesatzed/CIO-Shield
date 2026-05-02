import Foundation

/// Protocol for the XPC audit helper service.
/// CIO-II Python process sends categorical audit events via stdin JSON lines.
/// The helper validates, encrypts (AES-256-GCM), signs (HMAC-SHA256), and
/// appends to root-owned JSONL files.
@objc protocol AuditHelperProtocol {
    func appendAuditEvent(_ eventJSON: String, reply: @escaping (Bool, String?) -> Void)
    func getManifest(reply: @escaping (String?) -> Void)
    func verifyIntegrity(_ filename: String, reply: @escaping (Bool) -> Void)
}

/// Audit event structure (decoded from incoming JSON).
struct AuditEventPayload: Codable {
    let event: String
    let ts: String?
    let reason: String?
    let app: String?
    let profile: String?

    // Clipboard-specific
    let content_type: String?
    let pixel_dimensions: String?
    let byte_size: Int?
    let source_hint: String?
    let destination_app: String?

    // Redaction-specific
    let pattern_type: String?
    let token_count: Int?

    // Session summary
    let accept_rate: Double?
    let blocks: Int?
    let redactions: Int?
    let duration_seconds: Int?
}
