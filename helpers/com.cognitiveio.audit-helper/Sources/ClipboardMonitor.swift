import AppKit
import Foundation

/// Monitors NSPasteboard for content-type metadata.
/// Extracts categorical information (type, size, dimensions) — NEVER the content itself.
final class ClipboardMonitor {

    /// Content-type metadata for an observed clipboard change.
    struct PasteMetadata {
        let contentType: String      // UTType string: public.png, public.utf8-plain-text, etc.
        let byteSize: Int            // Size in bytes
        let pixelDimensions: String  // "WIDTHxHEIGHT" for images, empty for text/binary
        let sourceHint: String       // "screenshot" or "copy"
        let isText: Bool             // Whether this is plain text content
    }

    private let pasteboard = NSPasteboard.general
    private var lastChangeCount: Int

    init() {
        self.lastChangeCount = pasteboard.changeCount
    }

    /// Check if the pasteboard has changed and return metadata if so.
    func checkForChange() -> PasteMetadata? {
        let currentCount = pasteboard.changeCount
        guard currentCount != lastChangeCount else { return nil }
        lastChangeCount = currentCount
        return extractMetadata()
    }

    /// Extract content-type metadata from the current pasteboard contents.
    /// NEVER reads or stores the actual content — only categorical metadata.
    func extractMetadata() -> PasteMetadata {
        let types = pasteboard.types ?? []

        // Determine primary content type.
        let imageTypes: Set<NSPasteboard.PasteboardType> = [
            .png, .tiff,
            NSPasteboard.PasteboardType("public.jpeg"),
            NSPasteboard.PasteboardType("public.heic"),
        ]

        let textTypes: Set<NSPasteboard.PasteboardType> = [
            .string,
            NSPasteboard.PasteboardType("public.utf8-plain-text"),
            NSPasteboard.PasteboardType("public.rtf"),
        ]

        let isImage = types.contains(where: { imageTypes.contains($0) })
        let isText = types.contains(where: { textTypes.contains($0) })

        // Get the primary content type string.
        let contentType: String
        if let firstType = types.first {
            contentType = firstType.rawValue
        } else {
            contentType = "unknown"
        }

        // Get byte size (from the primary type data).
        var byteSize = 0
        if let firstType = types.first, let data = pasteboard.data(forType: firstType) {
            byteSize = data.count
        }

        // Get pixel dimensions for images.
        var pixelDimensions = ""
        if isImage {
            pixelDimensions = extractImageDimensions()
        }

        // Source hint: screenshots typically come from the system screencapture process.
        let sourceHint: String
        if isImage && types.contains(NSPasteboard.PasteboardType("com.apple.screencapture")) {
            sourceHint = "screenshot"
        } else if isImage {
            sourceHint = "image_copy"
        } else {
            sourceHint = "copy"
        }

        return PasteMetadata(
            contentType: contentType,
            byteSize: byteSize,
            pixelDimensions: pixelDimensions,
            sourceHint: sourceHint,
            isText: isText
        )
    }

    /// Extract image dimensions without retaining the image data.
    private func extractImageDimensions() -> String {
        // Try PNG first, then TIFF.
        for pasteType in [NSPasteboard.PasteboardType.png, NSPasteboard.PasteboardType.tiff] {
            guard let data = pasteboard.data(forType: pasteType) else { continue }
            guard let imageRep = NSBitmapImageRep(data: data) else { continue }
            let width = imageRep.pixelsWide
            let height = imageRep.pixelsHigh
            // Release image data immediately — we only needed dimensions.
            return "\(width)x\(height)"
        }
        return ""
    }
}
