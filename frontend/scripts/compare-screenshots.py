#!/usr/bin/env python3
"""FE4a screenshot comparator (kickoff §3.8).

Two directories of PNG screenshots are compared pairwise by relative path.
Only 8-bit, non-interlaced RGB/RGBA Playwright PNGs are accepted (exit 2
otherwise).  Files are classified in this order:

  相同       identical bytes
  尺寸不同   width or height differs, or one side is missing from the pair
  内容变化   differing pixels > 100, or the largest 8-connected difference
             component > 16
  噪声       at most 100 differing pixels and no component above 16

The two limits are constants and cannot be changed by arguments or
environment.  Every non-identical file prints one deterministic line; a
summary with category counts follows.  Repeat runs produce identical bytes.

Usage:
  compare-screenshots.py DIR_A DIR_B            compare mode
  compare-screenshots.py --stable DIR_A DIR_B   stability gate
  compare-screenshots.py --self-test

Exit codes: 0 success (compare mode always, --stable only when every pair is
相同/噪声), 1 stability failure, 2 usage or PNG format error.
Only the standard library is used; run with ``python3 -I``.
"""

import argparse
import struct
import sys
import zlib
from pathlib import Path

DIFF_PIXEL_LIMIT = 100
COMPONENT_SIZE_LIMIT = 16
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CATEGORY_ORDER = ("内容变化", "尺寸不同", "缺失", "噪声", "相同")


class FormatError(Exception):
    """A PNG the comparator cannot compare, or an unusable input directory."""


def paeth(left, up, up_left):
    estimate = left + up - up_left
    distance_left = abs(estimate - left)
    distance_up = abs(estimate - up)
    distance_up_left = abs(estimate - up_left)
    if distance_left <= distance_up and distance_left <= distance_up_left:
        return left
    if distance_up <= distance_up_left:
        return up
    return up_left


def unfilter_row(filter_type, row, previous, bytes_per_pixel):
    if filter_type == 0:
        return bytes(row)
    output = bytearray(row)
    for index in range(len(output)):
        left = output[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
        up = previous[index] if previous is not None else 0
        up_left = previous[index - bytes_per_pixel] if previous is not None and index >= bytes_per_pixel else 0
        if filter_type == 1:
            output[index] = (output[index] + left) & 0xFF
        elif filter_type == 2:
            output[index] = (output[index] + up) & 0xFF
        elif filter_type == 3:
            output[index] = (output[index] + (left + up) // 2) & 0xFF
        elif filter_type == 4:
            output[index] = (output[index] + paeth(left, up, up_left)) & 0xFF
        else:
            raise FormatError(f"unknown PNG row filter {filter_type}")
    return bytes(output)


def decode_png(path):
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise FormatError(f"{path}: cannot read ({exc})") from exc
    if data[:8] != PNG_SIGNATURE:
        raise FormatError(f"{path}: not a PNG")
    position = 8
    width = height = bit_depth = color_type = interlace = None
    compressed = bytearray()
    saw_end = False
    while position + 8 <= len(data):
        length = struct.unpack(">I", data[position:position + 4])[0]
        chunk_type = data[position + 4:position + 8]
        payload = data[position + 8:position + 8 + length]
        if len(payload) != length:
            raise FormatError(f"{path}: truncated {chunk_type!r} chunk")
        if chunk_type == b"IHDR":
            if length != 13:
                raise FormatError(f"{path}: bad IHDR length")
            width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(">IIBBBBB", payload)
            if compression != 0 or filter_method != 0:
                raise FormatError(f"{path}: unsupported PNG compression/filter method")
        elif chunk_type == b"IDAT":
            compressed.extend(payload)
        elif chunk_type == b"IEND":
            saw_end = True
            break
        position += 12 + length
    if width is None or not saw_end:
        raise FormatError(f"{path}: missing IHDR or IEND")
    if bit_depth != 8:
        raise FormatError(f"{path}: unsupported bit depth {bit_depth} (need 8)")
    if color_type not in (2, 6):
        raise FormatError(f"{path}: unsupported color type {color_type} (need RGB or RGBA)")
    if interlace != 0:
        raise FormatError(f"{path}: interlaced PNG is not supported")
    channels = 3 if color_type == 2 else 4
    bytes_per_pixel = channels
    try:
        raw = zlib.decompress(bytes(compressed))
    except zlib.error as exc:
        raise FormatError(f"{path}: cannot inflate IDAT ({exc})") from exc
    stride = width * bytes_per_pixel
    if len(raw) != height * (stride + 1):
        raise FormatError(f"{path}: decoded size mismatch")
    rows = []
    previous = None
    offset = 0
    for _y in range(height):
        filter_type = raw[offset]
        row = raw[offset + 1:offset + 1 + stride]
        offset += stride + 1
        restored = unfilter_row(filter_type, row, previous, bytes_per_pixel)
        rows.append(restored)
        previous = restored
    return {"path": str(path), "width": width, "height": height, "channels": channels, "rows": rows}


def differing_pixels(first, second):
    """Return (count, largest_component, max_delta, bbox) for equal-size images."""
    width = first["width"]
    height = first["height"]
    channels = first["channels"]
    if second["channels"] != channels:
        raise FormatError("channel layout mismatch")
    mask = bytearray(width * height)
    count = 0
    max_delta = 0
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1
    for y in range(height):
        first_row = first["rows"][y]
        second_row = second["rows"][y]
        if first_row == second_row:
            continue
        row_base = y * width
        for x in range(width):
            base = x * channels
            pixel_delta = 0
            for channel in range(channels):
                delta = abs(first_row[base + channel] - second_row[base + channel])
                if delta > pixel_delta:
                    pixel_delta = delta
            if pixel_delta == 0:
                continue
            mask[row_base + x] = 1
            count += 1
            if pixel_delta > max_delta:
                max_delta = pixel_delta
            if x < min_x:
                min_x = x
            if x > max_x:
                max_x = x
            if y < min_y:
                min_y = y
            if y > max_y:
                max_y = y
    largest = 0
    if count:
        stack = []
        for index in range(len(mask)):
            if mask[index] != 1:
                continue
            mask[index] = 0
            stack.append(index)
            component = 0
            while stack:
                current = stack.pop()
                component += 1
                cx = current % width
                cy = current // width
                for dy in (-1, 0, 1):
                    ny = cy + dy
                    if ny < 0 or ny >= height:
                        continue
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        nx = cx + dx
                        if nx < 0 or nx >= width:
                            continue
                        neighbour = ny * width + nx
                        if mask[neighbour] == 1:
                            mask[neighbour] = 0
                            stack.append(neighbour)
            if component > largest:
                largest = component
    bbox = (min_x, min_y, max_x, max_y)
    return count, largest, max_delta, bbox


def classify(first, second):
    if first is None or second is None:
        return {"category": "缺失", "diff": 0, "largest": 0, "delta": 0, "bbox": (0, 0, 0, 0)}
    if first["width"] != second["width"] or first["height"] != second["height"]:
        return {"category": "尺寸不同", "diff": 0, "largest": 0, "delta": 0, "bbox": (0, 0, 0, 0)}
    if first["channels"] != second["channels"]:
        return {"category": "尺寸不同", "diff": 0, "largest": 0, "delta": 0, "bbox": (0, 0, 0, 0)}
    if all(a == b for a, b in zip(first["rows"], second["rows"])):
        return {"category": "相同", "diff": 0, "largest": 0, "delta": 0, "bbox": (0, 0, 0, 0)}
    count, largest, delta, bbox = differing_pixels(first, second)
    noisy = count <= DIFF_PIXEL_LIMIT and largest <= COMPONENT_SIZE_LIMIT
    return {
        "category": "噪声" if noisy else "内容变化",
        "diff": count,
        "largest": largest,
        "delta": delta,
        "bbox": bbox,
    }


def png_files(directory):
    root = Path(directory)
    if not root.is_dir():
        raise FormatError(f"not a directory: {root}")
    found = {}
    for path in sorted(root.rglob("*.png")):
        if path.is_file():
            found[path.relative_to(root).as_posix()] = path
    return found


def compare_directories(first_dir, second_dir):
    first_files = png_files(first_dir)
    second_files = png_files(second_dir)
    names = sorted(set(first_files) | set(second_files))
    results = []
    counts = {category: 0 for category in CATEGORY_ORDER}
    for name in names:
        first = decode_png(first_files[name]) if name in first_files else None
        second = decode_png(second_files[name]) if name in second_files else None
        outcome = classify(first, second)
        counts[outcome["category"]] += 1
        results.append((name, outcome))
    return results, counts


def print_results(results, counts):
    for name, outcome in results:
        if outcome["category"] == "相同":
            continue
        bbox = outcome["bbox"]
        print(
            f"{name}: {outcome['category']} 不同像素={outcome['diff']} "
            f"最大连通块={outcome['largest']} 最大通道差={outcome['delta']} "
            f"边界={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
        )
    print(
        "合计 "
        + " ".join(f"{category}={counts[category]}" for category in CATEGORY_ORDER)
    )


def make_png(width, height, pixels, color_type=6, bit_depth=8, interlace=0):
    """Encode RGBA/RGB pixels so the self-test exercises all five row filters."""
    channels = 4 if color_type == 6 else 3
    filters = (0, 1, 2, 3, 4)
    raw = bytearray()
    previous = bytes(width * channels)
    for y in range(height):
        row = bytes(pixels[y * width * channels:(y + 1) * width * channels])
        filter_type = filters[y % len(filters)]
        filtered = bytearray(row)
        for index in range(len(filtered)):
            left = row[index - channels] if index >= channels else 0
            up = previous[index]
            up_left = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                filtered[index] = (filtered[index] - left) & 0xFF
            elif filter_type == 2:
                filtered[index] = (filtered[index] - up) & 0xFF
            elif filter_type == 3:
                filtered[index] = (filtered[index] - (left + up) // 2) & 0xFF
            elif filter_type == 4:
                filtered[index] = (filtered[index] - paeth(left, up, up_left)) & 0xFF
        raw.append(filter_type)
        raw.extend(filtered)
        previous = row

    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, bit_depth, color_type, 0, 0, interlace)
    return PNG_SIGNATURE + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b"")


def solid(width, height, rgba=(0, 0, 0, 255)):
    return bytearray(bytes(rgba) * (width * height))


def paint(image, width, coordinates, rgba=(255, 255, 255, 255)):
    for x, y in coordinates:
        base = (y * width + x) * 4
        image[base:base + 4] = bytes(rgba)


def image_of(width, height, pixels):
    return {
        "path": "memory",
        "width": width,
        "height": height,
        "channels": 4,
        "rows": [bytes(pixels[y * width * 4:(y + 1) * width * 4]) for y in range(height)],
    }


def with_size(width, height):
    return solid(width, height)
def expect_category(image_a, image_b, expected, label):
    outcome = classify(image_a, image_b)
    if outcome["category"] != expected:
        raise AssertionError(f"{label}: expected {expected}, got {outcome['category']} {outcome}")


def self_test():
    import tempfile

    failures = []

    def check(condition, message):
        if not condition:
            failures.append(message)

    base_pixels = with_size(20, 20)
    base = image_of(20, 20, base_pixels)
    check(classify(base, image_of(20, 20, with_size(20, 20)))['category'] == '相同', 'identical image')
    one_pixels = bytearray(base_pixels)
    paint(one_pixels, 20, [(3, 4)])
    check(classify(base, image_of(20, 20, one_pixels))['category'] == '噪声', 'single pixel is noise')

    block_pixels = bytearray(base_pixels)
    paint(block_pixels, 20, [(x, y) for y in range(2, 6) for x in range(2, 6)])
    outcome = classify(base, image_of(20, 20, block_pixels))
    check(outcome['category'] == '噪声' and outcome['largest'] == 16, '16-pixel component is noise')

    bigger_pixels = bytearray(base_pixels)
    paint(bigger_pixels, 20, [(x, 8) for x in range(17)])
    outcome = classify(base, image_of(20, 20, bigger_pixels))
    check(outcome['category'] == '内容变化' and outcome['largest'] == 17, '17-pixel component is content')

    scattered_pixels = bytearray(solid(30, 30))
    points = []
    for y in range(0, 30, 2):
        for x in range(0, 30, 2):
            points.append((x, y))
    paint(scattered_pixels, 30, points[:101])
    outcome = classify(image_of(30, 30, solid(30, 30)), image_of(30, 30, scattered_pixels))
    check(outcome['category'] == '内容变化' and outcome['diff'] == 101, '101 scattered pixels are content')

    check(classify(base, image_of(20, 21, with_size(20, 21)))['category'] == '尺寸不同', 'size difference')
    check(classify(base, None)['category'] == '缺失', 'missing file')
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "a").mkdir()
        (root / "b").mkdir()
        (root / "a" / "same.png").write_bytes(make_png(5, 5, bytes(solid(5, 5))))
        (root / "b" / "same.png").write_bytes(make_png(5, 5, bytes(solid(5, 5))))
        filtered = bytearray(solid(6, 6))
        paint(filtered, 6, [(1, 1), (4, 4)], (10, 20, 30, 255))
        (root / 'a' / 'multi-filter.png').write_bytes(make_png(6, 6, bytes(filtered)))
        check(decode_png(root / 'a' / 'multi-filter.png')['rows'][1][4:8] == bytes((10, 20, 30, 255)), 'row filter 1')
        (root / 'a' / 'only-a.png').write_bytes(make_png(2, 2, bytes(solid(2, 2))))
        changed_a = bytearray(solid(3, 3))
        changed_b = bytearray(solid(3, 3))
        paint(changed_b, 3, [(1, 1)])
        (root / 'a' / 'changed.png').write_bytes(make_png(3, 3, bytes(changed_a)))
        (root / 'b' / 'changed.png').write_bytes(make_png(3, 3, bytes(changed_b)))
        results, counts = compare_directories(root / 'a', root / 'b')
        names = {name: outcome['category'] for name, outcome in results}
        check(names.get('only-a.png') == '缺失', 'directory comparison missing')
        check(names.get('same.png') == '相同', 'directory comparison same')
        check(names.get('changed.png') == '噪声', 'directory comparison noise')
        check(counts['缺失'] == 2 and counts['相同'] == 1 and counts['噪声'] == 1, 'directory counts')

        bad = bytearray(make_png(2, 2, bytes(solid(2, 2))))
        bad[24] = 16  # IHDR bit depth
        (root / "bad.png").write_bytes(bytes(bad))
        try:
            decode_png(root / "bad.png")
        except FormatError:
            pass
        else:
            failures.append("16-bit PNG must be rejected")

        interlaced = bytearray(make_png(2, 2, bytes(solid(2, 2))))
        interlaced[28] = 1  # IHDR interlace flag
        (root / "interlaced.png").write_bytes(bytes(interlaced))
        try:
            decode_png(root / "interlaced.png")
        except FormatError:
            pass
        else:
            failures.append("interlaced PNG must be rejected")

    if failures:
        for failure in failures:
            print(f"self-test failure: {failure}")
        return 1
    print("self-test: ok")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stable", action="store_true", help="exit 1 unless every pair is 相同/噪声")
    parser.add_argument("--self-test", action="store_true", help="run the built-in comparator self-test")
    parser.add_argument("first", nargs="?", help="first screenshot directory")
    parser.add_argument("second", nargs="?", help="second screenshot directory")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.first or not args.second:
        parser.error("two screenshot directories are required")
    try:
        results, counts = compare_directories(args.first, args.second)
    except FormatError as exc:
        print(f"error: {exc}")
        return 2
    print_results(results, counts)
    if args.stable:
        failed = counts["内容变化"] + counts["尺寸不同"] + counts["缺失"]
        return 1 if failed else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
