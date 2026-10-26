import AVFoundation
import Foundation

/// AVAudioEngine capture converted to 16 kHz mono PCM16 in 1 s chunks. `onFirstBuffer` fires only when real
/// frames arrive — the only signal allowed to turn the UI to "Recording" (master 7.1 invariant).
public final class AudioCapture: @unchecked Sendable {
    public let sampleRate: Double = 16_000
    private let engine = AVAudioEngine()
    private var converter: AVAudioConverter?
    private var pending: [Int16] = []
    private var first = true
    private var chunkStartMs: Int64 = 0
    private let queue = DispatchQueue(label: "ms.capture")
    public var clockOrigin: Date = Date()

    public var onFirstBuffer: (@Sendable () -> Void)?
    public var onChunk: (@Sendable (_ startMs: Int64, _ durationMs: Int, _ pcm: Data, _ levelDbfs: Double) -> Void)?
    public var onLevel: (@Sendable (Double) -> Void)?
    public var onFailure: (@Sendable (String) -> Void)?

    public init() {}

    func nowMs() -> Int64 { Int64(Date().timeIntervalSince(clockOrigin) * 1000) }

    public func start() -> Bool {
        let input = engine.inputNode
        let inFormat = input.outputFormat(forBus: 0)
        guard inFormat.sampleRate > 0, inFormat.channelCount > 0,
              let outFormat = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: sampleRate, channels: 1, interleaved: true),
              let conv = AVAudioConverter(from: inFormat, to: outFormat) else {
            onFailure?("INPUT_LOST"); return false
        }
        converter = conv
        first = true
        pending.removeAll()
        chunkStartMs = nowMs()
        input.installTap(onBus: 0, bufferSize: AVAudioFrameCount(inFormat.sampleRate / 10), format: inFormat) { [weak self] buf, _ in
            // AVAudioEngine owns/reuses the tap buffer after this callback returns. Copy before
            // dispatching, otherwise a busy capture queue can transcribe overwritten audio.
            guard let owned = AVAudioPCMBuffer(pcmFormat: buf.format, frameCapacity: buf.frameLength) else { return }
            owned.frameLength = buf.frameLength
            let sources = UnsafeMutableAudioBufferListPointer(buf.mutableAudioBufferList)
            let destinations = UnsafeMutableAudioBufferListPointer(owned.mutableAudioBufferList)
            for (source, destination) in zip(sources, destinations) {
                if let src = source.mData, let dst = destination.mData {
                    memcpy(dst, src, Int(source.mDataByteSize))
                }
            }
            self?.queue.async { self?.process(owned, outFormat) }
        }
        do {
            engine.prepare()
            try engine.start()
        } catch {
            input.removeTap(onBus: 0)
            onFailure?("INPUT_LOST") // e.g. microphone in use by another app
            return false
        }
        return true
    }

    private func process(_ buf: AVAudioPCMBuffer, _ outFormat: AVAudioFormat) {
        guard let conv = converter else { return }
        let ratio = outFormat.sampleRate / buf.format.sampleRate
        let cap = AVAudioFrameCount(Double(buf.frameLength) * ratio) + 32
        guard let out = AVAudioPCMBuffer(pcmFormat: outFormat, frameCapacity: cap) else { return }
        var fed = false
        var err: NSError?
        conv.convert(to: out, error: &err) { _, status in
            if fed { status.pointee = .noDataNow; return nil }
            fed = true; status.pointee = .haveData; return buf
        }
        guard err == nil, let ch = out.int16ChannelData, out.frameLength > 0 else { return }
        let samples = Array(UnsafeBufferPointer(start: ch[0], count: Int(out.frameLength)))
        if first { first = false; onFirstBuffer?() }
        onLevel?(Signal.rmsDbfs(samples))
        pending.append(contentsOf: samples)
        let per = Int(sampleRate)
        while pending.count >= per {
            let chunk = Array(pending.prefix(per))
            pending.removeFirst(per)
            onChunk?(chunkStartMs, 1000, Signal.littleEndianBytes(chunk), Signal.rmsDbfs(chunk))
            chunkStartMs += 1000
        }
    }

    /// Stops the microphone immediately; never waits on the network (ADR-010). Flushes the last partial chunk.
    public func stop() {
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        queue.sync {
            if pending.count > Int(sampleRate) / 10 {
                let ms = pending.count * 1000 / Int(sampleRate)
                onChunk?(chunkStartMs, ms, Signal.littleEndianBytes(pending), Signal.rmsDbfs(pending))
            }
            pending.removeAll()
        }
    }
}
