// vision_probe.swift — macOS Vision detector for check_vertical_layout.py.
//
// Usage: vision_probe <image>...
// Prints one JSON object per image, one per line:
//   {"image": path, "w": W, "h": H,
//    "text":  [{"text": s, "conf": c, "box": [x0, y0, x1, y1]}],
//    "faces": [{"box": [x0, y0, x1, y1], "eye_y": y}]}
// Coordinates are pixels with the origin at the top-left (Vision's own origin is
// bottom-left; this flips it). eye_y is the mean y of the pupil landmarks, falling
// back to the eye contours; it is absent when Vision returns no eye landmarks.
//
// check_vertical_layout.py compiles this once into its cache dir with `swiftc -O`.
import AppKit
import Foundation
import Vision

func r1(_ v: Double) -> Double { (v * 10).rounded() / 10 }

func topLeftBox(_ r: CGRect, _ w: Double, _ h: Double) -> [Double] {
    let x0: Double = Double(r.minX) * w
    let y0: Double = (1.0 - Double(r.maxY)) * h
    let x1: Double = Double(r.maxX) * w
    let y1: Double = (1.0 - Double(r.minY)) * h
    return [r1(x0), r1(y0), r1(x1), r1(y1)]
}

func emit(_ obj: [String: Any]) {
    let data = try! JSONSerialization.data(withJSONObject: obj, options: [.sortedKeys])
    print(String(data: data, encoding: .utf8)!)
}

for path in CommandLine.arguments.dropFirst() {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        emit(["image": path, "error": "unreadable image"])
        continue
    }
    let w = Double(cg.width)
    let h = Double(cg.height)
    let textReq = VNRecognizeTextRequest()
    textReq.recognitionLevel = .accurate
    textReq.usesLanguageCorrection = false
    let faceReq = VNDetectFaceLandmarksRequest()
    do {
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([textReq, faceReq])
    } catch {
        emit(["image": path, "error": "vision request failed: \(error)"])
        continue
    }

    var texts: [[String: Any]] = []
    for obs in textReq.results ?? [] {
        guard let best = obs.topCandidates(1).first else { continue }
        texts.append(["text": best.string, "conf": Double(best.confidence),
                      "box": topLeftBox(obs.boundingBox, w, h)])
    }

    var faces: [[String: Any]] = []
    let size = CGSize(width: w, height: h)
    for face in faceReq.results ?? [] {
        var entry: [String: Any] = ["box": topLeftBox(face.boundingBox, w, h)]
        if let lm = face.landmarks,
           let left = lm.leftPupil ?? lm.leftEye,
           let right = lm.rightPupil ?? lm.rightEye {
            let pts = left.pointsInImage(imageSize: size) + right.pointsInImage(imageSize: size)
            if !pts.isEmpty {
                var sum: Double = 0
                for p in pts { sum += h - Double(p.y) }
                entry["eye_y"] = r1(sum / Double(pts.count))
            }
        }
        faces.append(entry)
    }

    emit(["image": path, "w": w, "h": h, "text": texts, "faces": faces])
}
