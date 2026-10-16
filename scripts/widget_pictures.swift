// Draws the three sizes of the widget, with its invented sample numbers, for the user guide.
//   python scripts/build_app.py does not need this; run it on purpose:
//   swiftc -parse-as-library -D PICTURES widget/JobHelperWidget.swift scripts/widget_pictures.swift -o /tmp/pictures && /tmp/pictures docs/img
import AppKit
import SwiftUI

@main
struct Pictures {
    @MainActor static func main() {
        let out = URL(fileURLWithPath: CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : ".")
        let now = Date.now
        let s = Sample.snapshot
        let sizes: [(String, AnyView, CGSize)] = [
            ("widget_small", AnyView(SmallView(s: s, now: now)), CGSize(width: 170, height: 170)),
            ("widget_medium", AnyView(MediumView(s: s, now: now)), CGSize(width: 364, height: 170)),
            ("widget_large", AnyView(LargeView(s: s, now: now)), CGSize(width: 364, height: 382)),
        ]
        for (name, view, size) in sizes {
            let card = view
                .padding(16)
                .frame(width: size.width, height: size.height, alignment: .topLeading)
                .background(Color(red: 0.13, green: 0.15, blue: 0.19))
                .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
                .padding(14)
                .environment(\.colorScheme, .dark)
            let renderer = ImageRenderer(content: card)
            renderer.scale = 2
            guard let image = renderer.nsImage, let tiff = image.tiffRepresentation,
                  let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) else {
                print("could not draw \(name)"); exit(1)
            }
            try! png.write(to: out.appendingPathComponent("\(name).png"))
            print("drew \(name).png")
        }
    }
}
